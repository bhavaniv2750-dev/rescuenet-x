"""S1 + S5: development-only behaviour must never switch on by accident in production.

Each check runs in a fresh interpreter with its own throw-away database, because the environment is read at start-up.

S5 CHANGES to this file (documented in docs/security/S5_ACCOUNTS_AGENCIES.md, "Changed existing tests"):
* production no longer creates an `admin` account from RESCUENET_ADMIN_PASSWORD / .admin_password: it creates NO account, and the
  first administrator comes from scripts/bootstrap_admin.py (tests/test_s5_bootstrap_demo_scripts.py);
* SEED_DEMO_USERS in production is no longer silently ignored: the server REFUSES to start;
* there is no built-in demo password, so the login probe uses a random per-run value.
The assertions are stricter than before (nothing may exist, nothing may start), not weaker.
"""

import json
import secrets
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
GOOD_JWT = "j" * 48

SCRIPT = r"""
import json, os
from fastapi.testclient import TestClient
from app.db.init_db import init_db
init_db()
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import User
c = TestClient(app)
db = SessionLocal()
users = sorted(u.username for u in db.query(User).all())
portals = c.get("/api/auth/portals").json()
login = c.post("/api/auth/login", json={"portal": "operations", "username": "commander", "password": os.environ.get("PROBE_PW", "x")}).status_code
lora = c.post("/api/incidents/lora", json={"beacon_id": "BCN-001", "latitude": 12.9, "longitude": 77.6, "battery_pct": 50, "gateway_readings": []}).status_code
print(json.dumps({"users": users, "demo_mode": portals["demo_mode"], "portal_keys": sorted(portals), "login": login, "lora": lora,
                  "demo_flags": sorted(u.username for u in db.query(User).filter(User.is_demo.is_(True)))}))
"""


def _env(tmp_path, **env):
    base = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'e.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
            "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": GOOD_JWT,
            "MFA_ENCRYPTION_KEYS": __import__("os").environ["MFA_ENCRYPTION_KEYS"]}
    base.update(env)
    return base


def run(tmp_path, **env):
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=_env(tmp_path, **env), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def run_expect_refusal(tmp_path, **env):
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=_env(tmp_path, **env), capture_output=True, text=True)
    assert r.returncode != 0
    return r.stderr


def test_production_creates_no_account_at_all(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production")
    assert out["users"] == []
    assert out["login"] == 401


def test_production_ignores_an_admin_password_variable_and_writes_no_password_file(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production", RESCUENET_ADMIN_PASSWORD="Adm1n!Pass-for-test")
    assert out["users"] == []
    assert not (BACKEND / ".admin_password").exists()


def test_production_refuses_to_start_with_demo_seeding_switched_on(tmp_path):
    err = run_expect_refusal(tmp_path, RESCUENET_ENV="production", SEED_DEMO_USERS="1", DEMO_USER_PASSWORD="Chosen-pw-1")
    assert "DEMO_SEEDING_IN_PRODUCTION" in err and "Chosen-pw-1" not in err


def test_production_never_advertises_demo_mode_or_credentials(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production")
    assert out["demo_mode"] is False and "demo_password" not in out["portal_keys"] and "demo_accounts" not in out["portal_keys"]


def test_unset_environment_means_production(tmp_path):
    out = run(tmp_path)  # RESCUENET_ENV not set at all
    assert out["users"] == [] and out["demo_mode"] is False


def test_production_lora_intake_is_closed_until_a_gateway_key_is_configured(tmp_path):
    (tmp_path / "k").mkdir()
    assert run(tmp_path, RESCUENET_ENV="production")["lora"] == 503
    assert run(tmp_path / "k", RESCUENET_ENV="production", LORA_GATEWAY_KEY="a-real-gateway-key")["lora"] == 401  # key required


def test_development_creates_no_account_unless_fixtures_are_explicitly_enabled(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="development")
    assert out["users"] == [] and out["demo_mode"] is False


def test_development_fixtures_are_flagged_use_a_chosen_password_and_never_a_built_in_one(tmp_path):
    pw = "Fx1-" + secrets.token_urlsafe(10)
    out = run(tmp_path, RESCUENET_ENV="development", SEED_DEMO_USERS="true", DEMO_USER_PASSWORD=pw, PROBE_PW=pw)
    assert "commander" in out["users"] and out["demo_mode"] is True and out["login"] == 200
    assert out["demo_flags"] == out["users"]          # every fixture account is marked as a demo account
    assert "demo_password" not in out["portal_keys"]


def test_development_fixtures_without_a_chosen_password_get_a_random_one_printed_once(tmp_path):
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, capture_output=True, text=True,
                       env=_env(tmp_path, RESCUENET_ENV="development", SEED_DEMO_USERS="true", PROBE_PW="Rescue" + "@2026"))
    assert r.returncode == 0, r.stderr[-500:]
    assert json.loads(r.stdout.strip().splitlines()[-1])["login"] == 401       # the former built-in password does not work
    assert "shared password (shown once" in r.stdout


def test_a_misspelt_environment_name_refuses_to_start(tmp_path):
    r = subprocess.run([sys.executable, "-c", "import app.core.config"], cwd=BACKEND, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "RESCUENET_ENV": "Dev"})
    assert r.returncode != 0 and "RESCUENET_ENV" in r.stderr
