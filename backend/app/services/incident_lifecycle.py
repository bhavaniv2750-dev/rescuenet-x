"""Incident lifecycle: the allowed states and the transitions between them.

REPORTED -> UNDER_VERIFICATION -> VERIFIED -> QUEUED -> TRIAGE_IN_PROGRESS
         -> PENDING_APPROVAL -> DISPATCHED -> IN_TRANSIT -> ON_SCENE -> RESOLVED

Side branches: DUPLICATE and CANCELLED are terminal, and REJECTED (a report
found invalid, or a dispatch the commander declined) can be re-queued.
"""

from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Incident
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


def allowed_next(status: str) -> List[str]:
    return TRANSITIONS.get(normalize(status), [])


def transition(
    db: Session,
    incident: Incident,
    to_status: str,
    actor: str = "operator",
    role: str = "OPERATOR",
    note: Optional[str] = None,
) -> Incident:
    """Move an incident to a new state, or raise 409 if the move is not allowed."""
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
    incident.status = target
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
