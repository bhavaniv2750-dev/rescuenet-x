"""Alert rules: Common Alerting Protocol 1.2 export, duplicate detection and escalation.

Alerts are shown inside this app and can be exported as CAP 1.2 XML. Nothing is sent by SMS,
e-mail or push, so "escalation" means flagging an alert for a commander, not messaging anyone.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.models.entities import Alert
from app.services.audit import record_audit

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

# CAP severity / urgency for each of our levels.
CAP_SEVERITY = {"CRITICAL": "Extreme", "HIGH": "Severe", "WARNING": "Moderate", "INFO": "Minor"}
CAP_URGENCY = {"CRITICAL": "Immediate", "HIGH": "Immediate", "WARNING": "Expected", "INFO": "Future"}

# Minutes an alert may wait for a commander before it is escalated (level 1, then level 2 after the same time again).
ESCALATION_MINUTES = {"CRITICAL": 10, "HIGH": 20, "WARNING": 60}
MAX_ESCALATION_LEVEL = 2

# Another alert counts as a duplicate when it is in force, has the same severity,
# is centred within this distance and was issued within this window.
DUPLICATE_RADIUS_KM = 1.0
DUPLICATE_WINDOW_MINUTES = 30

IN_FORCE = ("ACTIVE", "ACKNOWLEDGED")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # the database stores naive UTC


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def find_duplicate(db: Session, title: str, severity: str, lat: float, lon: float, now: Optional[datetime] = None) -> Optional[Alert]:
    """An alert already in force that makes the new one redundant, or None."""
    now = now or utcnow()
    since = now - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    for alert in db.query(Alert).filter(Alert.status.in_(IN_FORCE)).all():
        if _norm(alert.title) == _norm(title):
            return alert
        if (
            alert.severity == severity.upper()
            and alert.created_at is not None
            and alert.created_at >= since
            and _haversine_km(alert.latitude, alert.longitude, lat, lon) <= DUPLICATE_RADIUS_KM
        ):
            return alert
    return None


def escalate_overdue(db: Session, now: Optional[datetime] = None) -> int:
    """Raise the escalation level of alerts no commander has acknowledged in time. Returns how many changed."""
    now = now or utcnow()
    changed = 0
    for alert in db.query(Alert).filter(Alert.status == "ACTIVE").all():
        minutes = ESCALATION_MINUTES.get(alert.severity)
        if minutes is None or alert.created_at is None:
            continue
        waited = (now - alert.created_at).total_seconds() / 60.0
        level = min(int(waited // minutes), MAX_ESCALATION_LEVEL)
        if level > (alert.escalation_level or 0):
            alert.escalation_level = level
            alert.escalated_at = now
            record_audit(
                db, "alert-monitor", "ALERT_ESCALATED", "alert", alert.id,
                f"level {level}: not acknowledged by a commander after {minutes * level} minutes", role="SYSTEM",
            )
            changed += 1
    if changed:
        db.commit()
    return changed


def _sub(parent: ET.Element, tag: str, text: Optional[str] = None) -> ET.Element:
    el = ET.SubElement(parent, f"{{{CAP_NS}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _iso(dt: datetime) -> str:
    """CAP dates carry an explicit offset."""
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def build_cap_xml(alert: Alert, sender: str = "rescuenet.local") -> bytes:
    """CAP 1.2 document for one alert. Sample (SIMULATED) alerts are marked as an Exercise."""
    ET.register_namespace("", CAP_NS)
    root = ET.Element(f"{{{CAP_NS}}}alert")
    exercise = (alert.data_label or "SIMULATED") != "OBSERVED"
    resolved = alert.status == "RESOLVED"

    _sub(root, "identifier", alert.id)
    _sub(root, "sender", sender)
    _sub(root, "sent", _iso(alert.resolved_at if resolved and alert.resolved_at else alert.created_at))
    _sub(root, "status", "Exercise" if exercise else "Actual")
    _sub(root, "msgType", "Cancel" if resolved else "Alert")
    _sub(root, "scope", "Public")
    if exercise:
        _sub(root, "note", "Sample alert shipped with the RescueNet project. Not a real emergency.")

    info = _sub(root, "info")
    _sub(info, "language", "en-IN")
    _sub(info, "category", "Met")
    _sub(info, "event", alert.title)
    _sub(info, "urgency", CAP_URGENCY.get(alert.severity, "Unknown"))
    _sub(info, "severity", CAP_SEVERITY.get(alert.severity, "Unknown"))
    _sub(info, "certainty", "Likely")
    _sub(info, "senderName", "RescueNet Control Room")
    _sub(info, "headline", alert.title[:160])
    _sub(info, "description", alert.message)
    area = _sub(info, "area")
    _sub(area, "areaDesc", alert.area)
    # CAP circle: "latitude,longitude radius" with the radius in kilometres.
    _sub(area, "circle", f"{alert.latitude:.5f},{alert.longitude:.5f} {alert.radius_km:g}")

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
