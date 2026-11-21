"""CAP 1.2 export, duplicate blocking, escalation and acknowledgement rules."""

import uuid
from datetime import timedelta
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Alert
from app.services.alerting import CAP_NS, ESCALATION_MINUTES, escalate_overdue, utcnow
from tests.conftest import sign_in

ops = sign_in(TestClient(app), "operator")
commander = sign_in(TestClient(app), "commander")
citizen = sign_in(TestClient(app), "citizen")
NS = {"c": CAP_NS}


def _issue(client=ops, severity="HIGH", lat=None, lon=None, title=None):
    n = uuid.uuid4().int % 1000
    body = {"title": title or f"Test alert {uuid.uuid4().hex[:8]}", "message": "Water rising on the main road",
            "severity": severity, "area": "Test ward",
            # spread test alerts about 11 km apart so they never count as duplicates of each other
            "latitude": lat if lat is not None else 11.6 + n * 0.0035, "longitude": lon if lon is not None else 76.0 + n * 0.002,
            "radius_km": 2.5}
    return client.post("/api/alerts/", json=body)


def test_cap_document_is_valid_and_complete():
    alert = _issue().json()
    r = ops.get(f"/api/alerts/{alert['id']}/cap")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/cap+xml")
    root = ET.fromstring(r.content)
    assert root.tag == f"{{{CAP_NS}}}alert"
    # element order required by the CAP 1.2 specification
    order = [c.tag.split("}")[1] for c in root]
    assert order == ["identifier", "sender", "sent", "status", "msgType", "scope", "info"]
    assert root.find("c:identifier", NS).text == alert["id"]
    assert root.find("c:status", NS).text == "Actual"
    assert root.find("c:msgType", NS).text == "Alert"
    info = root.find("c:info", NS)
    info_order = [c.tag.split("}")[1] for c in info]
    assert info_order == ["language", "category", "event", "urgency", "severity", "certainty", "senderName", "headline", "description", "area"]
    assert info.find("c:severity", NS).text == "Severe" and info.find("c:urgency", NS).text == "Immediate"
    circle = info.find("c:area/c:circle", NS).text
    coords, radius = circle.split(" ")
    assert len(coords.split(",")) == 2 and float(radius) == 2.5
    assert root.find("c:sent", NS).text.endswith("+00:00")


def test_sample_alerts_are_exported_as_exercise_and_resolved_ones_as_cancel():
    sample = ops.get("/api/alerts/ALT-2026-01/cap")
    root = ET.fromstring(sample.content)
    assert root.find("c:status", NS).text == "Exercise"
    assert "Not a real emergency" in root.find("c:note", NS).text
    alert = _issue().json()
    ops.post(f"/api/alerts/{alert['id']}/resolve")
    done = ET.fromstring(ops.get(f"/api/alerts/{alert['id']}/cap").content)
    assert done.find("c:msgType", NS).text == "Cancel"


def test_cap_is_public_and_404s_for_unknown_alert():
    alert = _issue().json()
    anon = TestClient(app)
    assert anon.get(f"/api/alerts/{alert['id']}/cap").status_code == 200
    assert anon.get("/api/alerts/NOPE/cap").status_code == 404


def test_duplicate_alert_is_blocked():
    first = _issue(lat=12.50, lon=76.50, severity="WARNING").json()
    # same place, same severity, different words
    near = _issue(lat=12.5030, lon=76.5030, severity="WARNING")
    assert near.status_code == 409 and first["id"] in near.json()["detail"]
    # identical title anywhere
    same_title = _issue(lat=13.9, lon=75.1, severity="HIGH", title=first["title"].upper())
    assert same_title.status_code == 409
    # different severity at the same place is a new alert
    assert _issue(lat=12.50, lon=76.50, severity="CRITICAL").status_code == 201
    # far away is a new alert
    assert _issue(lat=14.2, lon=75.9, severity="WARNING").status_code == 201


def test_resolving_frees_the_slot_for_a_new_alert():
    first = _issue(lat=13.40, lon=74.60, severity="HIGH").json()
    assert _issue(lat=13.40, lon=74.60, severity="HIGH").status_code == 409
    ops.post(f"/api/alerts/{first['id']}/resolve")
    assert _issue(lat=13.40, lon=74.60, severity="HIGH").status_code == 201


def test_public_seen_does_not_change_status_but_commander_ack_does():
    alert = _issue().json()
    seen = citizen.post(f"/api/alerts/{alert['id']}/acknowledge").json()
    assert seen["status"] == "ACTIVE" and seen["acknowledged_count"] == 1
    op_seen = ops.post(f"/api/alerts/{alert['id']}/acknowledge").json()
    assert op_seen["status"] == "ACTIVE" and op_seen["acknowledged_count"] == 2
    cmd = commander.post(f"/api/alerts/{alert['id']}/acknowledge").json()
    assert cmd["status"] == "ACKNOWLEDGED" and cmd["acknowledged_by"] == "commander"
    # still counted as in force, so the public keeps seeing it
    listing = TestClient(app).get("/api/alerts/").json()
    assert any(a["id"] == alert["id"] and a["status"] == "ACKNOWLEDGED" for a in listing["items"])


def test_escalation_levels_follow_the_waiting_time_and_commander_ack_stops_it():
    a = _issue(severity="CRITICAL").json()["id"]
    b = _issue(severity="CRITICAL").json()["id"]
    wait = ESCALATION_MINUTES["CRITICAL"]
    db = SessionLocal()
    try:
        for alert_id in (a, b):
            row = db.query(Alert).filter(Alert.id == alert_id).first()
            row.created_at = utcnow() - timedelta(minutes=wait * 2 + 1)
        db.commit()
    finally:
        db.close()
    commander.post(f"/api/alerts/{b}/acknowledge")  # b is acknowledged before the check runs
    db = SessionLocal()
    try:
        escalate_overdue(db)
        assert db.query(Alert).filter(Alert.id == a).first().escalation_level == 2
        assert db.query(Alert).filter(Alert.id == b).first().escalation_level == 0
        assert escalate_overdue(db) == 0  # idempotent
    finally:
        db.close()
    listing = ops.get("/api/alerts/").json()
    assert listing["escalated_count"] >= 1
    actions = [e["action"] for e in sign_in(TestClient(app), "admin").get("/api/auth/audit", params={"limit": 300}).json()["items"]]
    assert "ALERT_ESCALATED" in actions


def test_a_fresh_alert_is_not_escalated_and_info_never_is():
    fresh = _issue(severity="HIGH").json()
    info = _issue(severity="INFO").json()
    db = SessionLocal()
    try:
        row = db.query(Alert).filter(Alert.id == info["id"]).first()
        row.created_at = utcnow() - timedelta(days=2)
        db.commit()
        escalate_overdue(db)
        assert db.query(Alert).filter(Alert.id == fresh["id"]).first().escalation_level == 0
        assert db.query(Alert).filter(Alert.id == info["id"]).first().escalation_level == 0
    finally:
        db.close()


def test_only_operations_staff_can_issue_alerts():
    assert _issue(client=citizen).status_code == 403
    assert _issue(client=TestClient(app)).status_code == 401
    assert _issue(client=commander).status_code == 201


def test_sample_alerts_do_not_claim_invented_acknowledgements():
    items = {a["id"]: a for a in TestClient(app).get("/api/alerts/").json()["items"]}
    for alert_id in ("ALT-2026-01", "ALT-2026-02", "ALT-2026-03"):
        assert items[alert_id]["data_label"] == "SIMULATED"
        assert items[alert_id]["acknowledged_count"] == 0
