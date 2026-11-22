from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import actor_name, actor_role, require_roles
from app.core.security import APPROVERS, DEPT, OPS
from app.db.session import get_db
from app.models.entities import Incident, RescueTeam, User
from app.schemas.domain import RescueTeamCreate, RescueTeamOut
from app.services import incident_lifecycle as lifecycle
from app.services.audit import record_audit
from app.services.dispatch import dispatch_incident_to_team

router = APIRouter()

class TeamStatusUpdate(BaseModel):
    status: str = Field(pattern="(?i)^(AVAILABLE|DEPLOYED|STANDBY)$")  # AVAILABLE, DEPLOYED, STANDBY

class TeamAssignRequest(BaseModel):
    incident_id: str

@router.get("/", response_model=dict, dependencies=[Depends(require_roles(*DEPT))])
def list_teams(status_filter: Optional[str] = Query(None, alias="status"), db: Session = Depends(get_db)):
    query = db.query(RescueTeam)
    if isinstance(status_filter, str) and status_filter.strip():
        query = query.filter(RescueTeam.status == status_filter.upper())
    teams = query.all()
    return {
        "items": [RescueTeamOut.model_validate(t) for t in teams],
        "count": len(teams),
        "available_count": sum(1 for t in teams if t.status == "AVAILABLE"),
        "deployed_count": sum(1 for t in teams if t.status == "DEPLOYED"),
    }

@router.post("/", response_model=RescueTeamOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(*OPS))])
def create_team(payload: RescueTeamCreate, db: Session = Depends(get_db)):
    count = db.query(RescueTeam).count()
    new_id = f"TEAM-{payload.callsign.upper()}-{count + 1}"

    team = RescueTeam(
        id=new_id,
        name=payload.name,
        callsign=payload.callsign,
        status="AVAILABLE",
        vehicle_type=payload.vehicle_type,
        members_count=payload.members_count,
        skills=payload.skills,
        latitude=payload.latitude,
        longitude=payload.longitude,
        base_station=payload.base_station,
        contact_number=payload.contact_number,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return RescueTeamOut.model_validate(team)

@router.patch("/{team_id}/status", response_model=RescueTeamOut, dependencies=[Depends(require_roles(*OPS))])
def update_team_status(team_id: str, payload: TeamStatusUpdate, db: Session = Depends(get_db)):
    team = db.query(RescueTeam).filter(RescueTeam.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Rescue team {team_id} not found")

    new_status = payload.status.upper()
    if new_status == "AVAILABLE" and (team.status or "").upper() != "AVAILABLE":
        # A team on a live mission cannot be freed: it would show as bookable while still out in the field.
        active = db.query(Incident).filter(
            Incident.assigned_team_id == team.id,
            Incident.status.in_(["DISPATCHED", "IN_TRANSIT", "ON_SCENE"]),
        ).first()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"Team {team.id} is on an active mission ({active.id}, {active.status}). Resolve or cancel the incident before releasing the team.",
            )
    team.status = new_status
    db.commit()
    db.refresh(team)
    return RescueTeamOut.model_validate(team)

@router.post("/{team_id}/assign")
def assign_team_to_incident(team_id: str, payload: TeamAssignRequest, db: Session = Depends(get_db),
                            user: User = Depends(require_roles(*OPS))):
    team = db.query(RescueTeam).filter(RescueTeam.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Rescue team {team_id} not found")

    incident = db.query(Incident).filter(Incident.id == payload.incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {payload.incident_id} not found")

    # One routine claims the team (atomic conditional update), enforces the commander-approval gate and moves the
    # incident to DISPATCHED. Nothing is committed unless every step succeeds.
    dispatch_incident_to_team(
        db, incident, team.id, actor=actor_name(user, "operator"), role=actor_role(user, "OPERATOR"),
    )
    db.commit()
    db.refresh(team)
    db.refresh(incident)
    return {
        "message": f"Team {team.name} assigned to incident {incident.id}",
        "team_id": team.id,
        "incident_id": incident.id,
        "team_status": team.status,
        "incident_status": incident.status,
    }
