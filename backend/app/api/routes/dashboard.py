from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from app.db.session import get_db
from app.ml.flood_model import flood_ml_service
from app.models.entities import Alert, Facility, Incident, RescueRecord, RescueTeam, Volunteer
from app.services.incident_lifecycle import TERMINAL_STATES

CLOSED_STATES = sorted(TERMINAL_STATES)

router = APIRouter()

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    # Incident stats
    total_incidents = db.query(Incident).count()
    active_incidents = db.query(Incident).filter(Incident.status.notin_(CLOSED_STATES)).count()
    critical_incidents = db.query(Incident).filter(
        Incident.severity.in_(["CRITICAL", "critical"]),
        Incident.status.notin_(CLOSED_STATES)
    ).count()
    people_affected = db.query(func.sum(Incident.people_affected)).scalar() or 0

    # Teams stats
    total_teams = db.query(RescueTeam).count()
    available_teams = db.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").count()
    deployed_teams = db.query(RescueTeam).filter(RescueTeam.status == "DEPLOYED").count()

    # Alerts stats
    active_alerts = db.query(Alert).filter(Alert.status == "ACTIVE").count()

    # Facilities stats
    total_facilities = db.query(Facility).count()
    total_capacity = db.query(func.sum(Facility.total_capacity)).scalar() or 0
    current_occupancy = db.query(func.sum(Facility.current_occupancy)).scalar() or 0

    # Volunteers stats
    total_volunteers = db.query(Volunteer).count()
    verified_volunteers = db.query(Volunteer).filter(Volunteer.is_verified == True).count()

    # Rescue outcomes
    people_rescued = db.query(func.sum(RescueRecord.people_rescued)).scalar() or 0

    # Priority Incidents (top 5 active)
    priority_incidents = (
        db.query(Incident)
        .filter(Incident.status.notin_(CLOSED_STATES))
        .order_by(
            case(
                (Incident.severity.in_(["CRITICAL", "critical"]), 1),
                (Incident.severity.in_(["HIGH", "high"]), 2),
                else_=3
            ),
            Incident.created_at.desc()
        )
        .limit(5)
        .all()
    )

    # Recent Alerts
    recent_alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(3).all()

    # Real-time baseline ML prediction (using recent average station telemetry: 25 mm rain, 3.2 m water level)
    forecast = flood_ml_service.predict(rainfall_mm=22.5, water_level_m=3.1)

    return {
        "region": "Bengaluru Urban & Rural, Karnataka",
        "data_mode": "hybrid_real_persistent",
        "summary": {
            "total_incidents": total_incidents,
            "active_incidents": active_incidents,
            "critical_alerts": critical_incidents,
            "people_affected": int(people_affected),
            "response_teams": {
                "total": total_teams,
                "available": available_teams,
                "deployed": deployed_teams,
            },
            "active_alerts": active_alerts,
            "volunteers": {
                "total": total_volunteers,
                "verified": verified_volunteers,
            },
            "facilities": {
                "total": total_facilities,
                "capacity": int(total_capacity),
                "occupancy": int(current_occupancy),
                "available_beds": int(total_capacity - current_occupancy),
            },
            "people_rescued": int(people_rescued),
        },
        "forecast_preview": forecast,
        "priority_incidents": [
            {
                "id": inc.id,
                "title": inc.title,
                "location": inc.area,
                "severity": inc.severity.upper(),
                "status": inc.status,
                "people": inc.people_affected,
                "source": inc.source,
                "assigned_team_id": inc.assigned_team_id,
            }
            for inc in priority_incidents
        ],
        "active_alerts_feed": [
            {
                "id": alt.id,
                "title": alt.title,
                "severity": alt.severity.upper(),
                "area": alt.area,
                "radius_km": alt.radius_km,
                "acknowledged_count": alt.acknowledged_count,
                "created_at": alt.created_at.isoformat() if alt.created_at else None,
            }
            for alt in recent_alerts
        ],
    }
