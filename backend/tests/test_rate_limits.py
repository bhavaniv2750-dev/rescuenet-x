"""S3: rate limiting backed by a shared, persistent store (the application database).

Covers every limiter named in the S3 brief: login, registration, verification attempts and resends, password recovery
requests and reset attempts, guest emergency reports, guest tracking lookups and guest image uploads. Several worker
processes are simulated with real subprocesses that share the database file.
"""

import io
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import RateLimitEvent
from app.services import rate_limit
from tests.conftest import PORTAL_FOR_ROLE, make_user, make_user_with_email

BACKEND = Path(__file__).resolve().parent.parent
PW = "Str0ng!Passw0rd"
REPORT = dict(title="Water rising", description="Street is flooding fast", area="Hebbal", latitude=13.0, longitude=77.6, severity="LOW", people_affected=1)


def png():
    b = io.BytesIO(); Image.new("RGB", (16, 16), (1, 2, 3)).save(b, format="PNG"); return b.getvalue()


def worker(code):
    """Run code in a separate Python process (a second 'worker') against the same database."""
    r = subprocess.run([sys.executable, "-c", "import sys\nfrom app.services import rate_limit as rl\n" + code], cwd=BACKEND,
                       env=dict(os.environ), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    return r.stdout.strip()


# ---------------------------------------------------------------- shared and persistent

def test_events_are_stored_in_the_database_not_in_process_memory():
    rate_limit.check("probe-bucket", "k1", 5, 3600)
    db = SessionLocal()
    assert db.query(RateLimitEvent).filter(RateLimitEvent.bucket == "probe-bucket").count() == 1
    db.close()


def test_two_worker_processes_share_one_counter():
    code = ("from fastapi import HTTPException\nn=0\n"
            "for _ in range(2):\n    try:\n        rl.check('xworker', 'same-key', 3, 3600); n+=1\n    except HTTPException: pass\nprint(n)")
    assert worker(code) == "2"              # worker A uses 2 of the 3 allowed events
    assert worker(code) == "1"              # worker B only gets 1: the counter is shared
    with pytest.raises(Exception) as e:
        rate_limit.check("xworker", "same-key", 3, 3600)   # and so does this process
    assert getattr(e.value, "status_code", None) == 429


def test_counters_survive_a_restart():
    for _ in range(2):
        rate_limit.check("persist", "k", 2, 3600)
    out = worker("from fastapi import HTTPException\ntry:\n    rl.check('persist', 'k', 2, 3600); print('allowed')\nexcept HTTPException as e:\n    print(e.status_code)")
    assert out == "429"


def test_window_slides_old_events_stop_counting():
    rate_limit.check("slide", "k", 1, 3600)
    db = SessionLocal()
    from datetime import timedelta
    db.query(RateLimitEvent).filter(RateLimitEvent.bucket == "slide").update({"created_at": rate_limit._now() - timedelta(hours=2)}); db.commit(); db.close()
    rate_limit.check("slide", "k", 1, 3600)          # the old event is outside the window: allowed again


def test_the_store_holds_only_keyed_hashes_never_addresses_or_identifiers():
    c = TestClient(app)
    c.post("/api/auth/login", json={"portal": "public", "username": "victim.person@example.org", "password": "x-wrong-1"})
    c.post("/api/public/reports", json=REPORT)
    raw = sqlite3.connect(str(SessionLocal().get_bind().url).replace("sqlite:///", ""))
    rows = raw.execute("SELECT bucket, key_hash FROM rate_limit_events").fetchall()
    assert rows and all(len(h) == 32 and all(ch in "0123456789abcdef" for ch in h) for _, h in rows)
    blob = " ".join(f"{b} {h}" for b, h in rows)
    assert "victim.person" not in blob and "testclient" not in blob and "127.0.0.1" not in blob
    raw.close()


def test_rejected_requests_do_not_consume_extra_capacity():
    for _ in range(3):
        rate_limit.check("cap", "k", 3, 3600)
    for _ in range(5):
        with pytest.raises(Exception):
            rate_limit.check("cap", "k", 3, 3600)
    db = SessionLocal()
    assert db.query(RateLimitEvent).filter(RateLimitEvent.bucket == "cap").count() == 3          # refused attempts left no rows
    db.close()


# ---------------------------------------------------------------- failure policy

def broken_store(monkeypatch):
    def boom(*a, **k):
        raise OperationalError("select", {}, Exception("database is locked"))
    monkeypatch.setattr(rate_limit, "SessionLocal", boom)


def test_emergency_endpoints_fail_open_when_the_store_is_down(monkeypatch):
    broken_store(monkeypatch)
    assert TestClient(app).post("/api/public/reports", json=REPORT).status_code == 201
    up = TestClient(app).post("/api/incidents/upload-image", files={"file": ("p.png", png(), "image/png")})
    assert up.status_code == 201


def test_authentication_endpoints_fail_closed_when_the_store_is_down(monkeypatch):
    uid, name = make_user("CITIZEN", PW)
    broken_store(monkeypatch)
    r = TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": PW})
    assert r.status_code == 503
    assert TestClient(app).post("/api/auth/password/forgot", json={"identifier": name}).status_code == 503
    assert TestClient(app).post("/api/auth/password/reset", json={"token": "A" * 43, "new_password": PW}).status_code == 503


# ---------------------------------------------------------------- login

def test_login_failures_are_limited_per_account_and_the_answer_is_the_same_for_unknown_accounts():
    uid, name = make_user("CITIZEN", PW)
    def attempt(user):
        return TestClient(app).post("/api/auth/login", json={"portal": "public", "username": user, "password": "wrong-Pass-1"})
    real = [attempt(name).status_code for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN + 1)]
    ghost = [attempt("ghost_no_such_user").status_code for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN + 1)]
    assert real == ghost == [401] * settings.LOGIN_PER_ACCOUNT_15MIN + [429]               # identical pattern: nothing to enumerate
    blocked_real, blocked_ghost = attempt(name), attempt("ghost_no_such_user")
    assert blocked_real.json() == blocked_ghost.json() and blocked_real.headers["retry-after"] == blocked_ghost.headers["retry-after"]


def test_correct_password_is_also_refused_while_an_account_is_locked_out():
    uid, name = make_user("CITIZEN", PW)
    for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN):
        TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": "wrong-Pass-1"})
    assert TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).status_code == 429


def test_successful_logins_do_not_count_against_the_account_limit():
    uid, name = make_user("CITIZEN", PW)
    for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN + 3):
        assert TestClient(app).post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).status_code == 200


def test_login_is_limited_per_client_address(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_PER_IP_15MIN", 4)
    codes = [TestClient(app).post("/api/auth/login", json={"portal": "public", "username": f"nobody{i}", "password": "x-wrong-1"}).status_code for i in range(6)]
    assert codes == [401, 401, 401, 401, 429, 429]


def test_one_accounts_lockout_does_not_lock_other_accounts():
    uid1, n1 = make_user("CITIZEN", PW); uid2, n2 = make_user("CITIZEN", PW)
    for _ in range(settings.LOGIN_PER_ACCOUNT_15MIN):
        TestClient(app).post("/api/auth/login", json={"portal": "public", "username": n1, "password": "wrong-Pass-1"})
    assert TestClient(app).post("/api/auth/login", json={"portal": "public", "username": n2, "password": PW}).status_code == 200


# ---------------------------------------------------------------- registration

def test_registration_is_limited_per_address(monkeypatch):
    monkeypatch.setattr(settings, "REGISTER_PER_IP_HOUR", 3)
    def reg():
        return TestClient(app).post("/api/auth/register", json={"role": "CITIZEN", "username": f"r{uuid.uuid4().hex[:8]}", "full_name": "Reg Person",
                                                                "password": PW, "phone": "9999999999"})
    assert [reg().status_code for _ in range(5)] == [201, 201, 201, 429, 429]


# ---------------------------------------------------------------- verification and recovery (more in their own suites)

def test_verification_resend_and_attempt_limits_exist(monkeypatch):
    monkeypatch.setattr(settings, "VERIFY_SEND_PER_ACCOUNT_HOUR", 1)
    monkeypatch.setattr(settings, "VERIFY_RESEND_COOLDOWN_S", 0)
    uid, name, _ = make_user_with_email("CITIZEN")
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).json()["access_token"]
    assert c.post("/api/auth/verify/email/request").status_code == 200
    assert c.post("/api/auth/verify/email/request").status_code == 429
    monkeypatch.setattr(settings, "VERIFY_CONFIRM_PER_ACCOUNT_HOUR", 2)
    assert [c.post("/api/auth/verify/email/confirm", json={"code": "999999"}).status_code for _ in range(3)] == [400, 400, 429]


def test_recovery_request_and_reset_limits_exist(monkeypatch):
    monkeypatch.setattr(settings, "FORGOT_PER_IP_HOUR", 2)
    monkeypatch.setattr(settings, "RESET_PER_IP_HOUR", 2)
    assert [TestClient(app).post("/api/auth/password/forgot", json={"identifier": f"x{i}"}).status_code for i in range(3)] == [202, 202, 429]
    assert [TestClient(app).post("/api/auth/password/reset", json={"token": "B" * 43, "new_password": PW}).status_code for i in range(3)] == [400, 400, 429]


# ---------------------------------------------------------------- guest emergency endpoints (S0 limits, now on the shared store)

def test_guest_report_limit_is_shared_across_workers():
    code = ("from fastapi import HTTPException\nn=0\n"
            "for _ in range(6):\n    try:\n        rl.check('report-guest', 'shared-guest', 10, 3600, fail_open=True); n+=1\n    except HTTPException: pass\nprint(n)")
    assert worker(code) == "6" and worker(code) == "4"      # 10 reports per hour in total, not per worker


def test_guest_report_upload_and_tracking_limits_still_apply(monkeypatch):
    assert settings.GUEST_REPORTS_PER_HOUR == 10
    g = TestClient(app)
    assert [g.post("/api/public/reports", json=REPORT).status_code for _ in range(10)] == [201] * 10
    r = g.post("/api/public/reports", json=REPORT)
    assert r.status_code == 429 and "112" in r.json()["detail"]
    rate_limit.reset_all()
    monkeypatch.setattr(settings, "GUEST_UPLOADS_PER_HOUR", 2)
    assert [g.post("/api/incidents/upload-image", files={"file": ("p.png", png(), "image/png")}).status_code for _ in range(3)] == [201, 201, 429]
    monkeypatch.setattr(settings, "TRACKING_FAILURES_PER_15_MIN", 2)
    codes = [g.get("/api/public/reports/RN-0000-0000-0000", headers={"X-Tracking-Code": "0000-0000-0000-0000-0000"}).status_code for _ in range(3)]
    assert codes == [404, 404, 429]


def test_429_responses_always_carry_retry_after():
    for _ in range(11):
        r = TestClient(app).post("/api/public/reports", json=REPORT)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
