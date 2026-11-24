"""Multi-factor authentication endpoints (TOTP, recovery codes, login challenge, re-authentication)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_recent_mfa
from app.api.routes.auth import start_session, user_out
from app.core.config import settings
from app.core.security import verify_password
from app.db.session import get_db
from app.models.entities import AuthSession, User
from app.services import auth_state as astate
from app.services import mfa as mfa_svc
from app.services import rate_limit
from app.services import sessions as sess
from app.services.audit import record_audit
from app.services.mfa_crypto import MfaDecryptError

router = APIRouter()

INVALID = "That code is not valid. Check that the clock on your phone is correct and try the newest code."
SIGN_IN_AGAIN = "This sign-in has expired or is no longer valid. Please sign in again."
STORE_RECOVERY = ("Each recovery code works ONCE. Store them offline (printed, or in a password manager), apart from your phone. "
                  "They are shown only now and cannot be shown again; if you lose them, generate a new set (that cancels these).")


class VerifyIn(BaseModel):
    challenge_token: str = Field(min_length=10, max_length=200)
    code: Optional[str] = Field(default=None, max_length=12)
    recovery_code: Optional[str] = Field(default=None, max_length=40)


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class StartIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)


class DisableIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)


def _no_store(content: dict, status_code: int = 200) -> JSONResponse:
    r = JSONResponse(content=content, status_code=status_code)
    r.headers["Cache-Control"] = "no-store"
    return r


def _check_totp(db: Session, user: User, code: str) -> bool:
    try:
        return mfa_svc.verify_totp(db, user, code)
    except MfaDecryptError:
        # The stored secret cannot be read (lost/rotated-out key). Never expose why; the account needs host-level recovery.
        raise HTTPException(status_code=503, detail="Multi-factor authentication is temporarily unavailable for this account. "
                                                    "Contact the person who runs this server.")


# ------------------------------------------------------------------ login second step

@router.post("/verify")
def verify_login(payload: VerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Complete a sign-in with a TOTP code or a recovery code. Only a challenge from a successful password step is accepted; it
    is single use, expires in minutes and allows a few attempts. Every failure gets the same generic answer."""
    rate_limit.check("mfa-ip", rate_limit.client_fingerprint(request), settings.MFA_ATTEMPTS_PER_IP_15MIN, 900)
    ch = mfa_svc.find_challenge(db, payload.challenge_token)
    user = db.query(User).filter(User.id == ch.user_id).first() if ch else None
    if ch is None or user is None or not user.is_active:
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN)
    if rate_limit.too_many("mfa-fail", str(user.id), settings.MFA_FAILS_PER_ACCOUNT_15MIN, 900):
        raise HTTPException(status_code=429, headers={"Retry-After": "900"}, detail="Too many wrong codes. Please wait a while and sign in again.")
    method, ok = None, False
    if payload.recovery_code:
        if rate_limit.too_many("mfa-recovery-fail", str(user.id), settings.MFA_RECOVERY_FAILS_PER_ACCOUNT_HOUR, 3600):
            raise HTTPException(status_code=429, headers={"Retry-After": "3600"}, detail="Too many wrong recovery codes. Please wait before trying again.")
        method, ok = "RECOVERY", mfa_svc.consume_recovery_code(db, user, payload.recovery_code)
    elif payload.code:
        method, ok = "TOTP", _check_totp(db, user, payload.code)
    else:
        raise HTTPException(status_code=422, detail="Enter your authenticator code or a recovery code.")
    if not ok:
        db.rollback()                      # release the write lock BEFORE the limiter (a separate connection) writes
        rate_limit.record("mfa-fail", str(user.id))
        if method == "RECOVERY":
            rate_limit.record("mfa-recovery-fail", str(user.id))
        mfa_svc.note_failed_attempt(db, db.get(type(ch), ch.id))
        record_audit(db, user.username, "MFA_CHALLENGE_FAILED", "user", user.id, method or "", role=user.role)
        db.commit()
        raise HTTPException(status_code=401, detail=INVALID if method == "TOTP" else "That recovery code is not valid or was already used.")
    if not mfa_svc.claim_challenge(db, ch):       # concurrent use of the same challenge: exactly one wins
        db.rollback()
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN)
    user.last_login_at = sess.now()
    record_audit(db, user.username, "LOGIN", "user", user.id, f"mfa {method.lower()}", role=user.role)
    if method == "RECOVERY":
        record_audit(db, user.username, "MFA_RECOVERY_CODE_USED", "user", user.id,
                     f"{mfa_svc.recovery_codes_remaining(db, user.id)} unused codes remain", role=user.role)
    out = start_session(db, user, request, response, ch.remember, "MFA", method, sess.now())
    result = _no_store(out.model_dump(mode="json"))
    for cookie in response.headers.getlist("set-cookie"):       # cookies were set on the injected response: carry them over
        result.headers.append("set-cookie", cookie)
    return result


# ------------------------------------------------------------------ status and enrolment

@router.get("/status")
def mfa_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cred = mfa_svc.get_credential(db, user.id)
    return _no_store({
        "required": mfa_svc.required_for(user),
        "enabled": cred is not None and cred.status == "ACTIVE",
        "enrollment_pending": cred is not None and cred.status == "PENDING",
        "recovery_codes_remaining": mfa_svc.recovery_codes_remaining(db, user.id),
        "auth_state": user.auth_state,
        "can_disable": not mfa_svc.required_for(user),
    })


@router.post("/enroll/start")
def enroll_start(payload: StartIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Begin enrolment: returns the secret, the otpauth URI and a QR code ONCE. Nothing is active until /enroll/confirm.
    The password is asked again so a stolen session alone cannot enrol an attacker's authenticator."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    rate_limit.check("mfa-enroll-start", str(user.id), settings.MFA_ENROLL_START_PER_ACCOUNT_HOUR, 3600)
    try:
        secret = mfa_svc.start_enrollment(db, user)
    except ValueError:
        raise HTTPException(status_code=409, detail="Multi-factor authentication is already set up for this account.")
    record_audit(db, user.username, "MFA_ENROLLMENT_STARTED", "user", user.id, role=user.role)
    db.commit()
    uri = mfa_svc.provisioning_uri(secret, user.username)
    return _no_store({"secret": secret, "otpauth_uri": uri, "qr_svg_data_uri": mfa_svc.qr_data_uri(uri), "issuer": settings.MFA_ISSUER,
                      "account": user.username, "algorithm": "SHA1", "digits": mfa_svc.DIGITS, "period": mfa_svc.STEP_SECONDS,
                      "notice": "Shown only now. Add it to your authenticator app, then enter the 6-digit code to finish."})


@router.post("/enroll/confirm")
def enroll_confirm(payload: CodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Activate MFA after the user proves their authenticator works. Returns the recovery codes ONCE. This session becomes an
    MFA session (the user just proved a second factor); every other session of the account is ended."""
    if rate_limit.too_many("mfa-fail", str(user.id), settings.MFA_FAILS_PER_ACCOUNT_15MIN, 900):
        raise HTTPException(status_code=429, headers={"Retry-After": "900"}, detail="Too many wrong codes. Please wait a while.")
    try:
        ok = mfa_svc.confirm_enrollment(db, user, payload.code)
    except MfaDecryptError:
        raise HTTPException(status_code=503, detail="Multi-factor authentication is temporarily unavailable for this account.")
    if not ok:
        db.rollback()
        rate_limit.record("mfa-fail", str(user.id))
        raise HTTPException(status_code=400, detail=INVALID)
    codes = mfa_svc.generate_recovery_codes(db, user)
    current: Optional[AuthSession] = getattr(user, "_session", None)
    for s in sess.active_sessions(db, user.id):
        if current is None or s.id != current.id:
            sess.revoke_session(db, s, "MFA_ENROLLED", actor=user.username, role=user.role)
    if current is not None:
        current.assurance, current.mfa_method, current.mfa_at = "MFA", "TOTP", sess.now()
    record_audit(db, user.username, "MFA_ENROLLED", "user", user.id, f"{len(codes)} recovery codes issued", role=user.role)
    db.commit()
    db.refresh(user)
    return _no_store({"enabled": True, "recovery_codes": codes, "instructions": STORE_RECOVERY,
                      "user": user_out(db, user, current).model_dump(mode="json")})


# ------------------------------------------------------------------ re-authentication and management

@router.post("/reauth")
def reauth(payload: CodeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Prove a second factor again inside this session (sensitive actions need a recent one). Same limits as sign-in."""
    if not getattr(user, "_mfa_enabled", False):
        raise HTTPException(status_code=409, detail="Multi-factor authentication is not set up for this account.")
    rate_limit.check("mfa-ip", rate_limit.client_fingerprint(request), settings.MFA_ATTEMPTS_PER_IP_15MIN, 900)
    if rate_limit.too_many("mfa-fail", str(user.id), settings.MFA_FAILS_PER_ACCOUNT_15MIN, 900):
        raise HTTPException(status_code=429, headers={"Retry-After": "900"}, detail="Too many wrong codes. Please wait a while.")
    if not _check_totp(db, user, payload.code):
        db.rollback()
        rate_limit.record("mfa-fail", str(user.id))
        raise HTTPException(status_code=401, detail=INVALID)
    s = user._session
    s.assurance, s.mfa_method, s.mfa_at = "MFA", "TOTP", sess.now()
    record_audit(db, user.username, "MFA_REAUTHENTICATED", "user", user.id, role=user.role)
    db.commit()
    return {"fresh_for_minutes": settings.MFA_FRESH_MINUTES}


@router.post("/recovery-codes/regenerate")
def regenerate_recovery_codes(user: User = Depends(require_recent_mfa()), db: Session = Depends(get_db)):
    """New set of recovery codes (shown once). Every previous code stops working immediately."""
    rate_limit.check("mfa-recovery-regen", str(user.id), 5, 3600)
    if not getattr(user, "_mfa_enabled", False):
        raise HTTPException(status_code=409, detail="Multi-factor authentication is not set up for this account.")
    codes = mfa_svc.generate_recovery_codes(db, user)
    record_audit(db, user.username, "MFA_RECOVERY_CODES_REGENERATED", "user", user.id, f"{len(codes)} new codes; old codes cancelled", role=user.role)
    db.commit()
    return _no_store({"recovery_codes": codes, "instructions": STORE_RECOVERY})


@router.post("/disable")
def disable_mfa(payload: DisableIn, user: User = Depends(require_recent_mfa()), db: Session = Depends(get_db)):
    """Turn MFA off. Only for roles where it is optional (citizen, volunteer); mandatory roles cannot, and nobody - not an
    administrator - can remove another user's MFA through the web application."""
    if mfa_svc.required_for(user):
        raise HTTPException(status_code=403, detail="Multi-factor authentication is mandatory for your role and cannot be turned off.")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    mfa_svc.remove_credential(db, user.id)
    current = getattr(user, "_session", None)
    for s in sess.active_sessions(db, user.id):
        if current is None or s.id != current.id:
            sess.revoke_session(db, s, "MFA_DISABLED", actor=user.username, role=user.role)
    record_audit(db, user.username, "MFA_DISABLED", "user", user.id, role=user.role)
    db.commit()
    return {"enabled": False}
