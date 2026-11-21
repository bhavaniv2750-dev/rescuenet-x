from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import Alert
from app.schemas.domain import AlertCreate, AlertOut

router = APIRouter()

@router.get("/", response_model=dict)
def list_alerts(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Alert)
    if status_filter:
        query = query.filter(Alert.status == status_filter.upper())
    items = query.order_by(Alert.created_at.desc()).all()
    return {
        "items": [AlertOut.model_validate(alt) for alt in items],
        "count": len(items),
        "active_count": sum(1 for a in items if a.status == "ACTIVE"),
    }

@router.post("/", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    count = db.query(Alert).count()
    new_id = f"ALT-2026-{count + 1:02d}"

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
        delivery_channel="SIMULATED_CAP_ALERT",
        acknowledged_count=0,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)

@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.acknowledged_count += 1
    if alert.status == "ACTIVE":
        alert.status = "ACKNOWLEDGED"

    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)

@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)
