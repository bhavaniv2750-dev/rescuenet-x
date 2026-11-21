from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import actor_name, require_roles
from app.core.security import APPROVERS, DEPT, OPS
from app.db.session import get_db
from app.models.entities import User, Volunteer
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
    count = db.query(Volunteer).count()
    new_id = f"VOL-{106 + count}"

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

@router.patch("/{volunteer_id}", response_model=VolunteerOut)
def update_volunteer(volunteer_id: str, payload: VolunteerStatusUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*OPS))):
    vol = db.query(Volunteer).filter(Volunteer.id == volunteer_id).first()
    if not vol:
        raise HTTPException(status_code=404, detail=f"Volunteer {volunteer_id} not found")

    if payload.status is not None:
        vol.status = payload.status.upper()
    if payload.is_verified is not None:
        vol.is_verified = payload.is_verified

    db.commit()
    db.refresh(vol)
    return VolunteerOut.model_validate(vol)
