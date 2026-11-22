"""Incident lifecycle: the allowed states and the transitions between them.

REPORTED -> UNDER_VERIFICATION -> VERIFIED -> QUEUED -> TRIAGE_IN_PROGRESS
         -> PENDING_APPROVAL -> DISPATCHED -> IN_TRANSIT -> ON_SCENE -> RESOLVED

Side branches: DUPLICATE and CANCELLED are terminal, and REJECTED (a report
found invalid, or a dispatch the commander declined) can be re-queued.
"""

from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.permissions import P, role_has
from app.models.entities import Incident, RescueTeam, Volunteer
from app.services.audit import record_audit

STATES: List[str] = [
    "REPORTED",
    "UNDER_VERIFICATION",
    "VERIFIED",
    "QUEUED",
    "TRIAGE_IN_PROGRESS",
    "PENDING_APPROVAL",
    "DISPATCHED",
    "IN_TRANSIT",
    "ON_SCENE",
    "RESOLVED",
    "DUPLICATE",
    "REJECTED",
    "CANCELLED",
]

TERMINAL_STATES = {"RESOLVED", "DUPLICATE", "CANCELLED"}

TRANSITIONS: Dict[str, List[str]] = {
    "REPORTED": ["UNDER_VERIFICATION", "VERIFIED", "DUPLICATE", "REJECTED", "CANCELLED"],
    "UNDER_VERIFICATION": ["VERIFIED", "DUPLICATE", "REJECTED", "CANCELLED"],
    "VERIFIED": ["QUEUED", "TRIAGE_IN_PROGRESS", "DISPATCHED", "CANCELLED"],
    "QUEUED": ["TRIAGE_IN_PROGRESS", "DISPATCHED", "CANCELLED"],
    "TRIAGE_IN_PROGRESS": ["PENDING_APPROVAL", "DISPATCHED", "QUEUED"],
    "PENDING_APPROVAL": ["DISPATCHED", "REJECTED"],
    "REJECTED": ["QUEUED", "CANCELLED"],
    "DISPATCHED": ["IN_TRANSIT", "ON_SCENE", "CANCELLED"],
    "IN_TRANSIT": ["ON_SCENE"],
    "ON_SCENE": ["RESOLVED"],
    "RESOLVED": [],
    "DUPLICATE": [],
    "CANCELLED": [],
}

# Older clients and databases used these names.
LEGACY_ALIASES = {"ASSIGNED": "DISPATCHED", "IN_PROGRESS": "ON_SCENE"}


def normalize(status: str) -> str:
    s = (status or "").strip().upper()
    return LEGACY_ALIASES.get(s, s)


def requires_commander_approval(people_affected: int, severity: Optional[str]) -> bool:
    """Deterministic safety rule: five or more victims, or HIGH or CRITICAL severity."""
    return (people_affected or 0) >= 5 or (severity or "").upper() in ("HIGH", "CRITICAL")


SEVERITY_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}


def severity_rank(severity: Optional[str]) -> int:
    """Unknown or missing severities count as HIGH, so a bad value can never lower the gate."""
    return SEVERITY_RANK.get((severity or "").upper(), SEVERITY_RANK["HIGH"])


def effective_risk(incident: Incident) -> Tuple[str, int]:
    """(severity, people) the approval rule must use.

    The assessment recorded when the incident was created is kept, and editing the current values can only
    raise the effective risk, never lower it. The one exception is a downgrade a commander or administrator
    authorised in writing (risk_downgraded_by), which makes the current values the baseline.
    """
    cur_sev = (incident.severity or "HIGH").upper()
    cur_people = incident.people_affected or 0
    if incident.risk_downgraded_by:
        return cur_sev, cur_people
    orig_sev = (incident.reported_severity or cur_sev).upper()
    orig_people = incident.reported_people_affected or cur_people
    sev = cur_sev if severity_rank(cur_sev) >= severity_rank(orig_sev) else orig_sev
    return sev, max(cur_people, orig_people)


def incident_requires_approval(incident: Incident) -> bool:
    """True when dispatch needs a commander: five or more people, or HIGH or CRITICAL severity."""
    severity, people = effective_risk(incident)
    return requires_commander_approval(people, severity)


def allowed_next(status: str) -> List[str]:
    return TRANSITIONS.get(normalize(status), [])


def transition(
    db: Session,
    incident: Incident,
    to_status: str,
    actor: str = "operator",
    role: str = "OPERATOR",
    note: Optional[str] = None,
    approved_by_commander: bool = False,
) -> Incident:
    """Move an incident to a new state, or raise 409 if the move is not allowed.

    DISPATCHED has two extra conditions that no caller can skip: the incident must hold a team that is
    DEPLOYED, and an incident that needs commander approval may only reach it through that approval
    (approved_by_commander=True, passed by the approval route).
    """
    target = normalize(to_status)
    current = normalize(incident.status)
    if target not in STATES:
        raise HTTPException(status_code=422, detail=f"Unknown incident status '{to_status}'")
    if target == current:
        return incident
    if target not in TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=409,
            detail=f"Transition {current} -> {target} is not allowed. Allowed: {', '.join(TRANSITIONS.get(current, [])) or 'none (terminal state)'}",
        )
    if target == "DISPATCHED":
        # Service-level authorization: whatever the caller, only a role holding dispatch.assign may dispatch (the
        # supervisor agent and system roles never do), and only dispatch.approve may claim commander approval.
        if not role_has(role, P.DISPATCH_ASSIGN):
            raise HTTPException(status_code=403, detail=f"Role {role} is not allowed to dispatch.")
        if approved_by_commander and not role_has(role, P.DISPATCH_APPROVE):
            raise HTTPException(status_code=403, detail=f"Role {role} cannot give commander approval.")
        if incident_requires_approval(incident) and not approved_by_commander:
            raise HTTPException(
                status_code=409,
                detail="This incident needs commander approval (five or more people, or HIGH or CRITICAL severity) before it can be dispatched.",
            )
        team = db.query(RescueTeam).filter(RescueTeam.id == incident.assigned_team_id).first() if incident.assigned_team_id else None
        if team is None or (team.status or "").upper() != "DEPLOYED":
            raise HTTPException(
                status_code=409,
                detail="An incident can be DISPATCHED only with a rescue team assigned and deployed to it. "
                       "Use POST /api/teams/{team_id}/assign (or a commander's approval of a supervisor task).",
            )
    incident.status = target
    if target in TERMINAL_STATES:
        # Volunteers on a finished incident become available again.
        for vol in db.query(Volunteer).filter(Volunteer.assigned_incident_id == incident.id).all():
            vol.assigned_incident_id = None
            vol.status = "AVAILABLE"
    if target == "VERIFIED":
        incident.verified_by = actor
    record_audit(
        db,
        actor=actor,
        role=role,
        action="INCIDENT_STATE_CHANGE",
        target_type="incident",
        target_id=incident.id,
        details=f"{current} -> {target}" + (f" | {note}" if note else ""),
    )
    return incident
