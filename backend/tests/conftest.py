"""Shared pytest setup.

The SQLite database file is not committed to the repository, so a fresh clone
has no tables. This file points the app at a throwaway database for the test
session and seeds it with the same data the app uses on start-up.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEST_DB_DIR = tempfile.mkdtemp(prefix="rescuenet_test_")
# The tests ALWAYS run against a throw-away database and a throw-away upload/backup directory, whatever the shell environment says
# (a developer's DATABASE_URL must never be touched by the test suite). Found when a test run inherited a demo database URL.
os.environ["RESCUENET_ENV"] = "development"
# A fresh throw-away MFA encryption key for the whole test run (never a fixed value in the repository).
import base64 as _b64, secrets as _sec
os.environ.setdefault("MFA_ENCRYPTION_KEYS", "test:" + _b64.urlsafe_b64encode(_sec.token_bytes(32)).decode().rstrip("="))
# Tests sign in as the same demo users hundreds of times; the production cap (10 sessions per user) is tested explicitly.
os.environ.setdefault("MAX_SESSIONS_PER_USER", "100000")
# S5: there is no built-in demo password. The development fixtures are created with a fresh random password for this run only.
os.environ["SEED_DEMO_USERS"] = "true"
DEMO_PASSWORD = "Dm1-" + _sec.token_urlsafe(12)
os.environ["DEMO_USER_PASSWORD"] = DEMO_PASSWORD
os.environ["UPLOAD_DIR"] = str(Path(_TEST_DB_DIR) / "uploads")
os.environ["BACKUP_DIR"] = str(Path(_TEST_DB_DIR) / "backups")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DB_DIR) / 'test_rescuenet.db'}"


import uuid

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.services import rate_limit
    rate_limit.reset_all()
    yield


@pytest.fixture(autouse=True)
def _restore_rescue_fleet():
    """Dispatching now really deploys a team, so a test that dispatches would otherwise use up the shared
    seeded teams for every later test. Team statuses are put back after each test, and any team the test
    created is parked on STANDBY so it cannot be chosen by another test."""
    from app.db.session import SessionLocal
    from app.models.entities import RescueTeam

    db = SessionLocal()
    saved = {t.id: t.status for t in db.query(RescueTeam).all()}
    db.close()
    yield
    db = SessionLocal()
    for t in db.query(RescueTeam).all():
        t.status = saved.get(t.id, "STANDBY")
    db.commit()
    db.close()


def make_team(client, lat=12.9300, lon=77.6200, tag="test"):
    """Create a fresh AVAILABLE rescue team through the API and return its id."""
    r = client.post("/api/teams/", json=dict(
        name=f"Test team {tag}", callsign=f"T{uuid.uuid4().hex[:6]}", vehicle_type="boat", members_count=4,
        skills="water rescue", latitude=lat, longitude=lon, base_station="Test base", contact_number="100"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def pytest_configure(config):
    from app.db.init_db import init_db

    init_db()


_MFA_SECRETS = {}      # user id -> base32 secret of accounts enrolled by the helpers below (test harness only)


def enroll_mfa_directly(user_id):
    """Give an account an ACTIVE TOTP credential, as the enrolment flow would leave it (encrypted secret). Returns the base32
    secret. The enrolment FLOW itself is tested through the API in tests/test_mfa_*.py."""
    from app.db.session import SessionLocal
    from app.models.entities import MfaCredential
    from app.services import mfa as mfa_svc, mfa_crypto

    secret = mfa_svc.new_secret()
    db = SessionLocal()
    try:
        db.query(MfaCredential).filter(MfaCredential.user_id == user_id).delete()
        db.add(MfaCredential(user_id=user_id, secret_enc=mfa_crypto.encrypt(secret, user_id), status="ACTIVE",
                             confirmed_at=mfa_svc.now(), last_used_step=None))
        db.commit()
    finally:
        db.close()
    _MFA_SECRETS[user_id] = secret
    return secret


def mfa_secret_of(user_id):
    return _MFA_SECRETS[user_id]


def totp_code(secret, offset_steps=0):
    from app.services import mfa as mfa_svc
    return mfa_svc.code_for_step(secret, mfa_svc.current_step() + offset_steps)


def _forget_replay(user_id):
    """Rapid test logins reuse the same 30 s step; clearing the stored step lets the HELPER sign in repeatedly. Replay
    prevention itself is tested without this helper."""
    from app.db.session import SessionLocal
    from app.models.entities import MfaCredential

    db = SessionLocal()
    db.query(MfaCredential).filter(MfaCredential.user_id == user_id).update({"last_used_step": None})
    db.commit()
    db.close()


def login_complete(client, portal, username, password, remember=False, secret=None):
    """Password step, then the second factor if the account has one. Returns the final login response (which carries the
    access token). Accounts without MFA return the password response (restricted for privileged roles)."""
    r = client.post("/api/auth/login", json={"portal": portal, "username": username, "password": password, "remember": remember})
    if r.status_code == 200 and r.json().get("status") == "mfa_required":
        from app.db.session import SessionLocal
        from app.models.entities import User
        db = SessionLocal(); uid = db.query(User).filter(User.username == username).one().id; db.close()
        secret = secret or _MFA_SECRETS[uid]
        _forget_replay(uid)
        r = client.post("/api/auth/mfa/verify", json={"challenge_token": r.json()["challenge_token"], "code": totp_code(secret)})
    return r


_DEMO_PRIVILEGED = {"admin", "developer", "commander", "operator", "officer"}


def sign_in(client, username: str = "commander", portal: str = None):
    """Log a demo account in (completing MFA for the privileged ones) and set its token on the client. Returns the client."""
    portals = {"admin": "admin", "developer": "admin", "commander": "operations", "operator": "operations",
               "officer": "operations", "volunteer": "public", "citizen": "public"}
    if username in _DEMO_PRIVILEGED:
        from app.db.session import SessionLocal
        from app.models.entities import User
        db = SessionLocal(); uid = db.query(User).filter(User.username == username).one().id; db.close()
        if uid not in _MFA_SECRETS:
            enroll_mfa_directly(uid)
    r = login_complete(client, portal or portals[username], username, DEMO_PASSWORD)
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client


def make_user(role: str = "OPERATOR", password: str = "Str0ng!Passw0rd", team_id=None, prefix: str = "tmp", mfa: bool = False):
    """Create an account directly in the database. Administrators can no longer provision staff accounts through the API
    (S2), so tests that need a throw-away staff account insert it here, as a host operator would. Returns (id, username)."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.entities import User

    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        u = User(username=name, full_name=f"Temp {role.title()}", role=role, password_hash=hash_password(password), team_id=team_id)
        db.add(u)
        db.commit()
        uid = u.id
    finally:
        db.close()
    if mfa:
        enroll_mfa_directly(uid)         # secret available through mfa_secret_of(uid)
    return uid, name


PORTAL_FOR_ROLE = {"ADMIN": "admin", "DEVELOPER": "admin", "COMMANDER": "operations", "OPERATOR": "operations",
                   "RESCUE_OFFICER": "operations", "VOLUNTEER": "public", "CITIZEN": "public"}


def latest_dev_message(user_id=None, purpose=None):
    """Newest message in the development outbox (the only place a code or reset link is ever readable)."""
    from app.db.session import SessionLocal
    from app.models.entities import NotificationOutbox

    db = SessionLocal()
    try:
        q = db.query(NotificationOutbox).filter(NotificationOutbox.transport == "DEV_OUTBOX")
        if user_id is not None:
            q = q.filter(NotificationOutbox.user_id == user_id)
        if purpose:
            q = q.filter(NotificationOutbox.purpose == purpose)
        return q.order_by(NotificationOutbox.id.desc()).first()
    finally:
        db.close()


def make_user_with_email(role="CITIZEN", email=None, verified=False, password="Str0ng!Passw0rd", changed_hours_ago=None, mfa=False):
    """Account with an email address, optionally already verified (set directly: simulates a completed verification)."""
    from datetime import datetime, timedelta, timezone
    from app.db.session import SessionLocal
    from app.models.entities import User

    uid, name = make_user(role, password, prefix="s3", mfa=mfa)
    email = email or f"{name}@example.org"
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        u.email = email
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        u.email_verified_at = now if verified else None
        if changed_hours_ago is not None:
            u.email_changed_at = now - timedelta(hours=changed_hours_ago)
        db.commit()
    finally:
        db.close()
    return uid, name, email


@pytest.fixture(autouse=True)
def _recent_mfa_for_existing_sessions():
    """Sessions created at collection time (module-level sign-ins) can be minutes old by the time a test runs, which would
    trip the 5-minute freshness rule for approvals. Refresh their MFA timestamp before each test (test harness only; the
    freshness rule itself is tested by setting mfa_at explicitly inside those tests)."""
    from app.db.session import SessionLocal
    from app.models.entities import AuthSession
    from app.services import mfa as mfa_svc

    db = SessionLocal()
    db.query(AuthSession).filter(AuthSession.assurance == "MFA", AuthSession.revoked_at.is_(None)).update({"mfa_at": mfa_svc.now()})
    db.commit()
    db.close()
    yield


def enroll_via_api(client, password, headers=None):
    """Enrol TOTP through the real endpoints (start with the password, confirm with a valid code). Returns
    (secret, recovery_codes). `headers` overrides the client's Authorization (e.g. a just-issued token)."""
    h = headers or {}
    r = client.post("/api/auth/mfa/enroll/start", json={"current_password": password}, headers=h)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    c = client.post("/api/auth/mfa/enroll/confirm", json={"code": totp_code(secret)}, headers=h)
    assert c.status_code == 200, c.text
    return secret, c.json()["recovery_codes"]


# S5: production no longer creates any account by itself. Subprocess tests that need a production-mode administrator insert one
# directly after start-up initialisation, exactly as a host operator's provisioning would leave it (password chosen by the test).
PROD_TEST_ADMIN_PASSWORD = "Adm1n!Pass-for-test"
PROD_TEST_JWT_SECRET = "p" * 48
_PROD_ADMIN_SNIPPET = (
    "\nfrom app.core.security import hash_password as _hp\nfrom app.db.session import SessionLocal as _SL\n"
    "from app.models.entities import User as _U\n_db = _SL()\n"
    "_db.add(_U(username='admin', full_name='Test Admin', role='ADMIN', password_hash=_hp('" + PROD_TEST_ADMIN_PASSWORD + "')))\n"
    "_db.commit(); _db.close()\n")


def with_prod_admin(script: str) -> str:
    return script.replace("\ninit_db()\n", "\ninit_db()" + _PROD_ADMIN_SNIPPET, 1)
