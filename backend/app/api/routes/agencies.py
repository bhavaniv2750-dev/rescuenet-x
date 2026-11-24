"""Agencies (S5): organisational metadata for personnel and squads.

An agency says WHICH ORGANISATION a person or squad belongs to. It is not a security boundary: permissions come from roles only
(app/core/permissions.py), incidents/teams/alerts are NOT filtered by agency, and any commander or operator can coordinate with
squads of any agency during an emergency. The tests assert this explicitly (tests/test_s5_agencies.py).
Types are generic categories; no real organisation or affiliation is implied by them.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import actor_name, ensure_recent_mfa, require_permission
from app.core.permissions import P
from app.db.session import get_db
from app.models.entities import Agency, RescueTeam, User
from app.services import sessions as sess
from app.services.audit import record_audit

router = APIRouter()

AGENCY_TYPES = ["DISASTER_RESPONSE", "FIRE_EMERGENCY", "MEDICAL_RESPONSE", "CIVIL_ADMINISTRATION", "VOLUNTEER_ORGANIZATION"]
AgencyType = Literal["DISASTER_RESPONSE", "FIRE_EMERGENCY", "MEDICAL_RESPONSE", "CIVIL_ADMINISTRATION", "VOLUNTEER_ORGANIZATION"]


class AgencyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    agency_type: AgencyType
    region: Optional[str] = Field(default=None, max_length=120)


class AgencyPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    agency_type: Optional[AgencyType] = None
    region: Optional[str] = Field(default=None, max_length=120)
    is_active: Optional[bool] = None


class AssignIn(BaseModel):
    agency_id: Optional[int] = None      # null removes the membership


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _out(db: Session, a: Agency, detail: bool = False) -> dict:
    out = {"id": a.id, "name": a.name, "agency_type": a.agency_type, "region": a.region, "is_active": bool(a.is_active),
           "created_at": a.created_at, "updated_at": a.updated_at,
           "personnel_count": db.query(func.count(User.id)).filter(User.agency_id == a.id).scalar() or 0,
           "team_count": db.query(func.count(RescueTeam.id)).filter(RescueTeam.agency_id == a.id).scalar() or 0}
    if detail:
        out["teams"] = [{"id": t.id, "name": t.name} for t in db.query(RescueTeam.id, RescueTeam.name).filter(RescueTeam.agency_id == a.id).order_by(RescueTeam.name)]
        out["personnel"] = [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role}
                            for u in db.query(User).filter(User.agency_id == a.id).order_by(User.username)]
    return out


@router.get("", response_model=dict)
@router.get("/", response_model=dict, include_in_schema=False)
def list_agencies(user: User = Depends(require_permission(P.AGENCY_VIEW)), db: Session = Depends(get_db)):
    rows = db.query(Agency).order_by(Agency.name).all()
    return {"items": [_out(db, a) for a in rows], "count": len(rows), "types": AGENCY_TYPES}


@router.get("/{agency_id}", response_model=dict)
def get_agency(agency_id: int, user: User = Depends(require_permission(P.AGENCY_VIEW)), db: Session = Depends(get_db)):
    a = db.get(Agency, agency_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Agency not found")
    return _out(db, a, detail=True)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_agency(payload: AgencyIn, admin: User = Depends(require_permission(P.AGENCY_MANAGE)), db: Session = Depends(get_db)):
    ensure_recent_mfa(admin)
    name = payload.name.strip()
    if db.query(Agency).filter(func.lower(Agency.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="An agency with that name already exists")
    a = Agency(name=name, agency_type=payload.agency_type, region=(payload.region or "").strip() or None,
               created_by=actor_name(admin), created_at=_now(), updated_at=_now())
    db.add(a)
    db.flush()
    record_audit(db, actor_name(admin), "AGENCY_CREATED", "agency", a.id, f"{name} ({payload.agency_type})", role=admin.role)
    db.commit()
    return _out(db, a)


@router.patch("/{agency_id}", response_model=dict)
def update_agency(agency_id: int, payload: AgencyPatch, admin: User = Depends(require_permission(P.AGENCY_MANAGE)),
                  db: Session = Depends(get_db)):
    ensure_recent_mfa(admin)
    a = db.get(Agency, agency_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Agency not found")
    changes = []
    if payload.name is not None and payload.name.strip() != a.name:
        if db.query(Agency).filter(func.lower(Agency.name) == payload.name.strip().lower(), Agency.id != a.id).first():
            raise HTTPException(status_code=409, detail="An agency with that name already exists")
        a.name = payload.name.strip(); changes.append("name")
    if payload.agency_type is not None and payload.agency_type != a.agency_type:
        a.agency_type = payload.agency_type; changes.append(f"type={payload.agency_type}")
    if payload.region is not None and (payload.region.strip() or None) != a.region:
        a.region = payload.region.strip() or None; changes.append("region")
    if payload.is_active is not None and payload.is_active != bool(a.is_active):
        a.is_active = payload.is_active; changes.append(f"active={payload.is_active}")
    if changes:
        a.updated_at = _now()
        record_audit(db, actor_name(admin), "AGENCY_UPDATED", "agency", a.id, ", ".join(changes), role=admin.role)
    db.commit()
    return _out(db, a)


@router.put("/members/{user_id}", response_model=dict)
def assign_member(user_id: int, payload: AssignIn, admin: User = Depends(require_permission(P.AGENCY_MANAGE)),
                  db: Session = Depends(get_db)):
    """Set (or clear, with null) a person's agency. Metadata only: it does not change the person's role, team or permissions,
    so it does not end their sessions."""
    ensure_recent_mfa(admin)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.agency_id is not None:
        a = db.get(Agency, payload.agency_id)
        if a is None or not a.is_active:
            raise HTTPException(status_code=422, detail="Choose an existing, active agency")
    if user.agency_id != payload.agency_id:
        record_audit(db, actor_name(admin), "AGENCY_MEMBER_CHANGED", "user", user.id,
                     f"agency {user.agency_id} -> {payload.agency_id}", role=admin.role)
        user.agency_id = payload.agency_id
    db.commit()
    return {"user_id": user.id, "agency_id": user.agency_id}


@router.put("/teams/{team_id}", response_model=dict)
def assign_team(team_id: str, payload: AssignIn, admin: User = Depends(require_permission(P.AGENCY_MANAGE)),
                db: Session = Depends(get_db)):
    """Associate a squad with an agency (descriptive only; dispatch ignores agencies)."""
    ensure_recent_mfa(admin)
    team = db.get(RescueTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if payload.agency_id is not None:
        a = db.get(Agency, payload.agency_id)
        if a is None or not a.is_active:
            raise HTTPException(status_code=422, detail="Choose an existing, active agency")
    if team.agency_id != payload.agency_id:
        record_audit(db, actor_name(admin), "AGENCY_TEAM_CHANGED", "team", team.id,
                     f"agency {team.agency_id} -> {payload.agency_id}", role=admin.role)
        team.agency_id = payload.agency_id
    db.commit()
    return {"team_id": team.id, "agency_id": team.agency_id}
