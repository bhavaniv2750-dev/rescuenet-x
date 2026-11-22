"""S1/S2: role changes and account deactivation must not leave stale elevated access.

S2 makes this stronger than S1: any change that affects what an account may do ends ALL of its sessions at once
(401, sign in again), and authorization still reads the user's current role and team from the database on every request.
"""

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident, User
from tests.conftest import PORTAL_FOR_ROLE, make_user, sign_in

PW = "Str0ng!Passw0rd"


def signed_in_user(role="OPERATOR", team_id=None):
    uid, name = make_user(role, PW, team_id=team_id)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return uid, name, c


@pytest.fixture
def staff_user():
    uid, name, c = signed_in_user()
    return sign_in(TestClient(app), "admin"), c, uid, name


def test_demoting_a_user_ends_their_sessions_at_once(staff_user):
    admin, c, uid, _ = staff_user
    assert c.get("/api/teams/").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "CITIZEN"}).status_code == 200
    assert c.get("/api/teams/").status_code == 401         # same token: the session is gone
    assert c.get("/api/volunteers/").status_code == 401


def test_admin_cannot_promote_so_promotion_never_reaches_stale_sessions():
    """Promotion into staff roles is disabled for administrators (see test_privileged_escalation.py)."""
    admin = sign_in(TestClient(app), "admin")
    uid, _, _ = signed_in_user("CITIZEN")
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "COMMANDER"}).status_code == 403


def test_deactivation_blocks_the_existing_token_immediately_and_blocks_sign_in(staff_user):
    admin, c, uid, name = staff_user
    assert c.get("/api/auth/me").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/incidents/").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).status_code == 403


def test_reactivation_is_explicit_and_does_not_revive_old_sessions(staff_user):
    admin, c, uid, name = staff_user
    admin.patch(f"/api/auth/users/{uid}", json={"is_active": False})
    admin.patch(f"/api/auth/users/{uid}", json={"is_active": True})
    assert c.get("/api/auth/me").status_code == 401         # the old session stays dead
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).status_code == 200


def test_authorization_reads_the_current_role_from_the_database_not_the_token(staff_user):
    """S1 rule, still true: even a still-valid session is judged by the role stored NOW. (The role is changed directly in
    the database here, bypassing the API's session revocation, to prove the check itself does not trust the token.)"""
    admin, c, uid, _ = staff_user
    assert c.get("/api/teams/").status_code == 200
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"role": "CITIZEN"}); db.commit(); db.close()
    assert c.get("/api/teams/").status_code == 403
    assert c.post("/api/agents/tasks/TASK-NOPE/approve", json={}).status_code == 403


def test_tokens_carry_no_role_or_permission_claims(staff_user):
    import jwt
    _, c, _, _ = staff_user
    claims = jwt.decode(c.headers["Authorization"][7:], options={"verify_signature": False})
    assert set(claims) == {"typ", "sub", "sid", "tv", "jti", "iat", "exp"}


def test_officer_team_reassignment_ends_sessions_and_moves_access():
    admin = sign_in(TestClient(app), "admin")
    team_a = [t["id"] for t in sign_in(TestClient(app), "commander").get("/api/teams/").json()["items"]][:2]
    uid, _, officer = signed_in_user("RESCUE_OFFICER", team_id=team_a[0])
    inc = TestClient(app).post("/api/incidents/", json=dict(title="Mission", description="Mission for officer team",
                               area="Hebbal", latitude=12.9, longitude=77.6, severity="LOW", people_affected=1)).json()
    db = SessionLocal(); db.query(Incident).filter(Incident.id == inc["id"]).update({"assigned_team_id": team_a[0]}); db.commit(); db.close()
    assert officer.get(f"/api/incidents/{inc['id']}").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"team_id": team_a[1]}).status_code == 200
    assert officer.get(f"/api/incidents/{inc['id']}").status_code == 401      # session ended by the team change


def test_an_administrator_cannot_disable_or_demote_their_own_account():
    admin = sign_in(TestClient(app), "admin")
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/auth/users/{me['id']}", json={"is_active": False}).status_code == 409
    assert admin.patch(f"/api/auth/users/{me['id']}", json={"role": "CITIZEN"}).status_code == 409


def test_role_change_and_session_revocation_are_audited(staff_user):
    admin, c, uid, _ = staff_user
    admin.patch(f"/api/auth/users/{uid}", json={"role": "VOLUNTEER"})
    actions = [e["action"] for e in admin.get("/api/auth/audit", params={"limit": 30}).json()["items"]]
    assert "USER_UPDATED" in actions and "SESSIONS_REVOKED_ALL" in actions
