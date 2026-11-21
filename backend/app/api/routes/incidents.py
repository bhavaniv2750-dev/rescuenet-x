import os
import re
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Incident
from app.schemas.domain import IncidentCreate, IncidentOut, IncidentStatusUpdate

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

@router.get("/", response_model=dict)
def list_incidents(
    db: Session = Depends(get_db),
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

@router.post("/", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)):
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
        reporter_name=payload.reporter_name,
        reporter_contact=payload.reporter_contact,
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)
    return IncidentOut.model_validate(incident)

@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return IncidentOut.model_validate(inc)

@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: str, payload: IncidentStatusUpdate, db: Session = Depends(get_db)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    if payload.status is not None:
        inc.status = payload.status.upper()
    if payload.assigned_team_id is not None:
        inc.assigned_team_id = payload.assigned_team_id
        if inc.status in ["REPORTED", "VERIFIED"]:
            inc.status = "ASSIGNED"
    if payload.severity is not None:
        inc.severity = payload.severity.upper()
    if payload.people_affected is not None:
        inc.people_affected = payload.people_affected

    db.commit()
    db.refresh(inc)
    return IncidentOut.model_validate(inc)

@router.delete("/{incident_id}", status_code=status.HTTP_200_OK)
def delete_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    db.delete(inc)
    db.commit()
    return {"message": f"Incident {incident_id} removed successfully"}
