"""Password hashing (PBKDF2-SHA256, standard library) and JWT access tokens."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt

from app.core.config import BASE_DIR, settings

PBKDF2_ITERATIONS = 240_000
ALGORITHM = "HS256"

ROLES = ["ADMIN", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]
# Which login portal each role signs in through.
PORTALS: Dict[str, list] = {
    "admin": ["ADMIN"],
    "operations": ["COMMANDER", "OPERATOR", "RESCUE_OFFICER"],
    "public": ["CITIZEN", "VOLUNTEER"],
}
ROLE_PORTAL = {role: portal for portal, roles in PORTALS.items() for role in roles}

# Permission groups used by the routes.
OPS = ("ADMIN", "COMMANDER", "OPERATOR")
DEPT = OPS + ("RESCUE_OFFICER",)
APPROVERS = ("ADMIN", "COMMANDER")

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if password.isdigit() or password.isalpha():
        return "Password must mix letters with numbers or symbols"
    return None


_secret_cache: Optional[str] = None


def jwt_secret() -> str:
    """JWT_SECRET from the environment, else a random secret saved once in backend/.jwt_secret."""
    global _secret_cache
    if settings.JWT_SECRET:
        return settings.JWT_SECRET
    if _secret_cache:
        return _secret_cache
    path = Path(BASE_DIR) / "backend" / ".jwt_secret"
    try:
        if path.exists():
            _secret_cache = path.read_text().strip()
        if not _secret_cache:
            _secret_cache = secrets.token_urlsafe(48)
            path.write_text(_secret_cache)
    except OSError:
        _secret_cache = _secret_cache or secrets.token_urlsafe(48)
    return _secret_cache


def create_access_token(user_id: int, role: str, minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes or settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
