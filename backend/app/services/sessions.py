"""Server-side sessions, rotating refresh tokens, revocation and CSRF checks.

Model
* Access token: JWT, 15 minutes, names its session (`sid`) and the user's `token_version`. Every request is checked
  against the session row (not revoked, not expired, not idle) and the user row (active, same token_version).
* Refresh token: 32 random bytes in an HttpOnly cookie. Only its SHA-256 is stored. It is single-use: refreshing marks it
  used and issues a new one. Presenting a USED token again (replay) revokes the whole session.
* Anything that changes what an account may do (password, role, team, deactivation) revokes all its sessions.
* Authorization itself still reads the user's current role/team from the database on every request (S1).

Nothing in this module logs or audits token values.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, jwt_secret
from app.models.entities import AuthSession, RefreshToken, User
from app.services.audit import record_audit
from app.services.rate_limit import client_fingerprint

COOKIE_PATH = "/api/auth"          # the refresh cookie is sent to the auth endpoints only
PUBLIC_ROLES = ("CITIZEN", "VOLUNTEER")


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)   # 256 bits


def csrf_value(session_id: str) -> str:
    """Per-session CSRF token: only the server can compute it, and it is bound to the session."""
    return hmac.new(jwt_secret().encode(), f"csrf:{session_id}".encode(), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ creating sessions

def _limits(user: User, remember: bool) -> Tuple[timedelta, int]:
    if remember and user.role in PUBLIC_ROLES:     # staff and admin sessions are never "remembered"
        return timedelta(days=settings.REMEMBER_ABSOLUTE_DAYS), int(settings.REMEMBER_IDLE_HOURS * 3600)
    return timedelta(hours=settings.SESSION_ABSOLUTE_HOURS), int(settings.SESSION_IDLE_MINUTES * 60)


def _enforce_session_cap(db: Session, user_id: int) -> None:
    active = (db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
              .order_by(AuthSession.created_at.asc()).all())
    for old in active[: max(0, len(active) - settings.MAX_SESSIONS_PER_USER + 1)]:
        old.revoked_at, old.revoked_reason = now(), "SESSION_LIMIT"


def create_session(db: Session, user: User, request: Optional[Request], remember: bool = False, assurance: str = "PASSWORD",
                   mfa_method: Optional[str] = None, mfa_at: Optional[datetime] = None) -> Tuple[AuthSession, str]:
    """Start a session. Returns (session, refresh_token). The caller commits. `assurance` is MFA only when a second factor was
    just completed for this session (or carried over from a session that had completed one moments ago)."""
    absolute, idle_s = _limits(user, remember)
    _enforce_session_cap(db, user.id)
    t = now()
    session = AuthSession(
        id=secrets.token_hex(16), user_id=user.id, created_at=t, last_used_at=t, expires_at=t + absolute,
        idle_timeout_s=idle_s, remember=bool(remember and user.role in PUBLIC_ROLES),
        assurance=assurance, mfa_method=mfa_method, mfa_at=mfa_at if assurance == "MFA" else None,
        user_agent=((request.headers.get("user-agent") or "")[:200] or None) if request else None,
        client_hash=client_fingerprint(request) if request else None)
    db.add(session)
    token = _issue_refresh_token(db, session)
    purge_old_rows(db)
    return session, token


def _issue_refresh_token(db: Session, session: AuthSession) -> str:
    token = new_refresh_token()
    expires = min(session.expires_at, now() + timedelta(seconds=session.idle_timeout_s))
    db.add(RefreshToken(session_id=session.id, token_hash=hash_token(token), created_at=now(), expires_at=expires))
    return token


def purge_old_rows(db: Session) -> None:
    """Delete session rows that ended more than 30 days ago (keeps the table small; recent history stays for audit)."""
    cutoff = now() - timedelta(days=30)
    old = [s.id for s in db.query(AuthSession.id).filter(
        ((AuthSession.revoked_at.isnot(None)) & (AuthSession.revoked_at < cutoff)) | (AuthSession.expires_at < cutoff)).all()]
    if old:
        db.query(RefreshToken).filter(RefreshToken.session_id.in_(old)).delete(synchronize_session=False)
        db.query(AuthSession).filter(AuthSession.id.in_(old)).delete(synchronize_session=False)


def access_token_for(session: AuthSession, user: User) -> str:
    return create_access_token(user.id, session.id, user.token_version or 0)


# ------------------------------------------------------------------ validating

def _session_live(session: Optional[AuthSession], at: datetime) -> bool:
    if session is None or session.revoked_at is not None:
        return False
    if session.expires_at <= at:
        return False
    return (session.last_used_at + timedelta(seconds=session.idle_timeout_s)) > at


def check_access_claims(db: Session, payload: dict) -> Tuple[User, AuthSession]:
    """Validate a decoded access token against the database. Raises 401 on any mismatch."""
    fail = HTTPException(status_code=401, detail="Your session has ended. Please sign in again.",
                         headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise fail
    session = db.query(AuthSession).filter(AuthSession.id == payload["sid"]).first()
    if session is None or session.user_id != user_id or not _session_live(session, now()):
        raise fail
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active or int(payload["tv"]) != (user.token_version or 0):
        raise fail
    return user, session


# ------------------------------------------------------------------ rotating

def rotate_refresh_token(db: Session, token: str, request: Request) -> Tuple[User, AuthSession, str]:
    """Exchange a refresh token for a new one. Replay of a used token revokes the session. Raises 401 otherwise."""
    fail = HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(token)).first() if token else None
    if row is None:
        raise fail
    session = db.query(AuthSession).filter(AuthSession.id == row.session_id).first()
    if session is None:
        raise fail
    user = db.query(User).filter(User.id == session.user_id).first()
    t = now()
    if row.used_at is not None:
        # A rotated token was presented again: either the legitimate client or a thief holds a stale copy.
        # Ending the whole session is the safe answer; the person simply signs in again.
        if session.revoked_at is None:
            session.revoked_at, session.revoked_reason = t, "REPLAY_DETECTED"
            record_audit(db, user.username if user else "unknown", "SESSION_REPLAY_DETECTED", "session", session.id[:8],
                         "a rotated refresh token was presented again; session revoked", role=user.role if user else "?")
        db.commit()
        raise fail
    if row.expires_at <= t or not _session_live(session, t) or user is None or not user.is_active:
        raise fail
    row.used_at = t
    session.last_used_at = t
    new_token = _issue_refresh_token(db, session)
    return user, session, new_token


# ------------------------------------------------------------------ revoking

def revoke_session(db: Session, session: AuthSession, reason: str, actor: str = "system", role: str = "SYSTEM") -> None:
    if session.revoked_at is None:
        session.revoked_at, session.revoked_reason = now(), reason
        record_audit(db, actor, "SESSION_REVOKED", "session", session.id[:8], reason, role=role)


def revoke_all_sessions(db: Session, user: User, reason: str, actor: str = "system", role: str = "SYSTEM") -> int:
    """End every session of the account and bump its token version, so even an in-flight access token fails at once."""
    t = now()
    n = 0
    for s in db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).all():
        s.revoked_at, s.revoked_reason = t, reason
        n += 1
    user.token_version = (user.token_version or 0) + 1
    record_audit(db, actor, "SESSIONS_REVOKED_ALL", "user", user.id, f"{reason}; {n} session(s) ended", role=role)
    return n


def active_sessions(db: Session, user_id: int) -> List[AuthSession]:
    t = now()
    rows = db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).order_by(AuthSession.created_at.desc()).all()
    return [s for s in rows if _session_live(s, t)]


# ------------------------------------------------------------------ cookies and CSRF

def set_session_cookies(response: Response, session: AuthSession, refresh_token: str) -> None:
    max_age = max(60, int((session.expires_at - now()).total_seconds()))
    samesite = "lax" if settings.is_development else "strict"
    response.set_cookie(settings.REFRESH_COOKIE_NAME, refresh_token, max_age=max_age, path=COOKIE_PATH, httponly=True,
                        secure=settings.cookie_secure, samesite=samesite)
    # Readable by the page (not HttpOnly) so it can be echoed in the X-CSRF-Token header (double submit).
    response.set_cookie(settings.CSRF_COOKIE_NAME, csrf_value(session.id), max_age=max_age, path="/", httponly=False,
                        secure=settings.cookie_secure, samesite=samesite)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=COOKIE_PATH)
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


def _allowed_origin(origin: str, request: Request) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if parsed.netloc == request.headers.get("host", ""):
        return True                                            # same origin (reverse-proxy deployment)
    trusted = [o.strip().rstrip("/") for o in settings.TRUSTED_ORIGINS.split(",") if o.strip()]
    if origin.rstrip("/") in trusted:
        return True
    if settings.is_development:                                # local Vite dev servers
        import re
        return bool(re.fullmatch(r"http://(localhost|127\.0\.0\.1):(517[0-9]|3000)", origin))
    return False


def verify_csrf(request: Request, session_id: str) -> None:
    """For endpoints authenticated by the refresh cookie (refresh, cookie logout). Do not rely on SameSite alone:
    1. If an Origin header is present it must be an allowed origin.
    2. The X-CSRF-Token header must equal the CSRF cookie AND the value derived from this session (double submit,
       bound to the session so a planted cookie is useless)."""
    origin = request.headers.get("origin")
    if origin and not _allowed_origin(origin, request):
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
    expected = csrf_value(session_id)
    if not (header and hmac.compare_digest(header, cookie) and hmac.compare_digest(header, expected)):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
