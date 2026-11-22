"""Sign-in, sign-up and account management.

Three portals, each accepting only its own roles:
  admin       ADMIN (administrators and developers)
  operations  COMMANDER, OPERATOR, RESCUE_OFFICER (rescue operations department)
  public      CITIZEN, VOLUNTEER (self sign-up)
Department and admin accounts are created by an administrator.
"""

from datetime import timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import actor_name, get_current_user, require_permission, utcnow_naive
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
from app.services import sessions as sess
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
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
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


def user_out(db: Session, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.portal = ROLE_PORTAL.get(user.role, "")
    out.permissions = sorted(permissions_for_role(user.role))
    if user.volunteer_id:
        vol = db.query(Volunteer).filter(Volunteer.id == user.volunteer_id).first()
        out.volunteer_verified = bool(vol and vol.is_verified)
    return out


def start_session(db: Session, user: User, request: Request, response: Response, remember: bool = False) -> TokenOut:
    """Create a session, set the refresh/CSRF cookies and return the short-lived access token. Caller commits first."""
    session, refresh = sess.create_session(db, user, request, remember)
    db.commit()
    sess.set_session_cookies(response, session, refresh)
    return TokenOut(access_token=sess.access_token_for(session, user), expires_in=int(settings.access_token_minutes * 60),
                    csrf_token=sess.csrf_value(session.id), user=user_out(db, user))


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


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ident = payload.username.strip().lower()
    user = db.query(User).filter((User.username == ident) | (User.email == ident)).first()
    now = utcnow_naive()
    generic = HTTPException(status_code=401, detail="Wrong username or password")
    if user is None:
        verify_password(payload.password, hash_password("timing-equaliser"))  # similar response time
        raise generic
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in a few minutes.")
    if not verify_password(payload.password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
            record_audit(db, user.username, "LOGIN_LOCKED", "user", user.id, f"{MAX_FAILED_LOGINS} failed attempts", role=user.role)
        db.commit()
        raise generic
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled. Contact an administrator.")
    if user.role not in PORTALS[payload.portal]:
        portal = ROLE_PORTAL.get(user.role, "?")
        raise HTTPException(status_code=403, detail=f"This account signs in through the '{portal}' portal.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    record_audit(db, user.username, "LOGIN", "user", user.id, f"portal {payload.portal}", role=user.role)
    return start_session(db, user, request, response, payload.remember)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Self sign-up for citizens and volunteers. Volunteers start unverified."""
    _check_password(payload.password)
    username = payload.username.lower()
    email = payload.email.strip().lower() if payload.email else None
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="That username is taken")
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists")

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
                    csrf_token=sess.csrf_value(session.id), user=user_out(db, user))
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
    """Change your own password. Every session, including this one, ends; a fresh session is started for this device."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    _check_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow_naive()
    record_audit(db, user.username, "PASSWORD_CHANGED", "user", user.id, role=user.role)
    ended = sess.revoke_all_sessions(db, user, "PASSWORD_CHANGED", actor=user.username, role=user.role)
    out = start_session(db, user, request, response)
    return {"message": "Password changed. All other sessions were signed out.", "sessions_ended": ended,
            **out.model_dump(mode="json")}


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
