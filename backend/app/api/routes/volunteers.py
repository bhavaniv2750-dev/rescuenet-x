from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import actor_name, actor_role, require_roles
from app.core.security import APPROVERS, DEPT, OPS
from app.db.session import get_db
from app.models.entities import Incident, User, Volunteer
from app.services import incident_lifecycle as lifecycle
from app.services.audit import record_audit
from app.services.ids import next_volunteer_id
from app.schemas.domain import VolunteerCreate, VolunteerOut

router = APIRouter()

class VolunteerStatusUpdate(BaseModel):
    status: Optional[str] = None
    is_verified: Optional[bool] = None

@router.get("/", response_model=dict, dependencies=[Depends(require_roles(*OPS))])
def list_volunteers(
    verified_only: Optional[bool] = Query(None, alias="verified"),
    skill: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Volunteer)
    if verified_only is not None:
        query = query.filter(Volunteer.is_verified == verified_only)
    if skill:
        query = query.filter(Volunteer.skills.ilike(f"%{skill}%"))

    items = query.order_by(Volunteer.registered_at.desc()).all()
    return {
        "items": [VolunteerOut.model_validate(v) for v in items],
        "count": len(items),
        "verified_count": sum(1 for v in items if v.is_verified),
    }

@router.post("/", response_model=VolunteerOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(*OPS))])
def register_volunteer(payload: VolunteerCreate, db: Session = Depends(get_db)):
    new_id = next_volunteer_id(db)

    vol = Volunteer(
        id=new_id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        skills=payload.skills,
        area=payload.area,
        is_verified=False,
        status="AVAILABLE",
    )
    db.add(vol)
    db.commit()
    db.refresh(vol)
    return VolunteerOut.model_validate(vol)

class VolunteerAssign(BaseModel):
    incident_id: str


ACTIVE_RESCUE_STATES = ("DISPATCHED", "IN_TRANSIT", "ON_SCENE")


@router.patch("/{volunteer_id}", response_model=VolunteerOut)
def update_volunteer(volunteer_id: str, payload: VolunteerStatusUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*OPS))):
    vol = db.query(Volunteer).filter(Volunteer.id == volunteer_id).first()
    if not vol:
        raise HTTPException(status_code=404, detail=f"Volunteer {volunteer_id} not found")

    if payload.status is not None:
        new_status = payload.status.upper()
        if new_status not in ("AVAILABLE", "STANDBY"):
            raise HTTPException(status_code=422, detail="Status can be AVAILABLE or STANDBY. Use the assign endpoint to send a volunteer to an incident.")
        if vol.assigned_incident_id:
            raise HTTPException(status_code=409, detail=f"{vol.id} is assigned to {vol.assigned_incident_id}. Release them first.")
        vol.status = new_status
    if payload.is_verified is not None and payload.is_verified != vol.is_verified:
        if not payload.is_verified and vol.assigned_incident_id:
            raise HTTPException(status_code=409, detail=f"{vol.id} is assigned to {vol.assigned_incident_id}. Release them first.")
        vol.is_verified = payload.is_verified
        vol.verified_by = actor_name(user) if payload.is_verified else None
        record_audit(db, actor_name(user), "VOLUNTEER_VERIFIED" if payload.is_verified else "VOLUNTEER_UNVERIFIED",
                     "volunteer", vol.id, vol.name, role=actor_role(user))

    db.commit()
    db.refresh(vol)
    return VolunteerOut.model_validate(vol)


@router.post("/{volunteer_id}/assign", response_model=VolunteerOut)
def assign_volunteer(volunteer_id: str, payload: VolunteerAssign, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*OPS))):
    """Send a volunteer to an active rescue. Only verified, available volunteers can be assigned."""
    vol = db.query(Volunteer).filter(Volunteer.id == volunteer_id).first()
    if not vol:
        raise HTTPException(status_code=404, detail=f"Volunteer {volunteer_id} not found")
    if not vol.is_verified:
        raise HTTPException(status_code=409, detail=f"{vol.name} is not verified yet. Verify the volunteer before assigning them.")
    if vol.assigned_incident_id:
        raise HTTPException(status_code=409, detail=f"{vol.name} is already assigned to {vol.assigned_incident_id}.")
    if vol.status != "AVAILABLE":
        raise HTTPException(status_code=409, detail=f"{vol.name} is {vol.status}, not AVAILABLE.")
    inc = db.query(Incident).filter(Incident.id == payload.incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {payload.incident_id} not found")
    if lifecycle.normalize(inc.status) not in ACTIVE_RESCUE_STATES:
        raise HTTPException(status_code=409, detail=f"{inc.id} is {inc.status}. Volunteers join incidents that are dispatched or under way.")
    vol.status = "ASSIGNED"
    vol.assigned_incident_id = inc.id
    record_audit(db, actor_name(user), "VOLUNTEER_ASSIGNED", "incident", inc.id, f"{vol.id} {vol.name}", role=actor_role(user))
    db.commit()
    db.refresh(vol)
    return VolunteerOut.model_validate(vol)


@router.post("/{volunteer_id}/release", response_model=VolunteerOut)
def release_volunteer(volunteer_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    vol = db.query(Volunteer).filter(Volunteer.id == volunteer_id).first()
    if not vol:
        raise HTTPException(status_code=404, detail=f"Volunteer {volunteer_id} not found")
    if not vol.assigned_incident_id:
        raise HTTPException(status_code=409, detail=f"{vol.name} is not assigned to an incident.")
    record_audit(db, actor_name(user), "VOLUNTEER_RELEASED", "incident", vol.assigned_incident_id, f"{vol.id} {vol.name}", role=actor_role(user))
    vol.assigned_incident_id = None
    vol.status = "AVAILABLE"
    db.commit()
    db.refresh(vol)
    return VolunteerOut.model_validate(vol)
