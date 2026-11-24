"""Start-up configuration validation (S5).

`evaluate()` returns findings of three levels:
  FATAL    the server refuses to start (production only; these would make a production deployment unsafe)
  WARNING  printed at start-up and shown to administrators/developers; the server still starts
  INFO     facts worth knowing (for example which notification transport is active)

Nothing here reads or prints a secret value. It never claims that email works: a missing SMTP configuration is reported as
"email is unavailable", and a development outbox is reported as "nothing is delivered".
Run it on its own, without starting the server: `python scripts/check_config.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse

from app.core.config import settings

FATAL, WARNING, INFO = "FATAL", "WARNING", "INFO"


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


def _loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "")


def evaluate() -> List[Finding]:
    from app.services import mfa_crypto, notifications as notif

    out: List[Finding] = []
    add = lambda level, code, msg: out.append(Finding(level, code, msg))
    prod = settings.is_production
    # In development the same problems are only warnings (a laptop is not a deployment) or not raised at all.
    hard = FATAL if prod else WARNING

    add(INFO, "ENV_MODE", f"RESCUENET_ENV={settings.RESCUENET_ENV}")

    # ---- demo fixtures
    if settings.SEED_DEMO_USERS and prod:
        add(FATAL, "DEMO_SEEDING_IN_PRODUCTION", "SEED_DEMO_USERS is on in production. Demo accounts are never created in production; "
            "remove SEED_DEMO_USERS from the environment.")
    elif settings.SEED_DEMO_USERS:
        add(WARNING, "DEMO_FIXTURES_ENABLED", "Development fixtures are enabled: simulated demo accounts are created on an EMPTY database.")
    if settings.DEMO_USER_PASSWORD and prod:
        add(FATAL, "DEMO_PASSWORD_IN_PRODUCTION", "DEMO_USER_PASSWORD is set in production. Remove it; it has no meaning there.")

    # ---- token signing
    if len(settings.JWT_SECRET) < 32:
        msg = ("JWT_SECRET is missing or shorter than 32 characters. Set a long random secret in the environment "
               "(python -c \"import secrets; print(secrets.token_urlsafe(48))\").")
        add(hard, "JWT_SECRET_WEAK", msg if prod else msg + " In development a random secret is kept in backend/.jwt_secret instead.")

    # ---- MFA keys
    try:
        mfa_crypto.validate_configuration()
        add(INFO, "MFA_KEYS_OK", "MFA encryption key configuration is valid.")
    except mfa_crypto.MfaKeyError as exc:
        add(hard, "MFA_KEYS_INVALID", str(exc))

    # ---- browser origins and cookies
    if prod:
        if not settings.allowed_origins:
            add(WARNING, "NO_CORS_ORIGINS", "No cross-origin browser origin is allowed (CORS_ORIGINS_PRODUCTION is empty). "
                "That is correct for a same-origin deployment; set it if the web app is served from another origin.")
        if any(_loopback(o) for o in settings.allowed_origins):
            add(FATAL, "LOCALHOST_ORIGIN_IN_PRODUCTION", "CORS_ORIGINS_PRODUCTION contains a localhost origin.")
    add(INFO, "COOKIES", "Refresh and CSRF cookies are " + ("Secure (production)." if settings.cookie_secure else "NOT Secure (development over plain http)."))

    # ---- database
    if not settings.DATABASE_URL.strip():
        add(FATAL, "DATABASE_URL_EMPTY", "DATABASE_URL is empty.")
    elif prod and settings.DATABASE_URL.startswith("sqlite"):
        add(WARNING, "SQLITE_IN_PRODUCTION", "SQLite is a single-node database: fine for this project's single-server deployment, "
            "but it cannot be shared by several server processes on different machines. Keep verified backups.")

    # ---- invitations
    if not 1 <= settings.INVITATION_HOURS <= 168:
        add(hard, "INVITATION_HOURS_RANGE", "INVITATION_HOURS must be between 1 and 168.")
    if prod and (_loopback(settings.PUBLIC_APP_URL) or not settings.PUBLIC_APP_URL.startswith("https://")):
        add(WARNING, "PUBLIC_APP_URL", "PUBLIC_APP_URL is not an https address of this deployment: invitation and reset links "
            "would point at the wrong place or travel unencrypted.")

    # ---- notifications (honest about what is and is not available)
    transport = notif.email_transport().name
    if transport == "SMTP":
        add(INFO, "EMAIL_SMTP", "SMTP is configured. Delivery to real mailboxes has NOT been verified by this check.")
    elif transport == "DEV_OUTBOX":
        if prod:
            add(FATAL, "DEV_OUTBOX_IN_PRODUCTION", "The development email outbox is active in production.")
        else:
            add(INFO, "EMAIL_DEV_OUTBOX", "Email is the development outbox: nothing is delivered to any mailbox.")
    else:
        add(WARNING if prod else INFO, "EMAIL_UNAVAILABLE",
            "No email provider is configured: email verification, password recovery by email and emailed invitations are "
            "unavailable. A host operator can still issue an invitation link by hand and, per account, waive contact "
            "verification (account_admin.py waive-contact-verification); this is recorded and never marks an address verified.")
    if settings.PRIVILEGED_REQUIRE_VERIFIED_EMAIL and transport == "DISABLED":
        add(WARNING, "VERIFIED_EMAIL_UNREACHABLE", "Privileged accounts must verify an email address but email is unavailable: "
            "they will stay in the restricted state until a host operator waives verification or an email provider is configured.")
    return out


def enforce() -> List[Finding]:
    """Called at start-up: print warnings, raise on FATAL."""
    findings = evaluate()
    for f in findings:
        if f.level == WARNING:
            print(f"[startup] WARNING {f.code}: {f.message}")
    fatal = [f for f in findings if f.level == FATAL]
    if fatal:
        raise RuntimeError("Refusing to start: unsafe production configuration:\n" +
                           "\n".join(f"  - {f.code}: {f.message}" for f in fatal))
    return findings
