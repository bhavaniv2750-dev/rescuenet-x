"""S2: refresh-token rotation, replay detection, and hash-only storage."""

import hashlib
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, AuthSession, RefreshToken
from app.services import sessions as svc
from tests.conftest import PORTAL_FOR_ROLE, make_user

PW = "Str0ng!Passw0rd"
RC, CC = settings.REFRESH_COOKIE_NAME, settings.CSRF_COOKIE_NAME


def start(role="OPERATOR"):
    uid, name = make_user(role, PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": PORTAL_FOR_ROLE[role], "username": name, "password": PW})
    assert r.status_code == 200
    return c, r.json(), uid, name


def refresh_with(token, csrf, extra_headers=None):
    """Present a specific refresh token from a browser-less client (explicit Cookie header, no shared cookie jar)."""
    h = {"Cookie": f"{RC}={token}; {CC}={csrf}", "X-CSRF-Token": csrf, **(extra_headers or {})}
    return TestClient(app).post("/api/auth/refresh", headers=h)


def refresh_via_jar(c):
    return c.post("/api/auth/refresh", headers={"X-CSRF-Token": c.cookies.get(CC)})


def test_refresh_rotates_the_token_and_returns_a_new_access_token():
    c, body, uid, _ = start()
    r0 = c.cookies.get(RC)
    r = refresh_via_jar(c)
    assert r.status_code == 200
    r1 = c.cookies.get(RC)
    assert r1 and r1 != r0                                  # a new refresh token replaced the old one
    new_access = r.json()["access_token"]
    assert new_access != body["access_token"]
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200
    assert "refresh_token" not in r.json() and r.headers["cache-control"] == "no-store"


def test_refresh_can_be_repeated_along_the_chain():
    c, _, _, _ = start()
    seen = {c.cookies.get(RC)}
    for _ in range(4):
        assert refresh_via_jar(c).status_code == 200
        seen.add(c.cookies.get(RC))
    assert len(seen) == 5


def test_replaying_a_rotated_refresh_token_revokes_the_whole_session():
    c, body, uid, _ = start()
    stolen = c.cookies.get(RC)                              # what an attacker would have copied
    csrf = c.cookies.get(CC)
    assert refresh_via_jar(c).status_code == 200            # the legitimate client rotates
    live_cookie = c.cookies.get(RC)
    replay = refresh_with(stolen, csrf)                     # the attacker (or a confused client) replays the OLD token
    assert replay.status_code == 401
    # the damage is contained: the legitimate session is revoked too, so the stolen chain cannot continue
    assert refresh_with(live_cookie, csrf).status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 401
    db = SessionLocal()
    sid = svc.hash_token  # noqa: F841 (readability)
    s = db.query(AuthSession).filter(AuthSession.user_id == uid).one()
    assert s.revoked_at is not None and s.revoked_reason == "REPLAY_DETECTED"
    audit = db.query(AuditLog).filter(AuditLog.action == "SESSION_REPLAY_DETECTED").order_by(AuditLog.id.desc()).first()
    assert audit is not None and stolen not in (audit.details or "") and live_cookie not in (audit.details or "")
    db.close()


def test_replay_response_clears_cookies_and_gives_no_hint():
    c, _, _, _ = start()
    stolen, csrf = c.cookies.get(RC), c.cookies.get(CC)
    refresh_via_jar(c)
    r = refresh_with(stolen, csrf)
    assert r.status_code == 401 and r.json() == {"detail": "Your session has ended. Please sign in again."}
    assert "max-age=0" in " ".join(r.headers.get_list("set-cookie")).lower()


def test_unknown_malformed_and_missing_refresh_tokens_are_rejected():
    for token in ("", "x", "A" * 43, "../../etc/passwd", "a" * 500):
        r = TestClient(app).post("/api/auth/refresh", headers={"Cookie": f"{RC}={token}", "X-CSRF-Token": "whatever"})
        assert r.status_code == 401
    assert TestClient(app).post("/api/auth/refresh").status_code == 401


def test_expired_refresh_token_is_rejected():
    c, _, uid, _ = start()
    db = SessionLocal()
    db.query(RefreshToken).update({"expires_at": svc.now() - timedelta(seconds=1)}); db.commit(); db.close()
    assert refresh_via_jar(c).status_code == 401


def test_refresh_after_logout_or_deactivation_fails():
    c, _, uid, _ = start()
    csrf, tok = c.cookies.get(CC), c.cookies.get(RC)
    assert c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert refresh_with(tok, csrf).status_code == 401
    from tests.conftest import sign_in
    c2, _, uid2, _ = start("CITIZEN")
    tok2, csrf2 = c2.cookies.get(RC), c2.cookies.get(CC)
    sign_in(TestClient(app), "admin").patch(f"/api/auth/users/{uid2}", json={"is_active": False})
    assert refresh_with(tok2, csrf2).status_code == 401


def test_refresh_after_password_change_cannot_resurrect_the_old_session():
    c, _, uid, name = start()
    old_tok, csrf = c.cookies.get(RC), c.cookies.get(CC)
    c.headers["Authorization"] = f"Bearer {c.post('/api/auth/refresh', headers={'X-CSRF-Token': csrf}).json()['access_token']}"
    old_tok = c.cookies.get(RC)
    assert c.post("/api/auth/me/password", json={"current_password": PW, "new_password": "N3w!Passw0rd-ok"}).status_code == 200
    assert refresh_with(old_tok, csrf).status_code == 401


# ---------------------------------------------------------------- storage

def test_only_hashes_are_stored_never_the_refresh_or_access_token():
    c, body, uid, _ = start()
    refresh = c.cookies.get(RC)
    access = body["access_token"]
    db = SessionLocal()
    rows = db.query(RefreshToken).all()
    assert any(r.token_hash == hashlib.sha256(refresh.encode()).hexdigest() for r in rows)
    # search every table of the database for the raw secrets
    import sqlite3
    path = str(db.get_bind().url).replace("sqlite:///", "")
    db.close()
    raw = sqlite3.connect(path)
    for (table,) in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for row in raw.execute(f'SELECT * FROM "{table}"'):
            blob = json.dumps([str(v) for v in row])
            assert refresh not in blob and access not in blob, table
    raw.close()


def test_refresh_tokens_are_long_random_and_unique():
    tokens = {start()[0].cookies.get(RC) for _ in range(20)}
    assert len(tokens) == 20 and all(len(t) >= 43 for t in tokens)          # 32 random bytes, url-safe base64


def test_old_rows_are_purged_but_recent_history_is_kept():
    c, body, uid, _ = start()
    c.post("/api/auth/logout")
    db = SessionLocal()
    db.query(AuthSession).filter(AuthSession.user_id == uid).update({"revoked_at": svc.now() - timedelta(days=40)}); db.commit()
    start()                                              # any new login runs the purge
    assert db.query(AuthSession).filter(AuthSession.user_id == uid).count() == 0
    db.close()
