"""S4: enrolment, login challenge, recovery codes, state enforcement and direct bypass attempts, through the real API."""

import re
import threading
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.permissions import PRIVILEGED_ROLES
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, AuthChallenge, AuthSession, MfaCredential, MfaRecoveryCode, User
from app.services import mfa as mfa_svc
from tests.conftest import (PORTAL_FOR_ROLE, _forget_replay, enroll_via_api, login_complete, make_team, make_user,
                            mfa_secret_of, sign_in, totp_code)

PW = "Str0ng!Passw0rd"
OPERATIONAL = [("GET", "/api/incidents/"), ("GET", "/api/teams/"), ("GET", "/api/volunteers/"), ("GET", "/api/dashboard"),
               ("GET", "/api/records/"), ("GET", "/api/agents/tasks"), ("POST", "/api/alerts/"), ("POST", "/api/teams/T/assign"),
               ("GET", "/api/auth/users"), ("GET", "/api/diagnostics/"), ("GET", "/api/auth/audit"), ("GET", "/api/datasets/inventory")]


def new_account(role, mfa=False):
    team = make_team(sign_in(TestClient(app), "operator")) if role == "RESCUE_OFFICER" else None
    uid, name = make_user(role, PW, team_id=team, mfa=mfa)
    return uid, name


def password_login(name, role):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    return c, r


def bearer(c, r):
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def audit_text(action=None):
    db = SessionLocal()
    rows = db.query(AuditLog)
    if action:
        rows = rows.filter(AuditLog.action == action)
    text = " ".join(f"{a.actor} {a.action} {a.details}" for a in rows.all())
    db.close()
    return text


# ================================================================ mandatory vs optional

@pytest.mark.parametrize("role", PRIVILEGED_ROLES)
def test_mfa_is_mandatory_for_every_privileged_role_no_operational_access_before_enrolment(role):
    uid, name = new_account(role)
    c, r = password_login(name, role)
    assert r.status_code == 200 and r.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"      # a restricted session, not a full one
    assert r.json()["user"]["mfa_required"] is True and r.json()["user"]["permissions"] == []
    bearer(c, r)
    for method, path in OPERATIONAL:
        resp = c.request(method, path, json={} if method == "POST" else None)
        assert resp.status_code == 403 and resp.headers.get("x-mfa-enrollment-required") == "true", (role, method, path)
    assert c.get("/api/auth/me").status_code == 200 and c.get("/api/auth/mfa/status").json()["required"] is True


@pytest.mark.parametrize("role", ["CITIZEN", "VOLUNTEER"])
def test_mfa_is_optional_for_public_roles_and_they_are_not_restricted(role):
    uid, name = new_account(role)
    c, r = password_login(name, role)
    assert r.json()["status"] == "authenticated" and r.json()["user"]["auth_state"] == "AUTHENTICATED"
    assert r.json()["user"]["mfa_required"] is False and r.json()["user"]["mfa_enabled"] is False
    bearer(c, r)
    assert c.get("/api/incidents/mine").status_code == 200


def test_guests_never_need_mfa_for_reporting_or_tracking():
    g = TestClient(app)
    rep = g.post("/api/public/reports", json=dict(title="Water rising", description="Street is flooding fast", area="Hebbal",
                                                 latitude=13.0, longitude=77.6, severity="LOW", people_affected=1))
    assert rep.status_code == 201
    assert g.get(f"/api/public/reports/{rep.json()['public_ref']}", headers={"X-Tracking-Code": rep.json()["tracking_code"]}).status_code == 200


def test_restricted_privileged_session_is_treated_as_a_guest_on_open_endpoints():
    """Endpoints that accept an optional user must not let a password-only privileged session act with its privileges."""
    from tests.test_public_media import png_bytes as png
    inc_owner = TestClient(app)
    up = inc_owner.post("/api/incidents/upload-image", files={"file": ("p.png", png(), "image/png")}).json()
    inc_owner.post("/api/incidents/", json=dict(title="Photo report", description="Report with a photo attached", area="Hebbal",
                                               latitude=13.0, longitude=77.6, severity="LOW", people_affected=1, image_url=up["image_url"]))
    uid, name = new_account("COMMANDER")
    c, r = password_login(name, "COMMANDER"); bearer(c, r)
    assert c.get(up["image_url"]).status_code == 401                   # guest semantics: no private photo
    full = sign_in(TestClient(app), "commander")
    assert full.get(up["image_url"]).status_code == 200


# ================================================================ enrolment

def test_enrolment_start_needs_the_password_and_returns_the_secret_only_once():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    assert c.post("/api/auth/mfa/enroll/start", json={"current_password": "wrong-Pass-1"}).status_code == 400
    s = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW})
    assert s.status_code == 200 and s.headers["cache-control"] == "no-store"
    body = s.json()
    assert len(body["secret"]) == 32 and body["otpauth_uri"].startswith("otpauth://totp/") and body["qr_svg_data_uri"].startswith("data:image/svg+xml")
    assert body["account"] == name and body["digits"] == 6 and body["period"] == 30 and body["algorithm"] == "SHA1"
    # nothing else ever returns it
    for path in ("/api/auth/me", "/api/auth/mfa/status"):
        assert body["secret"] not in c.get(path).text


def test_pending_enrolment_does_not_enable_mfa_until_confirmed():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    c.post("/api/auth/mfa/enroll/start", json={"current_password": PW})
    st = c.get("/api/auth/mfa/status").json()
    assert st["enabled"] is False and st["enrollment_pending"] is True
    again, r2 = password_login(name, "OPERATOR")
    assert r2.json()["status"] == "authenticated" and r2.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"   # no challenge: not enrolled yet
    assert c.get("/api/teams/").status_code == 403


def test_confirmation_with_a_wrong_or_stale_code_is_refused_and_a_right_one_activates():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).json()["secret"]
    assert c.post("/api/auth/mfa/enroll/confirm", json={"code": "000000"}).status_code == 400
    assert c.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(secret, -3)}).status_code == 400   # expired (> drift)
    assert c.get("/api/teams/").status_code == 403
    ok = c.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(secret)})
    assert ok.status_code == 200 and ok.json()["enabled"] is True
    assert len(ok.json()["recovery_codes"]) == settings.MFA_RECOVERY_CODE_COUNT
    assert ok.json()["user"]["auth_state"] == "AUTHENTICATED"
    assert c.get("/api/teams/").status_code == 200                       # now (and only now) operational access exists


def test_confirm_without_start_and_start_when_already_enrolled_are_refused():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    assert c.post("/api/auth/mfa/enroll/confirm", json={"code": "123456"}).status_code == 400
    enroll_via_api(c, PW)
    assert c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).status_code == 409


def test_restarting_enrolment_replaces_the_pending_secret():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    first = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).json()["secret"]
    second = c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).json()["secret"]
    assert first != second
    assert c.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(first)}).status_code == 400    # old secret is dead
    assert c.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(second)}).status_code == 200


def test_enrolment_ends_every_other_session_and_upgrades_only_this_one():
    uid, name = new_account("OPERATOR")
    c1, r1 = password_login(name, "OPERATOR"); bearer(c1, r1)
    c2, r2 = password_login(name, "OPERATOR"); bearer(c2, r2)
    enroll_via_api(c1, PW)
    assert c2.get("/api/auth/me").status_code == 401                         # the other session ended
    assert c1.get("/api/teams/").status_code == 200


def test_enrolment_is_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENROLL_START_PER_ACCOUNT_HOUR", 2)
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    codes = [c.post("/api/auth/mfa/enroll/start", json={"current_password": PW}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_enrolment_audit_has_no_secrets_or_codes():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret, codes = enroll_via_api(c, PW)
    text = audit_text()
    assert "MFA_ENROLLED" in text and secret not in text and all(code not in text for code in codes)


# ================================================================ login challenge

def enrolled(role="OPERATOR"):
    uid, name = new_account(role, mfa=True)
    return uid, name, mfa_secret_of(uid)


def challenge_for(name, role="OPERATOR"):
    c, r = password_login(name, role)
    return c, r


def test_a_correct_password_alone_never_yields_a_session_when_mfa_is_enrolled():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "mfa_required" and body["challenge_token"] and "access_token" not in body
    assert not r.headers.get_list("set-cookie") and not c.cookies                    # no refresh cookie, no CSRF cookie
    assert r.headers["cache-control"] == "no-store"
    db = SessionLocal(); assert db.query(AuthSession).filter(AuthSession.user_id == uid).count() == 0; db.close()


def test_challenge_is_not_a_token_and_cannot_be_used_as_one():
    uid, name, secret = enrolled()
    _, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    for path in ("/api/auth/me", "/api/teams/"):
        assert TestClient(app).get(path, headers={"Authorization": f"Bearer {ch}"}).status_code == 401


def test_correct_code_completes_the_login_with_an_mfa_session():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    _forget_replay(uid)
    v = c.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "code": totp_code(secret)})
    assert v.status_code == 200 and v.json()["user"]["auth_state"] == "AUTHENTICATED"
    assert c.cookies.get(settings.REFRESH_COOKIE_NAME) and c.cookies.get(settings.CSRF_COOKIE_NAME)
    assert jwt.decode(v.json()["access_token"], options={"verify_signature": False}).keys() >= {"sid", "tv"}
    db = SessionLocal(); s = db.query(AuthSession).filter(AuthSession.user_id == uid).one(); db.close()
    assert s.assurance == "MFA" and s.mfa_method == "TOTP" and s.mfa_at is not None


def test_wrong_codes_get_one_generic_answer_and_exhaust_the_challenge():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    for _ in range(settings.MFA_CHALLENGE_MAX_ATTEMPTS):
        resp = c.post("/api/auth/mfa/verify", json={"challenge_token": ch, "code": "000000"})
        assert resp.status_code == 401
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/verify", json={"challenge_token": ch, "code": totp_code(secret)}).status_code == 401   # even the right code
    assert "mfa_required" not in resp.text


def test_challenge_expires():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    db = SessionLocal(); db.query(AuthChallenge).filter(AuthChallenge.user_id == uid).update({"expires_at": mfa_svc.now() - timedelta(seconds=1)}); db.commit(); db.close()
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "code": totp_code(secret)}).status_code == 401


def test_challenge_is_single_use():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/verify", json={"challenge_token": ch, "code": totp_code(secret)}).status_code == 200
    _forget_replay(uid)
    assert TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": ch, "code": totp_code(secret)}).status_code == 401


def test_concurrent_verification_of_one_challenge_creates_exactly_one_session():
    uid, name, secret = enrolled()
    _, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    # five different valid recovery codes race on one challenge: every code is valid, only one request may win the challenge
    c0 = TestClient(app); c0.headers["Authorization"] = "Bearer " + sign_in(TestClient(app), "commander").headers["Authorization"][7:]
    from app.services.mfa import generate_recovery_codes
    db = SessionLocal(); codes = generate_recovery_codes(db, db.get(User, uid)); db.commit(); db.close()
    results = []

    def go(code):
        results.append(TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": ch, "recovery_code": code}).status_code)
    ts = [threading.Thread(target=go, args=(c,)) for c in codes[:5]]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(200) == 1
    db = SessionLocal(); assert db.query(AuthSession).filter(AuthSession.user_id == uid).count() == 1; db.close()


def test_a_new_password_login_voids_the_previous_challenge():
    uid, name, secret = enrolled()
    _, r1 = challenge_for(name)
    _, r2 = challenge_for(name)
    _forget_replay(uid)
    assert TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": r1.json()["challenge_token"], "code": totp_code(secret)}).status_code == 401
    assert TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": r2.json()["challenge_token"], "code": totp_code(secret)}).status_code == 200


def test_a_code_cannot_be_used_with_somebody_elses_challenge():
    uid1, name1, secret1 = enrolled()
    uid2, name2, secret2 = enrolled()
    _, r2 = challenge_for(name2)
    _forget_replay(uid1); _forget_replay(uid2)
    assert TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": r2.json()["challenge_token"], "code": totp_code(secret1)}).status_code == 401


def test_mfa_attempts_are_rate_limited_per_account_and_per_address(monkeypatch):
    monkeypatch.setattr(settings, "MFA_FAILS_PER_ACCOUNT_15MIN", 3)
    monkeypatch.setattr(settings, "MFA_CHALLENGE_MAX_ATTEMPTS", 100)
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    codes = [c.post("/api/auth/mfa/verify", json={"challenge_token": ch, "code": "000000"}).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    from app.services import rate_limit
    rate_limit.reset_all()
    monkeypatch.setattr(settings, "MFA_ATTEMPTS_PER_IP_15MIN", 2)
    other = TestClient(app)
    got = [other.post("/api/auth/mfa/verify", json={"challenge_token": "x" * 20, "code": "000000"}).status_code for _ in range(4)]
    assert got[:2] == [401, 401] and got[2:] == [429, 429]


def test_unknown_malformed_and_missing_challenges_are_refused_alike():
    for payload in ({"challenge_token": "A" * 43, "code": "123456"}, {"challenge_token": "short-tok-xx", "code": "123456"}):
        assert TestClient(app).post("/api/auth/mfa/verify", json=payload).status_code == 401
    uid, name, secret = enrolled()
    _, r = challenge_for(name)
    assert TestClient(app).post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"]}).status_code == 422


def test_totp_code_replay_is_refused_on_the_next_login(monkeypatch):
    state = {"t": 1_800_000_000.0}
    monkeypatch.setattr(mfa_svc, "_time", lambda: state["t"])
    uid, name, secret = enrolled()
    code = totp_code(secret)
    _forget_replay(uid)
    c1, r1 = challenge_for(name)
    assert c1.post("/api/auth/mfa/verify", json={"challenge_token": r1.json()["challenge_token"], "code": code}).status_code == 200
    c2, r2 = challenge_for(name)
    assert c2.post("/api/auth/mfa/verify", json={"challenge_token": r2.json()["challenge_token"], "code": code}).status_code == 401   # replay
    state["t"] += 30
    c3, r3 = challenge_for(name)
    assert c3.post("/api/auth/mfa/verify", json={"challenge_token": r3.json()["challenge_token"], "code": totp_code(secret)}).status_code == 200


def test_disabled_account_cannot_finish_a_pending_challenge():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"is_active": False}); db.commit(); db.close()
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "code": totp_code(secret)}).status_code == 401


def test_remember_me_is_honoured_for_public_roles_only_through_the_mfa_step():
    uid, name = make_user("CITIZEN", PW, mfa=True)
    secret = mfa_secret_of(uid)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW, "remember": True})
    assert r.json()["status"] == "mfa_required"
    _forget_replay(uid)
    v = c.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "code": totp_code(secret)})
    db = SessionLocal(); s = db.query(AuthSession).filter(AuthSession.user_id == uid).one(); db.close()
    assert v.status_code == 200 and s.remember is True


# ================================================================ refresh and bypass attempts

def test_refresh_keeps_the_session_assurance_and_never_raises_it():
    uid, name, secret = enrolled()
    c = TestClient(app)
    login_complete(c, "operations", name, PW, secret=secret)
    csrf = c.cookies.get(settings.CSRF_COOKIE_NAME)
    r = c.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["user"]["auth_state"] == "AUTHENTICATED"
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.get("/api/teams/").status_code == 200
    # a PASSWORD-assurance session of an enrolled account (e.g. one that pre-dates enrolment) stays blocked through refreshes
    db = SessionLocal()
    sid = db.query(AuthSession).filter(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None)).one().id
    db.query(AuthSession).filter(AuthSession.id == sid).update({"assurance": "PASSWORD", "mfa_at": None}); db.commit(); db.close()
    r2 = c.post("/api/auth/refresh", headers={"X-CSRF-Token": c.cookies.get(settings.CSRF_COOKIE_NAME)})
    assert r2.status_code == 200 and r2.json()["user"]["auth_state"] == "MFA_CHALLENGE_PENDING"
    c.headers["Authorization"] = f"Bearer {r2.json()['access_token']}"
    for method, path in OPERATIONAL:
        resp = c.request(method, path, json={} if method == "POST" else None)
        assert resp.status_code == 403 and resp.headers.get("x-mfa-required") == "true", (method, path)


def test_restricted_session_cannot_be_upgraded_by_refreshing():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR")
    for _ in range(3):
        r = c.post("/api/auth/refresh", headers={"X-CSRF-Token": c.cookies.get(settings.CSRF_COOKIE_NAME)})
        assert r.status_code == 200 and r.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING"
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        assert c.get("/api/teams/").status_code == 403


@pytest.mark.parametrize("extra", [{"aal": 2}, {"amr": ["mfa"]}, {"assurance": "MFA"}, {"mfa": True}, {"role": "COMMANDER"}])
def test_forged_assurance_claims_in_a_token_change_nothing(extra):
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR")
    claims = jwt.decode(r.json()["access_token"], options={"verify_signature": False})
    from app.core.security import ALGORITHM, jwt_secret
    forged = jwt.encode({**claims, **extra}, jwt_secret(), algorithm=ALGORITHM)       # even signed with the real key
    assert TestClient(app).get("/api/teams/", headers={"Authorization": f"Bearer {forged}"}).status_code == 403


def test_direct_calls_to_skip_mfa_do_not_work():
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    # enrol endpoints, reauth and status need a session, not a challenge
    for path, body in [("/api/auth/mfa/enroll/start", {"current_password": PW}), ("/api/auth/mfa/reauth", {"code": "123456"}),
                       ("/api/auth/mfa/disable", {"current_password": PW}), ("/api/auth/mfa/recovery-codes/regenerate", {})]:
        assert c.post(path, json=body, headers={"Authorization": f"Bearer {r.json()['challenge_token']}"}).status_code == 401
    # a refresh without ever finishing MFA has nothing to refresh
    assert TestClient(app).post("/api/auth/refresh", headers={"X-CSRF-Token": "x"}).status_code == 401
    # logging in with the wrong portal still needs a second factor afterwards (no shortcut around it)
    wrong = TestClient(app).post("/api/auth/login", json={"portal": "admin", "username": name, "password": PW})
    assert wrong.status_code == 403 and "access_token" not in wrong.text


def test_public_user_with_mfa_must_pass_it_and_privileged_cannot_turn_it_off():
    uid, name = make_user("CITIZEN", PW, mfa=True)
    c = TestClient(app)
    r = login_complete(c, "public", name, PW)
    assert r.status_code == 200 and "access_token" in r.json()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.post("/api/auth/mfa/disable", json={"current_password": "wrong-Pass-1"}).status_code == 400
    assert c.post("/api/auth/mfa/disable", json={"current_password": PW}).json() == {"enabled": False}
    again = TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": PW})
    assert again.json()["status"] == "authenticated"                              # optional: password alone is enough again
    uid2, name2, secret2 = enrolled("COMMANDER")
    c2 = TestClient(app)
    r2 = login_complete(c2, "operations", name2, PW, secret=secret2)
    c2.headers["Authorization"] = f"Bearer {r2.json()['access_token']}"
    d = c2.post("/api/auth/mfa/disable", json={"current_password": PW})
    assert d.status_code == 403 and "mandatory" in d.json()["detail"]


def test_an_administrator_has_no_way_to_remove_or_reset_anyones_mfa():
    admin = sign_in(TestClient(app), "admin")
    uid, name, secret = enrolled("COMMANDER")
    spec = app.openapi()["paths"]
    assert not [p for p in spec if "mfa" in p.lower() and ("reset" in p.lower() or p.lower().endswith("/mfa"))]
    admin.patch(f"/api/auth/users/{uid}", json={"mfa_enabled": False, "mfa_secret": "x", "reset_mfa": True})
    db = SessionLocal(); cred = db.query(MfaCredential).filter(MfaCredential.user_id == uid).one(); db.close()
    assert cred.status == "ACTIVE"
    for method, path in [("DELETE", f"/api/auth/mfa/{uid}"), ("POST", f"/api/auth/users/{uid}/reset-mfa"), ("POST", f"/api/auth/mfa/reset")]:
        assert admin.request(method, path).status_code in (404, 405)


# ================================================================ recovery codes

def finish_login(name, role, secret):
    c = TestClient(app)
    r = login_complete(c, PORTAL_FOR_ROLE[role], name, PW, secret=secret)
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c, r


def recovery_login(name, role, code):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    return c, c.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "recovery_code": code})


def test_recovery_codes_are_shown_once_high_entropy_hashed_and_single_use():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret, codes = enroll_via_api(c, PW)
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(re.fullmatch(r"([0-9A-HJKMNP-TV-Z]{4}-){3}[0-9A-HJKMNP-TV-Z]{4}", code) for code in codes)     # 16 symbols = 80 bits
    db = SessionLocal()
    rows = db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == uid).all()
    assert len(rows) == 10 and all(len(x.code_hash) == 64 and x.code_hash not in codes for x in rows)
    import sqlite3
    path = str(db.get_bind().url).replace("sqlite:///", ""); db.close()
    raw = sqlite3.connect(path)
    blob = " ".join(str(v) for t in ("mfa_recovery_codes", "audit_logs") for row in raw.execute(f"SELECT * FROM {t}") for v in row)
    assert all(code not in blob and code.replace("-", "") not in blob for code in codes)
    raw.close()
    _, ok = recovery_login(name, "OPERATOR", codes[0])
    assert ok.status_code == 200
    _, again = recovery_login(name, "OPERATOR", codes[0])
    assert again.status_code == 401                                                            # single use
    _, other = recovery_login(name, "OPERATOR", codes[1].lower().replace("-", " "))            # tolerant of case/spacing
    assert other.status_code == 200


def test_recovery_code_login_does_not_change_the_role_or_disable_mfa():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret, codes = enroll_via_api(c, PW)
    c2, ok = recovery_login(name, "OPERATOR", codes[0])
    assert ok.json()["user"]["role"] == "OPERATOR" and ok.json()["user"]["mfa_enabled"] is True and ok.json()["user"]["auth_state"] == "AUTHENTICATED"
    db = SessionLocal()
    assert db.get(User, uid).role == "OPERATOR" and db.query(MfaCredential).filter(MfaCredential.user_id == uid, MfaCredential.status == "ACTIVE").count() == 1
    s = db.query(AuthSession).filter(AuthSession.user_id == uid, AuthSession.mfa_method == "RECOVERY").one(); db.close()
    assert s.assurance == "MFA"
    nxt = TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW})
    assert nxt.json()["status"] == "mfa_required"                                              # the next login still needs a factor
    assert "MFA_RECOVERY_CODE_USED" in audit_text() and codes[0] not in audit_text()


def test_concurrent_use_of_one_recovery_code_has_exactly_one_winner():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret, codes = enroll_via_api(c, PW)
    challenges = [TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}) for _ in range(1)]
    results = []
    from app.services.mfa import consume_recovery_code

    def go():
        db = SessionLocal()
        try:
            ok = consume_recovery_code(db, db.get(User, uid), codes[2]); db.commit(); results.append(ok)
        finally:
            db.close()
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1


def test_regeneration_invalidates_all_previous_codes_and_needs_recent_mfa():
    uid, name, secret = enrolled()
    c, r = finish_login(name, "OPERATOR", secret)
    db = SessionLocal(); from app.services.mfa import generate_recovery_codes; old = generate_recovery_codes(db, db.get(User, uid)); db.commit(); db.close()
    db = SessionLocal(); db.query(AuthSession).filter(AuthSession.user_id == uid).update({"mfa_at": mfa_svc.now() - timedelta(hours=1)}); db.commit(); db.close()
    stale = c.post("/api/auth/mfa/recovery-codes/regenerate")
    assert stale.status_code == 403 and stale.headers.get("x-mfa-reauth-required") == "true"
    _forget_replay(uid)
    assert c.post("/api/auth/mfa/reauth", json={"code": totp_code(secret)}).status_code == 200
    new = c.post("/api/auth/mfa/recovery-codes/regenerate")
    assert new.status_code == 200 and len(new.json()["recovery_codes"]) == 10 and "instructions" in new.json()
    assert c.get("/api/auth/mfa/status").json()["recovery_codes_remaining"] == 10
    _, dead = recovery_login(name, "OPERATOR", old[0])
    assert dead.status_code == 401                                                              # previous batch is void
    _, fresh = recovery_login(name, "OPERATOR", new.json()["recovery_codes"][0])
    assert fresh.status_code == 200
    assert "MFA_RECOVERY_CODES_REGENERATED" in audit_text() and new.json()["recovery_codes"][1] not in audit_text()


def test_wrong_recovery_codes_are_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "MFA_RECOVERY_FAILS_PER_ACCOUNT_HOUR", 3)
    monkeypatch.setattr(settings, "MFA_CHALLENGE_MAX_ATTEMPTS", 100)
    uid, name, secret = enrolled()
    c, r = challenge_for(name)
    ch = r.json()["challenge_token"]
    codes = [c.post("/api/auth/mfa/verify", json={"challenge_token": ch, "recovery_code": "AAAA-AAAA-AAAA-AAAA"}).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_status_reports_remaining_recovery_codes_without_revealing_them():
    uid, name = new_account("OPERATOR")
    c, r = password_login(name, "OPERATOR"); bearer(c, r)
    secret, codes = enroll_via_api(c, PW)
    recovery_login(name, "OPERATOR", codes[0])
    st = c.get("/api/auth/mfa/status")
    assert st.json()["recovery_codes_remaining"] == 9 and all(code not in st.text for code in codes)
