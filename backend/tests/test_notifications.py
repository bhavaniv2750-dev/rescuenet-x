"""S3: notification transports, honest delivery status, and no leakage of codes."""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import NotificationOutbox
from app.services import notifications as notif
from tests.conftest import PORTAL_FOR_ROLE, latest_dev_message, make_user_with_email, with_prod_admin

BACKEND = Path(__file__).resolve().parent.parent
PW = "Str0ng!Passw0rd"


def signed_in(**kw):
    uid, name, email = make_user_with_email("CITIZEN", **kw)
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    return c, uid, email


class FakeSMTP:
    sent, fail, logged_in = [], None, []

    def __init__(self, host, port, timeout=None):
        if FakeSMTP.fail == "connect":
            raise ConnectionRefusedError("secret-host-details")
        self.host = host

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.tls = True
    def login(self, user, pw): FakeSMTP.logged_in.append((user, pw))
    def send_message(self, msg):
        if FakeSMTP.fail == "send":
            raise RuntimeError("550 mailbox unavailable for private@address.example")
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.fail, FakeSMTP.logged_in = [], None, []
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    for k, v in dict(SMTP_HOST="smtp.example.test", SMTP_FROM="noreply@rescuenet.example", SMTP_USER="mailer", SMTP_PASSWORD="smtp-secret-pw-123").items():
        monkeypatch.setattr(settings, k, v)
    return FakeSMTP


def test_development_outbox_is_labelled_and_never_claims_delivery():
    c, uid, _ = signed_in()
    r = c.post("/api/auth/verify/email/request").json()
    assert r["delivery_status"] == "NOT_DELIVERED_DEV"
    row = latest_dev_message(uid, "EMAIL_VERIFY")
    assert row.transport == "DEV_OUTBOX" and row.delivery_status == "NOT_DELIVERED_DEV"
    assert "nothing was delivered" in r["message"].lower()
    assert notif.DEV_NOTICE.startswith("DEVELOPMENT OUTBOX") and "nothing was delivered" in notif.DEV_NOTICE.lower()


def test_dev_outbox_endpoint_lists_messages_with_the_notice_in_development():
    c, uid, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    r = TestClient(app).get("/api/dev/outbox")
    assert r.status_code == 200 and "nothing was delivered" in r.json()["notice"].lower()
    assert any(m["purpose"] == "EMAIL_VERIFY" and "verification code" in m["body"] for m in r.json()["items"])


def test_dev_outbox_endpoint_is_404_for_non_local_callers(monkeypatch):
    c, uid, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    r = TestClient(app).get("/api/dev/outbox", headers={"X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 404


def test_smtp_acceptance_is_reported_as_accepted_not_delivered(smtp):
    c, uid, _ = signed_in()
    r = c.post("/api/auth/verify/email/request")
    assert r.status_code == 200 and r.json()["delivery_status"] == "ACCEPTED_BY_SMTP"
    assert len(smtp.sent) == 1 and smtp.sent[0]["To"] and smtp.logged_in == [("mailer", "smtp-secret-pw-123")]
    text = r.json()["message"].lower()
    assert "delivered" not in text.replace("not guaranteed", "") and "not guaranteed" in text
    db = SessionLocal()
    row = db.query(NotificationOutbox).filter(NotificationOutbox.user_id == uid, NotificationOutbox.transport == "SMTP").one()
    db.close()
    assert row.delivery_status == "ACCEPTED_BY_SMTP" and row.body is None and "confirmed" in row.detail     # no body, honest detail


def test_smtp_failure_is_reported_as_failed_and_leaves_no_live_code(smtp, caplog):
    caplog.set_level(logging.DEBUG)
    smtp.fail = "send"
    c, uid, _ = signed_in()
    r = c.post("/api/auth/verify/email/request")
    assert r.status_code == 502
    db = SessionLocal()
    row = db.query(NotificationOutbox).filter(NotificationOutbox.user_id == uid).order_by(NotificationOutbox.id.desc()).first()
    live = db.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM one_time_tokens WHERE user_id=:u AND expires_at > :n"), {"u": uid, "n": __import__("app.services.verification", fromlist=["now"]).now()}).scalar()
    db.close()
    assert row.delivery_status == "FAILED" and live == 0
    assert "private@address.example" not in caplog.text and "550" not in caplog.text       # error text is never logged
    assert "smtp-secret-pw-123" not in caplog.text


def test_smtp_connection_error_does_not_leak_details(smtp):
    smtp.fail = "connect"
    c, uid, _ = signed_in()
    r = c.post("/api/auth/verify/email/request")
    assert r.status_code == 502 and "secret-host" not in r.text


def test_the_body_with_the_code_is_stored_only_for_the_development_outbox(smtp):
    c, uid, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    db = SessionLocal()
    assert db.query(NotificationOutbox).filter(NotificationOutbox.user_id == uid, NotificationOutbox.body.isnot(None)).count() == 0
    db.close()


def test_recipients_are_masked_in_the_outbox_table():
    c, uid, email = signed_in()
    c.post("/api/auth/verify/email/request")
    db = SessionLocal()
    row = db.query(NotificationOutbox).filter(NotificationOutbox.user_id == uid).one()
    db.close()
    assert email not in row.recipient_masked and row.recipient_masked.endswith("@example.org") and "***" in row.recipient_masked


def test_sms_transport_is_always_disabled_until_a_provider_exists():
    assert notif.sms_transport().name == "DISABLED"
    res = notif.sms_transport().send(notif.Message("SMS", "+911234567890", "x", "your code is 123456", "PHONE_VERIFY"))
    assert res.status == "DISABLED"
    caps = notif.capabilities()
    assert caps["sms_delivery"]["delivers_to_real_phones"] is False and caps["phone_verification_available"] is False


def test_capabilities_endpoint_is_public_and_holds_no_secrets(smtp):
    r = TestClient(app).get("/api/auth/capabilities")
    assert r.status_code == 200
    body = r.text
    for secret in ("smtp-secret-pw-123", "mailer", "smtp.example.test", "noreply@"):
        assert secret not in body
    assert r.json()["email_delivery"] == {"transport": "SMTP", "delivers_to_real_mailboxes": True}


def test_codes_do_not_appear_in_logs_or_stdout(caplog, capfd):
    caplog.set_level(logging.DEBUG)
    c, uid, _ = signed_in()
    c.post("/api/auth/verify/email/request")
    code = re.search(r"code is (\d{6})", latest_dev_message(uid, "EMAIL_VERIFY").body).group(1)
    out, err = capfd.readouterr()
    assert code not in caplog.text and code not in out and code not in err


# ---------------------------------------------------------------- production (fresh interpreter)

PROD_SCRIPT = r"""
import json, re
from fastapi.testclient import TestClient
from app.db.init_db import init_db
init_db()
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import User, NotificationOutbox
from app.core.security import hash_password
db = SessionLocal()
db.add(User(username="p_user", full_name="P User", role="CITIZEN", email="p_user@example.org", password_hash=hash_password("Str0ng!Passw0rd"),
            email_verified_at=None))
db.commit()
c = TestClient(app)
tok = c.post("/api/auth/login", json={"portal": "public", "username": "p_user", "password": "Str0ng!Passw0rd"}).json()["access_token"]
h = {"Authorization": "Bearer " + tok}
verify = c.post("/api/auth/verify/email/request", headers=h)
forgot = c.post("/api/auth/password/forgot", json={"identifier": "p_user"})
outbox = c.get("/api/dev/outbox")
caps = c.get("/api/auth/capabilities").json()
db2 = SessionLocal()
print(json.dumps({"verify": verify.status_code, "verify_detail": verify.json().get("detail", ""), "forgot": forgot.status_code,
                  "outbox": outbox.status_code, "caps": caps, "rows": db2.query(NotificationOutbox).count(),
                  "codes_stored": db2.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM one_time_tokens")).scalar()}))
"""


def run_prod(tmp_path, **env):
    base = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'n.db'}", "UPLOAD_DIR": str(tmp_path / "up"),
            "BACKUP_DIR": str(tmp_path / "bk"), "JWT_SECRET": "p" * 48,
            "MFA_ENCRYPTION_KEYS": __import__("os").environ["MFA_ENCRYPTION_KEYS"]}
    base.update(env)
    r = subprocess.run([sys.executable, "-c", with_prod_admin(PROD_SCRIPT)], cwd=BACKEND, env=base, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout.strip().splitlines()[-1]), r


def test_production_without_smtp_delivers_nothing_stores_no_codes_and_hides_the_outbox(tmp_path):
    out, proc = run_prod(tmp_path, RESCUENET_ENV="production")
    assert out["verify"] == 503 and "not available" in out["verify_detail"] and out["forgot"] == 503
    assert out["outbox"] == 404
    assert out["caps"]["email_delivery"] == {"transport": "DISABLED", "delivers_to_real_mailboxes": False}
    assert out["codes_stored"] == 0 and out["rows"] == 0           # no code was even generated


def test_production_never_prints_codes(tmp_path):
    out, proc = run_prod(tmp_path, RESCUENET_ENV="production")
    assert not re.search(r"\b\d{6}\b.*verification|verification code is", proc.stdout + proc.stderr)
