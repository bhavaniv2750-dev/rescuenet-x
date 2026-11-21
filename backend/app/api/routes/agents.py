import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Facility, Incident, RescueTeam, SupervisorTask
from app.schemas.domain import SupervisorTaskOut, SupervisorTaskRequest
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


@router.get("/")
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


@router.get("/supervisor/health")
def get_supervisor_health():
    """Check connectivity and model availability of local Ollama server."""
    return ollama_supervisor_service.check_health()


@router.get("/tasks")
def list_supervisor_tasks(db: Session = Depends(get_db)):
    tasks = db.query(SupervisorTask).order_by(SupervisorTask.created_at.desc()).all()
    return {
        "items": [SupervisorTaskOut.model_validate(t) for t in tasks],
        "count": len(tasks),
    }


@router.post("/supervisor/triage", response_model=SupervisorTaskOut, status_code=status.HTTP_201_CREATED)
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
            people_count = incident.people_affected
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

    # 5. Deterministic Task ID and Database Persistence
    count = db.query(SupervisorTask).count()
    task_id = f"TASK-{803 + count}"

    task = SupervisorTask(
        id=task_id,
        task_type=payload.task_type.upper(),
        title=f"Autonomous Triage: {target_area} ({target_title[:40]})",
        status="PENDING_APPROVAL" if result.enforced_requires_approval else "COMPLETED",
        agent_flow=f"Supervisor (Ollama {result.model_name}) -> Geospatial Catchments -> Logistics Dispatch -> Safety Gatekeeper",
        input_summary=f"Incident: {target_title} | Area: {target_area} | Affected: {people_count} | Directive: {payload.instruction or 'Full Tactical Triage'}",
        findings=result.findings_formatted,
        recommendations=result.recommendations_formatted,
        requires_human_approval=result.enforced_requires_approval,
        approved_by=None if result.enforced_requires_approval else "Automated Agent Policy Guard",
    )

    db.add(task)
    db.commit()
    db.refresh(task)
    return SupervisorTaskOut.model_validate(task)


@router.post("/tasks/{task_id}/approve", response_model=SupervisorTaskOut)
def approve_supervisor_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(SupervisorTask).filter(SupervisorTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task.status = "COMPLETED"
    task.requires_human_approval = False
    task.approved_by = "Human Commander Authorization (Console OP-01)"
    task.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)
    return SupervisorTaskOut.model_validate(task)
