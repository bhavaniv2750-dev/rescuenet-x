"""S5: host-authorised first-admin bootstrap, safe disabling of known demo accounts, production credential hygiene, start-up validation.

Scripts run in a fresh interpreter against a throw-away database (never the shared test database).
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
GOOD_JWT = "j" * 48
HISTORIC = "Rescue" + "@2026"                 # the retired default demo password; built in pieces so source scans stay clean


def env_for(tmp_path, **extra):
    e = {"PATH": "/usr/bin:/bin:/usr/local/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 's5.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
         "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": GOOD_JWT, "RESCUENET_ENV": "production",
         "MFA_ENCRYPTION_KEYS": os.environ["MFA_ENCRYPTION_KEYS"]}
    e.update(extra)
    return e


def script(tmp_path, name, *args, stdin=None, **extra):
    return subprocess.run([sys.executable, str(BACKEND / "scripts" / name), *args], cwd=BACKEND, env=env_for(tmp_path, **extra),
                          capture_output=True, text=True, input=stdin)


def py(tmp_path, code, **extra):
    r = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env_for(tmp_path, **extra), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""


def db_rows(tmp_path, sql):
    con = sqlite3.connect(tmp_path / "s5.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


BOOT = ["--username", "firstadmin", "--full-name", "First Admin", "--email", "first.admin@example.org",
        "--reason", "initial deployment test", "--i-am-authorized"]


# ====================================================================== first administrator

def test_bootstrap_needs_explicit_authorisation_and_a_reason(tmp_path):
    r = script(tmp_path, "bootstrap_admin.py", "--username", "firstadmin", "--full-name", "A", "--email", "a@example.org", "--reason", "initial deployment")
    assert r.returncode == 2
    r = script(tmp_path, "bootstrap_admin.py", "--username", "firstadmin", "--full-name", "A", "--email", "a@example.org", "--reason", "x", "--i-am-authorized")
    assert r.returncode == 2
    assert not (tmp_path / "s5.db").exists() or db_rows(tmp_path, "SELECT COUNT(*) FROM users") == [(0,)]


def test_bootstrap_creates_one_restricted_admin_with_a_one_time_password_and_audits_it(tmp_path):
    r = script(tmp_path, "bootstrap_admin.py", *BOOT)
    assert r.returncode == 0, r.stderr
    pw = re.search(r"not stored anywhere in clear\): (\S+)", r.stdout).group(1)
    row = db_rows(tmp_path, "SELECT username, role, must_change_password, contact_verification_required, email_verified_at, password_hash, is_demo, email FROM users")
    assert len(row) == 1
    username, role, must_change, contact_req, verified, pw_hash, is_demo, email = row[0]
    assert (username, role, must_change, contact_req, verified, is_demo, email) == ("firstadmin", "ADMIN", 1, 1, None, 0, "first.admin@example.org")
    assert pw not in pw_hash and pw_hash.startswith("pbkdf2_sha256$")
    audit = db_rows(tmp_path, "SELECT actor, action, details FROM audit_logs WHERE action='FIRST_ADMIN_BOOTSTRAPPED'")
    assert len(audit) == 1 and audit[0][0].startswith("cli:") and pw not in audit[0][2]
    assert list((tmp_path / "bk").glob("*pre-bootstrap-admin*"))                       # verified backup taken first
    # nothing written anywhere on disk in clear
    for f in list(tmp_path.rglob("*")) + [BACKEND / ".admin_password"]:
        if f.is_file() and f.suffix not in (".db", ".bak"):
            assert pw not in f.read_text(errors="ignore")
    # the account has no permission until it changed the password, verified the contact and enrolled MFA
    state = py(tmp_path, "from app.db.session import SessionLocal\nfrom app.models.entities import User\nfrom app.services import auth_state as a\n"
                         "u=SessionLocal().query(User).one()\nprint(a.session_state(u,None,False))")
    assert state == "PASSWORD_CHANGE_PENDING"


def test_bootstrap_cannot_be_repeated_while_a_real_administrator_exists(tmp_path):
    assert script(tmp_path, "bootstrap_admin.py", *BOOT).returncode == 0
    again = script(tmp_path, "bootstrap_admin.py", "--username", "secondadmin", "--full-name", "Second", "--email", "second@example.org",
                   "--reason", "attempted takeover", "--i-am-authorized")
    assert again.returncode == 3 and "already exists" in again.stderr
    assert db_rows(tmp_path, "SELECT COUNT(*) FROM users") == [(1,)]


def test_bootstrap_has_no_default_password_and_no_public_endpoint(tmp_path):
    src = (BACKEND / "scripts" / "bootstrap_admin.py").read_text()
    assert 'add_argument("--password' not in src and "prov.one_time_password()" in src and "os.getenv" not in src and "os.environ" not in src
    code = ("from fastapi.testclient import TestClient\nfrom app.main import app\nc=TestClient(app)\n"
            "print([ (m,p) for p,ms in app.openapi()['paths'].items() for m in ms if 'bootstrap' in p or 'setup' in p or 'first' in p])")
    assert py(tmp_path, code) == "[]"


def test_two_bootstrap_runs_one_after_the_other_create_exactly_one_account(tmp_path):
    a = script(tmp_path, "bootstrap_admin.py", *BOOT)
    b = script(tmp_path, "bootstrap_admin.py", *BOOT)
    assert (a.returncode, b.returncode) == (0, 3)


# ====================================================================== demo-account disabling

SEED = """
from app.db.migrations import ensure_schema
from app.db.session import SessionLocal, engine
from app.core.security import hash_password
from app.models.entities import User, AuthSession
ensure_schema(engine)
db = SessionLocal()
legacy = hash_password("{historic}")
rows = [("admin","System Administrator","ADMIN","admin@rescuenet.local"),("commander","Incident Commander (Demo)","COMMANDER","commander@rescuenet.local"),
        ("operator","Control Room Operator (Demo)","OPERATOR","operator@rescuenet.local"),("citizen","Citizen Reporter (Demo)","CITIZEN","citizen@rescuenet.local")]
for n, f, r, e in rows: db.add(User(username=n, full_name=f, role=r, email=e, password_hash=legacy))
# a REAL person whose username merely resembles a demo account, and a real administrator
db.add(User(username="developer", full_name="Priya Nair", role="DEVELOPER", email="priya@agency.example", password_hash=hash_password("Real!Pass-word-1")))
db.add(User(username="realadmin", full_name="Real Admin", role="ADMIN", email="real.admin@agency.example", password_hash=hash_password("Real!Pass-word-2")))
db.commit()
# the demo commander has a live session
from app.services import sessions as s
u = db.query(User).filter(User.username=="commander").one()
db.add(AuthSession(id="sess-demo-1", user_id=u.id, created_at=s.now() if hasattr(s,"now") else __import__("datetime").datetime.utcnow(),
        last_used_at=__import__("datetime").datetime.utcnow(), expires_at=__import__("datetime").datetime(2999,1,1), idle_timeout_s=3600, remember=False))
db.commit()
print("seeded")
"""


def seeded(tmp_path):
    assert py(tmp_path, SEED.replace("{historic}", HISTORIC)) == "seeded"


def snapshot(tmp_path):
    return db_rows(tmp_path, "SELECT id, username, role, is_active, password_hash, token_version, is_demo FROM users ORDER BY id")


def test_dry_run_lists_candidates_and_changes_nothing(tmp_path):
    seeded(tmp_path)
    before = snapshot(tmp_path)
    r = script(tmp_path, "disable_demo_accounts.py")
    assert r.returncode == 0 and "DRY RUN: 4 demo account(s) recognised" in r.stdout
    assert "NOT TOUCHED    developer" in r.stdout          # same username, different person: never matched by name alone
    assert snapshot(tmp_path) == before and not list((tmp_path / "bk").glob("*")) if (tmp_path / "bk").exists() else True


def test_apply_requires_confirmation_authorisation_and_reason(tmp_path):
    seeded(tmp_path)
    before = snapshot(tmp_path)
    for args in (["--apply"], ["--apply", "--confirm", "wrong phrase", "--reason", "go-live ticket", "--i-am-authorized"],
                 ["--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "go-live ticket"],
                 ["--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "x", "--i-am-authorized"]):
        assert script(tmp_path, "disable_demo_accounts.py", *args).returncode == 2, args
    assert snapshot(tmp_path) == before


def test_apply_disables_only_fingerprinted_demo_accounts_backs_up_revokes_audits_and_deletes_nothing(tmp_path):
    seeded(tmp_path)
    before = snapshot(tmp_path)
    r = script(tmp_path, "disable_demo_accounts.py", "--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "go-live ticket 9", "--i-am-authorized")
    assert r.returncode == 0, r.stderr + r.stdout
    after = {row[1]: row for row in snapshot(tmp_path)}
    assert len(after) == len(before)                                               # nothing deleted
    for name in ("admin", "commander", "operator", "citizen"):
        assert after[name][3] == 0 and after[name][6] == 1 and after[name][5] >= 1  # inactive, flagged demo, sessions invalidated (token_version bumped)
    assert after["developer"][3] == 1 and after["developer"][6] == 0 and after["realadmin"][3] == 1   # real people untouched
    assert db_rows(tmp_path, "SELECT revoked_at IS NOT NULL FROM auth_sessions WHERE id='sess-demo-1'") == [(1,)]
    assert len(db_rows(tmp_path, "SELECT 1 FROM audit_logs WHERE action='DEMO_ACCOUNT_DISABLED'")) == 4
    assert list((tmp_path / "bk").glob("*pre-disable-demo*"))
    # idempotent
    again = script(tmp_path, "disable_demo_accounts.py", "--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "go-live ticket 9", "--i-am-authorized")
    assert again.returncode == 0 and "No active demo account" in again.stdout


def test_it_refuses_to_leave_the_deployment_without_an_administrator(tmp_path):
    seeded(tmp_path)
    py(tmp_path, "from app.db.session import SessionLocal\nfrom app.models.entities import User\ndb=SessionLocal()\n"
                 "db.query(User).filter(User.username=='realadmin').update({'is_active': False})\ndb.commit()\nprint('ok')")
    before = snapshot(tmp_path)
    r = script(tmp_path, "disable_demo_accounts.py", "--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "go-live ticket 9", "--i-am-authorized")
    assert r.returncode == 3 and "NO active administrator" in r.stderr and snapshot(tmp_path) == before
    ok = script(tmp_path, "disable_demo_accounts.py", "--apply", "--confirm", "DISABLE DEMO ACCOUNTS", "--reason", "go-live ticket 9",
                "--i-am-authorized", "--allow-no-admin")
    assert ok.returncode == 0
    assert script(tmp_path, "bootstrap_admin.py", *BOOT).returncode == 0            # and bootstrap then works (demo admin is not "real")


def test_password_check_option_finds_accounts_that_still_use_the_historic_password(tmp_path):
    seeded(tmp_path)
    # change the demo operator's name/email so only the password identifies it
    py(tmp_path, "from app.db.session import SessionLocal\nfrom app.models.entities import User\ndb=SessionLocal()\n"
                 "db.query(User).filter(User.username=='operator').update({'full_name':'Renamed','email':'x@y.example'})\ndb.commit()\nprint('ok')")
    dry = script(tmp_path, "disable_demo_accounts.py", "--also-check-password", stdin=HISTORIC + "\n")
    assert "PASSWORD matched" in dry.stdout and "operator" in dry.stdout
    assert HISTORIC not in dry.stdout + dry.stderr.replace("Password to test against demo usernames (not stored): ", "")
    plain = script(tmp_path, "disable_demo_accounts.py")
    assert "NOT TOUCHED    operator" in plain.stdout                                # without the password check it is left alone


# ====================================================================== repository hygiene

def tracked_text_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.splitlines()
    skip = ("backend/tests/", "docs/", "package-lock.json")
    exts = (".py", ".ts", ".tsx", ".md", ".example", ".json", ".yml", ".yaml", ".cfg", ".ini", ".txt", ".html", ".css", ".js")
    return [REPO / f for f in out if f.endswith(exts) and not f.startswith(skip) and (REPO / f).is_file()]


def test_no_current_source_file_contains_the_retired_demo_password():
    hits = [str(f.relative_to(REPO)) for f in tracked_text_files() if HISTORIC in f.read_text(errors="ignore")]
    assert hits == [], f"retired demo password still present in: {hits}"


def test_no_demo_credential_mechanism_remains_in_code_or_frontend():
    patterns = [r"\bdemo_password\b", r"\bdemo_accounts\b", r"\bADMIN_PASSWORD\b", r"RESCUENET_ADMIN_PASSWORD", r"Tap one to fill", r"\.admin_password"]
    code_files = [f for f in tracked_text_files() if f.suffix in (".py", ".ts", ".tsx")]
    bad = [(str(f.relative_to(REPO)), p) for f in code_files for p in patterns if re.search(p, f.read_text(errors="ignore"))]
    assert bad == [], bad


def test_the_env_example_documents_no_password_default():
    text = (REPO / ".env.example").read_text()
    assert re.search(r"^DEMO_USER_PASSWORD=\s*$", text, re.M) or "DEMO_USER_PASSWORD" not in text
    assert "RESCUENET_ADMIN_PASSWORD" not in text and re.search(r"^SEED_DEMO_USERS=false", text, re.M)


# ====================================================================== start-up validation

def good_prod(monkeypatch):
    from app.core.config import settings
    for k, v in dict(RESCUENET_ENV="production", JWT_SECRET=GOOD_JWT, SEED_DEMO_USERS=False, DEMO_USER_PASSWORD="",
                     CORS_ORIGINS_PRODUCTION="https://rescue.example.org", INVITATION_HOURS=72,
                     PUBLIC_APP_URL="https://rescue.example.org", SMTP_HOST="", SMTP_FROM="").items():
        monkeypatch.setattr(settings, k, v)
    return settings


def levels(findings):
    return {f.code: f.level for f in findings}


def test_a_correct_production_configuration_has_no_fatal_finding(monkeypatch):
    from app.services import startup_checks as sc
    good_prod(monkeypatch)
    lv = levels(sc.evaluate())
    assert "FATAL" not in lv.values()
    assert lv["EMAIL_UNAVAILABLE"] == "WARNING"            # honest: no provider is configured, so email is unavailable
    sc.enforce()


@pytest.mark.parametrize("field,value,code", [
    ("JWT_SECRET", "", "JWT_SECRET_WEAK"), ("JWT_SECRET", "short-secret", "JWT_SECRET_WEAK"),
    ("SEED_DEMO_USERS", True, "DEMO_SEEDING_IN_PRODUCTION"), ("DEMO_USER_PASSWORD", "anything-at-all-1", "DEMO_PASSWORD_IN_PRODUCTION"),
    ("CORS_ORIGINS_PRODUCTION", "http://localhost:5175", "LOCALHOST_ORIGIN_IN_PRODUCTION"),
    ("INVITATION_HOURS", 0, "INVITATION_HOURS_RANGE"), ("INVITATION_HOURS", 500, "INVITATION_HOURS_RANGE"),
    ("DATABASE_URL", " ", "DATABASE_URL_EMPTY"),
])
def test_unsafe_production_settings_are_fatal(monkeypatch, field, value, code):
    from app.services import startup_checks as sc
    s = good_prod(monkeypatch)
    monkeypatch.setattr(s, field, value)
    assert levels(sc.evaluate())[code] == "FATAL"
    with pytest.raises(RuntimeError) as exc:
        sc.enforce()
    assert code in str(exc.value) and (str(value).strip() == "" or len(str(value)) < 6 or str(value) not in str(exc.value))   # no secret echoed


def test_invalid_mfa_keys_are_fatal_in_production(monkeypatch):
    from app.services import mfa_crypto, startup_checks as sc
    s = good_prod(monkeypatch)
    monkeypatch.setattr(s, "MFA_ENCRYPTION_KEYS", "nonsense")
    assert levels(sc.evaluate())["MFA_KEYS_INVALID"] == "FATAL"


def test_in_development_the_same_gaps_are_only_warnings(monkeypatch):
    from app.services import startup_checks as sc
    s = good_prod(monkeypatch)
    monkeypatch.setattr(s, "RESCUENET_ENV", "development")
    monkeypatch.setattr(s, "JWT_SECRET", "")
    monkeypatch.setattr(s, "SEED_DEMO_USERS", True)
    lv = levels(sc.evaluate())
    assert lv["JWT_SECRET_WEAK"] == "WARNING" and lv["DEMO_FIXTURES_ENABLED"] == "WARNING" and "FATAL" not in lv.values()
    assert lv["EMAIL_DEV_OUTBOX"] == "INFO"


def test_smtp_is_never_reported_as_verified_and_unreachable_verification_is_called_out(monkeypatch):
    from app.services import startup_checks as sc
    s = good_prod(monkeypatch)
    monkeypatch.setattr(s, "SMTP_HOST", "smtp.example.org"); monkeypatch.setattr(s, "SMTP_FROM", "noreply@example.org")
    msg = next(f.message for f in sc.evaluate() if f.code == "EMAIL_SMTP")
    assert "NOT been verified" in msg
    monkeypatch.setattr(s, "SMTP_HOST", ""); monkeypatch.setattr(s, "SMTP_FROM", "")
    monkeypatch.setattr(s, "PRIVILEGED_REQUIRE_VERIFIED_EMAIL", True)
    assert levels(sc.evaluate())["VERIFIED_EMAIL_UNREACHABLE"] == "WARNING"


def test_check_config_script_exit_codes_and_no_secret_output(tmp_path):
    bad = script(tmp_path, "check_config.py", JWT_SECRET="x" * 10)
    assert bad.returncode == 1 and "FATAL" in bad.stdout and "JWT_SECRET_WEAK" in bad.stdout
    good = script(tmp_path, "check_config.py", CORS_ORIGINS_PRODUCTION="https://rescue.example.org", PUBLIC_APP_URL="https://rescue.example.org")
    assert good.returncode == 0, good.stdout
    assert GOOD_JWT not in good.stdout + bad.stdout and os.environ["MFA_ENCRYPTION_KEYS"].split(":")[1] not in good.stdout


def test_production_refuses_to_start_unsafe_and_does_not_allow_localhost_origins(tmp_path):
    start = "import app.main\nprint('started')"
    r = subprocess.run([sys.executable, "-c", start], cwd=BACKEND, env=env_for(tmp_path, JWT_SECRET="tiny"), capture_output=True, text=True)
    assert r.returncode != 0 and "JWT_SECRET_WEAK" in r.stderr
    probe = ("from fastapi.testclient import TestClient\nfrom app.main import app\nc=TestClient(app)\n"
             "h={'Origin':'http://localhost:5175','Access-Control-Request-Method':'GET'}\n"
             "print(c.options('/api/auth/portals',headers=h).headers.get('access-control-allow-origin'))")
    assert py(tmp_path, probe) == "None"                         # no development origin is trusted in production
    allowed = py(tmp_path, probe.replace("localhost:5175", "rescue.example.org").replace("http://", "https://"),
                 CORS_ORIGINS_PRODUCTION="https://rescue.example.org")
    assert allowed == "https://rescue.example.org"
