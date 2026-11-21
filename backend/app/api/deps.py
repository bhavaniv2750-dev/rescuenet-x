"""Authentication dependencies for the API routes."""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

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


def require_roles(*roles: str) -> Callable[..., User]:
    allowed = set(roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role ({user.role}) cannot do this. Allowed: {', '.join(sorted(allowed))}",
            )
        return user

    return checker


def actor_name(user: Any, default: str = "system") -> str:
    """Username for audit entries; tolerates direct function calls in tests (no user object)."""
    return getattr(user, "username", None) or default


def actor_role(user: Any, default: str = "SYSTEM") -> str:
    return getattr(user, "role", None) or default


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
