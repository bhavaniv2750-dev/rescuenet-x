from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import actor_name, actor_role, get_current_user, require_roles
from app.core.security import APPROVERS, OPS
from app.db.session import get_db
from app.models.entities import Alert, User
from app.schemas.domain import AlertCreate, AlertOut
from app.services.alerting import IN_FORCE, build_cap_xml, escalate_overdue, find_duplicate
from app.services.audit import record_audit

router = APIRouter()


@router.get("/", response_model=dict)
def list_alerts(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    escalate_overdue(db)
    query = db.query(Alert)
    if status_filter:
        query = query.filter(Alert.status == status_filter.upper())
    items = query.order_by(Alert.created_at.desc()).all()
    return {
        "items": [AlertOut.model_validate(alt) for alt in items],
        "count": len(items),
        "active_count": sum(1 for a in items if a.status in IN_FORCE),
        "escalated_count": sum(1 for a in items if a.status == "ACTIVE" and (a.escalation_level or 0) > 0),
    }


@router.post("/", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    duplicate = find_duplicate(db, payload.title, payload.severity, payload.latitude, payload.longitude)
    if duplicate is not None:
        record_audit(db, actor_name(user), "ALERT_DUPLICATE_BLOCKED", "alert", duplicate.id, payload.title, role=actor_role(user))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An equivalent alert is already in force ({duplicate.id}: {duplicate.title}). Resolve it first, or change the area, severity or wording.",
        )
    number = db.query(Alert).count() + 1
    new_id = f"ALT-2026-{number:02d}"
    while db.query(Alert).filter(Alert.id == new_id).first():
        number += 1
        new_id = f"ALT-2026-{number:02d}"

    alert = Alert(
        id=new_id,
        title=payload.title,
        message=payload.message,
        severity=payload.severity.upper(),
        area=payload.area,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_km=payload.radius_km,
        status="ACTIVE",
        delivery_channel="IN_APP",
        acknowledged_count=0,
        data_label="OBSERVED",
    )
    db.add(alert)
    record_audit(db, actor_name(user), "ALERT_ISSUED", "alert", new_id, f"{alert.severity}: {alert.title}", role=actor_role(user))
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Commanders and administrators acknowledge an alert for the control room (stops escalation).
    Everyone else is counted as having seen it; that never changes the alert's status."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if alert.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="This alert is already resolved")

    if user.role in APPROVERS:
        if alert.status == "ACTIVE":
            alert.status = "ACKNOWLEDGED"
            alert.acknowledged_by = actor_name(user)
            record_audit(db, actor_name(user), "ALERT_ACKNOWLEDGED", "alert", alert.id, alert.title, role=actor_role(user))
    else:
        alert.acknowledged_count += 1
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.now(timezone.utc)
    record_audit(db, actor_name(user), "ALERT_RESOLVED", "alert", alert.id, alert.title, role=actor_role(user))
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.get("/{alert_id}/cap")
def alert_as_cap(alert_id: str, db: Session = Depends(get_db)):
    """The alert as a Common Alerting Protocol 1.2 XML document. Public, like the alert itself."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return Response(
        content=build_cap_xml(alert),
        media_type="application/cap+xml",
        headers={"Content-Disposition": f'inline; filename="{alert.id}.cap.xml"'},
    )
