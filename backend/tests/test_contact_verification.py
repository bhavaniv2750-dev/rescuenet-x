"""S3: email / phone verification lifecycle."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, NotificationOutbox, OneTimeToken, User
from app.services import verification as ver
from tests.conftest import PORTAL_FOR_ROLE, latest_dev_message, make_user_with_email, make_user

PW = "Str0ng!Passw0rd"


def signed_in(role="CITIZEN", **kw):
    uid, name, email = make_user_with_email(role, **kw)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c, uid, name, email


def code_from_outbox(uid):
    msg = latest_dev_message(uid, "EMAIL_VERIFY")
    return re.search(r"code is (\d{6})", msg.body).group(1)


def user_row(uid):
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        return u.email, u.email_verified_at, u.phone, u.phone_verified_at
    finally:
        db.close()


def clear_cooldown(uid):
    db = SessionLocal()
    db.query(OneTimeToken).filter(OneTimeToken.user_id == uid).update({"created_at": ver.now() - timedelta(minutes=5)})
    db.commit(); db.close()


# ---------------------------------------------------------------- the happy path and honesty

def test_requesting_a_code_does_not_verify_the_email():
    c, uid, _, _ = signed_in()
    r = c.post("/api/auth/verify/email/request")
    assert r.status_code == 200 and r.json()["delivery_status"] == "NOT_DELIVERED_DEV"
    assert user_row(uid)[1] is None                                   # a code exists, the address is still unverified
    assert c.get("/api/auth/me").json()["email_verified"] is False


def test_correct_code_verifies_and_persists():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    r = c.post("/api/auth/verify/email/confirm", json={"code": code_from_outbox(uid)})
    assert r.status_code == 200 and r.json() == {"verified": True, "channel": "email"}
    assert user_row(uid)[1] is not None
    assert c.get("/api/auth/me").json()["email_verified"] is True
    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.action == "EMAIL_VERIFIED").count() >= 1
    db.close()


def test_the_response_never_contains_the_code_and_says_nothing_was_delivered_in_development():
    c, uid, _, _ = signed_in()
    r = c.post("/api/auth/verify/email/request")
    code = code_from_outbox(uid)
    assert code not in r.text
    text = r.json()["message"].lower()
    assert "nothing was delivered" in text and "development" in text
    assert "has been sent" not in text and "we sent" not in text


def test_code_is_six_digits_from_a_secure_source_and_stored_only_as_a_hash():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    code = code_from_outbox(uid)
    db = SessionLocal()
    tok = db.query(OneTimeToken).filter(OneTimeToken.user_id == uid).one()
    assert len(code) == 6 and code.isdigit()
    assert tok.token_hash != code and len(tok.token_hash) == 64 and code not in tok.token_hash
    import sqlite3
    path = str(db.get_bind().url).replace("sqlite:///", "")
    db.close()
    raw = sqlite3.connect(path)
    rows = raw.execute("SELECT token_hash, target FROM one_time_tokens WHERE user_id=?", (uid,)).fetchall()
    assert all(code != r[0] for r in rows)
    raw.close()
    import inspect
    assert "secrets" in inspect.getsource(ver.new_code) and "random." not in inspect.getsource(ver.new_code)


def test_hash_depends_on_user_purpose_and_target_so_a_stolen_row_cannot_be_replayed_elsewhere():
    h = ver._code_hash("EMAIL_VERIFY", 1, "a@x.org", "123456")
    assert h != ver._code_hash("EMAIL_VERIFY", 2, "a@x.org", "123456")
    assert h != ver._code_hash("PHONE_VERIFY", 1, "a@x.org", "123456")
    assert h != ver._code_hash("EMAIL_VERIFY", 1, "b@x.org", "123456")


# ---------------------------------------------------------------- expiry, attempts, cooldown

def test_wrong_codes_are_counted_and_the_code_dies_after_the_limit():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    good = code_from_outbox(uid)
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(settings.VERIFY_MAX_ATTEMPTS):
        r = c.post("/api/auth/verify/email/confirm", json={"code": wrong})
        assert r.status_code == 400
    # even the right code no longer works: a new one must be requested
    assert c.post("/api/auth/verify/email/confirm", json={"code": good}).status_code == 400
    assert user_row(uid)[1] is None


def test_expired_code_is_refused():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    good = code_from_outbox(uid)
    db = SessionLocal(); db.query(OneTimeToken).filter(OneTimeToken.user_id == uid).update({"expires_at": ver.now() - timedelta(seconds=1)}); db.commit(); db.close()
    assert c.post("/api/auth/verify/email/confirm", json={"code": good}).status_code == 400


def test_code_is_single_use():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    good = code_from_outbox(uid)
    assert c.post("/api/auth/verify/email/confirm", json={"code": good}).status_code == 200
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"email_verified_at": None}); db.commit(); db.close()
    assert c.post("/api/auth/verify/email/confirm", json={"code": good}).status_code == 400      # same code again


def test_resend_cooldown_and_new_code_voids_the_old_one():
    c, uid, _, _ = signed_in()
    assert c.post("/api/auth/verify/email/request").status_code == 200
    first = code_from_outbox(uid)
    r = c.post("/api/auth/verify/email/request")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0 and "wait" in r.json()["detail"]
    clear_cooldown(uid)
    assert c.post("/api/auth/verify/email/request").status_code == 200
    second = code_from_outbox(uid)
    if second != first:
        assert c.post("/api/auth/verify/email/confirm", json={"code": first}).status_code == 400
    assert c.post("/api/auth/verify/email/confirm", json={"code": second}).status_code == 200


def test_hourly_cap_on_verification_emails(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_SEND_PER_ACCOUNT_HOUR", 2)
    monkeypatch.setattr(settings, "VERIFY_RESEND_COOLDOWN_S", 0)
    c, uid, _, _ = signed_in()
    assert c.post("/api/auth/verify/email/request").status_code == 200
    assert c.post("/api/auth/verify/email/request").status_code == 200
    assert c.post("/api/auth/verify/email/request").status_code == 429


def test_confirmation_attempts_are_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_CONFIRM_PER_ACCOUNT_HOUR", 3)
    monkeypatch.setattr(settings, "VERIFY_MAX_ATTEMPTS", 100)
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    codes = [c.post("/api/auth/verify/email/confirm", json={"code": "999999"}).status_code for _ in range(4)]
    assert codes[:3] == [400, 400, 400] and codes[3] == 429


def test_malformed_codes_are_rejected_not_crashing():
    c, _, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    for bad in ("", "abc", "12", "1" * 40, "' OR 1=1 --"):
        assert c.post("/api/auth/verify/email/confirm", json={"code": bad}).status_code in (400, 422)


def test_confirm_without_a_pending_code_gives_the_same_generic_error():
    c, _, _, _ = signed_in()
    r = c.post("/api/auth/verify/email/confirm", json={"code": "123456"})
    assert r.status_code == 400 and "invalid or has expired" in r.json()["detail"]


# ---------------------------------------------------------------- changing a verified contact

def test_changing_a_verified_email_requires_the_password_and_reverification():
    c, uid, name, email = signed_in(verified=True)
    assert c.get("/api/auth/me").json()["email_verified"] is True
    assert c.patch("/api/auth/me/contact", json={"current_password": "wrong-pass-1", "email": "new@example.org"}).status_code == 400
    r = c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "New.Address@Example.org"})
    assert r.status_code == 200 and r.json()["changed"] == ["email"]
    assert r.json()["user"]["email"] == "new.address@example.org" and r.json()["user"]["email_verified"] is False
    assert user_row(uid)[1] is None


def test_codes_issued_for_the_old_address_stop_working_after_a_change():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    old_code = code_from_outbox(uid)
    c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "other@example.org"})
    assert c.post("/api/auth/verify/email/confirm", json={"code": old_code}).status_code == 400
    assert user_row(uid)[1] is None


def test_code_for_one_address_cannot_verify_another_even_if_the_row_is_replayed():
    c, uid, _, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    code = code_from_outbox(uid)
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"email": "swapped@example.org"}); db.commit(); db.close()   # swapped behind the API's back
    assert c.post("/api/auth/verify/email/confirm", json={"code": code}).status_code == 400


def test_unchanged_contact_keeps_its_verified_status():
    c, uid, _, email = signed_in(verified=True)
    r = c.patch("/api/auth/me/contact", json={"current_password": PW, "email": email})
    assert r.json()["changed"] == [] and user_row(uid)[1] is not None


def test_invalid_email_addresses_are_refused():
    c, _, _, _ = signed_in()
    for bad in ("nope", "a@b", "two@@x.org", "spaces in@x.org"):
        assert c.patch("/api/auth/me/contact", json={"current_password": PW, "email": bad}).status_code == 422


def test_a_verified_old_address_is_told_about_the_change():
    c, uid, _, email = signed_in(verified=True)
    c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "moved@example.org"})
    msg = latest_dev_message(uid, "CONTACT_CHANGED_NOTICE")
    assert msg is not None and "was changed" in msg.subject


def test_change_is_audited_without_the_addresses():
    c, uid, _, email = signed_in()
    c.patch("/api/auth/me/contact", json={"current_password": PW, "email": "audit-me@example.org"})
    db = SessionLocal()
    a = db.query(AuditLog).filter(AuditLog.action == "CONTACT_CHANGED", AuditLog.target_id == str(uid)).order_by(AuditLog.id.desc()).first()
    db.close()
    assert a and "audit-me@example.org" not in a.details and email not in a.details


# ---------------------------------------------------------------- one verified owner per address; no enumeration

def test_signing_up_with_someone_elses_address_reveals_nothing_and_cannot_verify_it():
    victim_uid, _, victim_email = make_user_with_email("CITIZEN", verified=True)
    import uuid
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"role": "CITIZEN", "username": f"squat{uuid.uuid4().hex[:6]}", "full_name": "Squatter",
                                           "password": PW, "phone": "9999999999", "email": victim_email})
    assert r.status_code == 201 and "already" not in r.text.lower()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    c.post("/api/auth/verify/email/request")
    sq_uid = r.json()["user"]["id"]
    code = code_from_outbox(sq_uid)
    assert c.post("/api/auth/verify/email/confirm", json={"code": code}).status_code == 400    # the real owner already proved it
    assert user_row(sq_uid)[1] is None


def test_login_by_email_only_works_when_exactly_one_account_has_it():
    uid1, name1, email = make_user_with_email("CITIZEN", email="shared-addr@example.org")
    ok = TestClient(app).post("/api/auth/login", json={"portal": "public", "username": email, "password": PW})
    assert ok.status_code == 200
    uid2, name2, _ = make_user_with_email("CITIZEN", email="shared-addr@example.org")
    both = TestClient(app).post("/api/auth/login", json={"portal": "public", "username": email, "password": PW})
    assert both.status_code == 401                                   # ambiguous address: use the username
    assert TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name1, "password": PW}).status_code == 200


# ---------------------------------------------------------------- phone

def test_phone_verification_is_unavailable_without_an_sms_provider_and_never_marks_verified():
    c, uid, _, _ = signed_in()
    c.patch("/api/auth/me/contact", json={"current_password": PW, "phone": "+919876543210"})
    r = c.post("/api/auth/verify/phone/request")
    assert r.status_code == 409 and "no SMS provider" in r.json()["detail"] and "stays unverified" in r.json()["detail"]
    assert c.post("/api/auth/verify/phone/confirm", json={"code": "123456"}).status_code == 409
    assert user_row(uid)[3] is None
    db = SessionLocal(); assert db.query(OneTimeToken).filter(OneTimeToken.user_id == uid, OneTimeToken.purpose == "PHONE_VERIFY").count() == 0; db.close()


def test_changing_a_phone_clears_its_verification_flag():
    c, uid, _, _ = signed_in()
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"phone": "+911111111111", "phone_verified_at": ver.now()}); db.commit(); db.close()
    c.patch("/api/auth/me/contact", json={"current_password": PW, "phone": "+912222222222"})
    assert user_row(uid)[3] is None


# ---------------------------------------------------------------- restrictions for unverified contacts

def test_volunteer_with_an_account_cannot_be_verified_until_a_contact_is_verified():
    import uuid
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"role": "VOLUNTEER", "username": f"vol{uuid.uuid4().hex[:6]}", "full_name": "New Volunteer",
                                           "password": PW, "phone": "9000000001", "email": f"v{uuid.uuid4().hex[:6]}@example.org",
                                           "skills": "boats", "area": "Hebbal"})
    assert r.status_code == 201
    vid, uid = r.json()["user"]["volunteer_id"], r.json()["user"]["id"]
    from tests.conftest import sign_in
    coord = sign_in(TestClient(app), "operator")
    blocked = coord.patch(f"/api/volunteers/{vid}", json={"is_verified": True})
    assert blocked.status_code == 409 and "verified an email address or phone" in blocked.json()["detail"]
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    c.post("/api/auth/verify/email/request")
    c.post("/api/auth/verify/email/confirm", json={"code": code_from_outbox(uid)})
    assert coord.patch(f"/api/volunteers/{vid}", json={"is_verified": True}).status_code == 200


def test_unverified_contact_never_blocks_emergency_reporting_or_sign_in():
    c, uid, _, _ = signed_in()
    assert c.get("/api/auth/me").status_code == 200
    r = c.post("/api/public/reports", json=dict(title="Water rising", description="Street is flooding fast", area="Hebbal",
                                                latitude=13.0, longitude=77.6, severity="LOW", people_affected=1))
    assert r.status_code == 201


def test_no_email_on_file_gives_a_clear_message_without_creating_a_code():
    uid, name = make_user("CITIZEN", PW)
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).json()["access_token"]
    r = c.post("/api/auth/verify/email/request", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422 and "Add an email address" in r.json()["detail"]
