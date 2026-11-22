"""Small in-process sliding-window rate limiter and client-address helper.

Limits are per process and reset when the server restarts. That is a documented limitation: it is enough to blunt
casual abuse of the public endpoints, not a substitute for limits at a reverse proxy in a multi-process deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import settings

_lock = threading.Lock()
_events: dict = defaultdict(deque)

EMERGENCY_NOTE = "If you are in immediate danger, call 112."


def reset_all() -> None:
    with _lock:
        _events.clear()


def client_ip(request: Request | None) -> str:
    """Socket address, or the right-most trusted X-Forwarded-For entry when proxies are configured."""
    if request is None:  # direct function call (tests)
        return "local"
    n = settings.TRUSTED_PROXY_COUNT
    if n > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return request.client.host if request.client else "unknown"


def client_fingerprint(request: Request) -> str:
    """Keyed hash of the client address. Stored instead of the address itself."""
    from app.core.security import jwt_secret
    return hmac.new(jwt_secret().encode(), client_ip(request).encode(), hashlib.sha256).hexdigest()[:32]


def _prune(q: deque, now: float, window: float) -> None:
    while q and now - q[0] > window:
        q.popleft()


def hits(bucket: str, key: str, window_s: float) -> int:
    now = time.monotonic()
    with _lock:
        q = _events[(bucket, key)]
        _prune(q, now, window_s)
        return len(q)


def record(bucket: str, key: str) -> None:
    with _lock:
        _events[(bucket, key)].append(time.monotonic())


def check(bucket: str, key: str, limit: int, window_s: float) -> None:
    """Raise 429 when `limit` events already happened in the window; otherwise count this one."""
    if not settings.RATE_LIMITS_ENABLED:
        return
    now = time.monotonic()
    with _lock:
        q = _events[(bucket, key)]
        _prune(q, now, window_s)
        if len(q) >= limit:
            retry = max(1, int(window_s - (now - q[0])) + 1)
            raise HTTPException(status_code=429, headers={"Retry-After": str(retry)},
                                detail=f"Too many requests from this connection. Please wait a few minutes and try again. {EMERGENCY_NOTE}")
        q.append(now)


def too_many(bucket: str, key: str, limit: int, window_s: float) -> bool:
    return settings.RATE_LIMITS_ENABLED and hits(bucket, key, window_s) >= limit
