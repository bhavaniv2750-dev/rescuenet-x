"""Authentication dependencies for the API routes."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import permissions as perms
from app.core.config import settings
from app.core.security import decode_access_token
from app.services import auth_state as astate
from app.services import mfa as mfa_svc
from app.services.sessions import check_access_claims
from app.db.session import get_db
from app.models.entities import User

_bearer = HTTPBearer(auto_error=False)


def _user_from_token(creds: Optional[HTTPAuthorizationCredentials], db: Session) -> Optional[User]:
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please sign in again",
                            headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        # malformed, tampered, wrong signature, or the old long-lived format (no session id): all refused the same way
        raise HTTPException(status_code=401, detail="Invalid access token", headers={"WWW-Authenticate": "Bearer"})
    # The token only names a session. The session row, the user's active flag and token version, and (in the routes)
    # the user's CURRENT role and team all come from the database, so revocation and role changes apply immediately.
    user, session = check_access_claims(db, payload)
    # Transient attributes (not columns): the session, and the account's authentication state computed from the database NOW.
    user.session_id = session.id
    user._session = session
    user._mfa_enabled = mfa_svc.is_enabled(db, user.id)
    user.auth_state = astate.session_state(user, session, user._mfa_enabled)
    return user


_STATE_MESSAGES = {
    astate.PASSWORD_CHANGE_PENDING: ("You must change your temporary password before doing anything else.", "X-Password-Change-Required"),
    astate.MFA_ENROLLMENT_PENDING: ("Multi-factor authentication must be set up before this account can be used.", "X-MFA-Enrollment-Required"),
    astate.MFA_CHALLENGE_PENDING: ("This session has not completed multi-factor authentication. Please sign in again.", "X-MFA-Required"),
    astate.CONTACT_VERIFICATION_PENDING: ("Verify your email address before doing anything else.", "X-Contact-Verification-Required"),
}


def get_current_user(
    request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    """The signed-in user. Restricted authentication states (temporary password, MFA enrolment or challenge pending, contact
    verification pending) reach only a short allow-list of endpoints; everything else, including every operational
    permission, answers 403. This is enforced here on the server, not by the frontend."""
    user = _user_from_token(creds, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required",
                            headers={"WWW-Authenticate": "Bearer"})
    if not astate.path_allowed(user.auth_state, request.url.path):
        message, flag = _STATE_MESSAGES[user.auth_state]
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message,
                            headers={flag: "true", astate.RESTRICTED_HEADER: user.auth_state})
    return user


def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer), db: Session = Depends(get_db)
) -> Optional[User]:
    """The signed-in user, or None for anonymous requests (for example an SOS report).

    A missing, expired, revoked or invalid token yields None, and so does a session that has not completed authentication
    (MFA or password change pending): such a session must not gain privileges, so it is treated as a guest. Emergency
    reporting therefore keeps working for everyone. Endpoints that need a real user use get_current_user."""
    try:
        user = _user_from_token(creds, db)
    except HTTPException:
        return None
    return user if user is not None and user.auth_state == astate.AUTHENTICATED else None


def ensure_recent_mfa(user: User, minutes: Optional[float] = None) -> None:
    """Sensitive-action re-authentication. If the account has MFA enabled, THIS session must have proven a second factor
    within `minutes` (default MFA_FRESH_MINUTES); otherwise 403 with X-MFA-Reauth-Required and the client asks for a code at
    POST /auth/mfa/reauth. Accounts without MFA (public roles that did not opt in) are not asked; they already re-enter their
    password for credential changes."""
    if not getattr(user, "_mfa_enabled", False):
        return
    session = getattr(user, "_session", None)
    window = timedelta(minutes=minutes if minutes is not None else settings.MFA_FRESH_MINUTES)
    fresh = session is not None and session.assurance == "MFA" and session.mfa_at is not None and (
        datetime.now(timezone.utc).replace(tzinfo=None) - session.mfa_at) <= window
    if not fresh:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, headers={"X-MFA-Reauth-Required": "true"},
                            detail="Please confirm with your authenticator code to continue with this sensitive action.")


def require_recent_mfa(minutes: Optional[float] = None) -> Callable[..., User]:
    """Route dependency form of ensure_recent_mfa."""
    def checker(user: User = Depends(get_current_user)) -> User:
        ensure_recent_mfa(user, minutes)
        return user
    checker.recent_mfa_minutes = minutes
    return checker


def require_permission(*needed: str) -> Callable[..., User]:
    """Route guard: the signed-in user's CURRENT role (read from the database on every request, never from the token)
    must hold at least one of the listed permissions. Role changes and deactivation therefore apply immediately."""
    wanted = frozenset(needed)

    def checker(user: User = Depends(get_current_user)) -> User:
        if not (perms.user_permissions(user) & wanted):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Your role ({user.role}) does not have permission for this action.")
        return user

    checker.permissions = wanted  # introspected by the policy tests
    return checker


def require_roles(*roles: str) -> Callable[..., User]:
    """Legacy role-name guard, kept only for compatibility. New code uses require_permission."""
    allowed = set(roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role ({user.role}) cannot do this. Allowed: {', '.join(sorted(allowed))}",
            )
        return user

    return checker


def ensure_permission(user: Any, permission: str) -> None:
    """In-handler / service-level check for rules that depend on the resource (turns PermissionDenied into 403)."""
    if not perms.has_permission(user, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Your role ({getattr(user, 'role', 'guest')}) does not have permission for this action.")


def actor_name(user: Any, default: str = "system") -> str:
    """Username for audit entries; tolerates direct function calls in tests (no user object)."""
    return getattr(user, "username", None) or default


def actor_role(user: Any, default: str = "SYSTEM") -> str:
    return getattr(user, "role", None) or default


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
