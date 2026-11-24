"""S4: MFA interplay with password recovery, contact changes, administrator resets, break-glass recovery, host-level MFA reset,
sensitive-action re-authentication, the state machine and start-up safety."""

import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, AuthSession, Incident, MfaCredential, MfaRecoveryCode, RescueTeam, User
from app.services import auth_state as astate
from app.services import mfa as mfa_svc
from tests.conftest import (with_prod_admin, PORTAL_FOR_ROLE, _forget_replay, enroll_via_api, latest_dev_message, login_complete, make_team,
                            make_user, make_user_with_email, mfa_secret_of, sign_in, totp_code)

BACKEND = Path(__file__).resolve().parent.parent
PW = "Str0ng!Passw0rd"
NEW = "Brand-New!Passw0rd9"


def mfa_enabled(uid):
    db = SessionLocal()
    try:
        c = db.query(MfaCredential).filter(MfaCredential.user_id == uid).first()
        return c is not None and c.status == "ACTIVE"
    finally:
        db.close()


def password_step(name, role, password=PW):
    c = TestClient(app)
    return c, c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": password})


def full_client(role, **kw):
    uid, name = make_user(role, PW, mfa=True, **kw)
    c = TestClient(app)
    r = login_complete(c, PORTAL_FOR_ROLE[role], name, PW)
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c, uid, name


def age_mfa(uid, minutes):
    db = SessionLocal()
    db.query(AuthSession).filter(AuthSession.user_id == uid).update({"mfa_at": mfa_svc.now() - timedelta(minutes=minutes)})
    db.commit(); db.close()


# ================================================================ recovery paths never remove MFA

def test_password_reset_by_email_keeps_mfa_and_the_next_login_still_needs_a_second_factor():
    uid, name, _ = make_user_with_email("OPERATOR", verified=True, changed_hours_ago=48, mfa=True)
    TestClient(app).post("/api/auth/password/forgot", json={"identifier": name})
    token = re.search(r"\?reset=([A-Za-z0-9_\-]+)", latest_dev_message(uid, "PASSWORD_RESET").body).group(1)
    assert TestClient(app).post("/api/auth/password/reset", json={"token": token, "new_password": NEW}).status_code == 200
    assert mfa_enabled(uid)
    c, r = password_step(name, "OPERATOR", NEW)
    assert r.json()["status"] == "mfa_required" and "access_token" not in r.text            # the reset granted no session and no shortcut
    full = login_complete(TestClient(app), "operations", name, NEW)
    assert full.status_code == 200 and full.json()["user"]["auth_state"] == "AUTHENTICATED"


def test_a_reset_of_an_unenrolled_staff_account_still_leads_to_mandatory_enrolment():
    uid, name, _ = make_user_with_email("COMMANDER", verified=True, changed_hours_ago=48, mfa=False)
    TestClient(app).post("/api/auth/password/forgot", json={"identifier": name})
    token = re.search(r"\?reset=([A-Za-z0-9_\-]+)", latest_dev_message(uid, "PASSWORD_RESET").body).group(1)
    TestClient(app).post("/api/auth/password/reset", json={"token": token, "new_password": NEW})
    c, r = password_step(name, "COMMANDER", NEW)
    assert r.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"


def test_email_verification_does_not_replace_mfa():
    uid, name, email = make_user_with_email("OPERATOR", verified=True, mfa=False)         # a verified mailbox, no MFA
    c, r = password_step(name, "OPERATOR")
    assert r.json()["user"]["email_verified"] is True and r.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.get("/api/teams/").status_code == 403


def test_contact_changes_do_not_remove_mfa_and_need_a_recent_factor():
    c, uid, name = full_client("OPERATOR")
    ok = c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "moved@example.org"})
    assert ok.status_code == 200 and mfa_enabled(uid)
    age_mfa(uid, 60)
    stale = c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "again@example.org"})
    assert stale.status_code == 403 and stale.headers["x-mfa-reauth-required"] == "true"
    assert mfa_enabled(uid)


def test_administrator_reset_of_a_public_accounts_password_keeps_that_accounts_mfa():
    uid, name = make_user("CITIZEN", PW, mfa=True)
    admin = sign_in(TestClient(app), "admin")
    assert admin.patch(f"/api/auth/users/{uid}", json={"new_password": "Admin!Chosen-pw1"}).status_code == 200
    assert mfa_enabled(uid)
    c, r = password_step(name, "CITIZEN", "Admin!Chosen-pw1")
    assert r.json()["status"] == "mfa_required"


def cli(*args):
    return subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), *args], cwd=BACKEND, env=dict(os.environ),
                          capture_output=True, text=True)


def temp_of(out):
    return out.split("shown once, not stored anywhere in clear): ")[1].splitlines()[0].strip()


def test_break_glass_password_recovery_does_not_remove_mfa_or_skip_the_challenge():
    uid, name = make_user("COMMANDER", PW, mfa=True)
    r = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert r.returncode == 0 and mfa_enabled(uid)
    c, step = password_step(name, "COMMANDER", temp_of(r.stdout))
    assert step.json()["status"] == "mfa_required"
    done = login_complete(c, "operations", name, temp_of(r.stdout))
    assert done.json()["user"]["auth_state"] == "PASSWORD_CHANGE_PENDING"                  # MFA first, then the forced change


def test_break_glass_created_staff_account_must_change_password_then_enrol_before_any_operations():
    name = "bg_" + os.urandom(4).hex()
    # S5: --email is mandatory and the account must verify it BEFORE enrolling MFA (password -> contact -> MFA -> access)
    r = cli("create", "--username", name, "--role", "COMMANDER", "--full-name", "Provisioned", "--email", f"{name}@example.org",
            "--reason", "new duty commander, ticket 7", "--i-am-authorized")
    c, step = password_step(name, "COMMANDER", temp_of(r.stdout))
    assert step.json()["user"]["auth_state"] == "PASSWORD_CHANGE_PENDING"
    c.headers["Authorization"] = f"Bearer {step.json()['access_token']}"
    ch = c.post("/api/auth/me/password", json={"current_password": temp_of(r.stdout), "new_password": NEW})
    assert ch.json()["user"]["auth_state"] == "CONTACT_VERIFICATION_PENDING"
    c.headers["Authorization"] = f"Bearer {ch.json()['access_token']}"
    assert c.get("/api/teams/").status_code == 403
    uid = ch.json()["user"]["id"]
    assert c.post("/api/auth/verify/email/request").status_code == 200
    code = re.search(r"code is (\d{6})", latest_dev_message(uid, "EMAIL_VERIFY").body).group(1)
    assert c.post("/api/auth/verify/email/confirm", json={"code": code}).status_code == 200
    assert c.get("/api/auth/me").json()["auth_state"] == "MFA_ENROLLMENT_PENDING"
    assert c.get("/api/teams/").status_code == 403
    enroll_via_api(c, NEW)
    assert c.get("/api/teams/").status_code == 200


# ================================================================ host-level MFA reset

def reset_mfa(name, *extra, identity="photo ID checked in person against the HR record, ticket 99"):
    return cli("reset-mfa", "--username", name, "--reason", "phone lost and replaced", "--identity-verified", identity, "--i-am-authorized", *extra)


def test_mfa_reset_requires_authorisation_reason_and_identity_reverification():
    uid, name = make_user("COMMANDER", PW, mfa=True)
    assert cli("reset-mfa", "--username", name, "--reason", "phone lost and replaced", "--identity-verified", "checked ID in person ok").returncode == 2
    assert cli("reset-mfa", "--username", name, "--reason", "x", "--identity-verified", "checked ID in person ok", "--i-am-authorized").returncode == 2
    assert cli("reset-mfa", "--username", name, "--reason", "phone lost and replaced", "--identity-verified", "short", "--i-am-authorized").returncode == 2
    assert mfa_enabled(uid)
    assert cli("reset-mfa", "--username", "no_such_person", "--reason", "phone lost and replaced",
               "--identity-verified", "checked ID in person ok", "--i-am-authorized").returncode == 1


def test_mfa_reset_backs_up_ends_sessions_audits_keeps_the_password_and_forces_re_enrolment():
    c, uid, name = full_client("COMMANDER")
    assert c.get("/api/teams/").status_code == 200
    r = reset_mfa(name)
    assert r.returncode == 0, r.stderr
    assert "Backup written and verified" in r.stdout
    assert c.get("/api/auth/me").status_code == 401                                         # every session ended
    assert not mfa_enabled(uid)
    db = SessionLocal()
    assert db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == uid).count() == 0
    a = db.query(AuditLog).filter(AuditLog.action == "ACCOUNT_CLI_MFA_RESET", AuditLog.target_id == str(uid)).one(); db.close()
    assert a.actor.startswith("cli:") and "phone lost" in a.details and "photo ID checked in person" in a.details
    # the password is unchanged, but there is no MFA any more: enrolment is mandatory before any operational access
    c2, step = password_step(name, "COMMANDER")
    assert step.status_code == 200 and step.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"
    c2.headers["Authorization"] = f"Bearer {step.json()['access_token']}"
    assert c2.get("/api/teams/").status_code == 403 and c2.post("/api/agents/tasks/X/approve", json={}).status_code == 403


def test_mfa_reset_never_changes_role_or_password_and_old_recovery_codes_die():
    uid, name = make_user("OPERATOR", PW, mfa=True)
    db = SessionLocal(); before = db.get(User, uid).password_hash; db.close()
    from app.services.mfa import generate_recovery_codes
    db = SessionLocal(); codes = generate_recovery_codes(db, db.get(User, uid)); db.commit(); db.close()
    assert reset_mfa(name).returncode == 0
    db = SessionLocal(); u = db.get(User, uid); assert (u.role, u.password_hash, u.is_active) == ("OPERATOR", before, True); db.close()
    c, step = password_step(name, "OPERATOR")
    assert "challenge_token" not in step.text                                               # nothing to challenge: credential and codes are gone


def test_password_and_mfa_recovery_cannot_be_combined_in_one_sitting_either_order():
    uid, name = make_user("COMMANDER", PW, mfa=True)
    first = cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert first.returncode == 0
    blocked = reset_mfa(name)
    assert blocked.returncode == 3 and "one sitting" in blocked.stderr
    assert mfa_enabled(uid)
    uid2, name2 = make_user("OPERATOR", PW, mfa=True)
    assert reset_mfa(name2).returncode == 0
    second = cli("reset-password", "--username", name2, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    assert second.returncode == 3 and "MFA was reset" in second.stderr


def test_a_documented_second_authoriser_can_override_the_combination_rule_and_it_is_recorded():
    uid, name = make_user("COMMANDER", PW, mfa=True)
    cli("reset-password", "--username", name, "--reason", "locked out, identity verified in person", "--i-am-authorized")
    same = reset_mfa(name, "--second-authorizer", os.environ.get("USER", "root"))
    assert same.returncode == 3                                                              # the same operator cannot "second" themselves
    ok = reset_mfa(name, "--second-authorizer", "Dr Second Operator")
    assert ok.returncode == 0
    db = SessionLocal()
    a = db.query(AuditLog).filter(AuditLog.action == "ACCOUNT_CLI_MFA_RESET", AuditLog.target_id == str(uid)).one(); db.close()
    assert "second authorizer: Dr Second Operator" in a.details


def test_email_password_reset_followed_by_cli_mfa_reset_is_also_refused():
    uid, name, _ = make_user_with_email("COMMANDER", verified=True, changed_hours_ago=48, mfa=True)
    TestClient(app).post("/api/auth/password/forgot", json={"identifier": name})
    token = re.search(r"\?reset=([A-Za-z0-9_\-]+)", latest_dev_message(uid, "PASSWORD_RESET").body).group(1)
    TestClient(app).post("/api/auth/password/reset", json={"token": token, "new_password": NEW})
    assert reset_mfa(name).returncode == 3 and mfa_enabled(uid)


def test_no_http_route_can_reset_mfa_for_a_privileged_user():
    paths = [p.lower() for p in app.openapi()["paths"]]
    assert not [p for p in paths if "reset-mfa" in p or "mfa/reset" in p or "mfa/remove" in p]
    uid, name = make_user("COMMANDER", PW, mfa=True)
    for who in ("admin", "developer", "commander", "operator"):
        c = sign_in(TestClient(app), who)
        for m, path in [("POST", f"/api/auth/users/{uid}/reset-mfa"), ("DELETE", f"/api/auth/users/{uid}/mfa"), ("POST", "/api/auth/mfa/disable")]:
            assert c.request(m, path, json={"current_password": PW}).status_code in (403, 404, 405), (who, path)
    assert mfa_enabled(uid)


def test_the_mfa_key_tool_reports_rotates_and_never_prints_secrets(tmp_path):
    uid, _ = make_user("CITIZEN", PW, mfa=True)
    secret = mfa_secret_of(uid)
    old_spec = settings.MFA_ENCRYPTION_KEYS
    from app.services import mfa_crypto
    new_spec = f"fresh:{mfa_crypto.new_key()},{old_spec}"
    env = {**os.environ, "MFA_ENCRYPTION_KEYS": new_spec}
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "mfa_keys.py"), "rotate"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "Backup written and verified" in r.stdout and "undecryptable: 0" in r.stdout
    assert secret not in r.stdout + r.stderr and new_spec.split(",")[0].split(":")[1] not in r.stdout
    db = SessionLocal(); row = db.query(MfaCredential).filter(MfaCredential.user_id == uid).one()
    assert mfa_crypto.key_id_of(row.secret_enc) == "fresh"; db.close()
    only_new = {**os.environ, "MFA_ENCRYPTION_KEYS": new_spec.split(",")[0]}
    chk = subprocess.run([sys.executable, str(BACKEND / "scripts" / "mfa_keys.py"), "check"], cwd=BACKEND, env=only_new, capture_output=True, text=True)
    assert chk.returncode == 0                                                                  # data was moved to the new key
    # restore the old encryption so the shared test database keeps working for later tests
    subprocess.run([sys.executable, str(BACKEND / "scripts" / "mfa_keys.py"), "rotate"], cwd=BACKEND,
                   env={**os.environ, "MFA_ENCRYPTION_KEYS": f"test:{old_spec.split(':', 1)[1]},fresh:{new_spec.split(',')[0].split(':')[1]}"}, capture_output=True, text=True)


def test_a_lost_key_makes_secrets_unreadable_without_leaking_and_reports_the_affected_accounts():
    uid, _ = make_user("CITIZEN", PW, mfa=True)
    from app.services import mfa_crypto
    other = {**os.environ, "MFA_ENCRYPTION_KEYS": "other:" + mfa_crypto.new_key()}
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "mfa_keys.py"), "check"], cwd=BACKEND, env=other, capture_output=True, text=True)
    assert r.returncode == 1 and "undecryptable" in r.stdout and "reset-mfa" in r.stdout


# ================================================================ sensitive-action re-authentication

SENSITIVE_PUBLIC_CHANGES = [
    ("POST", "/api/auth/me/password", {"current_password": PW, "new_password": "Changed!Passw0rd7"}),
    ("PATCH", "/api/auth/me/contact", {"current_password": PW, "email": "x@example.org"}),
    ("POST", "/api/auth/mfa/recovery-codes/regenerate", {}),
]


@pytest.mark.parametrize("method,path,body", SENSITIVE_PUBLIC_CHANGES)
def test_credential_and_mfa_changes_need_a_recent_second_factor(method, path, body):
    c, uid, name = full_client("OPERATOR")
    age_mfa(uid, settings.MFA_FRESH_MINUTES + 1)
    r = c.request(method, path, json=body)
    assert r.status_code == 403 and r.headers["x-mfa-reauth-required"] == "true"
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/reauth", json={"code": totp_code(mfa_secret_of(uid))}).status_code == 200
    assert c.request(method, path, json=body).status_code == 200


def test_privileged_account_management_needs_a_recent_second_factor():
    c, uid, name = full_client("ADMIN")
    target, tname = make_user("CITIZEN", PW)
    age_mfa(uid, 60)
    for m, p, b in [("POST", "/api/auth/users", {"role": "CITIZEN", "username": "zz_new_one", "full_name": "New One", "password": PW}),
                    ("PATCH", f"/api/auth/users/{target}", {"is_active": False}), ("POST", f"/api/auth/users/{target}/revoke-sessions", None)]:
        r = c.request(m, p, json=b)
        assert r.status_code == 403 and r.headers.get("x-mfa-reauth-required") == "true", (m, p)
    _forget_replay(uid)
    c.post("/api/auth/mfa/reauth", json={"code": totp_code(mfa_secret_of(uid))})
    assert c.patch(f"/api/auth/users/{target}", json={"is_active": False}).status_code == 200


def test_critical_alert_publication_needs_a_very_recent_factor_but_other_alerts_do_not():
    c, uid, name = full_client("COMMANDER")
    age_mfa(uid, settings.MFA_APPROVAL_FRESH_MINUTES + 1)
    body = dict(title="Dam release", message="Water release expected within the hour", severity="CRITICAL", area="Bellandur",
                latitude=11.9, longitude=76.4, radius_km=2.0)
    r = c.post("/api/alerts/", json=body)
    assert r.status_code == 403 and r.headers["x-mfa-reauth-required"] == "true"
    info = c.post("/api/alerts/", json={**body, "severity": "INFO", "title": "Drain works", "latitude": 11.95, "longitude": 76.45})
    assert info.status_code == 201                                                          # not critical: unchanged behaviour
    _forget_replay(uid)
    c.post("/api/auth/mfa/reauth", json={"code": totp_code(mfa_secret_of(uid))})
    assert c.post("/api/alerts/", json={**body, "latitude": 12.1, "longitude": 76.7}).status_code == 201


def gated_incident():
    op = sign_in(TestClient(app), "operator")
    inc = TestClient(app).post("/api/incidents/", json=dict(title="Trapped family", description="Nine people on a roof", area="Hebbal",
                               latitude=13.03, longitude=77.59, severity="CRITICAL", people_affected=9)).json()["id"]
    op.post(f"/api/incidents/{inc}/state", json={"to_status": "VERIFIED"})
    team = make_team(op, lat=13.031, lon=77.591)
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("offline")):
        task = op.post("/api/agents/supervisor/triage", json={"task_type": "TRIAGE", "incident_id": inc}).json()
    return inc, task, team


def test_commander_approval_of_a_high_risk_dispatch_needs_a_recent_factor_and_p0_rules_still_hold():
    inc, task, team = gated_incident()
    c, uid, _ = full_client("COMMANDER")
    age_mfa(uid, settings.MFA_APPROVAL_FRESH_MINUTES + 1)
    stale = c.post(f"/api/agents/tasks/{task['id']}/approve", json={})
    assert stale.status_code == 403 and stale.headers["x-mfa-reauth-required"] == "true"
    db = SessionLocal()
    assert db.get(Incident, inc).status == "PENDING_APPROVAL" and db.get(Incident, inc).assigned_team_id is None   # nothing was dispatched
    db.close()
    # the P0 gate is untouched: an operator still cannot dispatch the gated incident
    op = sign_in(TestClient(app), "operator")
    assert op.post(f"/api/teams/{task.get('suggested_team_id') or team}/assign", json={"incident_id": inc}).status_code == 409
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/reauth", json={"code": totp_code(mfa_secret_of(uid))}).status_code == 200
    ok = c.post(f"/api/agents/tasks/{task['id']}/approve", json={})
    assert ok.status_code == 200
    db = SessionLocal(); assert db.get(Incident, inc).status == "DISPATCHED"; db.close()


def test_declining_a_plan_does_not_need_the_extra_factor_it_dispatches_nothing():
    inc, task, _ = gated_incident()
    c, uid, _ = full_client("COMMANDER")
    age_mfa(uid, 120)
    assert c.post(f"/api/agents/tasks/{task['id']}/decline", json={}).status_code == 200


def test_reauth_needs_a_valid_code_is_rate_limited_and_replay_protected(monkeypatch):
    c, uid, name = full_client("OPERATOR")
    assert c.post("/api/auth/mfa/reauth", json={"code": "000000"}).status_code == 401
    code = totp_code(mfa_secret_of(uid))
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/reauth", json={"code": code}).status_code == 200
    assert c.post("/api/auth/mfa/reauth", json={"code": code}).status_code == 401                # same code twice: replay
    monkeypatch.setattr(settings, "MFA_FAILS_PER_ACCOUNT_15MIN", 2)
    from app.services import rate_limit
    rate_limit.reset_all()
    got = [c.post("/api/auth/mfa/reauth", json={"code": "111111"}).status_code for _ in range(3)]
    assert got == [401, 401, 429]


def test_users_without_mfa_are_not_asked_for_a_factor_they_do_not_have():
    uid, name = make_user("CITIZEN", PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW})
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.post("/api/auth/me/password", json={"current_password": PW, "new_password": "Changed!Passw0rd7"}).status_code == 200


# ================================================================ state machine

def user_obj(role, must_change=False, verified=True):
    return User(username="x", full_name="x", role=role, password_hash="x", must_change_password=must_change,
                email_verified_at=mfa_svc.now() if verified else None)


def sess_obj(assurance):
    return AuthSession(id="s" * 32, user_id=1, created_at=mfa_svc.now(), last_used_at=mfa_svc.now(), expires_at=mfa_svc.now(),
                       idle_timeout_s=60, assurance=assurance)


@pytest.mark.parametrize("role,must_change,enabled,assurance,expected", [
    ("OPERATOR", False, False, "PASSWORD", astate.MFA_ENROLLMENT_PENDING),
    ("COMMANDER", False, False, "PASSWORD", astate.MFA_ENROLLMENT_PENDING),
    ("ADMIN", False, True, "PASSWORD", astate.MFA_CHALLENGE_PENDING),
    ("DEVELOPER", False, True, "MFA", astate.AUTHENTICATED),
    ("RESCUE_OFFICER", False, True, "MFA", astate.AUTHENTICATED),
    ("CITIZEN", False, False, "PASSWORD", astate.AUTHENTICATED),
    ("VOLUNTEER", False, True, "PASSWORD", astate.MFA_CHALLENGE_PENDING),     # opted in: a password-only session is not enough
    ("VOLUNTEER", False, True, "MFA", astate.AUTHENTICATED),
    ("OPERATOR", True, True, "MFA", astate.PASSWORD_CHANGE_PENDING),           # forced password change comes first
    ("OPERATOR", True, False, "PASSWORD", astate.PASSWORD_CHANGE_PENDING),
    ("CITIZEN", True, False, "PASSWORD", astate.PASSWORD_CHANGE_PENDING),
])
def test_state_machine_table(role, must_change, enabled, assurance, expected):
    assert astate.session_state(user_obj(role, must_change), sess_obj(assurance), enabled) == expected


def test_contact_verification_state_applies_only_when_the_policy_is_on(monkeypatch):
    u, s = user_obj("OPERATOR", verified=False), sess_obj("MFA")
    assert astate.session_state(u, s, True) == astate.AUTHENTICATED
    monkeypatch.setattr(settings, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", True)
    assert astate.session_state(u, s, True) == astate.CONTACT_VERIFICATION_PENDING
    assert astate.session_state(user_obj("OPERATOR", verified=True), s, True) == astate.AUTHENTICATED
    assert astate.session_state(user_obj("CITIZEN", verified=False), sess_obj("PASSWORD"), False) == astate.AUTHENTICATED   # public roles exempt


def test_contact_verification_pending_reaches_only_verification_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", True)
    c, uid, name = full_client("OPERATOR")
    assert c.get("/api/auth/me").json()["auth_state"] == "CONTACT_VERIFICATION_PENDING"
    assert c.get("/api/teams/").status_code == 403 and c.get("/api/teams/").headers["x-contact-verification-required"] == "true"
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"email": "o@example.org", "email_verified_at": mfa_svc.now()}); db.commit(); db.close()
    assert c.get("/api/teams/").status_code == 200


def test_allow_lists_are_exactly_what_the_documentation_says():
    assert astate.ALLOWED_PATHS[astate.PASSWORD_CHANGE_PENDING] == {"/api/auth/me", "/api/auth/logout", "/api/auth/logout-all", "/api/auth/me/password"}
    assert astate.ALLOWED_PATHS[astate.MFA_CHALLENGE_PENDING] == {"/api/auth/me", "/api/auth/logout", "/api/auth/logout-all"}
    enrol = astate.ALLOWED_PATHS[astate.MFA_ENROLLMENT_PENDING]
    assert "/api/auth/mfa/enroll/start" in enrol and "/api/auth/mfa/enroll/confirm" in enrol and not any("/teams" in p or "/incidents" in p for p in enrol)
    assert astate.path_allowed(astate.AUTHENTICATED, "/api/anything") and not astate.path_allowed(astate.MFA_ENROLLMENT_PENDING, "/api/teams/")


def test_revoked_and_expired_sessions_are_the_session_ended_state():
    c, uid, name = full_client("OPERATOR")
    assert c.get("/api/teams/").status_code == 200
    sign_in(TestClient(app), "admin").post(f"/api/auth/users/{uid}/revoke-sessions")
    assert c.get("/api/teams/").status_code == 401 and c.get("/api/auth/me").status_code == 401


def test_every_privileged_demo_role_reaches_operations_only_after_mfa():
    for role in ("admin", "developer", "commander", "operator", "officer"):
        c = sign_in(TestClient(app), role)
        assert c.get("/api/auth/me").json()["auth_state"] == "AUTHENTICATED"


# ================================================================ start-up safety and secrets hygiene

START = r"""
import json
try:
    import app.main
    print(json.dumps({"started": True}))
except Exception as e:
    print(json.dumps({"started": False, "error": type(e).__name__}))
"""


def boot(tmp_path, **env):
    base = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 's.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
            "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": "p" * 48}
    base.update(env)
    r = subprocess.run([sys.executable, "-c", START], cwd=BACKEND, env=base, capture_output=True, text=True)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"started": False, "error": r.stderr[-200:]}


def test_production_refuses_to_start_without_a_valid_mfa_encryption_key(tmp_path):
    from app.services import mfa_crypto
    assert boot(tmp_path, RESCUENET_ENV="production") == {"started": False, "error": "MfaKeyError"}
    assert boot(tmp_path) == {"started": False, "error": "MfaKeyError"}                                 # unset environment = production
    for bad in ("short", "k:" + "A" * 10, "k:" + "A" * 60, "!!!", "a:" + "A" * 43 + ",a:" + "B" * 43):
        assert boot(tmp_path, RESCUENET_ENV="production", MFA_ENCRYPTION_KEYS=bad)["started"] is False, bad
    assert boot(tmp_path, RESCUENET_ENV="production", MFA_ENCRYPTION_KEYS="prod:" + mfa_crypto.new_key()) == {"started": True}


def test_an_invalid_key_is_refused_even_in_development(tmp_path):
    assert boot(tmp_path, RESCUENET_ENV="development", MFA_ENCRYPTION_KEYS="nonsense")["started"] is False


def test_there_is_no_switch_that_turns_mfa_off_or_a_bypass_code_in_production(tmp_path):
    from app.services import mfa_crypto
    src = "\n".join(p.read_text() for p in (BACKEND / "app").rglob("*.py"))
    # (the audit action name "MFA_DISABLED" is a record of a user turning OPTIONAL mfa off; it is not a setting)
    assert not re.search(r"(getenv\(|settings\.|environ\[)\s*[\"']?MFA_(DISABLED|ENFORCEMENT|BYPASS|OFF|SKIP)", src) and "bypass_code" not in src.lower()
    script = r"""
import json
from fastapi.testclient import TestClient
from app.db.init_db import init_db
init_db()
from app.main import app
c = TestClient(app)
r = c.post("/api/auth/login", json={"portal": "admin", "username": "admin", "password": "Adm1n!Pass-for-test"})
h = {"Authorization": "Bearer " + r.json()["access_token"]}
print(json.dumps({"state": r.json()["user"]["auth_state"], "teams": c.get("/api/teams/", headers=h).status_code}))
"""
    env = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'p.db'}", "UPLOAD_DIR": str(tmp_path / "up"), "BACKUP_DIR": str(tmp_path / "bk"),
           "JWT_SECRET": "p" * 48, "RESCUENET_ENV": "production",
           "MFA_ENCRYPTION_KEYS": "prod:" + mfa_crypto.new_key(), "MFA_ENFORCEMENT": "off", "MFA_DISABLED": "true", "MFA_BYPASS": "1",
           "PRIVILEGED_REQUIRE_VERIFIED_EMAIL": "false"}   # S5: production default is "true" (contact step first); off here to test the MFA step
    out = subprocess.run([sys.executable, "-c", with_prod_admin(script)], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"state": "MFA_ENROLLMENT_PENDING", "teams": 403}


def test_no_secret_reaches_diagnostics_audit_logs_or_the_dev_outbox(caplog, capfd):
    import logging
    caplog.set_level(logging.DEBUG)
    uid, name = make_user("OPERATOR", PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW})
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    started = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).json()
    secret = started["secret"]
    conf = c.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(secret)}).json()
    codes = conf["recovery_codes"]
    secrets_seen = [secret, *codes, settings.MFA_ENCRYPTION_KEYS.split(":", 1)[1].split(",")[0]]
    diag = sign_in(TestClient(app), "developer").get("/api/diagnostics/").text
    dev_outbox = TestClient(app).get("/api/dev/outbox").text
    db = SessionLocal()
    audit = " ".join(f"{a.actor} {a.action} {a.target_id} {a.details}" for a in db.query(AuditLog).all())
    enc = db.query(MfaCredential).filter(MfaCredential.user_id == uid).one().secret_enc; db.close()
    out, err = capfd.readouterr()
    haystack = "\n".join([diag, dev_outbox, audit, caplog.text, out, err, c.get("/api/auth/me").text, c.get("/api/auth/mfa/status").text,
                          sign_in(TestClient(app), "admin").get("/api/auth/users").text])
    for item in secrets_seen + [enc]:
        assert item and item not in haystack, "a TOTP secret, recovery code or key leaked"
    assert "otpauth://" not in haystack


def test_diagnostics_reports_only_counts_of_mfa_enrolment():
    d = sign_in(TestClient(app), "developer").get("/api/diagnostics/").json()
    mfa = d["auth"]["mfa"]
    assert set(mfa) == {"mfa_key_configured", "enrolled_accounts", "pending_enrolments", "privileged_accounts_without_mfa"}
    assert all(isinstance(v, (int, bool)) for v in mfa.values())
    text = json.dumps(d).lower()
    for forbidden in ("secret_enc", "otpauth", "recovery_code", "mfa_secret", settings.MFA_ENCRYPTION_KEYS.split(":", 1)[1].split(",")[0].lower()):
        assert forbidden not in text


def test_emergency_upload_restrictions_do_not_depend_on_the_rate_limit_store(monkeypatch):
    """With the limiter store down emergency endpoints fail OPEN, but size, type, decoding, storage and per-client caps are
    enforced independently in the media layer."""
    import io
    from PIL import Image
    from sqlalchemy.exc import OperationalError
    from app.services import rate_limit

    def boom(*a, **k):
        raise OperationalError("select", {}, Exception("database is locked"))
    monkeypatch.setattr(rate_limit, "SessionLocal", boom)
    g = TestClient(app)

    def png():
        b = io.BytesIO(); Image.new("RGB", (16, 16), (1, 2, 3)).save(b, format="PNG"); return b.getvalue()
    assert g.post("/api/incidents/upload-image", files={"file": ("a.png", png(), "image/png")}).status_code == 201      # fails open
    big = b"\xff\xd8\xff" + b"0" * (settings.MAX_IMAGE_BYTES + 10)
    assert g.post("/api/incidents/upload-image", files={"file": ("big.jpg", big, "image/jpeg")}).status_code == 400       # size cap
    assert g.post("/api/incidents/upload-image", files={"file": ("x.png", b"<html>not an image</html>", "image/png")}).status_code == 400   # decoding
    monkeypatch.setattr(settings, "UPLOAD_QUOTA_MB", 0)
    assert g.post("/api/incidents/upload-image", files={"file": ("a.png", png(), "image/png")}).status_code == 400        # storage quota
    monkeypatch.setattr(settings, "UPLOAD_QUOTA_MB", 2048)
    monkeypatch.setattr(settings, "MAX_UNATTACHED_UPLOADS_PER_CLIENT", 1)
    # g already has one waiting upload from above, so the per-client cap now refuses another (limiter store still down)
    assert g.post("/api/incidents/upload-image", files={"file": ("p2.png", png(), "image/png")}).status_code == 400
    assert g.post("/api/public/reports", json=dict(title="Water rising", description="Street is flooding fast", area="Hebbal",
                                                  latitude=13.0, longitude=77.6, severity="LOW", people_affected=1)).status_code == 201
