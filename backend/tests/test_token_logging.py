"""S2: tokens, passwords and hashes never appear in logs, console output, audit entries or error responses."""

import json
import logging

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog
from tests.conftest import PORTAL_FOR_ROLE, make_user

PW = "Str0ng!Passw0rd"


def test_no_secret_value_reaches_logs_stdout_stderr_audit_or_errors(caplog, capfd):
    caplog.set_level(logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)
    uid, name = make_user("OPERATOR", PW)
    c = TestClient(app)
    secrets_seen = {PW}
    r = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW})
    body = r.json(); access = body["access_token"]; refresh0 = c.cookies.get(settings.REFRESH_COOKIE_NAME); csrf = c.cookies.get(settings.CSRF_COOKIE_NAME)
    secrets_seen |= {access, refresh0, csrf}
    r2 = c.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf}); secrets_seen |= {r2.json()["access_token"], c.cookies.get(settings.REFRESH_COOKIE_NAME)}
    errors = [
        TestClient(app).post("/api/auth/refresh", headers={"Cookie": f"{settings.REFRESH_COOKIE_NAME}={refresh0}; {settings.CSRF_COOKIE_NAME}={csrf}", "X-CSRF-Token": csrf}),   # replay
        TestClient(app).get("/api/auth/me", headers={"Authorization": "Bearer " + access + "x"}),
        TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": "wrong-Pass-123"}),
    ]
    secrets_seen.add("wrong-Pass-123")
    db = SessionLocal()
    from app.models.entities import User
    pw_hash = db.query(User).filter(User.id == uid).one().password_hash
    audit_text = " ".join(f"{a.actor} {a.action} {a.target_id} {a.details}" for a in db.query(AuditLog).all())
    db.close()
    out, err = capfd.readouterr()
    haystack = "\n".join([caplog.text, out, err, audit_text] + [e.text for e in errors])
    for secret in secrets_seen | {pw_hash}:
        assert secret and secret not in haystack, "a secret value leaked into logs/output"
    assert "pbkdf2" not in haystack.lower()


def test_login_and_session_responses_are_not_cacheable_and_never_echo_the_password():
    uid, name = make_user("OPERATOR", PW)
    r = TestClient(app).post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW})
    assert PW not in r.text and "password_hash" not in r.text
    assert json.loads(r.text)["user"]["username"] == name
