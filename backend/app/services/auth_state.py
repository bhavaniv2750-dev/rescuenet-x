"""The authentication state machine, enforced by the backend on every request.

                 password OK + MFA enabled           correct code / recovery code
 UNAUTHENTICATED ------------------------------> MFA_CHALLENGE_PENDING ------------------+
      |  (login returns a challenge, NO session)   (5 min, 5 tries, single use)           |
      |                                                                                   v
      | password OK, MFA not required or not enrolled ------------------------------> [session issued]
      v                                                                                   |
   state of a SESSION is computed from the account on every request, first match wins:    |
     1. PASSWORD_CHANGE_PENDING      must_change_password (break-glass / admin reset)     |
     2. CONTACT_VERIFICATION_PENDING (S5) contact verification required, no verified      |
                                     email and no second factor enrolled yet: an invited  |
                                     account proves its mailbox BEFORE enrolling MFA      |
     3. MFA_ENROLLMENT_PENDING       privileged role and no ACTIVE TOTP credential        |
     4. MFA_CHALLENGE_PENDING        privileged/enrolled account but THIS session never   |
                                     completed a second factor (e.g. a pre-S4 session)   |
     5. CONTACT_VERIFICATION_PENDING same requirement for an account that already has MFA |
     6. AUTHENTICATED                everything else                                      |
   Contact verification is required when the ACCOUNT is flagged (every invited / host-created privileged account) or when the
   production policy PRIVILEGED_REQUIRE_VERIFIED_EMAIL applies to a privileged role, unless a host operator recorded a waiver.
   SESSION_ENDED = expired / revoked / replay / password or role change -> 401 (sessions.py)

Only AUTHENTICATED sessions reach operational endpoints. The other states reach a short allow-list (below). Refresh-token
rotation keeps the same session row, so it cannot raise a session's assurance.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.models.entities import AuthSession, User

UNAUTHENTICATED = "UNAUTHENTICATED"
MFA_CHALLENGE_PENDING = "MFA_CHALLENGE_PENDING"
PASSWORD_CHANGE_PENDING = "PASSWORD_CHANGE_PENDING"
MFA_ENROLLMENT_PENDING = "MFA_ENROLLMENT_PENDING"
CONTACT_VERIFICATION_PENDING = "CONTACT_VERIFICATION_PENDING"
AUTHENTICATED = "AUTHENTICATED"
SESSION_ENDED = "SESSION_ENDED"

ALL_STATES = [UNAUTHENTICATED, MFA_CHALLENGE_PENDING, PASSWORD_CHANGE_PENDING, MFA_ENROLLMENT_PENDING,
              CONTACT_VERIFICATION_PENDING, AUTHENTICATED, SESSION_ENDED]

_BASE = {"/api/auth/me", "/api/auth/logout", "/api/auth/logout-all"}
ALLOWED_PATHS = {
    PASSWORD_CHANGE_PENDING: _BASE | {"/api/auth/me/password"},
    MFA_ENROLLMENT_PENDING: _BASE | {"/api/auth/me/password", "/api/auth/mfa/status", "/api/auth/mfa/enroll/start", "/api/auth/mfa/enroll/confirm"},
    MFA_CHALLENGE_PENDING: set(_BASE),
    CONTACT_VERIFICATION_PENDING: _BASE | {"/api/auth/me/password", "/api/auth/mfa/status", "/api/auth/me/contact",
                                            "/api/auth/verify/email/request", "/api/auth/verify/email/confirm"},
}
RESTRICTED_HEADER = "X-Auth-State"


def contact_verification_pending(user: User) -> bool:
    """True when the account must still prove control of its email address (and has no host-recorded waiver)."""
    if user.email_verified_at is not None or user.contact_verification_waived_at is not None:
        return False
    privileged = user.role not in ("CITIZEN", "VOLUNTEER")
    return bool(user.contact_verification_required or (privileged and settings.PRIVILEGED_REQUIRE_VERIFIED_EMAIL))


def session_state(user: User, session: Optional[AuthSession], mfa_enabled: bool) -> str:
    """State of an authenticated session (the account is looked at NOW, not at sign-in time)."""
    if user.must_change_password:
        return PASSWORD_CHANGE_PENDING
    required = user.role not in ("CITIZEN", "VOLUNTEER")
    pending = contact_verification_pending(user)
    if pending and not mfa_enabled:
        return CONTACT_VERIFICATION_PENDING
    if required and not mfa_enabled:
        return MFA_ENROLLMENT_PENDING
    if (required or mfa_enabled) and (session is None or session.assurance != "MFA"):
        return MFA_CHALLENGE_PENDING
    if pending:
        return CONTACT_VERIFICATION_PENDING
    return AUTHENTICATED


def path_allowed(state: str, path: str) -> bool:
    if state == AUTHENTICATED:
        return True
    return path.rstrip("/") in ALLOWED_PATHS.get(state, set())
