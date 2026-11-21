"""Helper for writing audit log entries."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import AuditLog


def record_audit(
    db: Session,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[str] = None,
    role: str = "SYSTEM",
) -> AuditLog:
    """Add an audit entry to the current session. The caller commits."""
    entry = AuditLog(
        actor=actor or "system",
        role=role or "SYSTEM",
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details=details,
    )
    db.add(entry)
    return entry
