"""Portals, roles and what each role may do."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEMO_PASSWORD, sign_in

PW = DEMO_PASSWORD


def fresh(username=None):
    c = TestClient(app)
    if username:
        sign_in(c, username)
    return c


def login(c, portal, username, password=PW):
    return c.post("/api/auth/login", json={"portal": portal, "username": username, "password": password})


def test_each_role_signs_in_only_through_its_own_portal():
    c = fresh()
    assert login(c, "admin", "admin").status_code == 200
    assert login(c, "operations", "commander").status_code == 200
    assert login(c, "operations", "officer").status_code == 200
    assert login(c, "public", "citizen").status_code == 200
    assert login(c, "public", "volunteer").status_code == 200
    # wrong portal
    assert login(c, "public", "admin").status_code == 403
    assert login(c, "admin", "commander").status_code == 403
    assert login(c, "operations", "citizen").status_code == 403
    assert login(c, "public", "officer").status_code == 403


def test_wrong_password_and_unknown_user_give_the_same_message():
    c = fresh()
    a = login(c, "admin", "admin", "nope-nope1")
    b = login(c, "admin", "ghost-user", "nope-nope1")
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_account_locks_after_repeated_failures():
    c = fresh()
    name = f"lock{uuid.uuid4().hex[:6]}"
    assert c.post("/api/auth/register", json={"role": "CITIZEN", "username": name, "full_name": "Lock Test",
                                               "password": "Strong#Pass1", "phone": "9999999999"}).status_code == 201
    for _ in range(5):
        assert login(c, "public", name, "wrong-pass1").status_code == 401
    assert login(c, "public", name, "Strong#Pass1").status_code == 429


def test_protected_routes_need_a_token_and_the_right_role():
    anon = fresh()
    assert anon.get("/api/incidents/").status_code == 401
    assert anon.get("/api/teams/").status_code == 401
    citizen = fresh("citizen")
    assert citizen.get("/api/incidents/").status_code == 403
    assert citizen.get("/api/auth/users").status_code == 403
    officer = fresh("officer")
    assert officer.post("/api/agents/supervisor/triage", json={"task_type": "TRIAGE"}).status_code == 403
    operator = fresh("operator")
    assert operator.get("/api/auth/audit").status_code == 403
    assert fresh("admin").get("/api/auth/audit").status_code == 200


def test_public_information_is_open_without_signing_in():
    anon = fresh()
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/alerts/").status_code == 200
    assert anon.get("/api/facilities/").status_code == 200
    assert anon.get("/api/flood/gauges").status_code == 200
    assert anon.get("/api/auth/portals").status_code == 200


def test_only_commanders_can_approve():
    for who in ("operator", "officer", "citizen", "volunteer"):
        r = fresh(who).post("/api/agents/tasks/TASK-801/approve")
        assert r.status_code == 403, who


def test_anyone_can_report_but_only_the_reporter_sees_it():
    body = {"title": "Water in my street", "description": "Knee deep outside", "area": "HSR Layout",
            "latitude": 12.91, "longitude": 77.64, "severity": "MODERATE", "people_affected": 2}
    anon = fresh()
    r = anon.post("/api/incidents/", json=body)
    assert r.status_code == 201 and r.json()["reporter_name"] is None

    me = fresh("citizen")
    mine = me.post("/api/incidents/", json=body).json()
    assert mine["reporter_name"] == "Citizen Reporter (Demo)"
    assert any(i["id"] == mine["id"] for i in me.get("/api/incidents/mine").json()["items"])
    assert me.get(f"/api/incidents/{mine['id']}").status_code == 200
    # another citizen cannot open it
    other = TestClient(app)
    reg = other.post("/api/auth/register", json={"role": "CITIZEN", "username": f"c{uuid.uuid4().hex[:6]}",
                     "full_name": "Other Citizen", "password": "Strong#Pass1", "phone": "8888888888"}).json()
    other.headers["Authorization"] = f"Bearer {reg['access_token']}"
    assert other.get(f"/api/incidents/{mine['id']}").status_code == 404
    assert other.get("/api/incidents/mine").json()["count"] == 0


def test_volunteer_signup_starts_unverified_and_needs_skills():
    c = TestClient(app)
    base = {"role": "VOLUNTEER", "username": f"v{uuid.uuid4().hex[:6]}", "full_name": "New Volunteer",
            "password": "Strong#Pass1", "phone": "7777777777"}
    assert c.post("/api/auth/register", json=base).status_code == 422
    r = c.post("/api/auth/register", json={**base, "skills": "First aid", "area": "Whitefield"})
    assert r.status_code == 201
    assert r.json()["user"]["volunteer_verified"] is False
    assert r.json()["user"]["role"] == "VOLUNTEER"


def test_signup_cannot_create_staff_accounts():
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"role": "ADMIN", "username": "sneaky1", "full_name": "Sneaky",
                                           "password": "Strong#Pass1", "phone": "6666666666"})
    assert r.status_code == 422


def test_weak_passwords_are_refused():
    c = TestClient(app)
    for pw in ("short1", "12345678", "onlyletters"):
        r = c.post("/api/auth/register", json={"role": "CITIZEN", "username": f"w{uuid.uuid4().hex[:6]}",
                   "full_name": "Weak Pass", "password": pw, "phone": "5555555555"})
        assert r.status_code == 422, pw


def test_rescue_officer_can_only_update_their_own_teams_missions():
    op = fresh("operator")
    body = {"title": "Officer scope test", "description": "Boat needed", "area": "Hebbal",
            "latitude": 13.03, "longitude": 77.59, "severity": "LOW", "people_affected": 1}
    inc = op.post("/api/incidents/", json=body).json()["id"]
    for to in ("VERIFIED",):
        assert op.post(f"/api/incidents/{inc}/state", json={"to_status": to}).status_code == 200
    officer = fresh("officer")
    me = officer.get("/api/auth/me").json()
    # not assigned yet
    assert officer.post(f"/api/incidents/{inc}/state", json={"to_status": "IN_TRANSIT"}).status_code == 403
    assert op.post(f"/api/teams/{me['team_id']}/assign", json={"incident_id": inc}).status_code in (200, 409)
    r = officer.post(f"/api/incidents/{inc}/state", json={"to_status": "VERIFIED"})
    assert r.status_code == 403  # officers cannot set non-field states


def test_admin_can_manage_public_accounts_but_not_lock_themselves_out():
    """S2: administrators manage citizen/volunteer accounts. Staff accounts are not admin-provisioned any more (see
    tests/test_privileged_escalation.py), so this uses a citizen account."""
    admin = fresh("admin")
    name = f"cit{uuid.uuid4().hex[:6]}"
    r = admin.post("/api/auth/users", json={"role": "CITIZEN", "username": name, "full_name": "New Citizen",
                                            "password": "Strong#Pass1"})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert login(TestClient(app), "public", name, "Strong#Pass1").status_code == 200
    assert admin.patch(f"/api/auth/users/{uid}", json={"is_active": False}).status_code == 200
    assert login(TestClient(app), "public", name, "Strong#Pass1").status_code == 403
    my_id = admin.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/auth/users/{my_id}", json={"is_active": False}).status_code == 409
    # staff accounts, officers included, can no longer be created by an administrator
    assert admin.post("/api/auth/users", json={"role": "RESCUE_OFFICER", "username": f"o{uuid.uuid4().hex[:6]}",
                      "full_name": "No Team", "password": "Strong#Pass1"}).status_code == 403


def test_changing_password_requires_the_current_one():
    c = TestClient(app)
    name = f"pw{uuid.uuid4().hex[:6]}"
    tok = c.post("/api/auth/register", json={"role": "CITIZEN", "username": name, "full_name": "Pw Change",
                 "password": "Strong#Pass1", "phone": "4444444444"}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    assert c.post("/api/auth/me/password", json={"current_password": "bad-bad-1", "new_password": "Newer#Pass2"}).status_code == 400
    assert c.post("/api/auth/me/password", json={"current_password": "Strong#Pass1", "new_password": "Newer#Pass2"}).status_code == 200
    assert login(TestClient(app), "public", name, "Newer#Pass2").status_code == 200


def test_login_events_are_in_the_audit_log():
    admin = fresh("admin")
    actions = {e["action"] for e in admin.get("/api/auth/audit", params={"limit": 200}).json()["items"]}
    assert "LOGIN" in actions


def test_diagnostics_is_admin_only_and_reports_warnings():
    assert fresh("commander").get("/api/diagnostics/").status_code == 403
    assert TestClient(app).get("/api/diagnostics/").status_code == 401
    body = fresh("admin").get("/api/diagnostics/").json()
    assert body["database"]["tables"]["users"] >= 6
    assert body["flood_model"]["loaded"] is True
    assert any("development-fixture (demo) account" in w for w in body["warnings"])   # S5: no shared demo password exists; fixtures are flagged instead
    assert "jwt_secret_from_env" in body["auth"] and "secret" not in str(body["auth"]).lower().replace("jwt_secret_from_env", "")


# ---- F1: the sign-in form no longer asks for a portal ("auto" derives it from the verified account)

def test_login_without_a_portal_signs_each_role_in_and_still_requires_the_password():
    for username in ("citizen", "volunteer"):
        r = TestClient(app).post("/api/auth/login", json={"username": username, "password": PW})
        assert r.status_code == 200, (username, r.text)
    for username in ("citizen", "commander", "admin"):
        bad = TestClient(app).post("/api/auth/login", json={"username": username, "password": "wrong-password-1"})
        assert bad.status_code == 401
        assert bad.json()["detail"] == "Wrong username or password"          # same generic answer, no portal or role hint


def test_login_auto_portal_leaves_privileged_accounts_behind_mfa():
    r = TestClient(app).post("/api/auth/login", json={"username": "commander", "password": PW, "portal": "auto"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "mfa_required" or body["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"
    assert body.get("user", {}).get("permissions", []) == []


def test_an_explicit_wrong_portal_is_still_refused():
    r = TestClient(app).post("/api/auth/login", json={"portal": "admin", "username": "citizen", "password": PW})
    assert r.status_code == 403 and "public" in r.json()["detail"]
