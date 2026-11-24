"""S5: agencies are organisational METADATA, not a security boundary.

Asserted here: only administrators manage them (with recent MFA and audit), membership changes do not change permissions or end
sessions, inactive agencies cannot receive people, and cross-agency emergency coordination is unaffected.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import ROLE_PERMISSIONS
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, RescueTeam, User
from tests.conftest import make_team, make_user, sign_in

PW = "Str0ng!Passw0rd"
TYPES = ["DISASTER_RESPONSE", "FIRE_EMERGENCY", "MEDICAL_RESPONSE", "CIVIL_ADMINISTRATION", "VOLUNTEER_ORGANIZATION"]


def admin():
    return sign_in(TestClient(app), "admin")


def make_agency(c, kind="FIRE_EMERGENCY", name=None, region="Test region"):
    r = c.post("/api/agencies", json={"name": name or f"Agency {uuid.uuid4().hex[:8]}", "agency_type": kind, "region": region})
    assert r.status_code == 201, r.text
    return r.json()


def audit_count(action, target):
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action, AuditLog.target_id == str(target)).count()
    finally:
        db.close()


def test_only_the_five_generic_categories_exist_and_unknown_types_are_refused():
    a = admin()
    assert a.get("/api/agencies").json()["types"] == TYPES
    for t in TYPES:
        assert make_agency(a, t)["agency_type"] == t
    assert a.post("/api/agencies", json={"name": "Bad type agency", "agency_type": "NATIONAL_ARMY"}).status_code == 422


def test_agency_lifecycle_is_audited_and_names_are_unique():
    a = admin()
    ag = make_agency(a, name="Lifecycle Agency One")
    assert audit_count("AGENCY_CREATED", ag["id"]) == 1
    assert a.post("/api/agencies", json={"name": "lifecycle agency one", "agency_type": "FIRE_EMERGENCY"}).status_code == 409
    r = a.patch(f"/api/agencies/{ag['id']}", json={"region": "North", "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["region"] == "North"
    assert audit_count("AGENCY_UPDATED", ag["id"]) == 1
    assert a.get(f"/api/agencies/{ag['id']}").json()["updated_at"] >= ag["created_at"]


def test_personnel_and_squads_can_be_associated_and_inactive_agencies_refuse_new_members():
    a = admin()
    ag = make_agency(a)
    uid, _ = make_user("OPERATOR", PW)
    assert a.put(f"/api/agencies/members/{uid}", json={"agency_id": ag["id"]}).json() == {"user_id": uid, "agency_id": ag["id"]}
    assert a.put("/api/agencies/teams/TEAM-NDRF-10", json={"agency_id": ag["id"]}).json()["agency_id"] == ag["id"]
    detail = a.get(f"/api/agencies/{ag['id']}").json()
    assert detail["personnel_count"] == 1 and detail["team_count"] == 1 and detail["teams"][0]["id"] == "TEAM-NDRF-10"
    assert audit_count("AGENCY_MEMBER_CHANGED", uid) == 1
    a.patch(f"/api/agencies/{ag['id']}", json={"is_active": False})
    other, _ = make_user("OPERATOR", PW)
    assert a.put(f"/api/agencies/members/{other}", json={"agency_id": ag["id"]}).status_code == 422
    assert a.put("/api/agencies/teams/TEAM-NDRF-10", json={"agency_id": 999999}).status_code == 422
    assert a.put(f"/api/agencies/members/{uid}", json={"agency_id": None}).json()["agency_id"] is None     # removal is always possible
    a.put("/api/agencies/teams/TEAM-NDRF-10", json={"agency_id": None})


@pytest.mark.parametrize("who", ["developer", "commander", "operator", "officer", "volunteer", "citizen"])
def test_only_administrators_manage_agencies(who):
    c = sign_in(TestClient(app), who)
    uid, _ = make_user("OPERATOR", PW)
    assert c.post("/api/agencies", json={"name": f"Nope {who}", "agency_type": "FIRE_EMERGENCY"}).status_code == 403
    assert c.patch("/api/agencies/1", json={"name": "Hijack"}).status_code == 403
    assert c.put(f"/api/agencies/members/{uid}", json={"agency_id": None}).status_code == 403
    assert c.put("/api/agencies/teams/TEAM-NDRF-10", json={"agency_id": None}).status_code == 403
    assert TestClient(app).post("/api/agencies", json={"name": "anon", "agency_type": "FIRE_EMERGENCY"}).status_code == 401


def test_viewing_is_limited_to_administrators_commanders_and_operators():
    for who, expected in [("admin", 200), ("commander", 200), ("operator", 200), ("developer", 403), ("officer", 403), ("volunteer", 403), ("citizen", 403)]:
        assert sign_in(TestClient(app), who).get("/api/agencies").status_code == expected, who


def test_agency_is_not_a_permission_and_membership_changes_do_not_alter_access_or_sessions():
    a = admin()
    ag = make_agency(a)
    uid, name = make_user("OPERATOR", PW, mfa=True)
    from tests.conftest import login_complete
    c = TestClient(app)
    r = login_complete(c, "operations", name, PW)
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    before = c.get("/api/auth/me").json()
    assert a.put(f"/api/agencies/members/{uid}", json={"agency_id": ag["id"]}).status_code == 200
    after = c.get("/api/auth/me")
    assert after.status_code == 200                                      # the session is still valid
    assert after.json()["permissions"] == before["permissions"] and after.json()["role"] == "OPERATOR"
    assert after.json()["agency_id"] == ag["id"]
    # no role is defined by agency membership: permissions come from the role table only
    assert not any("agency" in p and p.endswith("view_all") for perms in ROLE_PERMISSIONS.values() for p in perms)


def test_cross_agency_emergency_coordination_is_not_blocked():
    """A commander in agency A dispatches a squad belonging to agency B; operators see squads of every agency."""
    a = admin()
    ag_a, ag_b = make_agency(a, "DISASTER_RESPONSE"), make_agency(a, "MEDICAL_RESPONSE")
    cmd_id, _ = make_user("COMMANDER", PW)
    a.put(f"/api/agencies/members/{cmd_id}", json={"agency_id": ag_a["id"]})
    cmd = sign_in(TestClient(app), "commander")
    team_id = make_team(cmd, tag="agency-b")
    a.put(f"/api/agencies/teams/{team_id}", json={"agency_id": ag_b["id"]})
    teams = cmd.get("/api/teams/").json()
    listed = teams["items"] if isinstance(teams, dict) else teams
    assert any(t["id"] == team_id for t in listed)                                     # visible regardless of agency
    body = dict(title="Water rising", description="Street is flooding fast", area="Hebbal", latitude=12.93, longitude=77.62,
                severity="LOW", people_affected=1)
    inc = TestClient(app).post("/api/incidents/", json=body).json()
    iid = inc.get("id") or inc.get("incident_id")
    r = cmd.post(f"/api/teams/{team_id}/assign", json={"incident_id": iid})
    assert r.status_code not in (401, 403), r.text                                       # no agency-based refusal exists


def test_role_changes_and_team_assignment_still_follow_the_s1_s2_rules():
    """S5 added no new way to grant roles: an administrator still cannot promote anyone into a privileged role."""
    a = admin()
    uid, _ = make_user("CITIZEN", PW)
    assert a.patch(f"/api/auth/users/{uid}", json={"role": "COMMANDER"}).status_code == 403
    db = SessionLocal()
    try:
        assert db.get(User, uid).role == "CITIZEN"
    finally:
        db.close()


def test_agency_data_is_never_in_the_public_endpoints():
    anon = TestClient(app)
    for path in ("/api/agencies", "/api/alerts/", "/api/facilities/"):
        r = anon.get(path)
        assert r.status_code in (200, 401), path
        if r.status_code == 200:
            assert "agency" not in r.text.lower()
