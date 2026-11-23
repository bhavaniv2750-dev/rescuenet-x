"""Shared, persistent sliding-window rate limiter and client-address helper.

Events are rows in the application database (`rate_limit_events`), so every worker process that shares the database
shares the same counters, and counters survive restarts. No extra infrastructure is needed. Keys (client addresses,
usernames, e-mail addresses) are stored only as keyed hashes.

Counting is insert-then-count in one small transaction: concurrent workers may both reject the borderline request, but
they can never both let it through. Writes are serialised by SQLite, so this is correct for several workers on one host.
Several hosts need a server database (PostgreSQL) or a Redis-backed implementation of this same interface; see
docs/security/S3_RECOVERY.md.

Failure policy: if the store is unavailable, emergency endpoints (reports, uploads, tracking) fail OPEN so a database hiccup
never blocks someone calling for help; authentication endpoints fail CLOSED.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import RateLimitEvent

log = logging.getLogger("rescuenet.ratelimit")
EMERGENCY_NOTE = "If you are in immediate danger, call 112."
MAX_WINDOW_S = 24 * 3600


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reset_all() -> None:
    db = SessionLocal()
    try:
        db.query(RateLimitEvent).delete()
        db.commit()
    finally:
        db.close()


def client_ip(request: Optional[Request]) -> str:
    """Socket address, or the right-most trusted X-Forwarded-For entry when proxies are configured."""
    if request is None:  # direct function call (tests)
        return "local"
    n = settings.TRUSTED_PROXY_COUNT
    if n > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return request.client.host if request.client else "unknown"


def _hash(value: str) -> str:
    from app.core.security import jwt_secret
    return hmac.new(jwt_secret().encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def client_fingerprint(request: Optional[Request]) -> str:
    """Keyed hash of the client address. Stored instead of the address itself."""
    return _hash(client_ip(request))


def identifier_key(value: str) -> str:
    """Key for a username/e-mail supplied by a client (normalised), so limits apply whether or not the account exists."""
    return _hash("id:" + (value or "").strip().lower())


def _retry_after(db, bucket: str, key_hash: str, window_s: float) -> int:
    oldest = db.query(func.min(RateLimitEvent.created_at)).filter(
        RateLimitEvent.bucket == bucket, RateLimitEvent.key_hash == key_hash,
        RateLimitEvent.created_at > _now() - timedelta(seconds=window_s)).scalar()
    if oldest is None:
        return 1
    return max(1, int(window_s - (_now() - oldest).total_seconds()) + 1)


def clear(bucket: str, key: str) -> None:
    """Forget the counted events of one key (used after a successful password reset or recovery)."""
    db = None
    try:
        db = SessionLocal()
        db.query(RateLimitEvent).filter(RateLimitEvent.bucket == bucket, RateLimitEvent.key_hash == _hash(f"{bucket}:{key}")).delete()
        db.commit()
    except SQLAlchemyError:
        if db is not None:
            db.rollback()
    finally:
        if db is not None:
            db.close()


def hits(bucket: str, key: str, window_s: float) -> int:
    db = SessionLocal()
    try:
        return db.query(RateLimitEvent).filter(
            RateLimitEvent.bucket == bucket, RateLimitEvent.key_hash == _hash(f"{bucket}:{key}"),
            RateLimitEvent.created_at > _now() - timedelta(seconds=window_s)).count()
    finally:
        db.close()   # (callers catch SQLAlchemyError; see too_many and the login route)


def record(bucket: str, key: str) -> None:
    db = None
    try:
        db = SessionLocal()
        db.add(RateLimitEvent(bucket=bucket, key_hash=_hash(f"{bucket}:{key}"), created_at=_now()))
        db.commit()
    except SQLAlchemyError:
        if db is not None:
            db.rollback()
        log.warning("rate-limit store unavailable while recording (%s)", bucket)
    finally:
        if db is not None:
            db.close()


def too_many(bucket: str, key: str, limit: int, window_s: float, fail_open: bool = False) -> bool:
    if not settings.RATE_LIMITS_ENABLED:
        return False
    try:
        return hits(bucket, key, window_s) >= limit
    except SQLAlchemyError:
        log.warning("rate-limit store unavailable (%s); failing %s", bucket, "open" if fail_open else "closed")
        return not fail_open


def check(bucket: str, key: str, limit: int, window_s: float, fail_open: bool = False) -> None:
    """Count this event; raise 429 when more than `limit` events happened in the window."""
    if not settings.RATE_LIMITS_ENABLED:
        return
    key_hash = _hash(f"{bucket}:{key}")
    db = None
    try:
        db = SessionLocal()
        event = RateLimitEvent(bucket=bucket, key_hash=key_hash, created_at=_now())
        db.add(event)
        db.flush()
        count = db.query(RateLimitEvent).filter(
            RateLimitEvent.bucket == bucket, RateLimitEvent.key_hash == key_hash,
            RateLimitEvent.created_at > _now() - timedelta(seconds=window_s)).count()
        if count > limit:
            retry = _retry_after(db, bucket, key_hash, window_s)
            db.delete(event)
            db.commit()
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry)},
                                detail=f"Too many requests from this connection. Please wait a few minutes and try again. {EMERGENCY_NOTE}")
        if random.random() < 0.02:   # housekeeping
            db.query(RateLimitEvent).filter(RateLimitEvent.created_at < _now() - timedelta(seconds=MAX_WINDOW_S + 3600)).delete()
        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError:
        if db is not None:
            db.rollback()
        log.warning("rate-limit store unavailable (%s); failing %s", bucket, "open" if fail_open else "closed")
        if not fail_open:
            raise HTTPException(status_code=503, detail="Please try again in a moment.")
    finally:
        if db is not None:
            db.close()
