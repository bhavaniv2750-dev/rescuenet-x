"""S3: forgot / reset password. Enumeration-safe, single-use, short-lived, rate limited, ends all sessions, audited."""

import re
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, AuthSession, NotificationOutbox, OneTimeToken, User
from app.services import verification as ver
from tests.conftest import PORTAL_FOR_ROLE, latest_dev_message, make_user, make_user_with_email

PW = "Str0ng!Passw0rd"
NEW = "Brand-New!Passw0rd9"


def forgot(identifier, client=None, **kw):
    return (client or TestClient(app)).post("/api/auth/password/forgot", json={"identifier": identifier}, **kw)


def token_for(uid):
    msg = latest_dev_message(uid, "PASSWORD_RESET")
    return re.search(r"\?reset=([A-Za-z0-9_\-]+)", msg.body).group(1)


def reset(token, pw=NEW, client=None):
    return (client or TestClient(app)).post("/api/auth/password/reset", json={"token": token, "new_password": pw})


def can_login(name, password, role="CITIZEN"):
    return TestClient(app).post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": password}).status_code == 200


# ---------------------------------------------------------------- enumeration safety

def test_known_unknown_unverified_and_inactive_accounts_get_the_identical_answer(monkeypatch):
    monkeypatch.setattr(settings, "FORGOT_PER_IP_HOUR", 50)
    uid, name, email = make_user_with_email("CITIZEN", verified=True)
    _, unverified, _ = make_user_with_email("CITIZEN", verified=False)
    _, inactive, _ = make_user_with_email("CITIZEN", verified=True)
    db = SessionLocal(); db.query(User).filter(User.username == inactive).update({"is_active": False}); db.commit(); db.close()
    answers = [forgot(i) for i in (name, email, unverified, inactive, "no_such_person_here", "ghost@nowhere.example")]
    assert {a.status_code for a in answers} == {202}
    bodies = {tuple(sorted(a.json().items())) for a in answers}
    assert len(bodies) == 1, "responses differ between existing and non-existing accounts"
    assert "exists" not in answers[0].json()["message"].lower().replace("nothing here confirms that an account exists", "")


def test_only_an_active_account_with_a_verified_address_gets_a_reset_link():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    uid_u, name_u, _ = make_user_with_email("CITIZEN", verified=False)
    forgot(name); forgot(name_u)
    assert latest_dev_message(uid, "PASSWORD_RESET") is not None
    assert latest_dev_message(uid_u, "PASSWORD_RESET") is None          # unverified address: nothing is mailed to it


def test_the_link_is_only_in_the_mail_never_in_the_response():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    r = forgot(name)
    tok = token_for(uid)
    assert tok not in r.text and "reset=" not in r.text


# ---------------------------------------------------------------- the reset itself

def test_reset_changes_the_password_ends_every_session_and_does_not_sign_anyone_in():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    c = TestClient(app)
    tok0 = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).json()["access_token"]
    forgot(name)
    r = reset(token_for(uid))
    assert r.status_code == 200 and "access_token" not in r.text and "set-cookie" not in r.headers
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok0}"}).status_code == 401     # old session dead
    assert not can_login(name, PW) and can_login(name, NEW)
    db = SessionLocal()
    assert db.query(AuthSession).filter(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None)).count() == 1   # only the login just above
    assert db.query(AuditLog).filter(AuditLog.action == "PASSWORD_RESET_COMPLETED", AuditLog.target_id == str(uid)).count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "SESSIONS_REVOKED_ALL", AuditLog.target_id == str(uid)).count() >= 1
    db.close()


def test_reset_token_is_single_use():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    assert reset(tok).status_code == 200
    assert reset(tok, "Another!Passw0rd8").status_code == 400
    assert can_login(name, NEW)


def test_concurrent_use_of_one_token_has_exactly_one_winner():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    results = []
    def go(pw):
        results.append(reset(tok, pw).status_code)
    ts = [threading.Thread(target=go, args=(f"Parallel!Passw0rd{i}",)) for i in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(results).count(200) == 1


def test_expired_unknown_malformed_and_reused_tokens_all_get_the_same_answer():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    db = SessionLocal(); db.query(OneTimeToken).filter(OneTimeToken.user_id == uid, OneTimeToken.purpose == "PASSWORD_RESET").update({"expires_at": ver.now() - timedelta(seconds=1)}); db.commit(); db.close()
    answers = [reset(tok), reset("A" * 43), reset("short-token-x"), reset("../../etc/passwd"), reset("%00%00%00%00%00%00")]
    assert {a.status_code for a in answers} == {400}
    assert len({a.json()["detail"] for a in answers}) == 1


def test_a_weak_password_does_not_burn_the_token():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    for weak in ("short1", "12345678", "onlyletters"):
        assert reset(tok, weak).status_code == 422
    assert reset(tok).status_code == 200


def test_the_new_password_must_differ_from_the_current_one_and_does_not_burn_the_token():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    assert reset(tok, PW).status_code == 422
    assert reset(tok, NEW).status_code == 200


def test_a_new_request_voids_the_previous_link():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name); first = token_for(uid)
    forgot(name); second = token_for(uid)
    assert first != second
    assert reset(first).status_code == 400 and reset(second).status_code == 200


def test_token_is_32_random_bytes_valid_30_minutes_and_stored_only_as_a_hash():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name)
    tok = token_for(uid)
    assert len(tok) >= 43
    db = SessionLocal()
    row = db.query(OneTimeToken).filter(OneTimeToken.user_id == uid, OneTimeToken.purpose == "PASSWORD_RESET").one()
    db.close()
    assert row.token_hash != tok and tok not in row.token_hash and len(row.token_hash) == 64
    assert timedelta(minutes=settings.RESET_TOKEN_MINUTES - 1) < row.expires_at - row.created_at <= timedelta(minutes=settings.RESET_TOKEN_MINUTES)
    assert settings.RESET_TOKEN_MINUTES <= 30


def test_reset_clears_a_login_lockout():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN):
        TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": "wrong-Pass-1"})
    assert TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).status_code == 429
    forgot(name)
    assert reset(token_for(uid)).status_code == 200
    assert can_login(name, NEW)


def test_security_notices_go_to_the_verified_address_after_a_reset():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name); reset(token_for(uid))
    assert latest_dev_message(uid, "PASSWORD_RESET_NOTICE") is not None


def test_request_and_completion_are_audited_without_secrets():
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    forgot(name); tok = token_for(uid); reset(tok)
    db = SessionLocal()
    entries = db.query(AuditLog).filter(AuditLog.target_id == str(uid), AuditLog.action.like("PASSWORD_RESET%")).all()
    text = " ".join(f"{e.action} {e.details}" for e in entries)
    db.close()
    assert {"PASSWORD_RESET_REQUESTED", "PASSWORD_RESET_COMPLETED"} <= {e.action for e in entries}
    assert tok not in text and NEW not in text


# ---------------------------------------------------------------- staff accounts

@pytest.mark.parametrize("role", ["OPERATOR", "COMMANDER", "RESCUE_OFFICER", "DEVELOPER", "ADMIN"])
def test_staff_can_recover_only_with_a_verified_address_that_was_not_changed_recently(role):
    uid, name, _ = make_user_with_email(role, verified=True, changed_hours_ago=48)
    team = None
    forgot(name)
    assert latest_dev_message(uid, "PASSWORD_RESET") is not None
    assert reset(token_for(uid)).status_code == 200
    assert can_login(name, NEW, role)


def test_staff_with_a_recently_changed_address_get_no_reset_link():
    uid, name, _ = make_user_with_email("OPERATOR", verified=True, changed_hours_ago=1)
    assert forgot(name).status_code == 202                         # same answer
    assert latest_dev_message(uid, "PASSWORD_RESET") is None
    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.action == "PASSWORD_RESET_BLOCKED", AuditLog.target_id == str(uid)).count() == 1
    db.close()


def test_a_session_thief_cannot_swap_the_staff_email_and_reset_at_once():
    uid, name, _ = make_user_with_email("OPERATOR", verified=True, changed_hours_ago=72)
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "thief@example.org"})
    code = re.search(r"code is (\d{6})", (c.post("/api/auth/verify/email/request"), latest_dev_message(uid, "EMAIL_VERIFY"))[1].body).group(1)
    assert c.post("/api/auth/verify/email/confirm", json={"code": code}).status_code == 200      # thief verifies their own mailbox
    forgot(name)
    assert latest_dev_message(uid, "PASSWORD_RESET") is None                                      # still blocked for 24 h


def test_staff_without_any_email_have_no_email_recovery():
    uid, name = make_user("OPERATOR", PW)
    assert forgot(name).status_code == 202
    assert latest_dev_message(uid, "PASSWORD_RESET") is None


def test_reset_does_not_change_role_or_grant_anything():
    uid, name, _ = make_user_with_email("OPERATOR", verified=True, changed_hours_ago=48)
    forgot(name); reset(token_for(uid))
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": NEW}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert tok["user"]["role"] == "OPERATOR"
    assert c.post("/api/agents/tasks/TASK-X/approve", json={}, headers=h).status_code == 403          # still no approval authority
    assert c.post("/api/auth/users", json={}, headers=h).status_code == 403


# ---------------------------------------------------------------- rate limits

def test_forgot_is_limited_per_address_and_per_identifier(monkeypatch):
    monkeypatch.setattr(settings, "FORGOT_PER_IDENTIFIER_HOUR", 2)
    uid, name, _ = make_user_with_email("CITIZEN", verified=True)
    assert [forgot(name).status_code for _ in range(3)] == [202, 202, 429]
    assert forgot("someone_else_entirely").status_code == 202           # another identifier is unaffected


def test_forgot_ip_limit_applies_to_unknown_identifiers_too(monkeypatch):
    monkeypatch.setattr(settings, "FORGOT_PER_IP_HOUR", 3)
    codes = [forgot(f"ghost{i}").status_code for i in range(5)]
    assert codes == [202, 202, 202, 429, 429]
    r = forgot("ghost-again")
    assert int(r.headers["retry-after"]) > 0


def test_reset_attempts_are_limited_per_address(monkeypatch):
    monkeypatch.setattr(settings, "RESET_PER_IP_HOUR", 3)
    codes = [reset("A" * 43).status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400] and codes[3:] == [429, 429]
