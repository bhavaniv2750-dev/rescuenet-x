"""Dispatching an incident: the one place where a team is claimed and an incident becomes DISPATCHED.

The team is claimed with a conditional UPDATE (status AVAILABLE -> DEPLOYED), so two requests racing for the
same team cannot both win: the second one updates zero rows and is refused. The claim, the team link and the
state change all happen inside the caller's transaction. The caller commits once at the end, so a failure at
any step (including the state change) leaves the team untouched.
"""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models.entities import Incident, RescueTeam
from app.services import incident_lifecycle as lifecycle
from app.services.audit import record_audit


def _check_dispatchable(incident: Incident, commander_approved: bool) -> str:
    """The preconditions for dispatching, evaluated on the incident as it is right now. Returns its current state."""
    current = lifecycle.normalize(incident.status)
    if current != "DISPATCHED" and "DISPATCHED" not in lifecycle.TRANSITIONS.get(current, []):
        raise HTTPException(status_code=409, detail=f"Incident {incident.id} is {incident.status} and cannot be dispatched from that state.")
    if current == "DISPATCHED" and incident.assigned_team_id:
        raise HTTPException(
            status_code=409,
            detail=f"Incident {incident.id} already has team {incident.assigned_team_id} assigned. One team is assigned per incident.",
        )
    # An assigned_team_id on an incident that is not dispatched yet is a stale leftover from the old editable
    # field; it carries no claim on a team and is simply replaced.
    if commander_approved:
        if current != "PENDING_APPROVAL":
            raise HTTPException(status_code=409, detail=f"Incident {incident.id} is {incident.status}, not waiting for approval.")
    else:
        if current == "PENDING_APPROVAL":
            raise HTTPException(status_code=409, detail="Incident is waiting for commander approval; approve the supervisor task to dispatch it.")
        if lifecycle.incident_requires_approval(incident):
            raise HTTPException(
                status_code=409,
                detail="This incident needs commander approval (five or more victims, or HIGH or CRITICAL severity). Run supervisor triage and approve the task.",
            )
    return current


def dispatch_incident_to_team(
    db: Session,
    incident: Incident,
    team_id: str,
    *,
    actor: str,
    role: str,
    note: Optional[str] = None,
    commander_approved: bool = False,
) -> RescueTeam:
    team = db.query(RescueTeam).filter(RescueTeam.id == team_id).first()
    if team is None:
        raise HTTPException(status_code=404, detail=f"Rescue team {team_id} not found")

    # Checked twice: first to refuse early without touching a team, then again right after the claim. The claim
    # holds the database write lock, so the second check sees the incident exactly as it will be committed
    # (a severity raised by someone else in between cannot slip past the approval rule).
    current = _check_dispatchable(incident, commander_approved)

    claimed = db.execute(
        update(RescueTeam).where(RescueTeam.id == team_id, func.upper(RescueTeam.status) == "AVAILABLE").values(status="DEPLOYED")
    ).rowcount
    db.refresh(team)
    if claimed != 1:
        raise HTTPException(status_code=409, detail=f"Team {team.id} is {team.status}, not AVAILABLE")
    db.refresh(incident)
    current = _check_dispatchable(incident, commander_approved)

    incident.assigned_team_id = team.id
    if current != "DISPATCHED":
        lifecycle.transition(
            db, incident, "DISPATCHED", actor=actor, role=role, note=note or f"team {team.id}",
            approved_by_commander=commander_approved,
        )
    record_audit(db, actor, "TEAM_ASSIGNED", "incident", incident.id, team.id, role=role)
    return team
