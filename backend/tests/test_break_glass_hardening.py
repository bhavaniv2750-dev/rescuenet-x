"""S3: host-level break-glass recovery is hardened. The temporary password forces a change at first sign-in, nothing
operational works until then, the temporary password cannot be kept, and recovery can never widen a role."""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, User
from tests.conftest import PORTAL_FOR_ROLE, enroll_via_api, make_team, make_user, sign_in

BACKEND = Path(__file__).resolve().parent.parent
PW = "Str0ng!Passw0rd"
NEW = "Chosen!By-Owner-9"


def cli(*args):
    return subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), *args], cwd=BACKEND, env=dict(os.environ),
                          capture_output=True, text=True)


def temp_password(out):
    return out.split("shown once, not stored anywhere in clear): ")[1].splitlines()[0].strip()


def recover(role="OPERATOR", **kw):
    uid, name = make_user(role, PW, **kw)
    r = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert r.returncode == 0, r.stderr
    return uid, name, temp_password(r.stdout), r


def login(name, pw, role):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": pw})
    if r.status_code == 200:
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c, r


OPERATIONAL = [("GET", "/api/incidents/"), ("GET", "/api/teams/"), ("GET", "/api/volunteers/"), ("GET", "/api/dashboard"),
               ("GET", "/api/records/"), ("GET", "/api/agents/tasks"), ("POST", "/api/alerts/"), ("POST", "/api/teams/T/assign"),
               ("GET", "/api/auth/sessions"), ("POST", "/api/auth/verify/email/request"), ("PATCH", "/api/auth/me/contact")]


def test_recovery_flags_the_account_and_the_temp_password_signs_in():
    uid, name, temp, r = recover()
    c, login_r = login(name, temp, "OPERATOR")
    assert login_r.status_code == 200 and login_r.json()["user"]["password_change_required"] is True
    me = c.get("/api/auth/me").json()
    assert me["password_change_required"] is True and me["permissions"] == []          # nothing operational is advertised


@pytest.mark.parametrize("method,path", OPERATIONAL)
def test_until_the_password_is_changed_every_operational_endpoint_is_refused(method, path):
    _, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    r = c.request(method, path, json={} if method != "GET" else None)
    assert r.status_code == 403 and r.headers.get("x-password-change-required") == "true"
    assert "temporary password" in r.json()["detail"]


def test_a_recovered_commander_cannot_approve_dispatch_until_the_password_is_changed():
    _, name, temp, _ = recover("COMMANDER")
    c, _ = login(name, temp, "COMMANDER")
    assert c.post("/api/agents/tasks/TASK-X/approve", json={}).status_code == 403          # blocked by the forced change, not a 404
    assert c.post("/api/agents/tasks/TASK-X/decline", json={}).status_code == 403


def test_the_only_things_that_work_are_profile_password_change_and_sign_out():
    _, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200


def test_changing_the_password_completes_recovery_and_restores_exactly_the_roles_permissions():
    _, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    r = c.post("/api/auth/me/password", json={"current_password": temp, "new_password": NEW})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = c.get("/api/auth/me", headers=h).json()
    assert me["password_change_required"] is False and me["role"] == "OPERATOR"
    # S4: an operator without MFA must ENROL before any operational access, even after the forced change
    assert me["auth_state"] == "MFA_ENROLLMENT_PENDING" and c.get("/api/teams/", headers=h).status_code == 403
    enroll_via_api(c, NEW, headers=h)
    assert c.get("/api/teams/", headers=h).status_code == 200                                   # operator powers are back...
    assert c.post("/api/agents/tasks/TASK-X/approve", json={}, headers=h).status_code == 403   # ...and no more than that
    assert c.get("/api/auth/users", headers=h).status_code == 403


def test_the_temporary_password_cannot_be_kept_or_reused():
    _, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    keep = c.post("/api/auth/me/password", json={"current_password": temp, "new_password": temp})
    assert keep.status_code == 422 and "different" in keep.json()["detail"]
    assert c.get("/api/teams/").status_code == 403                                              # still locked out
    assert c.post("/api/auth/me/password", json={"current_password": temp, "new_password": NEW}).status_code == 200
    assert login(name, temp, "OPERATOR")[1].status_code == 401                                  # the temp password is dead
    assert login(name, NEW, "OPERATOR")[1].status_code == 200


def test_a_second_recovery_issues_a_different_temporary_password_and_forces_a_change_again():
    uid, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    c.post("/api/auth/me/password", json={"current_password": temp, "new_password": NEW})
    r2 = cli("reset-password", "--username", name, "--reason", "locked out again, verified in person", "--i-am-authorized")
    temp2 = temp_password(r2.stdout)
    assert temp2 != temp and temp2 != NEW
    c2, lr = login(name, temp2, "OPERATOR")
    assert lr.json()["user"]["password_change_required"] is True and c2.get("/api/teams/").status_code == 403


def test_the_temporary_password_is_never_stored_in_plaintext_anywhere():
    uid, name, temp, r = recover("OPERATOR")
    db = SessionLocal()
    path = str(db.get_bind().url).replace("sqlite:///", "")
    db.close()
    raw = sqlite3.connect(path)
    for (table,) in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for row in raw.execute(f'SELECT * FROM "{table}"'):
            assert temp not in " ".join(str(v) for v in row), f"temporary password found in {table}"
    raw.close()
    h = raw = sqlite3.connect(path).execute("SELECT password_hash FROM users WHERE username=?", (name,)).fetchone()[0]
    assert h.startswith("pbkdf2") or "$" in h and temp not in h
    assert temp not in r.stderr and r.stdout.count(temp) == 1                                    # printed exactly once, to the operator


def test_cli_still_requires_host_authorisation_audits_and_backs_up():
    uid, name = make_user("OPERATOR", PW)
    assert cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person").returncode == 2
    assert cli("reset-password", "--username", name, "--reason", "x", "--i-am-authorized").returncode == 2
    r = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert "Backup written and verified" in r.stdout
    db = SessionLocal()
    a = db.query(AuditLog).filter(AuditLog.action == "ACCOUNT_CLI_PASSWORD_RESET", AuditLog.target_id == str(uid)).one()
    db.close()
    assert a.actor.startswith("cli:") and "identity verified in person" in a.details and temp_password(r.stdout) not in a.details


@pytest.mark.parametrize("role", ["CITIZEN", "VOLUNTEER", "OPERATOR", "COMMANDER", "RESCUE_OFFICER", "DEVELOPER", "ADMIN"])
def test_recovery_never_changes_the_role_team_or_active_flag(role):
    team = make_team(sign_in(TestClient(app), "operator")) if role == "RESCUE_OFFICER" else None
    uid, name = make_user(role, PW, team_id=team)
    db = SessionLocal(); before = db.get(User, uid); snapshot = (before.role, before.team_id, before.is_active); db.close()
    r = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert r.returncode == 0, r.stderr
    db = SessionLocal(); after = db.get(User, uid); assert (after.role, after.team_id, after.is_active) == snapshot; db.close()


def test_the_cli_cannot_be_used_to_create_a_privileged_account_without_going_through_the_flag():
    name = f"cli_{uuid.uuid4().hex[:8]}"
    r = cli("create", "--username", name, "--role", "COMMANDER", "--full-name", "Provisioned", "--reason", "new duty commander, ticket 7", "--i-am-authorized")
    temp = temp_password(r.stdout)
    c, lr = login(name, temp, "COMMANDER")
    assert lr.json()["user"]["password_change_required"] is True
    assert c.post("/api/agents/tasks/X/approve", json={}).status_code == 403


def test_administrator_reset_of_a_public_account_also_forces_the_owner_to_choose_their_own_password():
    uid, name = make_user("CITIZEN", PW)
    admin = sign_in(TestClient(app), "admin")
    assert admin.patch(f"/api/auth/users/{uid}", json={"new_password": "Admin!Chosen-pw1"}).status_code == 200
    c, lr = login(name, "Admin!Chosen-pw1", "CITIZEN")
    assert lr.json()["user"]["password_change_required"] is True
    assert c.get("/api/incidents/mine").status_code == 403
    assert c.post("/api/auth/me/password", json={"current_password": "Admin!Chosen-pw1", "new_password": NEW}).status_code == 200


def test_guest_emergency_reporting_is_unaffected_by_a_pending_forced_change():
    _, name, temp, _ = recover("OPERATOR")
    c, _ = login(name, temp, "OPERATOR")
    body = dict(title="Water rising", description="Street is flooding fast", area="Hebbal", latitude=13.0, longitude=77.6, severity="LOW", people_affected=1)
    assert c.post("/api/public/reports", json=body).status_code == 201
    assert TestClient(app).post("/api/public/reports", json=body).status_code == 201
