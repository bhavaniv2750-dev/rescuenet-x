"""Verification codes and password-reset tokens.

* Email/phone verification: 6-digit code from `secrets` (cryptographically secure), valid 10 minutes, 5 wrong tries, resend
  cooldown. A short numeric code has little entropy, so it is stored as an HMAC keyed with the server secret and bound to
  user, purpose and target (a stolen database alone cannot reveal or replay it).
* Password reset: 32 random bytes in a link, valid 30 minutes, single use, stored as SHA-256.
* A contact is marked verified ONLY here, when a correct code is entered. Generating or sending a code never does.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import jwt_secret
from app.models.entities import OneTimeToken, User

EMAIL_VERIFY, PHONE_VERIFY, PASSWORD_RESET = "EMAIL_VERIFY", "PHONE_VERIFY", "PASSWORD_RESET"


class Cooldown(Exception):
    def __init__(self, seconds: int):
        super().__init__(f"wait {seconds}s")
        self.seconds = seconds


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_code() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def _code_hash(purpose: str, user_id: int, target: str, code: str) -> str:
    return hmac.new(jwt_secret().encode(), f"{purpose}|{user_id}|{target}|{code}".encode(), hashlib.sha256).hexdigest()


def _reset_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise_email(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    return v or None


def normalise_phone(value: Optional[str]) -> Optional[str]:
    digits = "".join(c for c in (value or "") if c.isdigit() or c == "+")
    return digits or None


def _void_open_tokens(db: Session, user_id: int, purpose: str, target: Optional[str] = None) -> None:
    q = db.query(OneTimeToken).filter(OneTimeToken.user_id == user_id, OneTimeToken.purpose == purpose,
                                      OneTimeToken.used_at.is_(None), OneTimeToken.expires_at > now())
    if target is not None:
        q = q.filter(OneTimeToken.target == target)
    for t in q.all():
        t.expires_at = now()


def void_verification_codes(db: Session, user_id: int, purpose: str) -> None:
    """Invalidate every outstanding code of a purpose (used when the contact it was issued for changes)."""
    _void_open_tokens(db, user_id, purpose)


def issue_code(db: Session, user: User, purpose: str, target: str) -> str:
    """New verification code for (user, target). Enforces the resend cooldown; older open codes are voided. Caller commits."""
    last = (db.query(OneTimeToken).filter(OneTimeToken.user_id == user.id, OneTimeToken.purpose == purpose)
            .order_by(OneTimeToken.created_at.desc()).first())
    if last is not None:
        wait = settings.VERIFY_RESEND_COOLDOWN_S - int((now() - last.created_at).total_seconds())
        if wait > 0:
            raise Cooldown(wait)
    _void_open_tokens(db, user.id, purpose)
    code = new_code()
    t = now()
    db.add(OneTimeToken(user_id=user.id, purpose=purpose, target=target, token_hash=_code_hash(purpose, user.id, target, code),
                        created_at=t, expires_at=t + timedelta(minutes=settings.VERIFY_CODE_MINUTES),
                        max_attempts=settings.VERIFY_MAX_ATTEMPTS))
    return code


def check_code(db: Session, user: User, purpose: str, target: str, code: str) -> bool:
    """True only for a correct, unexpired, unused code for this exact target. Wrong guesses are counted and committed;
    after the limit the code is void and a new one must be requested."""
    tok = (db.query(OneTimeToken).filter(OneTimeToken.user_id == user.id, OneTimeToken.purpose == purpose,
                                         OneTimeToken.target == target, OneTimeToken.used_at.is_(None),
                                         OneTimeToken.expires_at > now()).order_by(OneTimeToken.created_at.desc()).first())
    if tok is None:
        return False
    if tok.attempts >= tok.max_attempts:
        tok.expires_at = now()
        db.commit()
        return False
    tok.attempts += 1
    ok = hmac.compare_digest(tok.token_hash, _code_hash(purpose, user.id, target, (code or "").strip()))
    if ok:
        ok = db.query(OneTimeToken).filter(OneTimeToken.id == tok.id, OneTimeToken.used_at.is_(None)).update(
            {"used_at": now()}, synchronize_session=False) == 1   # single use even under concurrency
    elif tok.attempts >= tok.max_attempts:
        tok.expires_at = now()
    db.commit()
    return ok


# ------------------------------------------------------------------ password reset

def issue_reset_token(db: Session, user: User) -> str:
    _void_open_tokens(db, user.id, PASSWORD_RESET)
    token = secrets.token_urlsafe(32)
    t = now()
    db.add(OneTimeToken(user_id=user.id, purpose=PASSWORD_RESET, target=None, token_hash=_reset_hash(token), created_at=t,
                        expires_at=t + timedelta(minutes=settings.RESET_TOKEN_MINUTES), max_attempts=1))
    return token


def find_valid_reset(db: Session, token: str):
    """(row, user) for a valid, unused, unexpired reset token, else None. Does not consume it."""
    row = db.query(OneTimeToken).filter(OneTimeToken.purpose == PASSWORD_RESET,
                                        OneTimeToken.token_hash == _reset_hash(token or "")).first()
    if row is None or row.used_at is not None or row.expires_at <= now():
        return None
    user = db.query(User).filter(User.id == row.user_id).first()
    return (row, user) if user is not None else None


def claim_reset(db: Session, row: OneTimeToken) -> bool:
    """Atomic single use: if two requests present the same token at once, exactly one wins."""
    return db.query(OneTimeToken).filter(OneTimeToken.id == row.id, OneTimeToken.used_at.is_(None)).update(
        {"used_at": now()}, synchronize_session=False) == 1


def void_reset_tokens(db: Session, user_id: int) -> None:
    _void_open_tokens(db, user_id, PASSWORD_RESET)
