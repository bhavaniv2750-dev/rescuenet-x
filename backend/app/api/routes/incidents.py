import hmac
import json
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.api.deps import actor_name, actor_role, ensure_permission, get_optional_user, require_permission
from app.core.config import settings
from app.core.permissions import P, has_permission, role_has
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
    IncidentCreatedOut,
    IncidentOut,
    IncidentStateChange,
    IncidentStatusUpdate,
    LoRaPacket,
)
from app.services import incident_lifecycle as lifecycle
from app.services import media, public_refs, rate_limit
from app.services.rate_limit import client_fingerprint
from app.services.audit import record_audit
from app.services.trilateration import rssi_to_distance_m, trilaterate

router = APIRouter()

@router.post("/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_incident_image(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                                user: Optional[User] = Depends(get_optional_user)):
    """Upload one evidence photo. Open to guests (emergency reporting needs no account), but limited:
    5 MB, JPEG/PNG/WebP only (decoded and re-encoded, metadata removed), and per-connection rate and quota limits.
    The returned image_url is a private reference: it is only useful to attach the photo to a report that is created
    next, and it cannot be opened without authorisation."""
    signed_in = isinstance(user, User)
    fingerprint = client_fingerprint(request)
    rate_limit.check("upload-user" if signed_in else "upload-guest", str(user.id) if signed_in else fingerprint,
                     settings.USER_REPORTS_PER_HOUR * settings.MAX_IMAGES_PER_REPORT if signed_in else settings.GUEST_UPLOADS_PER_HOUR, 3600,
                     fail_open=True)
    try:
        raw = media.read_limited(file.file, settings.MAX_IMAGE_BYTES)
        asset = media.store_upload(db, raw, user=user if signed_in else None, client_hash=fingerprint)
    except media.MediaRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "image_url": f"{media.MEDIA_URL_PREFIX}{asset.id}",
        "asset_id": asset.id,
        "size_bytes": asset.size_bytes,
        "content_type": asset.content_type,
        "valid_for_minutes": settings.UNATTACHED_UPLOAD_TTL_MINUTES,
    }


def _can_access_incident(inc: Incident, user: Optional[User]) -> bool:
    """Incident details: everything for incident.view_all; only the own team's missions for incident.view_assigned;
    only the user's own reports for incident.view_own."""
    if user is None:
        return False
    if has_permission(user, P.INCIDENT_VIEW_ALL):
        return True
    if has_permission(user, P.INCIDENT_VIEW_ASSIGNED) and user.team_id and inc.assigned_team_id == user.team_id:
        return True
    return has_permission(user, P.INCIDENT_VIEW_OWN) and inc.reporter_user_id == user.id


@router.get("/uploads/{filename}")
def get_legacy_incident_image(filename: str, db: Session = Depends(get_db),
                              user: Optional[User] = Depends(get_optional_user)):
    """Old photo route. No longer public: it now needs a sign-in and the same permission as /api/media/{id}."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    clean_name = os.path.basename(filename)
    inc = media.asset_for_legacy_filename(db, clean_name)
    file_path = settings.UPLOAD_DIR / clean_name
    if inc is None or not media.can_view_incident_evidence(inc, user) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path, headers=media.PRIVATE_HEADERS)


FIELD_STATES = ("IN_TRANSIT", "ON_SCENE", "RESOLVED")


def raise_if_dispatch_blocked(inc: Incident, target: str) -> None:
    """Setting DISPATCHED by editing a status is never allowed.

    An incident is dispatched only together with a team: POST /teams/{id}/assign for ordinary incidents, or a
    commander's approval (POST /agents/tasks/{id}/approve) for those that need one.
    """
    if target != "DISPATCHED":
        return
    if lifecycle.normalize(inc.status) == "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Incident is waiting for commander approval; approve its supervisor task to dispatch it.")
    if lifecycle.incident_requires_approval(inc):
        raise HTTPException(
            status_code=409,
            detail="This incident meets the approval rule (five or more victims, or HIGH or CRITICAL severity). Run supervisor triage and get commander approval before dispatch.",
        )
    raise HTTPException(
        status_code=409,
        detail="An incident is dispatched together with a rescue team, not by changing its status. Use POST /api/teams/{team_id}/assign.",
    )


def _apply_risk_edit(db: Session, inc: Incident, payload: IncidentStatusUpdate, user) -> None:
    """Edits to severity or people_affected, with the safety rules for lowering them.

    * Raising the risk is allowed for operations staff and is audited.
    * Lowering the risk of an incident that needs commander approval is allowed only for a commander
      (permission incident.reduce_risk), with a written reason; it is audited. Refused attempts are audited too.
    * The original assessment (reported_severity / reported_people_affected) is never changed.
    """
    if payload.severity is None and payload.people_affected is None:
        return
    old_sev, old_people = (inc.severity or "").upper(), inc.people_affected
    new_sev = payload.severity.upper() if payload.severity else old_sev
    new_people = payload.people_affected if payload.people_affected is not None else old_people
    if (new_sev, new_people) == (old_sev, old_people):
        return
    actor, role = actor_name(user, "operator"), actor_role(user, "OPERATOR")
    note = (payload.note or "").strip()
    detail = f"severity {old_sev}->{new_sev}; people {old_people}->{new_people}"
    lowers = lifecycle.severity_rank(new_sev) < lifecycle.severity_rank(old_sev) or new_people < old_people

    if lowers and lifecycle.incident_requires_approval(inc):
        if not role_has(role, P.INCIDENT_REDUCE_RISK):
            record_audit(db, actor, "INCIDENT_RISK_DOWNGRADE_DENIED", "incident", inc.id,
                         f"{detail} | refused: only a commander may lower the risk of an incident that needs approval", role=role)
            db.commit()
            raise HTTPException(
                status_code=403,
                detail="Only a commander or administrator can lower the severity or headcount of an incident that needs commander approval.",
            )
        if len(note) < 5:
            raise HTTPException(status_code=422, detail="A written reason (note, at least 5 characters) is required to lower the risk of an incident that needs commander approval.")
        inc.risk_downgraded_by = actor
        inc.risk_downgrade_note = note
        record_audit(db, actor, "INCIDENT_RISK_DOWNGRADE_AUTHORIZED", "incident", inc.id, f"{detail} | {note}", role=role)
    else:
        record_audit(db, actor, "INCIDENT_RISK_EDITED", "incident", inc.id, detail + (f" | {note}" if note else ""), role=role)
    inc.severity = new_sev
    inc.people_affected = new_people


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
def list_beacons(db: Session = Depends(get_db), _: User = Depends(require_permission(P.BEACON_VIEW))):
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
    if settings.is_production and not expected:
        # Secure by default: an unauthenticated device endpoint is a development convenience only.
        raise HTTPException(status_code=503, detail="LoRa intake is disabled until LORA_GATEWAY_KEY is configured.")
    if expected and not hmac.compare_digest(x_gateway_key or "", expected):
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
    user: User = Depends(require_permission(P.INCIDENT_VERIFY, P.INCIDENT_PROGRESS)),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    target = lifecycle.normalize(payload.to_status)
    if not has_permission(user, P.INCIDENT_VERIFY):
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
def get_incident_history(incident_id: str, db: Session = Depends(get_db),
                         user: User = Depends(require_permission(P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if (inc is None and not has_permission(user, P.INCIDENT_VIEW_ALL)) or (inc is not None and not _can_access_incident(inc, user)):
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
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
    user: User = Depends(require_permission(P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED)),
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    query = db.query(Incident)
    if not has_permission(user, P.INCIDENT_VIEW_ALL):  # field officers: their own team's missions only
        query = query.filter(Incident.assigned_team_id == (user.team_id or "__no_team__"))

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
def my_incidents(db: Session = Depends(get_db), user: User = Depends(require_permission(
        P.INCIDENT_VIEW_OWN, P.INCIDENT_VIEW_ASSIGNED))):
    """Reports filed by the signed-in user, or, for a rescue officer, their team's missions."""
    q = db.query(Incident)
    if has_permission(user, P.INCIDENT_VIEW_ASSIGNED):
        q = q.filter(Incident.assigned_team_id == (user.team_id or "__no_team__"))
    else:
        q = q.filter(Incident.reporter_user_id == user.id)
    items = q.order_by(Incident.created_at.desc()).limit(200).all()
    return {"items": [IncidentOut.model_validate(i) for i in items], "count": len(items)}


_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_incident_id(db: Session) -> str:
    """Random, non-sequential internal id (the old counter-based ids leaked report volume and could repeat after a delete)."""
    while True:
        candidate = "INC-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))
        if not db.query(Incident.id).filter(Incident.id == candidate).first():
            return candidate


def create_report(db: Session, payload: IncidentCreate, request: Request, user: Optional[User]) -> tuple:
    """Shared by POST /incidents/ and POST /public/reports. Reporting never requires an account.

    Guests are limited per connection (default 10 reports per hour); signed-in users per account. A photo problem
    never blocks the report: the report is saved and the problem is returned as a warning.
    """
    signed_in = isinstance(user, User)
    if signed_in:
        rate_limit.check("report-user", str(user.id), settings.USER_REPORTS_PER_HOUR, 3600, fail_open=True)
    else:
        rate_limit.check("report-guest", client_fingerprint(request), settings.GUEST_REPORTS_PER_HOUR, 3600, fail_open=True)

    new_id = _new_incident_id(db)
    tracking_code = public_refs.new_tracking_code()
    public_ref = public_refs.new_public_ref()
    while db.query(Incident.id).filter(Incident.public_ref == public_ref).first():
        public_ref = public_refs.new_public_ref()

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
        image_url=None,
        reporter_name=payload.reporter_name or (user.full_name if signed_in else None),
        reporter_contact=payload.reporter_contact or (user.phone if signed_in else None),
        reporter_user_id=user.id if signed_in else None,
        reported_water_depth=payload.reported_water_depth.upper() if payload.reported_water_depth else None,
        public_ref=public_ref,
        tracking_code_hash=public_refs.hash_code(tracking_code),
    )
    db.add(incident)
    db.flush()

    urls = ([payload.image_url] if payload.image_url else []) + list(payload.image_urls or [])
    attached, warnings_out = [], []
    for url in dict.fromkeys(urls):
        if len(attached) >= settings.MAX_IMAGES_PER_REPORT:
            warnings_out.append(f"Only {settings.MAX_IMAGES_PER_REPORT} photos can be attached to one report.")
            break
        try:
            attached += media.attach_to_incident(db, [url], incident, user if signed_in else None)
        except media.MediaRejected as exc:
            warnings_out.append(str(exc))
    if attached:
        incident.image_url = f"{media.MEDIA_URL_PREFIX}{attached[0].id}"

    record_audit(db, user.username if signed_in else "public", "INCIDENT_REPORTED",
                 "incident", new_id, payload.title, role=user.role if signed_in else "PUBLIC")
    db.commit()
    db.refresh(incident)
    return incident, tracking_code, len(attached), warnings_out


@router.post("/", response_model=IncidentCreatedOut, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate, request: Request = None, db: Session = Depends(get_db),
                    user: Optional[User] = Depends(get_optional_user)):
    """Anyone can report an emergency, signed in or not. Signed-in reports are linked to the account.
    The response includes a one-time tracking_code for following the report without an account."""
    incident, code, n, warns = create_report(db, payload, request, user)
    out = IncidentCreatedOut.model_validate(incident)
    out.tracking_code, out.photos_attached, out.photo_warnings = code, n, warns
    return out

@router.post("/{incident_id}/analyze-photo", response_model=IncidentOut)
def analyze_incident_photo(incident_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission(P.EVIDENCE_ANALYZE))):
    """Run the flood-photo models on the incident's uploaded photo and store the summary."""
    from app.services.vision_service import VisionModelUnavailable, flood_vision_service

    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not media.can_view_incident_evidence(inc, user):  # an officer may analyse only their own team's evidence
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    aid = media.asset_id_from_url(inc.image_url)
    legacy = media.LEGACY_URL_PREFIX
    if aid:
        asset = db.query(media.MediaAsset).filter(media.MediaAsset.id == aid).first()
        path = media.asset_path(asset) if asset else None
    elif inc.image_url and inc.image_url.startswith(legacy):
        path = settings.UPLOAD_DIR / os.path.basename(inc.image_url[len(legacy):])
    else:
        raise HTTPException(status_code=422, detail="Incident has no uploaded photo to analyse")
    if path is None or not path.is_file():
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
def get_incident(incident_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission(
        P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED, P.INCIDENT_VIEW_OWN))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not _can_access_incident(inc, user):
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return IncidentOut.model_validate(inc)

@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: str, payload: IncidentStatusUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_permission(P.INCIDENT_VERIFY, P.INCIDENT_EDIT_RISK))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if payload.status is not None:
        ensure_permission(user, P.INCIDENT_VERIFY)
    if payload.severity is not None or payload.people_affected is not None:
        ensure_permission(user, P.INCIDENT_EDIT_RISK)

    if payload.assigned_team_id is not None:
        raise HTTPException(
            status_code=409,
            detail="A team cannot be attached by editing the incident. Use POST /api/teams/{team_id}/assign "
                   "(or a commander's approval of a supervisor task), which also marks the team as deployed.",
        )
    _apply_risk_edit(db, inc, payload, user)  # before any state change, so a refused edit changes nothing
    if payload.status is not None:
        target = lifecycle.normalize(payload.status)
        raise_if_dispatch_blocked(inc, target)
        lifecycle.transition(db, inc, target, actor=actor_name(user, "operator"), role=actor_role(user, "OPERATOR"))

    db.commit()
    db.refresh(inc)
    return IncidentOut.model_validate(inc)

@router.delete("/{incident_id}", status_code=status.HTTP_200_OK)
def delete_incident(incident_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission(P.INCIDENT_DELETE))):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    record_audit(db, actor_name(user), "INCIDENT_DELETED", "incident", inc.id, inc.title, role="ADMIN")
    db.delete(inc)
    db.commit()
    return {"message": f"Incident {incident_id} removed successfully"}
