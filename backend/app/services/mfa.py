"""TOTP multi-factor authentication (RFC 6238), recovery codes and login challenges.

* TOTP itself is delegated to the maintained `pyotp` library (HMAC-SHA1, 6 digits, 30 s steps: what authenticator apps
  expect). This module adds what a library cannot: step-level replay prevention, a narrow drift window, encrypted secrets,
  recovery codes and challenges.
* Drift tolerance: +/- MFA_DRIFT_STEPS (default 1, never more) 30-second steps, i.e. a phone clock up to ~30 s off.
* Replay prevention: the newest accepted step is stored; a code for that step or an older one is refused, so a code that was
  observed once cannot be used again (the update is atomic, so concurrent use has one winner).
* Secrets are only ever held in memory in clear while being checked; at rest they are AES-256-GCM ciphertext (mfa_crypto).
Nothing here logs or audits a secret, code or token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pyotp
import segno
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import PRIVILEGED_ROLES
from app.core.security import jwt_secret
from app.models.entities import AuthChallenge, MfaCredential, MfaRecoveryCode, User
from app.services import mfa_crypto

STEP_SECONDS = 30
DIGITS = 6
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford base32 (no I, L, O, U)
RECOVERY_GROUPS, RECOVERY_GROUP_LEN = 4, 4          # 16 symbols = 80 bits per code


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _time() -> float:
    """Clock used for TOTP (a seam so tests can move time without sleeping)."""
    return time.time()


def current_step(at: Optional[float] = None) -> int:
    return int((_time() if at is None else at) // STEP_SECONDS)


def required_for(user: User) -> bool:
    """MFA is mandatory for every non-public role and optional for citizens and volunteers."""
    return user.role in PRIVILEGED_ROLES


# ------------------------------------------------------------------ pure TOTP helpers

def new_secret() -> str:
    return pyotp.random_base32()           # 160 random bits from the `secrets` module


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=settings.MFA_ISSUER)


def qr_data_uri(uri: str) -> str:
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2)


def code_for_step(secret: str, step: int) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS).at(step * STEP_SECONDS)


def match_step(secret: str, code: str, at: Optional[float] = None) -> Optional[int]:
    """The 30 s step the code belongs to within the drift window, or None. Every offset is evaluated (no early exit)."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isascii() and code.isdigit() and len(code) == DIGITS):     # format is not secret; also keeps compare_digest safe
        return None
    drift = max(0, min(settings.MFA_DRIFT_STEPS, 1))
    cur = current_step(at)
    found: Optional[int] = None
    for offset in range(-drift, drift + 1):
        if hmac.compare_digest(code_for_step(secret, cur + offset).encode(), code.encode()):
            found = cur + offset
    return found


# ------------------------------------------------------------------ credentials

def get_credential(db: Session, user_id: int) -> Optional[MfaCredential]:
    return db.query(MfaCredential).filter(MfaCredential.user_id == user_id).first()


def is_enabled(db: Session, user_id: int) -> bool:
    c = get_credential(db, user_id)
    return c is not None and c.status == "ACTIVE"


def start_enrollment(db: Session, user: User) -> str:
    """Create (or replace) a PENDING credential and return the new base32 secret. It becomes active only on confirmation."""
    existing = get_credential(db, user.id)
    if existing is not None and existing.status == "ACTIVE":
        raise ValueError("already enrolled")
    secret = new_secret()
    enc = mfa_crypto.encrypt(secret, user.id)
    if existing is None:
        db.add(MfaCredential(user_id=user.id, secret_enc=enc, status="PENDING", created_at=now()))
    else:
        existing.secret_enc, existing.status, existing.created_at, existing.confirmed_at, existing.last_used_step = enc, "PENDING", now(), None, None
    return secret


def confirm_enrollment(db: Session, user: User, code: str) -> bool:
    """Activate the pending credential if `code` is a valid current code. True on success."""
    cred = get_credential(db, user.id)
    if cred is None or cred.status != "PENDING":
        return False
    step = match_step(mfa_crypto.decrypt(cred.secret_enc, user.id), code)
    if step is None:
        return False
    claimed = db.query(MfaCredential).filter(MfaCredential.id == cred.id, MfaCredential.status == "PENDING").update(
        {"status": "ACTIVE", "confirmed_at": now(), "last_used_step": step}, synchronize_session=False)
    return claimed == 1


def verify_totp(db: Session, user: User, code: str) -> bool:
    """True for a valid code of a step newer than any accepted before (atomic: one winner under concurrency)."""
    cred = get_credential(db, user.id)
    if cred is None or cred.status != "ACTIVE":
        return False
    step = match_step(mfa_crypto.decrypt(cred.secret_enc, user.id), code)
    if step is None:
        return False
    claimed = db.query(MfaCredential).filter(
        MfaCredential.id == cred.id, MfaCredential.status == "ACTIVE",
        (MfaCredential.last_used_step.is_(None)) | (MfaCredential.last_used_step < step)).update(
        {"last_used_step": step}, synchronize_session=False)
    return claimed == 1


def remove_credential(db: Session, user_id: int) -> None:
    db.query(MfaCredential).filter(MfaCredential.user_id == user_id).delete()
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user_id).delete()


# ------------------------------------------------------------------ recovery codes

def _code_hash(code: str) -> str:
    return hmac.new(jwt_secret().encode(), ("mfa-recovery|" + normalise_recovery(code)).encode(), hashlib.sha256).hexdigest()


def normalise_recovery(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isascii() and ch.isalnum()).replace("O", "0").replace("I", "1").replace("L", "1")


def _new_recovery_code() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(RECOVERY_GROUPS * RECOVERY_GROUP_LEN))
    return "-".join(body[i:i + RECOVERY_GROUP_LEN] for i in range(0, len(body), RECOVERY_GROUP_LEN))


def generate_recovery_codes(db: Session, user: User) -> List[str]:
    """Replace ALL of the user's recovery codes with a new batch and return the plaintext ONCE. Old codes stop working."""
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete()
    codes = [_new_recovery_code() for _ in range(settings.MFA_RECOVERY_CODE_COUNT)]
    for c in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=_code_hash(c), created_at=now()))
    return codes


def consume_recovery_code(db: Session, user: User, code: str) -> bool:
    """Atomic single use: of any number of concurrent attempts with the same code, exactly one succeeds."""
    h = _code_hash(code)
    return db.query(MfaRecoveryCode).filter(
        MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.code_hash == h, MfaRecoveryCode.used_at.is_(None)).update(
        {"used_at": now()}, synchronize_session=False) == 1


def recovery_codes_remaining(db: Session, user_id: int) -> int:
    return db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None)).count()


# ------------------------------------------------------------------ login challenges

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_challenge(db: Session, user: User, remember: bool) -> str:
    """Short-lived, single-use proof that the password step passed. Older open challenges of the user are voided."""
    for old in db.query(AuthChallenge).filter(AuthChallenge.user_id == user.id, AuthChallenge.used_at.is_(None),
                                              AuthChallenge.expires_at > now()).all():
        old.expires_at = now()
    token = secrets.token_urlsafe(32)
    t = now()
    db.add(AuthChallenge(token_hash=_hash_token(token), purpose="MFA_LOGIN", user_id=user.id, remember=remember, created_at=t,
                         expires_at=t + timedelta(seconds=settings.MFA_CHALLENGE_SECONDS),
                         max_attempts=settings.MFA_CHALLENGE_MAX_ATTEMPTS))
    return token


def find_challenge(db: Session, token: str) -> Optional[AuthChallenge]:
    """The open challenge for a token, or None for anything unknown, expired, used or out of attempts."""
    ch = db.query(AuthChallenge).filter(AuthChallenge.token_hash == _hash_token(token or ""),
                                        AuthChallenge.purpose == "MFA_LOGIN").first()
    if ch is None or ch.used_at is not None or ch.expires_at <= now() or ch.attempts >= ch.max_attempts:
        return None
    return ch


def note_failed_attempt(db: Session, ch: AuthChallenge) -> None:
    ch.attempts += 1
    if ch.attempts >= ch.max_attempts:
        ch.expires_at = now()
    db.commit()


def claim_challenge(db: Session, ch: AuthChallenge) -> bool:
    return db.query(AuthChallenge).filter(AuthChallenge.id == ch.id, AuthChallenge.used_at.is_(None)).update(
        {"used_at": now()}, synchronize_session=False) == 1


def purge_old_challenges(db: Session) -> None:
    db.query(AuthChallenge).filter(AuthChallenge.expires_at < now() - timedelta(days=1)).delete()
