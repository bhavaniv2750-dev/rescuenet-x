"""S2: an administrator must not be able to obtain operational authority through account management.

Closed paths (all refused with 403 and audited): creating staff/admin/developer accounts with an admin-chosen password,
resetting the password of any such account, promoting any account into such a role, and the combination "reset a public
account's password, then promote it". Legitimate lock-out recovery is the separate host-level tool scripts/account_admin.py.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import PRIVILEGED_ROLES, PUBLIC_ROLES
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, User
from tests.conftest import PORTAL_FOR_ROLE, make_team, make_user, sign_in

BACKEND = Path(__file__).resolve().parent.parent
PW = "Str0ng!Passw0rd"
ATTACKER_PW = "Attack3r!Chosen-pw"


def admin():
    return sign_in(TestClient(app), "admin")


def can_login(name, password, role):
    r = TestClient(app).post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": password})
    return r.status_code == 200


def row(name):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == name).first()
        return None if u is None else (u.role, u.is_active, u.password_hash, u.token_version)
    finally:
        db.close()


def latest_audit(action):
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.id.desc()).first()
    finally:
        db.close()


def test_the_role_sets_used_by_the_guards_are_what_we_expect():
    assert set(PUBLIC_ROLES) == {"CITIZEN", "VOLUNTEER"}
    assert set(PRIVILEGED_ROLES) == {"ADMIN", "DEVELOPER", "COMMANDER", "OPERATOR", "RESCUE_OFFICER"}


@pytest.mark.parametrize("role", PRIVILEGED_ROLES)
def test_admin_cannot_create_privileged_accounts(role):
    import uuid
    name = f"esc_{uuid.uuid4().hex[:8]}"
    body = {"role": role, "username": name, "full_name": "Planted Account", "password": ATTACKER_PW}
    if role == "RESCUE_OFFICER":
        body["team_id"] = make_team(sign_in(TestClient(app), "operator"))
    r = admin().post("/api/auth/users", json=body)
    assert r.status_code == 403 and "invitation" in r.json()["detail"].lower()
    assert row(name) is None                                  # nothing was created
    assert latest_audit("ADMIN_PRIVILEGED_ACCOUNT_CREATE_DENIED") is not None


@pytest.mark.parametrize("role", PRIVILEGED_ROLES)
def test_admin_cannot_set_or_replace_a_privileged_accounts_password(role):
    uid, name = make_user(role, PW)
    before = row(name)
    r = admin().patch(f"/api/auth/users/{uid}", json={"new_password": ATTACKER_PW})
    assert r.status_code == 403
    assert row(name) == before                                # hash and token version untouched
    assert can_login(name, PW, role) and not can_login(name, ATTACKER_PW, role)
    assert latest_audit("ADMIN_PRIVILEGED_PASSWORD_RESET_DENIED") is not None


def test_admin_cannot_reset_another_admins_or_their_own_password_through_the_console():
    uid, name = make_user("ADMIN", PW)
    assert admin().patch(f"/api/auth/users/{uid}", json={"new_password": ATTACKER_PW}).status_code == 403
    me = admin().get("/api/auth/me").json()
    assert admin().patch(f"/api/auth/users/{me['id']}", json={"new_password": ATTACKER_PW}).status_code == 403


@pytest.mark.parametrize("target", PRIVILEGED_ROLES)
@pytest.mark.parametrize("start", ["CITIZEN", "VOLUNTEER"])
def test_admin_cannot_promote_a_public_account_into_a_privileged_role(start, target):
    uid, name = make_user(start, PW)
    body = {"role": target}
    if target == "RESCUE_OFFICER":
        body["team_id"] = make_team(sign_in(TestClient(app), "operator"))
    assert admin().patch(f"/api/auth/users/{uid}", json=body).status_code == 403
    assert row(name)[0] == start
    assert latest_audit("ADMIN_ROLE_PROMOTION_DENIED") is not None


def test_reset_then_promote_chain_does_not_work():
    """Reset a citizen's password (allowed, they are low-privilege), then try to make them an operator and sign in."""
    uid, name = make_user("CITIZEN", PW)
    a = admin()
    assert a.patch(f"/api/auth/users/{uid}", json={"new_password": ATTACKER_PW}).status_code == 200
    assert a.patch(f"/api/auth/users/{uid}", json={"role": "OPERATOR"}).status_code == 403
    assert a.patch(f"/api/auth/users/{uid}", json={"role": "COMMANDER", "new_password": ATTACKER_PW}).status_code == 403
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": ATTACKER_PW})
    assert r.status_code == 200 and r.json()["user"]["role"] == "CITIZEN"
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.post("/api/alerts/", json={}).status_code == 403
    assert c.get("/api/incidents/").status_code == 403


def test_after_every_attempt_the_administrator_still_cannot_dispatch_approve_triage_or_publish():
    a = admin()
    team = make_team(sign_in(TestClient(app), "operator"))
    inc = TestClient(app).post("/api/incidents/", json=dict(title="Esc test", description="Escalation test incident", area="Hebbal",
                               latitude=12.9, longitude=77.6, severity="LOW", people_affected=1)).json()["id"]
    assert a.post(f"/api/teams/{team}/assign", json={"incident_id": inc}).status_code == 403
    assert a.post("/api/agents/tasks/TASK-X/approve", json={}).status_code == 403
    assert a.post("/api/agents/supervisor/triage", json={}).status_code == 403
    assert a.post("/api/alerts/", json={}).status_code == 403
    assert a.get(f"/api/incidents/{inc}").status_code == 403


def test_admin_can_still_do_their_legitimate_identity_work():
    a = admin()
    import uuid
    name = f"cit_{uuid.uuid4().hex[:8]}"
    r = a.post("/api/auth/users", json={"role": "CITIZEN", "username": name, "full_name": "Legit Citizen", "password": PW})
    assert r.status_code == 201
    uid = r.json()["id"]
    assert a.patch(f"/api/auth/users/{uid}", json={"new_password": "Reset!Passw0rd1"}).status_code == 200
    assert a.patch(f"/api/auth/users/{uid}", json={"role": "VOLUNTEER"}).status_code == 200      # lateral, still public
    cuid, cname = make_user("COMMANDER", PW)
    assert a.patch(f"/api/auth/users/{cuid}", json={"is_active": False}).status_code == 200      # emergency containment works
    assert not can_login(cname, PW, "COMMANDER")
    assert a.patch(f"/api/auth/users/{cuid}", json={"role": "CITIZEN"}).status_code == 200      # demotion works
    assert a.post(f"/api/auth/users/{cuid}/revoke-sessions").status_code == 200


def test_privileged_owner_can_still_change_their_own_password():
    uid, name = make_user("OPERATOR", PW)
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    assert c.post("/api/auth/me/password", json={"current_password": PW, "new_password": "Own3r!Chosen-pw"}).status_code == 200
    assert can_login(name, "Own3r!Chosen-pw", "OPERATOR")


def test_developers_and_commanders_cannot_use_account_management_at_all():
    uid, _ = make_user("CITIZEN", PW)
    for who in ("developer", "commander", "operator", "officer"):
        c = sign_in(TestClient(app), who)
        assert c.patch(f"/api/auth/users/{uid}", json={"new_password": ATTACKER_PW}).status_code == 403
        assert c.post("/api/auth/users", json={"role": "CITIZEN", "username": "zzz_nope", "full_name": "No Way", "password": PW}).status_code == 403


# ---------------------------------------------------------------- the separately authorised recovery path

def cli(*args, extra_env=None):
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), *args], cwd=BACKEND, env=env, capture_output=True, text=True)


def test_cli_refuses_without_explicit_authorisation_and_reason():
    uid, name = make_user("OPERATOR", PW)
    assert cli("reset-password", "--username", name, "--reason", "locked out, verified in person").returncode == 2
    assert cli("reset-password", "--username", name, "--reason", "x", "--i-am-authorized").returncode == 2
    assert can_login(name, PW, "OPERATOR")


def test_cli_recovery_resets_password_ends_sessions_backs_up_and_audits():
    uid, name = make_user("OPERATOR", PW)
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).json()["access_token"]
    r = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert r.returncode == 0, r.stderr
    assert "Backup written and verified" in r.stdout
    new_pw = r.stdout.split("shown once, not stored anywhere in clear): ")[1].splitlines()[0].strip()
    assert new_pw and new_pw != PW
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401      # old session ended
    assert can_login(name, new_pw, "OPERATOR") and not can_login(name, PW, "OPERATOR")
    a = latest_audit("ACCOUNT_CLI_PASSWORD_RESET")
    assert a.actor.startswith("cli:") and "identity verified in person" in a.details and new_pw not in a.details
    assert "pbkdf2" not in r.stdout.lower()


def test_cli_can_provision_a_staff_account_with_a_random_password():
    import uuid
    name = f"cli_{uuid.uuid4().hex[:8]}"
    r = cli("create", "--username", name, "--role", "COMMANDER", "--full-name", "Provisioned Commander",
            "--reason", "new duty commander, ticket 42", "--i-am-authorized")
    assert r.returncode == 0, r.stderr
    pw = r.stdout.split("shown once, not stored anywhere in clear): ")[1].splitlines()[0].strip()
    assert can_login(name, pw, "COMMANDER")
    assert cli("create", "--username", name, "--role", "COMMANDER", "--full-name", "Dup", "--reason", "duplicate attempt",
               "--i-am-authorized").returncode == 1


def test_cli_rejects_unknown_user_and_officer_without_team():
    assert cli("reset-password", "--username", "no_such_user_x", "--reason", "testing refusal", "--i-am-authorized").returncode == 1
    assert cli("create", "--username", "o_noteam", "--role", "RESCUE_OFFICER", "--full-name", "No Team", "--reason",
               "testing refusal", "--i-am-authorized").returncode == 1
