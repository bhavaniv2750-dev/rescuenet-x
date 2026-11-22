import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import actor_name, actor_role, require_permission
from app.core.permissions import P
from app.db.session import get_db
from app.models.entities import Facility, Incident, RescueTeam, SupervisorTask, User
from app.schemas.domain import SupervisorTaskDecision, SupervisorTaskOut, SupervisorTaskRequest
from app.services import incident_lifecycle as lifecycle
from app.services.audit import record_audit
from app.services.dispatch import dispatch_incident_to_team
from app.services.geo_service import geo_service
from app.services.ollama_service import haversine_km, ollama_supervisor_service

router = APIRouter()

AGENTS_ROSTER = [
    {
        "id": "supervisor",
        "name": "Supervisor Agent",
        "role": "Autonomous Multi-Agent Orchestrator & Safety Gatekeeper",
        "state": "ACTIVE",
        "icon": "◎",
    },
    {
        "id": "flood-monitoring",
        "name": "Flood Telemetry Agent",
        "role": "Real-time Telemetry & ML Water-Level Forecaster",
        "state": "ACTIVE",
        "icon": "⌁",
    },
    {
        "id": "geospatial",
        "name": "Geospatial Intelligence Agent",
        "role": "IndoFloods Catchments & Gauge Proximity Mapping",
        "state": "ACTIVE",
        "icon": "◇",
    },
    {
        "id": "rescue-coordinator",
        "name": "Rescue Coordination Agent",
        "role": "Asset Triage, Distance Optimization & Squad Dispatch",
        "state": "ACTIVE",
        "icon": "⇄",
    },
    {
        "id": "resource-facility",
        "name": "Shelter & Logistics Agent",
        "role": "Emergency Shelter Capacity & Medical Bed Reservation",
        "state": "ACTIVE",
        "icon": "✚",
    },
    {
        "id": "alerts",
        "name": "Public Warning Agent",
        "role": "Geo-targeted CAP Emergency Broadcast Synthesizer",
        "state": "READY",
        "icon": "♧",
    },
]


@router.get("/", dependencies=[Depends(require_permission(P.SUPERVISOR_VIEW))])
def list_agents():
    health = ollama_supervisor_service.check_health()
    return {
        "count": len(AGENTS_ROSTER),
        "agents": AGENTS_ROSTER,
        "orchestration_active": True,
        "orchestrator_engine": "RescueNet Autonomous Multi-Agent Coordinator v2.0",
        "llm_supervisor": {
            "provider": "Ollama Local Inference",
            "model": settings.OLLAMA_MODEL,
            "available": health.get("available", False),
            "model_installed": health.get("model_installed", False),
            "status": "ONLINE" if health.get("available") else "OFFLINE",
            "error": health.get("error"),
        },
    }


@router.get("/supervisor/health", dependencies=[Depends(require_permission(P.SUPERVISOR_VIEW))])
def get_supervisor_health():
    """Check connectivity and model availability of local Ollama server."""
    return ollama_supervisor_service.check_health()


@router.get("/tasks", dependencies=[Depends(require_permission(P.SUPERVISOR_VIEW))])
def list_supervisor_tasks(db: Session = Depends(get_db)):
    tasks = db.query(SupervisorTask).order_by(SupervisorTask.created_at.desc()).all()
    return {
        "items": [SupervisorTaskOut.model_validate(t) for t in tasks],
        "count": len(tasks),
    }


@router.post("/supervisor/triage", response_model=SupervisorTaskOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(P.TRIAGE_RUN))])
async def execute_supervisor_triage(payload: SupervisorTaskRequest, db: Session = Depends(get_db)):
    # 1. Fetch incident or handle prospective / no-incident context
    incident = None
    target_lat = 12.9716
    target_lon = 77.5946
    target_title = payload.task_type or "General Flood Assessment"
    target_area = payload.area or "Central Bengaluru"
    people_count = 0

    if payload.incident_id:
        incident = db.query(Incident).filter(Incident.id == payload.incident_id).first()
        if incident:
            target_lat = incident.latitude
            target_lon = incident.longitude
            target_title = incident.title
            target_area = incident.area
            # The original assessment counts: editing the headcount down must not change the triage.
            people_count = lifecycle.effective_risk(incident)[1]
        else:
            target_title = f"Unregistered Incident Reference ({payload.incident_id})"
            target_area = payload.area or "Unknown Area"
    elif payload.area:
        target_title = f"Area Assessment: {payload.area}"
        target_area = payload.area

    # 2. Query verified real response teams and facilities from database
    available_teams = db.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").all()
    candidate_facilities = db.query(Facility).filter(Facility.status == "OPERATIONAL").all()

    # 3. Query geospatial catchments & nearest IndoFloods gauge
    gauges = geo_service.get_karnataka_gauges()
    nearest_gauge = None
    min_gauge_dist = 9999.0
    for g in gauges:
        dist = haversine_km(target_lat, target_lon, g["latitude"], g["longitude"])
        if dist < min_gauge_dist:
            min_gauge_dist = dist
            nearest_gauge = g

    # 4. Invoke local Ollama supervisor reasoning (with strict validation of IDs)
    result = await ollama_supervisor_service.run_supervisor_reasoning(
        incident=incident,
        target_lat=target_lat,
        target_lon=target_lon,
        target_title=target_title,
        target_area=target_area,
        people_count=people_count,
        task_type=payload.task_type,
        instruction=payload.instruction,
        available_teams=available_teams,
        candidate_facilities=candidate_facilities,
        nearest_gauge=nearest_gauge,
        gauge_dist_km=min_gauge_dist,
    )

    # The commander-approval rule is evaluated on the original assessment, whatever the supervisor concluded.
    requires_approval = bool(result.enforced_requires_approval or (incident is not None and lifecycle.incident_requires_approval(incident)))
    findings_text, recommendations_text = result.findings_formatted, result.recommendations_formatted
    if requires_approval and not result.enforced_requires_approval:
        recommendations_text += (
            "\n[6] Safety Policy (override): the original risk assessment of this incident requires commander "
            "authorization before dispatch."
        )

    # 5. Deterministic Task ID and Database Persistence
    count = db.query(SupervisorTask).count()
    task_id = f"TASK-{803 + count}"

    task = SupervisorTask(
        id=task_id,
        task_type=payload.task_type.upper(),
        title=f"Autonomous Triage: {target_area} ({target_title[:40]})",
        status="PENDING_APPROVAL" if requires_approval else "COMPLETED",
        agent_flow=f"Supervisor (Ollama {result.model_name}) -> Geospatial Catchments -> Logistics Dispatch -> Safety Gatekeeper",
        input_summary=f"Incident: {target_title} | Area: {target_area} | Affected: {people_count} | Directive: {payload.instruction or 'Full Tactical Triage'}",
        findings=findings_text,
        recommendations=recommendations_text,
        requires_human_approval=requires_approval,
        approved_by=None if requires_approval else "Automated Agent Policy Guard",
        incident_id=incident.id if incident else None,
        suggested_team_id=result.validated_team_id,
        suggested_facility_id=result.validated_facility_id,
    )
    db.add(task)
    record_audit(db, "supervisor-agent", "TRIAGE_COMPLETED", "task", task_id,
                 f"model {result.model_name} ({result.model_status}); approval required: {requires_approval}", role="AGENT")

    # Move the incident through the lifecycle. The gate result decides whether a commander must approve.
    if incident is not None:
        current = lifecycle.normalize(incident.status)
        if current in ("VERIFIED", "QUEUED"):
            lifecycle.transition(db, incident, "TRIAGE_IN_PROGRESS", actor="supervisor-agent", role="AGENT", note=task_id)
            current = "TRIAGE_IN_PROGRESS"
        if current == "TRIAGE_IN_PROGRESS" and requires_approval:
            lifecycle.transition(db, incident, "PENDING_APPROVAL", actor="safety-gate", role="SYSTEM", note=task_id)

    db.commit()
    db.refresh(task)
    return SupervisorTaskOut.model_validate(task)


def _decider(payload: SupervisorTaskDecision, user) -> SupervisorTaskDecision:
    """The decision is recorded under the signed-in commander's name."""
    if isinstance(user, User):
        return payload.model_copy(update={"commander": f"{user.full_name} ({user.username})"})
    return payload


def _get_pending_task(db: Session, task_id: str) -> SupervisorTask:
    task = db.query(SupervisorTask).filter(SupervisorTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"Task {task_id} is {task.status}, not waiting for approval")
    return task


@router.post("/tasks/{task_id}/approve", response_model=SupervisorTaskOut)
def approve_supervisor_task(task_id: str, payload: SupervisorTaskDecision = SupervisorTaskDecision(), db: Session = Depends(get_db),
                            user: User = Depends(require_permission(P.DISPATCH_APPROVE))):
    """Commander approves the plan. The linked incident is dispatched only if the suggested team can really be
    sent: it must still be AVAILABLE and is claimed atomically. Otherwise nothing changes and the approval is refused."""
    payload = _decider(payload, user)
    task = _get_pending_task(db, task_id)

    incident = db.query(Incident).filter(Incident.id == task.incident_id).first() if task.incident_id else None
    if incident is not None and lifecycle.normalize(incident.status) == "PENDING_APPROVAL":
        try:
            if not task.suggested_team_id:
                raise HTTPException(
                    status_code=409,
                    detail="This plan has no rescue team to send, so approving it would not dispatch anyone. "
                           "Decline it, or run triage again when a team is available.",
                )
            dispatch_incident_to_team(
                db, incident, task.suggested_team_id, actor=payload.commander, role=actor_role(user),
                note=f"approved {task.id}", commander_approved=True,
            )
        except HTTPException as exc:
            db.rollback()  # undo any partial work; keep a record that the approval was refused
            record_audit(db, payload.commander, "TASK_APPROVAL_BLOCKED", "incident", incident.id, f"{task.id}: {exc.detail}", role="COMMANDER")
            db.commit()
            raise

    task.status = "APPROVED"
    task.requires_human_approval = False
    task.approved_by = payload.commander
    task.decision_note = payload.note
    task.updated_at = datetime.now(timezone.utc)
    record_audit(db, payload.commander, "TASK_APPROVED", "task", task.id, payload.note, role="COMMANDER")

    db.commit()
    db.refresh(task)
    return SupervisorTaskOut.model_validate(task)


@router.post("/tasks/{task_id}/decline", response_model=SupervisorTaskOut)
def decline_supervisor_task(task_id: str, payload: SupervisorTaskDecision = SupervisorTaskDecision(), db: Session = Depends(get_db),
                            user: User = Depends(require_permission(P.DISPATCH_APPROVE))):
    """Commander declines the plan. The linked incident goes to REJECTED and can be re-queued."""
    payload = _decider(payload, user)
    task = _get_pending_task(db, task_id)
    task.status = "DECLINED"
    task.requires_human_approval = False
    task.approved_by = None
    task.decision_note = payload.note
    task.updated_at = datetime.now(timezone.utc)
    record_audit(db, payload.commander, "TASK_DECLINED", "task", task.id, payload.note, role="COMMANDER")

    if task.incident_id:
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if incident and lifecycle.normalize(incident.status) == "PENDING_APPROVAL":
            lifecycle.transition(db, incident, "REJECTED", actor=payload.commander, role=actor_role(user), note=f"declined {task.id}")

    db.commit()
    db.refresh(task)
    return SupervisorTaskOut.model_validate(task)
