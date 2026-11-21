import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.api.deps import actor_name, actor_role, get_optional_user, require_roles
from app.core.config import settings
from app.core.security import DEPT, OPS
from app.models.entities import User
from fastapi import Header
from app.db.session import get_db
from datetime import datetime, timedelta, timezone

from app.db.beacon_registry import KARNATAKA_BOUNDS, inside_karnataka
from app.models.entities import AuditLog, Beacon, Incident
from app.schemas.domain import (
    AuditOut,
    BeaconOut,
    IncidentCreate,
    IncidentOut,
    IncidentStateChange,
    IncidentStatusUpdate,
    LoRaPacket,
)
from app.services import incident_lifecycle as lifecycle
from app.services.audit import record_audit
from app.services.trilateration import rssi_to_distance_m, trilaterate

router = APIRouter()

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@router.post("/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_incident_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_IMAGE_EXTS))}",
        )
    
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    # Read and check size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds maximum 10MB limit")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Sanitize base filename and create unique name
    clean_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(file.filename).stem)[:30]
    safe_filename = f"inc_{uuid.uuid4().hex[:10]}_{clean_base}{ext}"
    
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = settings.UPLOAD_DIR / safe_filename
    
    with open(destination, "wb") as f:
        f.write(contents)

    return {
        "status": "success",
        "image_url": f"/api/incidents/uploads/{safe_filename}",
        "filename": safe_filename,
        "size_bytes": len(contents),
        "content_type": file.content_type or "image/jpeg",
    }

@router.get("/uploads/{filename}")
def get_incident_image(filename: str):
    # Guard against directory traversal
    clean_name = os.path.basename(filename)
    file_path = settings.UPLOAD_DIR / clean_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Incident attachment image not found")
    return FileResponse(file_path)

FIELD_STATES = ("IN_TRANSIT", "ON_SCENE", "RESOLVED")


def raise_if_dispatch_blocked(inc: Incident, target: str) -> None:
    """Dispatch of a gated incident is only possible through POST /agents/tasks/{id}/approve."""
    if target != "DISPATCHED":
        return
    if lifecycle.normalize(inc.status) == "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Incident is waiting for commander approval; approve its supervisor task to dispatch it.")
    if lifecycle.requires_commander_approval(inc.people_affected, inc.severity):
        raise HTTPException(
            status_code=409,
            detail="This incident meets the approval rule (five or more victims, or HIGH or CRITICAL severity). Run supervisor triage and get commander approval before dispatch.",
        )


@router.get("/lifecycle")
def get_lifecycle():
    """States and allowed transitions of the incident lifecycle."""
    return {
        "states": lifecycle.STATES,
        "transitions": lifecycle.TRANSITIONS,
        "terminal_states": sorted(lifecycle.TERMINAL_STATES),
        "legacy_aliases": lifecycle.LEGACY_ALIASES,
    }


@router.get("/beacons", response_model=dict)
def list_beacons(db: Session = Depends(get_db), _: User = Depends(require_roles(*DEPT))):
    beacons = db.query(Beacon).order_by(Beacon.beacon_id).all()
    return {
        "items": [BeaconOut.model_validate(b) for b in beacons],
        "count": len(beacons),
        "operating_bounds": KARNATAKA_BOUNDS,
    }


@router.post("/lora", status_code=status.HTTP_201_CREATED)
def ingest_lora_packet(packet: LoRaPacket, db: Session = Depends(get_db), x_gateway_key: Optional[str] = Header(None)):
    """Turn a LoRa distress packet into an incident (or refresh the open one for that beacon).

    Gateways are devices, not people, so they do not sign in. When LORA_GATEWAY_KEY is set,
    packets must carry it in the X-Gateway-Key header.
    """
    expected = settings.LORA_GATEWAY_KEY
    if expected and x_gateway_key != expected:
        raise HTTPException(status_code=401, detail="Missing or wrong gateway key")
    rms = None
    if packet.latitude is not None and packet.longitude is not None:
        lat, lon, method = packet.latitude, packet.longitude, "GPS"
    elif len(packet.gateway_readings) >= 3:
        try:
            lat, lon, rms = trilaterate(
                [(g.latitude, g.longitude, rssi_to_distance_m(g.rssi_dbm)) for g in packet.gateway_readings]
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        method = "TRILATERATION"
    else:
        raise HTTPException(status_code=422, detail="Packet has no GPS fix and fewer than three gateway readings")

    if not inside_karnataka(lat, lon):
        raise HTTPException(
            status_code=422,
            detail=f"Position {lat:.4f}, {lon:.4f} is outside the Karnataka operating area {KARNATAKA_BOUNDS}",
        )

    label = "SIMULATED" if packet.is_simulated else "OBSERVED"
    now = datetime.now(timezone.utc)
    beacon = db.query(Beacon).filter(Beacon.beacon_id == packet.beacon_id).first()
    if beacon is None:
        beacon = Beacon(beacon_id=packet.beacon_id, hotspot=packet.area or "Unregistered beacon", latitude=lat, longitude=lon, data_label=label)
        db.add(beacon)
    beacon.last_battery_pct = packet.battery_pct
    beacon.last_hops = packet.hop_count
    beacon.last_seen = now

    # One open incident per beacon: repeated packets refresh it instead of creating duplicates.
    open_inc = (
        db.query(Incident)
        .filter(Incident.beacon_id == packet.beacon_id, Incident.status.notin_(list(lifecycle.TERMINAL_STATES)))
        .order_by(Incident.created_at.desc())
        .first()
    )
    severity = packet.emergency_level.upper()
    description = (
        f"LoRa mesh distress packet. Trapped persons: {packet.casualty_estimate}. "
        f"Device battery: {packet.battery_pct}%. Mesh hop distance: {packet.hop_count}. Location: {method}"
        + (f" (fit error {rms:.0f} m)" if rms is not None else "")
        + "."
    )
    if open_inc is not None:
        open_inc.device_battery_pct = packet.battery_pct
        open_inc.mesh_hops = packet.hop_count
        open_inc.people_affected = max(open_inc.people_affected, packet.casualty_estimate)
        open_inc.description = description
        record_audit(db, "lora-gateway", "LORA_PACKET_REFRESH", "incident", open_inc.id, f"battery {packet.battery_pct}%", role="DEVICE")
        db.commit()
        db.refresh(open_inc)
        return {"created": False, "incident": IncidentOut.model_validate(open_inc), "location_method": method, "trilateration_rms_m": rms}

    inc = Incident(
        id=f"INC-LORA-{uuid.uuid4().hex[:6].upper()}",
        title=f"LoRa Mesh SOS from beacon {packet.beacon_id}",
        description=description,
        area=packet.area or beacon.hotspot,
        latitude=lat,
        longitude=lon,
        severity=severity,
        people_affected=packet.casualty_estimate,
        status="REPORTED",
        source="MESH_SOS",
        device_battery_pct=packet.battery_pct,
        mesh_hops=packet.hop_count,
        beacon_id=packet.beacon_id,
        location_method=method,
        data_label=label,
    )
    db.add(inc)
    record_audit(db, "lora-gateway", "LORA_PACKET_INGESTED", "incident", inc.id, f"beacon {packet.beacon_id} via {method}", role="DEVICE")
    db.commit()
    db.refresh(inc)
    return {"created": True, "incident": IncidentOut.model_validate(inc), "location_method": method, "trilateration_rms_m": rms}


@router.post("/{incident_id}/state", response_model=IncidentOut)
def change_incident_state(
    incident_id: str,
    payload: IncidentStateChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DEPT)),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    target = lifecycle.normalize(payload.to_status)
    if getattr(user, "role", None) == "RESCUE_OFFICER":
        # Field officers only report progress on missions given to their own team.
        if not inc.assigned_team_id or inc.assigned_team_id != user.team_id:
            raise HTTPException(status_code=403, detail="This incident is not assigned to your team")
        if target not in FIELD_STATES:
            raise HTTPException(status_code=403, detail=f"Rescue officers can set only {', '.join(FIELD_STATES)}")
    if target == "DUPLICATE":
        if not payload.duplicate_of:
            raise HTTPException(status_code=422, detail="duplicate_of is required when marking an incident as DUPLICATE")
        if not db.query(Incident).filter(Incident.id == payload.duplicate_of).first():
            raise HTTPException(status_code=404, detail=f"Incident {payload.duplicate_of} not found")
        inc.duplicate_of = payload.duplicate_of
    raise_if_dispatch_blocked(inc, target)
    lifecycle.transition(db, inc, target, actor=actor_name(user, payload.actor), role=actor_role(user, "OPERATOR"), note=payload.note)
    db.commit()
    db.refresh(inc)
    return IncidentOut.model_validate(inc)


@router.get("/{incident_id}/history", response_model=dict)
def get_incident_history(incident_id: str, db: Session = Depends(get_db), _: User = Depends(require_roles(*DEPT))):
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == "incident", AuditLog.target_id == incident_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    return {"items": [AuditOut.model_validate(e) for e in entries], "count": len(entries)}


@router.get("/", response_model=dict)
def list_incidents(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*DEPT)),
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    query = db.query(Incident)

    if isinstance(status_filter, str) and status_filter.strip():
        query = query.filter(Incident.status.ilike(f"%{status_filter}%"))
    if isinstance(severity, str) and severity.strip():
        query = query.filter(Incident.severity.ilike(f"%{severity}%"))
    if isinstance(search, str) and search.strip():
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Incident.id.ilike(search_term),
                Incident.title.ilike(search_term),
                Incident.area.ilike(search_term),
                Incident.description.ilike(search_term),
            )
        )

    total_count = query.count()
    items = query.order_by(Incident.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "items": [IncidentOut.model_validate(inc) for inc in items],
        "count": total_count,
        "limit": limit,
        "offset": offset,
        "data_mode": "persistent_sqlite",
    }

@router.get("/mine", response_model=dict)
def my_incidents(db: Session = Depends(get_db), user: User = Depends(require_roles(
        "ADMIN", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"))):
    """Reports filed by the signed-in user, or, for a rescue officer, their team's missions."""
    q = db.query(Incident)
    if user.role == "RESCUE_OFFICER":
        q = q.filter(Incident.assigned_team_id == user.team_id)
    else:
        q = q.filter(Incident.reporter_user_id == user.id)
    items = q.order_by(Incident.created_at.desc()).limit(200).all()
    return {"items": [IncidentOut.model_validate(i) for i in items], "count": len(items)}


@router.post("/", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    """Anyone can report an emergency, signed in or not. Signed-in reports are linked to the account."""
    signed_in = isinstance(user, User)
    # Generate unique ID
    count = db.query(Incident).count()
    new_id = f"INC-{1045 + count}"

    incident = Incident(
        id=new_id,
        title=payload.title,
        description=payload.description,
        area=payload.area,
        latitude=payload.latitude,
        longitude=payload.longitude,
        severity=payload.severity.upper(),
        people_affected=payload.people_affected,
        status="REPORTED",
        source=payload.source,
        incident_type=payload.incident_type or "FLOODING",
        image_url=payload.image_url,
        reporter_name=payload.reporter_name or (user.full_name if signed_in else None),
        reporter_contact=payload.reporter_contact or (user.phone if signed_in else None),
        reporter_user_id=user.id if signed_in else None,
        reported_water_depth=payload.reported_water_depth.upper() if payload.reported_water_depth else None,
    )

    db.add(incident)
    record_audit(db, user.username if signed_in else (payload.reporter_name or "anonymous"), "INCIDENT_REPORTED",
                 "incident", new_id, payload.title, role=user.role if signed_in else "PUBLIC")
    db.commit()
    db.refresh(incident)
    return IncidentOut.model_validate(incident)

@router.post("/{incident_id}/analyze-photo", response_model=IncidentOut)
def analyze_incident_photo(incident_id: str, db: Session = Depends(get_db), _: User = Depends(require_roles(*DEPT))):
    """Run the flood-photo models on the incident's uploaded photo and store the summary."""
    from app.services.vision_service import VisionModelUnavailable, flood_vision_service

    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    prefix = "/api/incidents/uploads/"
    if not inc.image_url or not inc.image_url.startswith(prefix):
        raise HTTPException(status_code=422, detail="Incident has no uploaded photo to analyse")
    path = settings.UPLOAD_DIR / os.path.basename(inc.image_url[len(prefix):])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded photo file is missing")
    try:
        result = flood_vision_service.analyze(path.read_bytes(), include_overlay=False)
    except VisionModelUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    keep = ["data_label", "model", "flood_detected", "flood_probability", "closest_description",
            "water_coverage_pct", "people_detected", "people_in_water", "vehicles_detected",
            "vehicles_in_water", "boats_detected", "suggested_severity", "inference_ms"]
    summary = {k: result[k] for k in keep}
    inc.photo_analysis = json.dumps(summary)
    record_audit(db, "vision-model", "PHOTO_ANALYSED", "incident", inc.id,
                 f"flood p={summary['flood_probability']}, suggested {summary['suggested_severity']}", role="AGENT")
    db.commit()
    db.refresh(inc)
    return IncidentOut.model_validate(inc)


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(
        "ADMIN", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if getattr(user, "role", "ADMIN") in ("CITIZEN", "VOLUNTEER") and inc.reporter_user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return IncidentOut.model_validate(inc)

@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: str, payload: IncidentStatusUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*OPS))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    if payload.status is not None:
        target = lifecycle.normalize(payload.status)
        raise_if_dispatch_blocked(inc, target)
        lifecycle.transition(db, inc, target, actor=actor_name(user, "operator"), role=actor_role(user, "OPERATOR"))
    if payload.assigned_team_id is not None:
        inc.assigned_team_id = payload.assigned_team_id
    if payload.severity is not None:
        inc.severity = payload.severity.upper()
    if payload.people_affected is not None:
        inc.people_affected = payload.people_affected

    db.commit()
    db.refresh(inc)
    return IncidentOut.model_validate(inc)

@router.delete("/{incident_id}", status_code=status.HTTP_200_OK)
def delete_incident(incident_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    record_audit(db, actor_name(user), "INCIDENT_DELETED", "incident", inc.id, inc.title, role="ADMIN")
    db.delete(inc)
    db.commit()
    return {"message": f"Incident {incident_id} removed successfully"}
