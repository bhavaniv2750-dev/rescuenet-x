"""Sign-in, sign-up and account management.

Three portals, each accepting only its own roles:
  admin       ADMIN (administrators and developers)
  operations  COMMANDER, OPERATOR, RESCUE_OFFICER (rescue operations department)
  public      CITIZEN, VOLUNTEER (self sign-up)
Department and admin accounts are created by an administrator.
"""

from datetime import timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import actor_name, ensure_recent_mfa, get_current_user, require_permission, utcnow_naive
from app.core.permissions import P, PRIVILEGED_ROLES, PUBLIC_ROLES, permissions_for_role
from app.core.security import (
    PORTALS,
    ROLE_PORTAL,
    ROLES,
    hash_password,
    password_problem,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import AuditLog, AuthSession, RefreshToken, RescueTeam, User, Volunteer
from app.services import auth_state as astate
from app.services import mfa as mfa_svc
from app.services import notifications as notif
from app.services import rate_limit
from app.services import sessions as sess
from app.services import verification as ver
from app.services.audit import record_audit
from app.services.ids import next_volunteer_id

router = APIRouter()

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5
USERNAME_PATTERN = r"^[a-zA-Z0-9_.\-]{3,60}$"


# ---------- schemas ----------
class LoginRequest(BaseModel):
    portal: Literal["admin", "operations", "public"]
    remember: bool = False   # "keep me signed in": longer session, honoured for citizens and volunteers only
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    role: Literal["CITIZEN", "VOLUNTEER"] = "CITIZEN"
    username: str = Field(pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    phone: str = Field(min_length=6, max_length=30)
    email: Optional[str] = Field(default=None, max_length=120)
    # Volunteers only
    skills: Optional[str] = Field(default=None, max_length=200)
    area: Optional[str] = Field(default=None, max_length=100)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    portal: str = ""
    team_id: Optional[str] = None
    volunteer_id: Optional[str] = None
    volunteer_verified: Optional[bool] = None
    is_active: bool
    permissions: List[str] = []   # what this role may do (informational; the API enforces it on every call)
    email_verified: bool = False
    phone_verified: bool = False
    password_change_required: bool = False   # only the password-change endpoints work until this is cleared
    mfa_required: bool = False               # mandatory for every non-public role
    mfa_enabled: bool = False
    auth_state: str = ""                      # see app/services/auth_state.py; only AUTHENTICATED reaches operational pages
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    status: str = "authenticated"
    """The refresh token is never in the body: it travels only in an HttpOnly cookie."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int          # seconds until the access token expires
    csrf_token: str          # echo in X-CSRF-Token on refresh/logout (also readable from the rn_csrf cookie)
    user: UserOut


class UserCreate(BaseModel):
    role: Literal["ADMIN", "DEVELOPER", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]
    username: str = Field(pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    team_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[Literal["ADMIN", "DEVELOPER", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]] = None
    team_id: Optional[str] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class AuditEntryOut(BaseModel):
    id: int
    actor: str
    role: str
    action: str
    target_type: str
    target_id: str
    details: Optional[str] = None
    created_at: object
    model_config = ConfigDict(from_attributes=True)


def user_out(db: Session, user: User, session: Optional[AuthSession] = None) -> UserOut:
    out = UserOut.model_validate(user)
    out.portal = ROLE_PORTAL.get(user.role, "")
    enabled = mfa_svc.is_enabled(db, user.id)
    out.mfa_enabled = enabled
    out.mfa_required = user.role in PRIVILEGED_ROLES
    # An explicit session means "state as of NOW for that session" (e.g. just after enrolment); otherwise use what the request
    # dependency computed; listing other users has neither and shows no state.
    state = astate.session_state(user, session, enabled) if session is not None else getattr(user, "auth_state", None)
    out.auth_state = state or ""
    # Permissions are advertised only to a fully authenticated session (the API enforces this anyway). Listing OTHER users
    # (administration) has no session and shows the role's permissions.
    out.permissions = sorted(permissions_for_role(user.role)) if state in (None, astate.AUTHENTICATED) else []
    out.email_verified = user.email_verified_at is not None
    out.phone_verified = user.phone_verified_at is not None
    out.password_change_required = bool(user.must_change_password)
    if user.volunteer_id:
        vol = db.query(Volunteer).filter(Volunteer.id == user.volunteer_id).first()
        out.volunteer_verified = bool(vol and vol.is_verified)
    return out


def start_session(db: Session, user: User, request: Request, response: Response, remember: bool = False,
                  assurance: str = "PASSWORD", mfa_method: Optional[str] = None, mfa_at=None) -> TokenOut:
    """Create a session, set the refresh/CSRF cookies and return the short-lived access token. Caller commits first.
    A session starts with assurance MFA only when a second factor was just completed; otherwise PASSWORD, and a privileged
    account in that state can do nothing but enrol MFA (see auth_state)."""
    session, refresh = sess.create_session(db, user, request, remember, assurance, mfa_method, mfa_at)
    db.commit()
    sess.set_session_cookies(response, session, refresh)
    return TokenOut(access_token=sess.access_token_for(session, user), expires_in=int(settings.access_token_minutes * 60),
                    csrf_token=sess.csrf_value(session.id), user=user_out(db, user, session))


def _check_password(pw: str) -> None:
    problem = password_problem(pw)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


# ---------- public endpoints ----------
@router.get("/portals")
def list_portals():
    # Demo credentials are a development-only convenience: never offered unless RESCUENET_ENV=development.
    demo = settings.SEED_DEMO_USERS and settings.is_development
    return {
        "demo_mode": demo,
        # Shown on the sign-in page only while demo accounts are enabled (development / project demo).
        "demo_accounts": [
            {"portal": ROLE_PORTAL[role], "username": username, "role": role, "label": label}
            for username, label, role in [
                ("citizen", "Citizen", "CITIZEN"), ("volunteer", "Volunteer", "VOLUNTEER"),
                ("operator", "Control room operator", "OPERATOR"), ("officer", "Rescue officer", "RESCUE_OFFICER"),
                ("commander", "Incident commander", "COMMANDER"), ("admin", "Administrator", "ADMIN"),
                ("developer", "Developer (diagnostics only)", "DEVELOPER"),
            ]
        ] if demo else [],
        "demo_password": settings.DEMO_USER_PASSWORD if demo else None,
        "portals": [
            {"id": "public", "name": "Citizens & Volunteers", "roles": PORTALS["public"], "self_signup": True},
            {"id": "operations", "name": "Rescue Operations Department", "roles": PORTALS["operations"], "self_signup": False},
            {"id": "admin", "name": "Admin & Developers", "roles": PORTALS["admin"], "self_signup": False},
        ]
    }


LOCKED = "Too many failed attempts. Try again in a few minutes."


def _find_login_user(db: Session, ident: str) -> Optional[User]:
    """Username first. An e-mail address works only when exactly ONE account has it: an address typed by someone else at
    sign-up (unverified) must never decide which account a login reaches."""
    user = db.query(User).filter(User.username == ident).first()
    if user is not None:
        return user
    matches = db.query(User).filter(User.email == ident).limit(2).all()
    return matches[0] if len(matches) == 1 else None


@router.post("/login", response_model=None)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ident = payload.username.strip().lower()
    ip, account_key = rate_limit.client_fingerprint(request), rate_limit.identifier_key(ident)
    # Both limits apply whether or not the account exists, and give the same answer, so they reveal nothing.
    rate_limit.check("login-ip", ip, settings.LOGIN_PER_IP_15MIN, 900)
    if rate_limit.too_many("login-account", account_key, settings.LOGIN_PER_ACCOUNT_15MIN, 900):
        raise HTTPException(status_code=429, detail=LOCKED, headers={"Retry-After": "900"})
    user = _find_login_user(db, ident)
    now = utcnow_naive()
    generic = HTTPException(status_code=401, detail="Wrong username or password")
    if user is None:
        verify_password(payload.password, hash_password("timing-equaliser"))  # similar response time
        rate_limit.record("login-account", account_key)
        raise generic
    if not verify_password(payload.password, user.password_hash):
        rate_limit.record("login-account", account_key)
        if rate_limit.hits("login-account", account_key, 900) >= settings.LOGIN_PER_ACCOUNT_15MIN:
            record_audit(db, user.username, "LOGIN_LOCKED", "user", user.id, f"{settings.LOGIN_PER_ACCOUNT_15MIN} failed attempts", role=user.role)
            db.commit()
        raise generic
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled. Contact an administrator.")
    if user.role not in PORTALS[payload.portal]:
        portal = ROLE_PORTAL.get(user.role, "?")
        raise HTTPException(status_code=403, detail=f"This account signs in through the '{portal}' portal.")
    user.failed_logins = 0
    user.locked_until = None
    if mfa_svc.is_enabled(db, user.id):
        # The password alone never yields a session for an account with MFA: only a short-lived, single-purpose challenge.
        challenge = mfa_svc.issue_challenge(db, user, payload.remember)
        mfa_svc.purge_old_challenges(db)
        record_audit(db, user.username, "LOGIN_PASSWORD_OK_MFA_PENDING", "user", user.id, f"portal {payload.portal}", role=user.role)
        db.commit()
        r = JSONResponse(content={"status": "mfa_required", "challenge_token": challenge,
                                  "expires_in": settings.MFA_CHALLENGE_SECONDS, "methods": ["totp", "recovery_code"]})
        r.headers["Cache-Control"] = "no-store"
        return r
    user.last_login_at = now
    record_audit(db, user.username, "LOGIN", "user", user.id, f"portal {payload.portal}", role=user.role)
    return start_session(db, user, request, response, payload.remember)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Self sign-up for citizens and volunteers. Volunteers start unverified. The e-mail address starts UNVERIFIED too."""
    rate_limit.check("register-ip", rate_limit.client_fingerprint(request), settings.REGISTER_PER_IP_HOUR, 3600)
    _check_password(payload.password)
    username = payload.username.lower()
    email = _valid_email(payload.email)
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="That username is taken")
    # An already-used e-mail address is NOT reported (that would reveal who has an account). Several accounts may hold the
    # same unverified address; only the owner who proves it with a code can verify it (see /auth/verify/email/confirm).

    volunteer_id = None
    if payload.role == "VOLUNTEER":
        if not payload.skills or not payload.area:
            raise HTTPException(status_code=422, detail="Volunteers must give their skills and area")
        volunteer_id = next_volunteer_id(db)
        db.add(Volunteer(id=volunteer_id, name=payload.full_name, phone=payload.phone, email=email or "",
                         skills=payload.skills, area=payload.area, is_verified=False, status="STANDBY"))

    user = User(username=username, full_name=payload.full_name, email=email, phone=payload.phone,
                role=payload.role, password_hash=hash_password(payload.password), volunteer_id=volunteer_id)
    db.add(user)
    db.flush()
    record_audit(db, username, "SIGN_UP", "user", user.id, payload.role, role=payload.role)
    db.commit()
    db.refresh(user)
    return start_session(db, user, request, response)


# ---------- signed-in user ----------
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


def _unauthorized(detail: str = "Your session has ended. Please sign in again.") -> JSONResponse:
    r = JSONResponse(status_code=401, content={"detail": detail})
    sess.clear_session_cookies(r)
    return r


@router.post("/refresh")
def refresh(request: Request, db: Session = Depends(get_db)):
    """Exchange the refresh cookie for a new access token and a NEW refresh cookie (rotation).
    Cookie-authenticated, so it is CSRF-protected (Origin check + X-CSRF-Token double submit bound to the session).
    A refresh token that was already used (replay) ends the whole session."""
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME, "")
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == sess.hash_token(token)).first() if token else None
    if row is None:
        return _unauthorized()
    sess.verify_csrf(request, row.session_id)            # 403 without clearing the cookie (a forged request must not log anyone out)
    try:
        user, session, new_token = sess.rotate_refresh_token(db, token, request)
    except HTTPException as exc:
        return _unauthorized(exc.detail)
    db.commit()
    body = TokenOut(access_token=sess.access_token_for(session, user), expires_in=int(settings.access_token_minutes * 60),
                    csrf_token=sess.csrf_value(session.id), user=user_out(db, user, session))
    response = JSONResponse(content=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    sess.set_session_cookies(response, session, new_token)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """End the current session. Idempotent. Authenticated by the access token (Authorization header) or, failing that,
    by the refresh cookie (CSRF-protected). Cookies are always cleared."""
    session = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from app.core.security import decode_access_token
            payload = decode_access_token(auth[7:].strip())
            session = db.query(AuthSession).filter(AuthSession.id == payload["sid"]).first()
            if session is not None and session.user_id != int(payload["sub"]):
                session = None
        except Exception:
            session = None
    if session is None:
        token = request.cookies.get(settings.REFRESH_COOKIE_NAME, "")
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == sess.hash_token(token)).first() if token else None
        if row is not None:
            sess.verify_csrf(request, row.session_id)
            session = db.query(AuthSession).filter(AuthSession.id == row.session_id).first()
    if session is not None:
        owner = db.query(User).filter(User.id == session.user_id).first()
        sess.revoke_session(db, session, "LOGOUT", actor=owner.username if owner else "unknown", role=owner.role if owner else "?")
        db.commit()
    response = JSONResponse(content={"message": "Signed out"})
    sess.clear_session_cookies(response)
    return response


@router.post("/logout-all")
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sign this account out of every device, including this one."""
    n = sess.revoke_all_sessions(db, user, "LOGOUT_ALL", actor=user.username, role=user.role)
    db.commit()
    response = JSONResponse(content={"message": "Signed out everywhere", "sessions_ended": n})
    sess.clear_session_cookies(response)
    return response


class SessionOut(BaseModel):
    id: str
    created_at: object
    last_used_at: object
    expires_at: object
    user_agent: Optional[str] = None
    remember: bool
    current: bool


@router.get("/sessions", response_model=dict)
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current = getattr(user, "session_id", None)
    items = [SessionOut(id=s.id, created_at=s.created_at, last_used_at=s.last_used_at, expires_at=s.expires_at,
                        user_agent=s.user_agent, remember=s.remember, current=(s.id == current))
             for s in sess.active_sessions(db, user.id)]
    return {"items": items, "count": len(items)}


@router.delete("/sessions/{session_id}")
def revoke_one_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke one of YOUR sessions (another device, or this one). Other people's sessions are not reachable here."""
    s = db.query(AuthSession).filter(AuthSession.id == session_id, AuthSession.user_id == user.id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    sess.revoke_session(db, s, "REVOKED_BY_USER", actor=user.username, role=user.role)
    db.commit()
    return {"message": "Session ended", "was_current": s.id == getattr(user, "session_id", None)}


@router.post("/me/password")
def change_password(payload: PasswordChange, request: Request, response: Response, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Change your own password. Every session, including this one, ends; a fresh session is started for this device.
    This is also how a forced change after break-glass recovery is completed: the temporary password cannot be reused."""
    ensure_recent_mfa(user)          # sensitive: with MFA enabled, a second factor must have been shown recently
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    _check_password(payload.new_password)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=422, detail="Choose a new password that is different from the current one.")
    old = getattr(user, "_session", None)
    carry = (old.assurance, old.mfa_method, old.mfa_at) if old is not None and old.assurance == "MFA" else ("PASSWORD", None, None)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow_naive()
    user.must_change_password = False
    record_audit(db, user.username, "PASSWORD_CHANGED", "user", user.id, role=user.role)
    ended = sess.revoke_all_sessions(db, user, "PASSWORD_CHANGED", actor=user.username, role=user.role)
    # The fresh session for this device keeps the MFA assurance the user JUST proved (required above); it is never raised.
    out = start_session(db, user, request, response, False, *carry)
    return {"message": "Password changed. All other sessions were signed out.", "sessions_ended": ended,
            **out.model_dump(mode="json")}


# ---------- contact verification ----------
EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: Optional[str]) -> Optional[str]:
    email = ver.normalise_email(value)
    if email and (len(email) > 120 or not EMAIL_RE.match(email)):
        raise HTTPException(status_code=422, detail="That does not look like an email address.")
    return email


class CodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class ContactChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=30)


@router.get("/capabilities")
def capabilities():
    """What this server can honestly do about notifications (no secrets). The page uses it to word messages truthfully."""
    return notif.capabilities()


def _delivery_text(row: "notif.NotificationOutbox", channel_word: str) -> str:
    if row.delivery_status == notif.NOT_DELIVERED_DEV:
        return f"Development mode: the code is in the development outbox. {notif.DEV_NOTICE}"
    if row.delivery_status == notif.ACCEPTED_BY_SMTP:
        return f"The code was handed to the mail server for {row.recipient_masked}. Delivery is not guaranteed: check your spam folder."
    return f"The {channel_word} could not be sent."


def _request_code(channel: str, user: User, db: Session) -> dict:
    purpose = ver.EMAIL_VERIFY if channel == "EMAIL" else ver.PHONE_VERIFY
    target = user.email if channel == "EMAIL" else user.phone
    verified = user.email_verified_at if channel == "EMAIL" else user.phone_verified_at
    transport = notif.email_transport() if channel == "EMAIL" else notif.sms_transport()
    word = "email" if channel == "EMAIL" else "text message"
    if transport.name == "DISABLED":
        # A fact about the server, not about any account, so it is safe to state plainly.
        raise HTTPException(status_code=409 if channel == "SMS" else 503,
                            detail=f"{'Phone' if channel == 'SMS' else 'Email'} verification is not available: {transport.reason}. "
                                   f"Your {'phone number' if channel == 'SMS' else 'email address'} stays unverified.")
    if not target:
        raise HTTPException(status_code=422, detail=f"Add {'an email address' if channel == 'EMAIL' else 'a phone number'} to your account first.")
    if verified:
        return {"already_verified": True, "message": "Already verified."}
    rate_limit.check("verify-send", f"{user.id}:{channel}", settings.VERIFY_SEND_PER_ACCOUNT_HOUR, 3600)
    try:
        code = ver.issue_code(db, user, purpose, target)
    except ver.Cooldown as c:
        raise HTTPException(status_code=429, headers={"Retry-After": str(c.seconds)},
                            detail=f"A code was requested a moment ago. Please wait {c.seconds} seconds before asking for another.")
    record_audit(db, user.username, "CONTACT_VERIFICATION_REQUESTED", "user", user.id, channel, role=user.role)
    db.commit()
    body = (f"Your RescueNet X verification code is {code}. It expires in {settings.VERIFY_CODE_MINUTES} minutes. "
            "If you did not ask for it, ignore this message.")
    row = notif.notify(notif.Message(channel, target, "Your RescueNet X verification code", body, purpose, user.id))
    if row.delivery_status in (notif.FAILED, notif.DISABLED):
        ver.void_verification_codes(db, user.id, purpose)   # nothing reached the person; do not leave a live code behind
        db.commit()
        raise HTTPException(status_code=502, detail=f"The {word} could not be sent. Try again later.")
    return {"already_verified": False, "delivery_status": row.delivery_status, "message": _delivery_text(row, word),
            "cooldown_seconds": settings.VERIFY_RESEND_COOLDOWN_S, "expires_in_minutes": settings.VERIFY_CODE_MINUTES}


def _confirm_code(channel: str, payload: CodeIn, user: User, db: Session) -> dict:
    purpose = ver.EMAIL_VERIFY if channel == "EMAIL" else ver.PHONE_VERIFY
    transport = notif.email_transport() if channel == "EMAIL" else notif.sms_transport()
    if channel == "SMS" and transport.name == "DISABLED":
        raise HTTPException(status_code=409, detail=f"Phone verification is not available: {transport.reason}.")
    rate_limit.check("verify-confirm", f"{user.id}:{channel}", settings.VERIFY_CONFIRM_PER_ACCOUNT_HOUR, 3600)
    target = user.email if channel == "EMAIL" else user.phone
    invalid = HTTPException(status_code=400, detail="That code is invalid or has expired. Request a new one.")
    if not target or not ver.check_code(db, user, purpose, target, payload.code):
        raise invalid
    if channel == "EMAIL" and db.query(User).filter(User.email == target, User.id != user.id, User.email_verified_at.isnot(None)).first():
        raise invalid      # another account already proved this address; answer like any wrong code
    if channel == "EMAIL":
        user.email_verified_at = utcnow_naive()
    else:
        user.phone_verified_at = utcnow_naive()
    record_audit(db, user.username, "EMAIL_VERIFIED" if channel == "EMAIL" else "PHONE_VERIFIED", "user", user.id, role=user.role)
    db.commit()
    return {"verified": True, "channel": channel.lower()}


@router.post("/verify/email/request")
def request_email_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _request_code("EMAIL", user, db)


@router.post("/verify/email/confirm")
def confirm_email(payload: CodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _confirm_code("EMAIL", payload, user, db)


@router.post("/verify/phone/request")
def request_phone_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _request_code("SMS", user, db)


@router.post("/verify/phone/confirm")
def confirm_phone(payload: CodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _confirm_code("SMS", payload, user, db)


@router.patch("/me/contact")
def change_contact(payload: ContactChange, background: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Change your email or phone. Needs your current password. A changed address is UNVERIFIED until a new code is entered;
    codes issued for the old address stop working, and a verified old address is told about the change."""
    ensure_recent_mfa(user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    changed: List[str] = []
    old_verified_email = user.email if user.email_verified_at else None
    if payload.email is not None:
        new_email = _valid_email(payload.email)
        if new_email != user.email:
            user.email, user.email_verified_at, user.email_changed_at = new_email, None, utcnow_naive()
            ver.void_verification_codes(db, user.id, ver.EMAIL_VERIFY)
            ver.void_reset_tokens(db, user.id)
            changed.append("email")
    if payload.phone is not None:
        new_phone = ver.normalise_phone(payload.phone)
        if new_phone != user.phone:
            user.phone, user.phone_verified_at = new_phone, None
            ver.void_verification_codes(db, user.id, ver.PHONE_VERIFY)
            changed.append("phone")
    if changed:
        record_audit(db, user.username, "CONTACT_CHANGED", "user", user.id, f"{'+'.join(changed)} changed; re-verification required", role=user.role)
    db.commit()
    if "email" in changed and old_verified_email:
        background.add_task(notif.notify, notif.Message(
            "EMAIL", old_verified_email, "Your RescueNet X email address was changed",
            "The email address on your RescueNet X account was changed. If this was not you, sign in and change your password, "
            "or contact your administrator.", "CONTACT_CHANGED_NOTICE", user.id))
    db.refresh(user)
    return {"changed": changed, "user": user_out(db, user), "message": "Saved. A changed email or phone must be verified again." if changed else "Nothing changed."}


# ---------- password recovery ----------
RESET_REQUESTED = ("If an account matches and its email address is verified, password-reset instructions have been requested. "
                   "Nothing here confirms that an account exists.")
INVALID_RESET = "This reset link is invalid or has expired. Request a new one."


class ForgotIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always answers the same way (202, same text) whether or not an account matches, so it cannot be used to discover
    accounts. A reset link is requested only for an active account with a VERIFIED email address; staff accounts also need
    an address that was not changed in the last STAFF_RESET_COOLDOWN_HOURS, so a thief of a session cannot swap the address
    and reset at once. Resetting never signs anyone in, and it does not bypass sign-in checks (and, later, MFA)."""
    transport = notif.email_transport()
    if transport.name == "DISABLED":
        raise HTTPException(status_code=503, detail=f"Password recovery by email is not available: {transport.reason}. Contact an administrator.")
    ident = payload.identifier.strip().lower()
    rate_limit.check("forgot-ip", rate_limit.client_fingerprint(request), settings.FORGOT_PER_IP_HOUR, 3600)
    rate_limit.check("forgot-id", rate_limit.identifier_key(ident), settings.FORGOT_PER_IDENTIFIER_HOUR, 3600)
    user = _find_login_user(db, ident)
    answer = {"message": RESET_REQUESTED, "delivery_mode": transport.name}
    eligible = bool(user and user.is_active and user.email and user.email_verified_at)
    if eligible and user.role in PRIVILEGED_ROLES:
        recent = user.email_changed_at and (utcnow_naive() - user.email_changed_at) < timedelta(hours=settings.STAFF_RESET_COOLDOWN_HOURS)
        if recent:
            record_audit(db, user.username, "PASSWORD_RESET_BLOCKED", "user", user.id, "staff email changed recently", role=user.role)
            db.commit()
            eligible = False
    if not eligible:
        ver._reset_hash(__import__("secrets").token_urlsafe(32))   # similar work for unknown accounts
        return answer
    token = ver.issue_reset_token(db, user)
    record_audit(db, user.username, "PASSWORD_RESET_REQUESTED", "user", user.id, role=user.role)
    db.commit()
    link = f"{settings.PUBLIC_APP_URL.rstrip('/')}/?reset={token}"
    background.add_task(notif.notify, notif.Message(
        "EMAIL", user.email, "Reset your RescueNet X password",
        f"Someone asked to reset the password of your RescueNet X account. If it was you, open this link within "
        f"{settings.RESET_TOKEN_MINUTES} minutes: {link}\nIf it was not you, ignore this message; your password has not changed.",
        "PASSWORD_RESET", user.id))
    return answer


@router.post("/password/reset")
def reset_password(payload: ResetIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Set a new password with a single-use reset token. Expired, reused, unknown and malformed tokens all get the same
    answer. Success ends every session of the account and does NOT sign anyone in."""
    rate_limit.check("reset-ip", rate_limit.client_fingerprint(request), settings.RESET_PER_IP_HOUR, 3600)
    _check_password(payload.new_password)          # a weak password does not burn the token
    found = ver.find_valid_reset(db, payload.token)
    if found is None or not found[1].is_active:
        raise HTTPException(status_code=400, detail=INVALID_RESET)
    row, user = found
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=422, detail="Choose a password you are not already using.")
    if not ver.claim_reset(db, row):
        raise HTTPException(status_code=400, detail=INVALID_RESET)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow_naive()
    user.must_change_password = False
    user.failed_logins, user.locked_until = 0, None
    ver.void_reset_tokens(db, user.id)
    record_audit(db, user.username, "PASSWORD_RESET_COMPLETED", "user", user.id, "via emailed link", role=user.role)
    sess.revoke_all_sessions(db, user, "PASSWORD_RESET", actor=user.username, role=user.role)
    db.commit()
    rate_limit.clear("login-account", rate_limit.identifier_key(user.username))
    if user.email and user.email_verified_at:
        background.add_task(notif.notify, notif.Message(
            "EMAIL", user.email, "Your RescueNet X password was changed",
            "The password of your RescueNet X account was just changed using a reset link. If this was not you, contact your "
            "administrator immediately.", "PASSWORD_RESET_NOTICE", user.id))
    return {"message": "Password changed. Every device was signed out; sign in with your new password."}


# ---------- administration ----------
@router.get("/users", response_model=dict)
def list_users(role: Optional[str] = Query(None), admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role.upper())
    users = q.order_by(User.role, User.username).all()
    return {"items": [user_out(db, u) for u in users], "count": len(users), "roles": ROLES}


@router.get("/team-options", response_model=dict)
def team_options(admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    """Just id and name of each squad, so an administrator can attach a rescue officer account to a team without
    being able to see squad locations, status or missions (team.view is an operations permission)."""
    teams = db.query(RescueTeam.id, RescueTeam.name).order_by(RescueTeam.name).all()
    return {"items": [{"id": t.id, "name": t.name} for t in teams]}


STAFF_ACCOUNT_NOTICE = (
    "Accounts for staff, administrators and developers cannot be created or have their password set by an administrator: "
    "that would let the administrator obtain operational authority. Owner-controlled invitation and recovery arrive with "
    "milestones S3-S5. Until then a server operator can provision or recover such an account with "
    "backend/scripts/account_admin.py (see docs/security/S2_SESSIONS.md)."
)


def _deny_admin_action(db: Session, admin: User, action: str, detail: str, message: str) -> None:
    record_audit(db, actor_name(admin), action, "user", detail, message[:120], role="ADMIN")
    db.commit()
    raise HTTPException(status_code=403, detail=message)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    """Administrators may create citizen and volunteer accounts only. Creating a privileged account with a password the
    administrator chose would hand them that account's authority, so it is disabled until owner-controlled invitations (S5)."""
    ensure_recent_mfa(admin)         # privileged account management: a second factor must be recent
    if payload.role in PRIVILEGED_ROLES:
        _deny_admin_action(db, admin, "ADMIN_PRIVILEGED_ACCOUNT_CREATE_DENIED", payload.username, STAFF_ACCOUNT_NOTICE)
    _check_password(payload.password)
    username = payload.username.lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="That username is taken")
    user = User(username=username, full_name=payload.full_name, email=(payload.email or None), phone=payload.phone,
                role=payload.role, password_hash=hash_password(payload.password), team_id=None,
                password_changed_at=utcnow_naive())
    db.add(user)
    db.flush()
    record_audit(db, actor_name(admin), "USER_CREATED", "user", user.id, f"{username} as {payload.role}", role="ADMIN")
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    ensure_recent_mfa(admin)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (payload.is_active is False or (payload.role and payload.role != "ADMIN")):
        raise HTTPException(status_code=409, detail="You cannot disable or demote your own admin account")
    # Escalation guards, checked BEFORE anything is changed:
    if payload.new_password and user.role in PRIVILEGED_ROLES:
        _deny_admin_action(db, admin, "ADMIN_PRIVILEGED_PASSWORD_RESET_DENIED", user.username, STAFF_ACCOUNT_NOTICE)
    if payload.role and payload.role != user.role and payload.role in PRIVILEGED_ROLES:
        _deny_admin_action(db, admin, "ADMIN_ROLE_PROMOTION_DENIED", f"{user.username}->{payload.role}",
                           "Administrators cannot grant staff, administrator or developer roles. " + STAFF_ACCOUNT_NOTICE)
    if payload.team_id is not None and user.role != "RESCUE_OFFICER" and payload.role != "RESCUE_OFFICER":
        payload = payload.model_copy(update={"team_id": None})

    changes: List[str] = []
    revoke_reason = None
    for field in ("full_name", "role", "team_id", "is_active"):
        value = getattr(payload, field)
        if value is not None and getattr(user, field) != value:
            setattr(user, field, value)
            changes.append(f"{field}={value}")
            if field == "is_active" and value is False:
                revoke_reason = revoke_reason or "ACCOUNT_DEACTIVATED"
            elif field == "role":
                revoke_reason = revoke_reason or "ROLE_CHANGED"
            elif field == "team_id":
                revoke_reason = revoke_reason or "TEAM_CHANGED"
    if user.role == "RESCUE_OFFICER" and not user.team_id:
        db.rollback()
        raise HTTPException(status_code=422, detail="Rescue officers must belong to a team")
    if payload.new_password:
        _check_password(payload.new_password)
        user.password_hash = hash_password(payload.new_password)
        user.password_changed_at = utcnow_naive()
        user.must_change_password = True      # the administrator chose it, so only the owner's own change makes it safe
        user.failed_logins, user.locked_until = 0, None
        changes.append("password reset")
        record_audit(db, actor_name(admin), "USER_PASSWORD_RESET_BY_ADMIN", "user", user.id, user.username, role="ADMIN")
        revoke_reason = "PASSWORD_RESET"
    record_audit(db, actor_name(admin), "USER_UPDATED", "user", user.id, ", ".join(changes) or "no change", role="ADMIN")
    if revoke_reason:
        # Access changed (or may have been taken over): end every existing session of this account immediately.
        sess.revoke_all_sessions(db, user, revoke_reason, actor=actor_name(admin), role="ADMIN")
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.post("/users/{user_id}/revoke-sessions")
def admin_revoke_sessions(user_id: int, admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    """Incident response: sign an account out everywhere (for example after a suspected theft)."""
    ensure_recent_mfa(admin)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    n = sess.revoke_all_sessions(db, user, "ADMIN_REVOKED", actor=actor_name(admin), role="ADMIN")
    db.commit()
    return {"message": f"{n} session(s) ended", "sessions_ended": n}


@router.get("/audit", response_model=dict)
def audit_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    admin: User = Depends(require_permission(P.AUDIT_READ)),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action.upper())
    if actor:
        q = q.filter(AuditLog.actor == actor)
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {"items": [AuditEntryOut.model_validate(r) for r in rows], "count": total}
