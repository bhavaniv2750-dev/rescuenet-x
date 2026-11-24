"""S2: session lifecycle. Short-lived access tokens, server-side sessions, logout, logout-all, session management,
expiry, and invalidation after password changes."""

from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ALGORITHM, create_access_token, jwt_secret
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuthSession, RefreshToken, User
from app.services import sessions as svc
from tests.conftest import PORTAL_FOR_ROLE, login_complete, make_user

PW = "Str0ng!Passw0rd"


def login(role="OPERATOR", remember=False, client=None, uid_name=None):
    """Sign in (privileged roles are enrolled in MFA first, since S4 makes it mandatory; the second step is completed)."""
    uid, name = uid_name or make_user(role, PW, mfa=role not in ("CITIZEN", "VOLUNTEER"))
    c = client or TestClient(app)
    r = login_complete(c, PORTAL_FOR_ROLE[role], name, PW, remember)
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c, r.json(), uid, name


def db_session(sid):
    db = SessionLocal()
    try:
        return db.get(AuthSession, sid)
    finally:
        db.close()


def sid_of(token):
    return jwt.decode(token, options={"verify_signature": False})["sid"]


# ---------------------------------------------------------------- what login issues

def test_login_issues_a_short_lived_access_token_and_a_cookie_only_refresh_token():
    c, body, uid, _ = login()
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60 and body["expires_in"] == 900
    assert "refresh_token" not in body and "refresh" not in " ".join(body).lower().replace("csrf", "")
    assert c.cookies.get(settings.REFRESH_COOKIE_NAME) and c.cookies.get(settings.CSRF_COOKIE_NAME)
    assert body["csrf_token"] == c.cookies.get(settings.CSRF_COOKIE_NAME) == svc.csrf_value(claims["sid"])


def test_refresh_cookie_attributes_in_development():
    r = TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": make_user("OPERATOR", PW)[1], "password": PW})
    cookies = {h.split("=")[0]: h for h in r.headers.get_list("set-cookie")}
    refresh, csrf = cookies[settings.REFRESH_COOKIE_NAME].lower(), cookies[settings.CSRF_COOKIE_NAME].lower()
    assert "httponly" in refresh and "samesite=lax" in refresh and "path=/api/auth" in refresh
    assert "httponly" not in csrf and "path=/" in csrf          # the page must be able to read the CSRF value
    assert "secure" not in refresh                                # plain-http development only; production test below


def test_access_token_lifetime_is_capped_at_one_hour(monkeypatch):
    monkeypatch.setattr(settings, "ACCESS_TOKEN_MINUTES", 480.0)      # the old setting must not bring back long-lived tokens
    assert settings.access_token_minutes == 60.0
    token = create_access_token(1, "a" * 32, 0)
    c = jwt.decode(token, options={"verify_signature": False})
    assert c["exp"] - c["iat"] == 3600


def test_session_row_holds_minimal_metadata_and_no_secrets():
    c, body, uid, _ = login()
    s = db_session(sid_of(body["access_token"]))
    assert s.user_id == uid and s.revoked_at is None and s.expires_at > s.created_at
    cols = {col.name for col in AuthSession.__table__.columns}
    # S4 added the three assurance columns (assurance, mfa_at, mfa_method); still no secret of any kind is stored here
    assert cols == {"id", "user_id", "created_at", "last_used_at", "expires_at", "idle_timeout_s", "remember", "revoked_at",
                    "revoked_reason", "user_agent", "client_hash", "assurance", "mfa_at", "mfa_method"}
    assert s.client_hash and "testclient" not in s.client_hash      # keyed hash, not the address


def test_staff_sessions_ignore_remember_me_but_public_roles_get_longer_ones():
    _, staff, _, _ = login("OPERATOR", remember=True)
    _, citizen, _, _ = login("CITIZEN", remember=True)
    _, plain, _, _ = login("CITIZEN", remember=False)
    s_staff, s_cit, s_plain = (db_session(sid_of(b["access_token"])) for b in (staff, citizen, plain))
    assert not s_staff.remember and (s_staff.expires_at - s_staff.created_at) <= timedelta(hours=12, seconds=5)
    assert s_cit.remember and (s_cit.expires_at - s_cit.created_at) >= timedelta(days=6)
    assert (s_plain.expires_at - s_plain.created_at) <= timedelta(hours=12, seconds=5)


# ---------------------------------------------------------------- rejection of bad tokens

def test_expired_access_token_is_rejected():
    c, body, uid, _ = login()
    old = create_access_token(uid, sid_of(body["access_token"]), 0, minutes=-1)
    r = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()


@pytest.mark.parametrize("make", [
    lambda t: t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB"),                 # tampered signature
    lambda t: t.rsplit(".", 1)[0] + ".",                                              # signature stripped
    lambda t: "not-a-jwt",
    lambda t: "",
    lambda t: t + "x.y",
    lambda t: ".".join([t.split(".")[0], t.split(".")[1][:-4] + "AAAA", t.split(".")[2]]),   # tampered payload
])
def test_malformed_and_tampered_tokens_are_rejected(make):
    c, body, _, _ = login()
    r = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {make(body['access_token'])}"})
    assert r.status_code == 401


def test_token_signed_with_another_key_or_algorithm_none_is_rejected():
    c, body, uid, _ = login()
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    wrong_key = jwt.encode(claims, "some-other-secret-key-of-32-bytes-long!!", algorithm=ALGORITHM)
    none_alg = jwt.encode(claims, key=None, algorithm="none")
    for tok in (wrong_key, none_alg):
        assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


@pytest.mark.parametrize("patch", [{"typ": "refresh"}, {"typ": None}, {"sid": None}, {"tv": None}, {"sid": "0" * 32}, {"tv": 99}])
def test_structurally_wrong_or_mismatched_claims_are_rejected(patch):
    c, body, uid, _ = login()
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    for k, v in patch.items():
        claims.pop(k) if v is None else claims.update({k: v})
    tok = jwt.encode(claims, jwt_secret(), algorithm=ALGORITHM)
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_a_token_cannot_be_used_with_another_users_session():
    c1, b1, uid1, _ = login()
    c2, b2, uid2, _ = login()
    tok = create_access_token(uid1, sid_of(b2["access_token"]), 0)       # user 1's id, user 2's session
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


# ---------------------------------------------------------------- session expiry

def test_absolute_expiry_ends_the_session():
    c, body, _, _ = login()
    db = SessionLocal(); db.query(AuthSession).filter(AuthSession.id == sid_of(body["access_token"])).update({"expires_at": svc.now() - timedelta(seconds=1)}); db.commit(); db.close()
    assert c.get("/api/auth/me").status_code == 401


def test_idle_timeout_ends_the_session():
    c, body, _, _ = login()
    db = SessionLocal()
    db.query(AuthSession).filter(AuthSession.id == sid_of(body["access_token"])).update({"last_used_at": svc.now() - timedelta(hours=2)})
    db.commit(); db.close()
    assert c.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------- logout and session management

def test_logout_revokes_the_session_clears_cookies_and_is_idempotent():
    c, body, _, _ = login()
    r = c.post("/api/auth/logout")
    assert r.status_code == 200
    cleared = " ".join(r.headers.get_list("set-cookie")).lower()
    assert settings.REFRESH_COOKIE_NAME in cleared and "max-age=0" in cleared
    assert db_session(sid_of(body["access_token"])).revoked_reason == "LOGOUT"
    assert c.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/logout").status_code == 200          # nothing to end, still fine


def test_logout_all_ends_every_session_of_the_account():
    c1, b1, uid, name = login()
    c2, b2, _, _ = login(uid_name=(uid, name))
    assert c1.post("/api/auth/logout-all").status_code == 200
    assert c1.get("/api/auth/me").status_code == 401 and c2.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).status_code == 200


def test_logout_all_does_not_touch_other_accounts():
    c1, _, _, _ = login()
    c2, _, _, _ = login()
    c1.post("/api/auth/logout-all")
    assert c2.get("/api/auth/me").status_code == 200


def test_list_and_revoke_own_sessions_only():
    c1, b1, uid, name = login()
    c2, b2, _, _ = login(uid_name=(uid, name))
    other, ob, _, _ = login()
    listed = c1.get("/api/auth/sessions").json()["items"]
    ids = {s["id"]: s for s in listed}
    assert len(listed) == 2 and ids[sid_of(b1["access_token"])]["current"] and not ids[sid_of(b2["access_token"])]["current"]
    for s in listed:
        assert set(s) == {"id", "created_at", "last_used_at", "expires_at", "user_agent", "remember", "current"}
    assert c1.delete(f"/api/auth/sessions/{sid_of(b2['access_token'])}").status_code == 200
    assert c2.get("/api/auth/me").status_code == 401 and c1.get("/api/auth/me").status_code == 200
    # another person's session id is simply "not found" and stays alive
    assert c1.delete(f"/api/auth/sessions/{sid_of(ob['access_token'])}").status_code == 404
    assert other.get("/api/auth/me").status_code == 200


def test_session_cap_revokes_the_oldest(monkeypatch):
    monkeypatch.setattr(settings, "MAX_SESSIONS_PER_USER", 3)
    uid_name = make_user("OPERATOR", PW)
    clients = [login(uid_name=uid_name)[0] for _ in range(4)]
    assert clients[0].get("/api/auth/me").status_code == 401           # oldest was ended
    assert all(c.get("/api/auth/me").status_code == 200 for c in clients[1:])


# ---------------------------------------------------------------- invalidation after security-relevant changes

def test_password_change_ends_all_other_sessions_and_keeps_this_device_signed_in():
    c1, b1, uid, name = login()
    c2, _, _, _ = login(uid_name=(uid, name))
    r = c1.post("/api/auth/me/password", json={"current_password": PW, "new_password": "N3w!Passw0rd-ok"})
    assert r.status_code == 200 and r.json()["sessions_ended"] >= 2
    assert c2.get("/api/auth/me").status_code == 401                    # other device signed out
    assert c1.get("/api/auth/me").status_code == 401                    # the old token of THIS device too
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}      # ...but a new session was issued for it
    assert c1.get("/api/auth/me", headers=fresh).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": "N3w!Passw0rd-ok"}).status_code == 200


def test_admin_password_reset_of_a_public_account_ends_its_sessions():
    from tests.conftest import sign_in
    admin = sign_in(TestClient(app), "admin")
    c, _, uid, _ = login("CITIZEN")
    assert admin.patch(f"/api/auth/users/{uid}", json={"new_password": "Reset!Passw0rd1"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_admin_can_revoke_all_sessions_of_an_account():
    from tests.conftest import sign_in
    admin = sign_in(TestClient(app), "admin")
    c, _, uid, _ = login("OPERATOR")
    assert admin.post(f"/api/auth/users/{uid}/revoke-sessions").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    assert sign_in(TestClient(app), "commander").post(f"/api/auth/users/{uid}/revoke-sessions").status_code == 403


def test_register_starts_a_session_too():
    c = TestClient(app)
    import uuid
    r = c.post("/api/auth/register", json={"role": "CITIZEN", "username": f"reg{uuid.uuid4().hex[:6]}", "full_name": "Reg Person",
                                           "password": PW, "phone": "9999999999"})
    assert r.status_code == 201 and r.json()["csrf_token"] and c.cookies.get(settings.REFRESH_COOKIE_NAME)


# ---------------------------------------------------------------- emergency reporting never depends on a login

@pytest.mark.parametrize("bad", ["garbage", "expired", "revoked"])
def test_a_stale_or_invalid_login_cannot_block_an_emergency_report(bad):
    c, body, uid, _ = login()
    if bad == "garbage":
        token = "definitely.not.valid"
    elif bad == "expired":
        token = create_access_token(uid, sid_of(body["access_token"]), 0, minutes=-5)
    else:
        c.post("/api/auth/logout"); token = body["access_token"]
    r = TestClient(app).post("/api/public/reports", headers={"Authorization": f"Bearer {token}"}, json=dict(
        title="Water rising", description="Street is flooding fast", area="Hebbal", latitude=13.0, longitude=77.6,
        severity="LOW", people_affected=1))
    assert r.status_code == 201
