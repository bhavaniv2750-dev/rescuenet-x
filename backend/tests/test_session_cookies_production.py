"""S2: cookie attributes in production, and that production defaults cannot be weakened. Fresh interpreter per case."""

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

SCRIPT = r"""
import json
from fastapi.testclient import TestClient
from app.db.init_db import init_db
init_db()
from app.main import app
c = TestClient(app, base_url="https://testserver")
r = c.post("/api/auth/login", json={"portal": "admin", "username": "admin", "password": "Adm1n!Pass-for-test"})
print(json.dumps({"status": r.status_code, "cookies": r.headers.get_list("set-cookie"),
                  "origin_check": TestClient(app).post("/api/auth/refresh", headers={"Origin": "https://evil.example"}).status_code}))
"""


def run(tmp_path, **env):
    base = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'p.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
            "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": "test-secret-not-for-production-use-1234567890",
            "RESCUENET_ADMIN_PASSWORD": "Adm1n!Pass-for-test"}
    base.update(env)
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=base, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def cookie(out, name):
    return next(c.lower() for c in out["cookies"] if c.lower().startswith(name + "="))


def test_production_cookies_are_httponly_secure_and_samesite_strict(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production")
    assert out["status"] == 200
    refresh, csrf = cookie(out, "rn_refresh"), cookie(out, "rn_csrf")
    assert all(x in refresh for x in ("httponly", "secure", "samesite=strict", "path=/api/auth"))
    assert "secure" in csrf and "samesite=strict" in csrf and "httponly" not in csrf


def test_unset_environment_is_production_so_cookies_are_secure_by_default(tmp_path):
    out = run(tmp_path)
    assert "secure" in cookie(out, "rn_refresh")


def test_development_is_the_only_mode_with_relaxed_cookie_flags(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="development", SEED_DEMO_USERS="false")
    refresh = cookie(out, "rn_refresh")
    assert "httponly" in refresh and "samesite=lax" in refresh and "secure" not in refresh


def test_dev_origin_allowance_is_not_available_in_production(tmp_path):
    prod = run(tmp_path, RESCUENET_ENV="production")
    assert prod["origin_check"] in (401, 403)          # refused (no cookie => 401 first; with a cookie the evil origin => 403)


def test_a_setting_cannot_turn_off_secure_cookies_in_production(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production", COOKIE_SECURE="false")      # there is deliberately no such switch
    assert "secure" in cookie(out, "rn_refresh")
