"""S5: invitation-based onboarding of privileged accounts and the activation sequence.

Sequence under test:  authorised invitation -> owner chooses password -> contact verification -> mandatory MFA -> successful
authentication -> workspace permissions. No privileged permission exists before the last step.
"""

import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import PRIVILEGED_ROLES, PUBLIC_ROLES
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Agency, AuditLog, Invitation, OneTimeToken, User
from app.services import provisioning as prov
from app.services import verification as ver
from tests.conftest import (enroll_via_api, latest_dev_message, login_complete, mfa_secret_of, sign_in, totp_code)

BACKEND = Path(__file__).resolve().parent.parent
PW = "Own3r!Chosen-pw"


def issue(role="OPERATOR", email=None, hours=None, agency_id=None, team_id=None):
    db = SessionLocal()
    try:
        inv, token = prov.issue_invitation(db, role=role, email=email or f"inv_{uuid.uuid4().hex[:8]}@example.org", actor="cli:test",
                                           reason="test invitation", agency_id=agency_id,
                                           team_id=team_id or ("TEAM-NDRF-10" if role == "RESCUE_OFFICER" else None), hours=hours)
        db.commit()
        return inv.id, token, inv.recipient_email
    finally:
        db.close()


def accept(token, username=None, password=PW, client=None, **extra):
    c = client or TestClient(app)
    body = {"token": token, "username": username or f"inv_{uuid.uuid4().hex[:8]}", "full_name": "Invited Person", "password": password, **extra}
    return c, c.post("/api/invitations/accept", json=body)


def authed(c, r):
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def row(inv_id):
    db = SessionLocal()
    try:
        i = db.get(Invitation, inv_id)
        db.expunge(i)
        return i
    finally:
        db.close()


# ------------------------------------------------------------------ issuing

def test_invitations_exist_for_privileged_roles_only():
    db = SessionLocal()
    try:
        for role in PUBLIC_ROLES:
            with pytest.raises(prov.InvitationError):
                prov.issue_invitation(db, role=role, email="x@example.org", actor="cli:t", reason="r")
        for role in PRIVILEGED_ROLES:
            if role == "RESCUE_OFFICER":
                continue
            _, token = prov.issue_invitation(db, role=role, email="y@example.org", actor="cli:t", reason="r")
            assert len(token) >= 40
        with pytest.raises(prov.InvitationError):            # an officer needs a real team
            prov.issue_invitation(db, role="RESCUE_OFFICER", email="y@example.org", actor="cli:t", reason="r")
        with pytest.raises(prov.InvitationError):
            prov.issue_invitation(db, role="OPERATOR", email="not-an-address", actor="cli:t", reason="r")
        for bad in (0, 169, -5):
            with pytest.raises(prov.InvitationError):
                prov.issue_invitation(db, role="OPERATOR", email="y@example.org", actor="cli:t", reason="r", hours=bad)
        db.rollback()
    finally:
        db.close()


def test_the_token_is_stored_only_as_a_hash_and_never_in_the_audit_log():
    inv_id, token, _ = issue()
    inv = row(inv_id)
    assert inv.token_hash == prov.token_hash(token) and token not in inv.token_hash and len(inv.token_hash) == 64
    db = SessionLocal()
    try:
        assert not any(token in (a.details or "") for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(50))
    finally:
        db.close()
    assert "#invite=" in prov.invitation_link(token) and "?invite" not in prov.invitation_link(token)   # fragment: never sent to a server


def test_no_web_endpoint_issues_an_invitation_even_for_an_administrator():
    a = sign_in(TestClient(app), "admin")
    for method, path in (("post", "/api/invitations"), ("post", "/api/invitations/"), ("put", "/api/invitations"),
                         ("post", "/api/invitations/issue"), ("post", "/api/invitations/create")):
        r = getattr(a, method)(path, json={"role": "ADMIN", "email": "me@example.org"})
        assert r.status_code in (404, 405, 422) and r.status_code != 201, (method, path, r.status_code)
    # and the old path stays closed: an administrator-chosen password for a staff account
    r = a.post("/api/auth/users", json={"role": "ADMIN", "username": "selfmade1", "full_name": "Self Made", "password": PW})
    assert r.status_code == 403


def test_the_cli_issues_a_link_once_stores_only_its_hash_and_audits():
    env = dict(os.environ)
    r = subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), "invite", "--email", "cli.person@example.org",
                        "--role", "OPERATOR", "--reason", "cli invitation test", "--i-am-authorized"],
                       cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    token = re.search(r"#invite=([A-Za-z0-9_\-]+)", r.stdout).group(1)
    db = SessionLocal()
    try:
        inv = db.query(Invitation).filter(Invitation.token_hash == prov.token_hash(token)).one()
        assert inv.created_by.startswith("cli:") and inv.role == "OPERATOR" and inv.recipient_email == "cli.person@example.org"
        assert db.query(AuditLog).filter(AuditLog.action == "INVITATION_ISSUED", AuditLog.target_id == str(inv.id)).count() == 1
    finally:
        db.close()
    refused = subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), "invite", "--email", "a@example.org",
                              "--role", "OPERATOR", "--reason", "no authorisation flag"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert refused.returncode == 2


# ------------------------------------------------------------------ inspect / accept

def test_inspect_shows_only_what_the_recipient_needs_and_unusable_tokens_look_identical():
    inv_id, token, email = issue("COMMANDER")
    c = TestClient(app)
    ok = c.post("/api/invitations/inspect", json={"token": token})
    assert ok.status_code == 200
    body = ok.json()
    assert body["role"] == "COMMANDER" and email not in str(body) and body["recipient"].endswith("@example.org") and "***" in body["recipient"]
    unknown = c.post("/api/invitations/inspect", json={"token": "x" * 43})
    assert unknown.status_code == 404
    # expired / revoked / used answer with the very same words
    exp_id, exp_token, _ = issue()
    db = SessionLocal(); db.query(Invitation).filter(Invitation.id == exp_id).update({"expires_at": prov._now() - timedelta(minutes=1)}); db.commit(); db.close()
    rev_id, rev_token, _ = issue()
    db = SessionLocal(); prov.revoke(db, db.get(Invitation, rev_id), "cli:t", "HOST_OPERATOR"); db.commit(); db.close()
    for t in (exp_token, rev_token):
        r = c.post("/api/invitations/inspect", json={"token": t})
        assert r.status_code == 404 and r.json() == unknown.json()


def test_acceptance_binds_role_agency_team_and_recipient_and_ignores_everything_else_in_the_request():
    db = SessionLocal()
    ag = Agency(name=f"Test agency {uuid.uuid4().hex[:6]}", agency_type="FIRE_EMERGENCY", created_at=prov._now(), updated_at=prov._now())
    db.add(ag); db.commit(); agency_id = ag.id; db.close()
    inv_id, token, email = issue("RESCUE_OFFICER", agency_id=agency_id)
    c, r = accept(token, role="ADMIN", email="attacker@example.org", team_id="TEAM-OTHER", agency_id=9999, is_active=True)
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert user["role"] == "RESCUE_OFFICER" and user["team_id"] == "TEAM-NDRF-10" and user["agency_id"] == agency_id
    assert user["email"] == email and user["email_verified"] is False
    inv = row(inv_id)
    assert inv.used_at is not None and inv.accepted_user_id == user["id"]


def test_a_new_account_has_no_permissions_and_no_operational_access_until_it_is_fully_activated():
    inv_id, token, email = issue("COMMANDER")
    c, r = accept(token)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["auth_state"] == "CONTACT_VERIFICATION_PENDING"
    assert body["user"]["permissions"] == [] and body["user"]["password_change_required"] is False
    authed(c, r)
    for path in ("/api/teams/", "/api/incidents/", "/api/agents/tasks", "/api/dashboard"):
        assert c.get(path).status_code == 403, path
    assert c.post("/api/agents/tasks/TASK-X/approve").status_code == 403            # not even the commander approval
    # step 1: contact verification (code goes to the INVITED address; development outbox holds it)
    assert c.post("/api/auth/verify/email/request").status_code == 200
    uid = body["user"]["id"]
    code = re.search(r"code is (\d{6})", latest_dev_message(uid, "EMAIL_VERIFY").body).group(1)
    assert c.post("/api/auth/verify/email/confirm", json={"code": code}).status_code == 200
    me = c.get("/api/auth/me").json()
    assert me["auth_state"] == "MFA_ENROLLMENT_PENDING" and me["permissions"] == []
    assert c.get("/api/teams/").status_code == 403
    # step 2: MFA enrolment
    secret, _codes = enroll_via_api(c, PW)
    # step 3: sign in again with the second factor -> authenticated, permissions appear
    username = me["username"]
    fresh = TestClient(app)
    out = fresh.post("/api/auth/login", json={"portal": "operations", "username": username, "password": PW})
    assert out.status_code == 200 and out.json()["status"] == "mfa_required"
    from tests.conftest import _forget_replay
    _forget_replay(uid)
    done = fresh.post("/api/auth/mfa/verify", json={"challenge_token": out.json()["challenge_token"], "code": totp_code(secret)})
    assert done.status_code == 200, done.text
    assert done.json()["user"]["auth_state"] == "AUTHENTICATED" and "dispatch.approve" in done.json()["user"]["permissions"]
    authed(fresh, done)
    assert fresh.get("/api/teams/").status_code == 200


def test_contact_verification_comes_before_mfa_enrolment_and_enrolment_is_not_reachable_early():
    _, token, _ = issue("OPERATOR")
    c, r = accept(token)
    authed(c, r)
    r2 = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW})
    assert r2.status_code == 403 and r2.headers.get("X-Auth-State") == "CONTACT_VERIFICATION_PENDING"


def test_a_token_works_exactly_once():
    inv_id, token, _ = issue()
    _, first = accept(token)
    _, second = accept(token)
    assert first.status_code == 201 and second.status_code == 404
    assert second.json()["detail"] == prov.INVALID


def test_expired_and_revoked_invitations_cannot_be_accepted():
    a, ta, _ = issue(); b, tb, _ = issue()
    db = SessionLocal()
    db.query(Invitation).filter(Invitation.id == a).update({"expires_at": prov._now() - timedelta(seconds=1)})
    prov.revoke(db, db.get(Invitation, b), "cli:t", "HOST_OPERATOR")
    db.commit(); db.close()
    assert accept(ta)[1].status_code == 404 and accept(tb)[1].status_code == 404


def test_lifetime_is_configurable_and_capped():
    inv_id, _, _ = issue(hours=1)
    assert timedelta(minutes=55) < row(inv_id).expires_at - prov._now() <= timedelta(hours=1, minutes=1)
    inv_id, _, _ = issue(hours=168)
    assert row(inv_id).expires_at - prov._now() > timedelta(hours=167)


def test_simultaneous_acceptance_creates_exactly_one_account():
    inv_id, token, _ = issue("OPERATOR")
    results, barrier = [], threading.Barrier(8)

    def go(i):
        c = TestClient(app)
        barrier.wait()
        results.append(c.post("/api/invitations/accept", json={"token": token, "username": f"race_{inv_id}_{i}", "full_name": "Racer",
                                                              "password": PW}).status_code)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert results.count(201) == 1, results
    assert all(s in (404, 201, 409, 429, 500) for s in results)
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.username.like(f"race_{inv_id}_%")).count() == 1
        assert row(inv_id).used_at is not None
    finally:
        db.close()


def test_a_taken_username_does_not_burn_the_invitation():
    inv_id, token, _ = issue()
    _, r = accept(token, username="admin")
    assert r.status_code == 409 and row(inv_id).used_at is None
    assert accept(token)[1].status_code == 201


def test_weak_passwords_are_refused_without_consuming_the_invitation():
    inv_id, token, _ = issue()
    assert accept(token, password="12345678")[1].status_code == 422
    assert accept(token, password="short")[1].status_code == 422
    assert row(inv_id).used_at is None


def test_acceptance_and_activation_are_audited_without_secrets():
    inv_id, token, _ = issue()
    _, r = accept(token, password=PW)
    uid = r.json()["user"]["id"]
    db = SessionLocal()
    try:
        actions = {a.action for a in db.query(AuditLog).filter(AuditLog.target_id.in_([str(inv_id), str(uid)]))}
        assert {"INVITATION_ISSUED", "INVITATION_ACCEPTED", "PRIVILEGED_ACCOUNT_ACTIVATED_PENDING"} <= actions
        blob = " ".join((a.details or "") for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(80))
        assert token not in blob and PW not in blob
    finally:
        db.close()


def test_public_registration_can_never_create_a_privileged_account():
    c = TestClient(app)
    for role in PRIVILEGED_ROLES:
        r = c.post("/api/auth/register", json={"role": role, "username": f"sneaky_{role.lower()}", "full_name": "Sneaky", "password": PW,
                                                "phone": "9999999999"})
        assert r.status_code == 422, (role, r.status_code)


def test_citizens_and_volunteers_still_register_themselves():
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"role": "CITIZEN", "username": f"cit_{uuid.uuid4().hex[:8]}", "full_name": "A Citizen", "password": PW,
                                            "phone": "9999999999"})
    assert r.status_code == 201 and r.json()["user"]["auth_state"] == "AUTHENTICATED"


# ------------------------------------------------------------------ admin view: list and revoke only

def test_administrators_can_list_and_revoke_but_see_no_secrets():
    inv_id, token, email = issue("DEVELOPER")
    a = sign_in(TestClient(app), "admin")
    listing = a.get("/api/invitations").json()
    item = next(i for i in listing["items"] if i["id"] == inv_id)
    assert item["status"] == "PENDING" and email not in str(item) and "token" not in str(item).lower().replace("token_", "")
    assert a.post(f"/api/invitations/{inv_id}/revoke").json() == {"revoked": True, "status": "REVOKED"}
    assert a.post(f"/api/invitations/{inv_id}/revoke").json()["revoked"] is False          # idempotent
    assert accept(token)[1].status_code == 404
    db = SessionLocal()
    try:
        assert db.query(AuditLog).filter(AuditLog.action == "INVITATION_REVOKED", AuditLog.target_id == str(inv_id)).count() == 1
    finally:
        db.close()


@pytest.mark.parametrize("who", ["developer", "commander", "operator", "officer", "volunteer", "citizen"])
def test_only_administrators_see_or_revoke_invitations(who):
    inv_id, _, _ = issue()
    c = sign_in(TestClient(app), who)
    assert c.get("/api/invitations").status_code == 403
    assert c.post(f"/api/invitations/{inv_id}/revoke").status_code == 403
    assert row(inv_id).revoked_at is None
    assert TestClient(app).get("/api/invitations").status_code == 401


def test_a_used_invitation_cannot_be_revoked_into_a_dead_account():
    inv_id, token, _ = issue()
    accept(token)
    a = sign_in(TestClient(app), "admin")
    assert a.post(f"/api/invitations/{inv_id}/revoke").json()["revoked"] is False
    assert row(inv_id).revoked_at is None


# ------------------------------------------------------------------ existing accounts and waivers

def test_production_policy_puts_an_existing_privileged_account_in_contact_verification_until_verified_or_waived(monkeypatch):
    from app.core.config import settings
    from tests.conftest import make_user
    monkeypatch.setattr(settings, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", True)
    uid, name = make_user("OPERATOR", PW, mfa=True)
    c = TestClient(app)
    r = login_complete(c, "operations", name, PW)
    assert r.json()["user"]["auth_state"] == "CONTACT_VERIFICATION_PENDING"
    authed(c, r)
    assert c.get("/api/teams/").status_code == 403
    # a host waiver (audited) restores access, WITHOUT marking an address verified
    p = subprocess.run([sys.executable, str(BACKEND / "scripts" / "account_admin.py"), "waive-contact-verification", "--username", name,
                        "--reason", "no email provider yet", "--i-am-authorized"], cwd=BACKEND, env=dict(os.environ), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert c.get("/api/teams/").status_code == 200
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        assert u.email_verified_at is None and u.contact_verification_waived_at is not None
        assert db.query(AuditLog).filter(AuditLog.action == "ACCOUNT_CLI_CONTACT_VERIFICATION_WAIVED", AuditLog.target_id == str(uid)).count() == 1
    finally:
        db.close()


def test_existing_accounts_are_not_flagged_or_silently_verified_by_the_migration_defaults():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == "citizen").one()
        assert u.contact_verification_required is False and u.email_verified_at is None
    finally:
        db.close()


def test_cli_create_of_a_privileged_account_needs_an_email_and_requires_verification():
    env = dict(os.environ)
    base = [sys.executable, str(BACKEND / "scripts" / "account_admin.py"), "create", "--role", "OPERATOR", "--full-name", "CLI Op",
            "--reason", "cli create test", "--i-am-authorized"]
    name = f"cliop_{uuid.uuid4().hex[:6]}"
    no_email = subprocess.run([*base, "--username", name], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert no_email.returncode == 1 and "--email" in no_email.stderr
    ok = subprocess.run([*base, "--username", name, "--email", f"{name}@example.org"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == name).one()
        assert u.contact_verification_required is True and u.must_change_password is True and u.email_verified_at is None
    finally:
        db.close()
