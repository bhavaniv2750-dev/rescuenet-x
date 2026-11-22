"""Authentication dependencies for the API routes."""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import permissions as perms
from app.core.security import decode_access_token
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
        raise HTTPException(status_code=401, detail="Invalid access token", headers={"WWW-Authenticate": "Bearer"})
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or disabled", headers={"WWW-Authenticate": "Bearer"})
    return user


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    user = _user_from_token(creds, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer), db: Session = Depends(get_db)
) -> Optional[User]:
    """The signed-in user, or None for anonymous requests (for example an SOS report)."""
    return _user_from_token(creds, db)


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
