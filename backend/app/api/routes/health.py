from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.ml.flood_model import flood_ml_service
from app.models.entities import Alert, Incident, RescueRecord, RescueTeam

router = APIRouter()

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    counts = {
        "incidents": 0,
        "alerts": 0,
        "rescue_records": 0,
        "rescue_teams": 0,
    }
    try:
        counts["incidents"] = db.query(Incident).count()
        counts["alerts"] = db.query(Alert).count()
        counts["rescue_records"] = db.query(RescueRecord).count()
        counts["rescue_teams"] = db.query(RescueTeam).count()
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    ml_status = "loaded" if flood_ml_service.model is not None else "unavailable"
    metrics = flood_ml_service.metrics or {}

    return {
        "status": "healthy",
        "service": "Flood Digital Twin + RescueNet X 2.0 API",
        "version": "2.0.0",
        "api_base": "/api",
        "geographic_region": {
            "name": "Bengaluru Urban/Rural & Karnataka River Basins",
            "center": {"lat": 12.9716, "lng": 77.5946},
            "river_basins": ["Shimsha", "Cauvery", "Krishna", "Ghataprabha"],
        },
        "database": {
            "status": db_status,
            "engine": "SQLite (SQLAlchemy 2.0)",
            "file": "backend/rescuenet.db",
            "total_incidents": counts["incidents"],
            "total_alerts": counts["alerts"],
            "total_records": counts["rescue_records"],
            "total_teams": counts["rescue_teams"],
        },
        "ml_service": {
            "status": ml_status,
            "model_architecture": metrics.get("model_architecture", "RandomForestClassifier(n_estimators=100, max_depth=6)"),
            "training_samples": metrics.get("training_samples"),
            "test_samples": metrics.get("test_samples"),
            "test_accuracy": metrics.get("accuracy"),
            "dataset_source": metrics.get("dataset_source", "clean_flood_prediction_data.csv"),
            "feature_names": ["rainfall_mm", "water_level_m", "humidity_pct", "temperature_c"],
            "validation_note": "Evaluated on stratified holdout test split (200 records). 30-60m horizons are hydrological scenario extrapolations, not field-validated predictions.",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
