"""S1: role changes and account deactivation must not leave stale elevated access.

What is enforceable now: every request re-reads the user (role, team, active flag) from the database; the role claim
inside a token is never used for authorization. So a demotion, reassignment or deactivation takes effect on the very
next request, with the old token.

What is NOT yet enforceable (needs the S2 session system): an already-issued token for an account that is still active
stays usable until it expires (default 480 minutes), even after a password change. That limitation is pinned by
test_KNOWN_LIMITATION_* so S2 must consciously change it.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import User
from tests.conftest import sign_in

ADMIN_PW = "Str0ng!Passw0rd"


@pytest.fixture
def staff_user():
    """A throw-away OPERATOR created through the admin API, signed in with a real token."""
    admin = sign_in(TestClient(app), "admin")
    import uuid
    name = f"tmp_{uuid.uuid4().hex[:8]}"
    r = admin.post("/api/auth/users", json=dict(role="OPERATOR", username=name, full_name="Temp Operator", password=ADMIN_PW))
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    c = TestClient(app)
    login = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": ADMIN_PW})
    assert login.status_code == 200
    token = login.json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return admin, c, uid, token


def test_demoting_a_user_takes_effect_on_the_next_request(staff_user):
    admin, c, uid, _ = staff_user
    assert c.get("/api/teams/").status_code == 200
    assert c.get("/api/volunteers/").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "CITIZEN"}).status_code == 200
    assert c.get("/api/teams/").status_code == 403          # same token, new role
    assert c.get("/api/volunteers/").status_code == 403
    assert c.post("/api/alerts/", json={}).status_code == 403


def test_changing_to_admin_removes_operational_rights_immediately(staff_user):
    admin, c, uid, _ = staff_user
    assert c.get("/api/incidents/").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "ADMIN"}).status_code == 200
    assert c.get("/api/incidents/").status_code == 403
    assert c.get("/api/auth/users").status_code == 200       # gained identity management, nothing operational


def test_promoting_grants_new_rights_without_a_new_token(staff_user):
    admin, c, uid, _ = staff_user
    assert c.post("/api/agents/tasks/TASK-NOPE/approve", json={}).status_code == 403
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "COMMANDER"}).status_code == 200
    assert c.post("/api/agents/tasks/TASK-NOPE/approve", json={}).status_code == 404   # now allowed through to the handler


def test_deactivation_blocks_the_existing_token_immediately(staff_user):
    admin, c, uid, _ = staff_user
    assert c.get("/api/auth/me").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"is_active": False}).status_code == 200
    r = c.get("/api/auth/me")
    assert r.status_code == 401
    assert c.get("/api/incidents/").status_code == 401
    # and the person cannot simply sign in again
    name = SessionLocal().query(User).filter(User.id == uid).one().username
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": ADMIN_PW}).status_code in (401, 403)


def test_reactivation_is_explicit(staff_user):
    admin, c, uid, _ = staff_user
    admin.patch(f"/api/auth/users/{uid}", json={"is_active": False})
    assert c.get("/api/auth/me").status_code == 401
    admin.patch(f"/api/auth/users/{uid}", json={"is_active": True})
    assert c.get("/api/auth/me").status_code == 200


def test_the_role_claim_inside_a_token_is_never_trusted(staff_user):
    """A token minted with a higher role in its claims still only carries the user's CURRENT database role."""
    admin, c, uid, _ = staff_user
    forged_claim = create_access_token(uid, "COMMANDER")   # signed by the server, but the user is an OPERATOR
    r = TestClient(app).post("/api/agents/tasks/TASK-NOPE/approve", json={}, headers={"Authorization": f"Bearer {forged_claim}"})
    assert r.status_code == 403
    adm = TestClient(app).get("/api/auth/users", headers={"Authorization": f"Bearer {create_access_token(uid, 'ADMIN')}"})
    assert adm.status_code == 403


def test_officer_team_reassignment_moves_access_immediately():
    admin = sign_in(TestClient(app), "admin")
    db = SessionLocal()
    original = db.query(User).filter(User.username == "officer").one().team_id
    uid = db.query(User).filter(User.username == "officer").one().id
    db.close()
    inc = TestClient(app).post("/api/incidents/", json=dict(title="Mission", description="Mission for officer team",
                               area="Hebbal", latitude=12.9, longitude=77.6, severity="LOW", people_affected=1)).json()
    db = SessionLocal()
    from app.models.entities import Incident
    db.query(Incident).filter(Incident.id == inc["id"]).update({"assigned_team_id": original}); db.commit(); db.close()
    officer = sign_in(TestClient(app), "officer")
    try:
        assert officer.get(f"/api/incidents/{inc['id']}").status_code == 200
        other = [t["id"] for t in sign_in(TestClient(app), "commander").get("/api/teams/").json()["items"] if t["id"] != original][0]
        assert admin.patch(f"/api/auth/users/{uid}", json={"team_id": other}).status_code == 200
        assert officer.get(f"/api/incidents/{inc['id']}").status_code == 404      # same token, new team
    finally:
        admin.patch(f"/api/auth/users/{uid}", json={"team_id": original})


def test_an_administrator_cannot_disable_or_demote_their_own_account():
    admin = sign_in(TestClient(app), "admin")
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/auth/users/{me['id']}", json={"is_active": False}).status_code == 409
    assert admin.patch(f"/api/auth/users/{me['id']}", json={"role": "OPERATOR"}).status_code == 409


def test_every_role_change_and_password_reset_is_audited(staff_user):
    admin, c, uid, _ = staff_user
    admin.patch(f"/api/auth/users/{uid}", json={"role": "VOLUNTEER", "new_password": "An0ther!Passw0rd"})
    actions = [e["action"] for e in admin.get("/api/auth/audit", params={"limit": 20}).json()["items"]]
    assert "USER_UPDATED" in actions and "USER_PASSWORD_RESET_BY_ADMIN" in actions


def test_KNOWN_LIMITATION_issued_token_survives_password_change_until_s2(staff_user):
    """Documents a limitation that S2 (sessions, token versioning) removes: there is no token revocation yet."""
    admin, c, uid, _ = staff_user
    admin.patch(f"/api/auth/users/{uid}", json={"new_password": "An0ther!Passw0rd"})
    assert c.get("/api/auth/me").status_code == 200       # TODAY: still valid. After S2 this must become 401.
