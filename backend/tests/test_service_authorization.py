"""S1: authorization enforced in the services, independent of the route that calls them (defence in depth).

Even if a future route forgot its permission dependency, dispatching still needs dispatch.assign, commander approval
still needs dispatch.approve, and the AI supervisor / system roles can never dispatch.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident, RescueTeam
from app.services import incident_lifecycle as lifecycle
from app.services.dispatch import dispatch_incident_to_team
from tests.conftest import make_team, sign_in


def _incident(severity="LOW", people=1, status="VERIFIED"):
    c = TestClient(app)
    r = c.post("/api/incidents/", json=dict(title="Svc test", description="Service-level check", area="Hebbal", latitude=12.97,
                                            longitude=77.59, severity=severity, people_affected=people))
    assert r.status_code == 201
    db = SessionLocal()
    db.query(Incident).filter(Incident.id == r.json()["id"]).update({"status": status}); db.commit()
    return db, r.json()["id"]


@pytest.mark.parametrize("role", ["AGENT", "SYSTEM", "ADMIN", "DEVELOPER", "RESCUE_OFFICER", "CITIZEN", "VOLUNTEER", "nonsense", ""])
def test_roles_without_dispatch_assign_cannot_dispatch_through_the_service(role):
    team = make_team(sign_in(TestClient(app), "operator"))
    db, iid = _incident()
    inc = db.get(Incident, iid)
    with pytest.raises(HTTPException) as e:
        dispatch_incident_to_team(db, inc, team, actor="x", role=role)
    assert e.value.status_code == 403
    db.rollback()
    assert db.get(RescueTeam, team).status.upper() == "AVAILABLE"   # no team was claimed
    assert db.get(Incident, iid).assigned_team_id is None
    db.close()


@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN", "AGENT", "SYSTEM", "RESCUE_OFFICER"])
def test_only_a_commander_can_claim_approval_through_the_service(role):
    team = make_team(sign_in(TestClient(app), "operator"))
    db, iid = _incident(severity="CRITICAL", people=9, status="PENDING_APPROVAL")
    inc = db.get(Incident, iid)
    with pytest.raises(HTTPException) as e:
        dispatch_incident_to_team(db, inc, team, actor="x", role=role, commander_approved=True)
    assert e.value.status_code == 403
    db.rollback()
    assert db.get(Incident, iid).status != "DISPATCHED"
    db.close()


def test_commander_approval_through_the_service_still_works():
    team = make_team(sign_in(TestClient(app), "operator"))
    db, iid = _incident(severity="CRITICAL", people=9, status="PENDING_APPROVAL")
    dispatch_incident_to_team(db, db.get(Incident, iid), team, actor="cmd", role="COMMANDER", commander_approved=True)
    db.commit()
    assert db.get(Incident, iid).status == "DISPATCHED"
    db.close()


def test_operator_still_cannot_dispatch_a_gated_incident_without_approval():
    team = make_team(sign_in(TestClient(app), "operator"))
    db, iid = _incident(severity="CRITICAL", people=9, status="PENDING_APPROVAL")
    with pytest.raises(HTTPException) as e:
        dispatch_incident_to_team(db, db.get(Incident, iid), team, actor="op", role="OPERATOR")
    assert e.value.status_code == 409          # the P0 approval rule, unchanged
    db.rollback(); db.close()


@pytest.mark.parametrize("role", ["AGENT", "SYSTEM", "ADMIN", "RESCUE_OFFICER"])
def test_lifecycle_refuses_dispatched_for_roles_without_dispatch_assign(role):
    db, iid = _incident(status="QUEUED")
    with pytest.raises(HTTPException) as e:
        lifecycle.transition(db, db.get(Incident, iid), "DISPATCHED", actor="x", role=role)
    assert e.value.status_code == 403
    db.rollback(); db.close()


def test_lifecycle_refuses_forged_commander_approval_flag_from_an_operator():
    db, iid = _incident(severity="CRITICAL", people=9, status="PENDING_APPROVAL")
    with pytest.raises(HTTPException) as e:
        lifecycle.transition(db, db.get(Incident, iid), "DISPATCHED", actor="op", role="OPERATOR", approved_by_commander=True)
    assert e.value.status_code == 403
    db.rollback(); db.close()


def test_admin_cannot_dispatch_assign_or_approve_through_the_api_either():
    admin = sign_in(TestClient(app), "admin")
    team = make_team(sign_in(TestClient(app), "operator"))
    db, iid = _incident()
    db.close()
    assert admin.post(f"/api/teams/{team}/assign", json={"incident_id": iid}).status_code == 403
    assert admin.post("/api/agents/tasks/TASK-NOPE/approve", json={}).status_code == 403
    assert admin.post("/api/agents/supervisor/triage", json={}).status_code == 403
    assert admin.post("/api/alerts/", json={}).status_code == 403
    assert admin.post(f"/api/incidents/{iid}/state", json={"to_status": "VERIFIED"}).status_code == 403
    assert admin.patch(f"/api/incidents/{iid}", json={"severity": "CRITICAL"}).status_code == 403


def test_operator_cannot_lower_the_risk_of_a_gated_incident_but_commander_can():
    """P0 rule preserved with the new permission names."""
    db, iid = _incident(severity="CRITICAL", people=9, status="VERIFIED")
    db.close()
    op, cmd = sign_in(TestClient(app), "operator"), sign_in(TestClient(app), "commander")
    assert op.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1}).status_code == 403
    r = cmd.patch(f"/api/incidents/{iid}", json={"severity": "LOW", "people_affected": 1, "note": "Verified false alarm by phone"})
    assert r.status_code == 200
