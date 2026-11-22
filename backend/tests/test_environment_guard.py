"""S1: development-only behaviour must never switch on by accident in production.

Each check runs in a fresh interpreter with its own throw-away database, because the environment is read at start-up.
Protections that are deferred to S5 (disabling demo accounts that ALREADY exist in a database, removing the demo password
from the source, first-admin CLI) are listed in docs/security/S1_AUTHORIZATION.md.
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

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
login = c.post("/api/auth/login", json={"portal": "operations", "username": "commander", "password": "Rescue@2026"}).status_code
lora = c.post("/api/incidents/lora", json={"beacon_id": "BCN-001", "latitude": 12.9, "longitude": 77.6, "battery_pct": 50, "gateway_readings": []}).status_code
print(json.dumps({"users": users, "demo_mode": portals["demo_mode"], "demo_accounts": len(portals["demo_accounts"]),
                  "demo_password": portals["demo_password"], "login": login, "lora": lora}))
"""


def run(tmp_path, **env):
    base = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'e.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
            "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": "test-secret-not-for-production",
            "RESCUENET_ADMIN_PASSWORD": "Adm1n!Pass-for-test", "SEED_DEMO_USERS": "true"}
    base.update(env)
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=base, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_production_never_creates_demo_accounts_even_if_seeding_is_switched_on(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production")
    assert out["users"] == ["admin"]                 # only the configured administrator
    assert out["login"] == 401                        # the well-known demo credentials do not work


def test_production_never_advertises_demo_credentials(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production")
    assert out["demo_mode"] is False and out["demo_accounts"] == 0 and out["demo_password"] is None


def test_unset_environment_means_production(tmp_path):
    out = run(tmp_path)  # RESCUENET_ENV not set at all
    assert out["users"] == ["admin"] and out["demo_password"] is None


def test_production_lora_intake_is_closed_until_a_gateway_key_is_configured(tmp_path):
    (tmp_path / "k").mkdir()
    assert run(tmp_path, RESCUENET_ENV="production")["lora"] == 503
    assert run(tmp_path / "k", RESCUENET_ENV="production", LORA_GATEWAY_KEY="a-real-gateway-key")["lora"] == 401  # key required


def test_development_still_offers_demo_accounts_for_local_work(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="development")
    assert "commander" in out["users"] and "developer" in out["users"] and out["demo_mode"] is True
    assert out["login"] == 200


def test_development_flag_is_not_enabled_by_demo_seeding_alone(tmp_path):
    out = run(tmp_path, RESCUENET_ENV="production", SEED_DEMO_USERS="1", DEMO_USER_PASSWORD="Rescue@2026")
    assert "commander" not in out["users"]


def test_a_misspelt_environment_name_refuses_to_start(tmp_path):
    r = subprocess.run([sys.executable, "-c", "import app.core.config"], cwd=BACKEND, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "RESCUENET_ENV": "Dev"})
    assert r.returncode != 0 and "RESCUENET_ENV" in r.stderr
