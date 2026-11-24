"""System diagnostics for administrators: what is running, what is configured, and what to fix."""

import os
import platform
import sys
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import P, PRIVILEGED_ROLES
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Alert, AuditLog, Beacon, Facility, Incident, MfaCredential, RescueTeam, SupervisorTask, User, Volunteer

router = APIRouter()


def _dir_size_mb(path) -> float:
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        return 0.0
    return round(total / 1e6, 2)


@router.get("/", dependencies=[Depends(require_permission(P.SYSTEM_DIAGNOSTICS))])
def diagnostics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    from app.ml.flood_model import flood_ml_service
    from app.services.ollama_service import ollama_supervisor_service
    from app.services.vision_service import flood_vision_service

    warnings: List[str] = []

    def count(model) -> int:
        return db.query(func.count()).select_from(model).scalar() or 0

    # ---- data
    by_label = dict(db.query(Incident.data_label, func.count()).group_by(Incident.data_label).all())
    tables = {
        "incidents": count(Incident), "alerts": count(Alert), "teams": count(RescueTeam),
        "volunteers": count(Volunteer), "facilities": count(Facility), "beacons": count(Beacon),
        "supervisor_tasks": count(SupervisorTask), "users": count(User), "audit_entries": count(AuditLog),
    }

    # ---- accounts
    demo_active = db.query(func.count(User.id)).filter(User.is_demo.is_(True), User.is_active.is_(True)).scalar() or 0
    if demo_active:
        warnings.append(f"{demo_active} active development-fixture (demo) account(s) exist. They must not exist in a real deployment: "
                        "run scripts/disable_demo_accounts.py (dry run first).")
    if settings.SEED_DEMO_USERS:
        warnings.append("SEED_DEMO_USERS is on: simulated demo accounts are created on an empty development database.")
    from app.services import startup_checks
    for f in startup_checks.evaluate():
        if f.level == startup_checks.WARNING:
            warnings.append(f"{f.code}: {f.message}")
    if not settings.LORA_GATEWAY_KEY:
        warnings.append("LORA_GATEWAY_KEY is not set: anyone who can reach /api/incidents/lora can create SOS incidents.")

    # ---- models
    ollama = ollama_supervisor_service.check_health()
    if not ollama.get("available"):
        warnings.append("Ollama is not reachable: supervisor triage uses the rule-based fallback and always requires commander approval.")
    vision = flood_vision_service.status()
    if not vision["ready"]:
        warnings.append("Flood photo models are not installed: run python scripts/download_vision_model.py.")

    return {
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform(), "debug": settings.DEBUG,
            "environment": settings.RESCUENET_ENV},
        "database": {"url_kind": settings.DATABASE_URL.split(":")[0], "tables": tables, "incidents_by_data_label": by_label},
        "flood_model": {
            "loaded": flood_ml_service.model is not None,
            "inputs": flood_ml_service.metrics.get("model_inputs"),
            "holdout_accuracy": flood_ml_service.metrics.get("accuracy"),
            "cv_accuracy": flood_ml_service.metrics.get("cv_5fold_accuracy_mean"),
        },
        "vision_model": vision,
        "ollama": {"model": settings.OLLAMA_MODEL, "timeout_s": settings.OLLAMA_TIMEOUT_SECONDS, **ollama},
        "auth": {
            "token_minutes": settings.ACCESS_TOKEN_MINUTES,
            "demo_mode": settings.SEED_DEMO_USERS,
            "jwt_secret_from_env": bool(settings.JWT_SECRET),
            "lora_gateway_key_set": bool(settings.LORA_GATEWAY_KEY),
            "cors_origins": settings.CORS_ORIGINS,
            # Counts and booleans only. Never a secret, a key, a code or a user name.
            "mfa": {"mfa_key_configured": bool(settings.MFA_ENCRYPTION_KEYS),
                    "enrolled_accounts": db.query(MfaCredential).filter(MfaCredential.status == "ACTIVE").count(),
                    "pending_enrolments": db.query(MfaCredential).filter(MfaCredential.status == "PENDING").count(),
                    "privileged_accounts_without_mfa": db.query(User).filter(User.role.in_(list(PRIVILEGED_ROLES)), User.is_active.is_(True))
                    .filter(~User.id.in_(db.query(MfaCredential.user_id).filter(MfaCredential.status == "ACTIVE"))).count()},
        },
        "storage": {"uploads_mb": _dir_size_mb(settings.UPLOAD_DIR), "flood_images_dir_exists": settings.FLOOD_IMG_DIR.exists()},
        "warnings": warnings,
    }
