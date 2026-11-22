"""S2: CSRF protection for the cookie-authenticated endpoints (refresh, cookie logout). SameSite is not relied on alone:
every such request needs an allowed Origin (when sent) AND an X-CSRF-Token that matches the CSRF cookie AND the session."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuthSession, RefreshToken
from tests.conftest import PORTAL_FOR_ROLE, make_user, sign_in

PW = "Str0ng!Passw0rd"
RC, CC = settings.REFRESH_COOKIE_NAME, settings.CSRF_COOKIE_NAME


def start(role="OPERATOR"):
    uid, name = make_user(role, PW)
    c = TestClient(app)
    c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    return c, uid


def unused_tokens(uid):
    db = SessionLocal()
    try:
        sids = [s.id for s in db.query(AuthSession).filter(AuthSession.user_id == uid).all()]
        return db.query(RefreshToken).filter(RefreshToken.session_id.in_(sids), RefreshToken.used_at.is_(None)).count()
    finally:
        db.close()


def live_sessions(uid):
    db = SessionLocal()
    try:
        return db.query(AuthSession).filter(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None)).count()
    finally:
        db.close()


def forged(c, **headers):
    """What a cross-site request can do: the browser attaches the cookies by itself, but the attacker cannot read the CSRF
    cookie, so it cannot set a valid X-CSRF-Token header."""
    return TestClient(app).post("/api/auth/refresh", headers={"Cookie": f"{RC}={c.cookies.get(RC)}; {CC}={c.cookies.get(CC)}", **headers})


def test_refresh_without_csrf_header_is_refused_and_consumes_nothing():
    c, uid = start()
    before = unused_tokens(uid)
    r = forged(c)
    assert r.status_code == 403
    assert "set-cookie" not in r.headers                       # a forged request must not log the victim out
    assert unused_tokens(uid) == before
    assert c.post("/api/auth/refresh", headers={"X-CSRF-Token": c.cookies.get(CC)}).status_code == 200   # the real client still works


@pytest.mark.parametrize("token", ["", "wrong", "0" * 64])
def test_refresh_with_wrong_csrf_header_is_refused(token):
    c, _ = start()
    assert forged(c, **{"X-CSRF-Token": token}).status_code == 403


def test_double_submit_cookie_must_match_the_header():
    c, _ = start()
    good = c.cookies.get(CC)
    r = TestClient(app).post("/api/auth/refresh", headers={"Cookie": f"{RC}={c.cookies.get(RC)}; {CC}=attacker-chosen", "X-CSRF-Token": good})
    assert r.status_code == 403                                  # header right, cookie planted: still refused


def test_csrf_value_is_bound_to_the_session_so_another_sessions_value_is_useless():
    c1, _ = start()
    c2, _ = start()
    r = TestClient(app).post("/api/auth/refresh", headers={
        "Cookie": f"{RC}={c1.cookies.get(RC)}; {CC}={c2.cookies.get(CC)}", "X-CSRF-Token": c2.cookies.get(CC)})
    assert r.status_code == 403


def test_a_cross_site_origin_is_refused_even_with_a_valid_token():
    c, _ = start()
    good = {"X-CSRF-Token": c.cookies.get(CC)}
    assert forged(c, **good, Origin="https://evil.example").status_code == 403
    assert forged(c, **good, Origin="http://localhost:9999").status_code == 403            # not an allowed dev port
    assert forged(c, **good, Origin="null").status_code == 403


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5175", "http://localhost:5173", "http://testserver"])   # dev servers; same origin
def test_allowed_origins_work(origin):
    c, _ = start()
    assert forged(c, **{"X-CSRF-Token": c.cookies.get(CC)}, Origin=origin).status_code == 200


def test_trusted_origins_setting_allows_a_reverse_proxy_origin(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_ORIGINS", "https://rescue.example.org")
    c, _ = start()
    assert forged(c, **{"X-CSRF-Token": c.cookies.get(CC)}, Origin="https://rescue.example.org").status_code == 200


def test_cookie_logout_needs_csrf_but_bearer_logout_does_not():
    c, uid = start()
    no_auth = TestClient(app)
    r = no_auth.post("/api/auth/logout", headers={"Cookie": f"{RC}={c.cookies.get(RC)}; {CC}={c.cookies.get(CC)}"})
    assert r.status_code == 403                                  # cross-site logout attack refused
    assert live_sessions(uid) == 1
    ok = no_auth.post("/api/auth/logout", headers={"Cookie": f"{RC}={c.cookies.get(RC)}; {CC}={c.cookies.get(CC)}",
                                                   "X-CSRF-Token": c.cookies.get(CC)})
    assert ok.status_code == 200 and live_sessions(uid) == 0


def test_the_cookies_never_authenticate_any_other_endpoint():
    """Every other state-changing endpoint needs the Authorization header, which a cross-site page cannot add, so they
    are immune to CSRF. The cookie alone must get a 401 everywhere."""
    c, _ = start("COMMANDER")
    cookie_only = {"Cookie": f"{RC}={c.cookies.get(RC)}; {CC}={c.cookies.get(CC)}"}
    for method, path in [("POST", "/api/alerts/"), ("POST", "/api/agents/tasks/X/approve"), ("POST", "/api/teams/T/assign"),
                         ("PATCH", "/api/incidents/X"), ("POST", "/api/auth/me/password"), ("POST", "/api/auth/logout-all"),
                         ("GET", "/api/auth/me"), ("DELETE", "/api/auth/sessions/" + "0" * 32)]:
        r = TestClient(app).request(method, path, headers=cookie_only, json={} if method != "GET" else None)
        assert r.status_code == 401, (method, path, r.status_code)


def test_cors_does_not_allow_other_origins_to_read_auth_responses():
    r = TestClient(app).options("/api/auth/refresh", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
    ok = TestClient(app).options("/api/auth/refresh", headers={"Origin": "http://127.0.0.1:5175", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:5175" and ok.headers.get("access-control-allow-credentials") == "true"
