"""Sign-in, sign-up and account management.

Three portals, each accepting only its own roles:
  admin       ADMIN (administrators and developers)
  operations  COMMANDER, OPERATOR, RESCUE_OFFICER (rescue operations department)
  public      CITIZEN, VOLUNTEER (self sign-up)
Department and admin accounts are created by an administrator.
"""

from datetime import timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import actor_name, get_current_user, require_roles, utcnow_naive
from app.core.security import (
    PORTALS,
    ROLE_PORTAL,
    ROLES,
    create_access_token,
    hash_password,
    password_problem,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import AuditLog, RescueTeam, User, Volunteer
from app.services.audit import record_audit
from app.services.ids import next_volunteer_id

router = APIRouter()

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5
USERNAME_PATTERN = r"^[a-zA-Z0-9_.\-]{3,60}$"


# ---------- schemas ----------
class LoginRequest(BaseModel):
    portal: Literal["admin", "operations", "public"]
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
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    role: Literal["ADMIN", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]
    username: str = Field(pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    team_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[Literal["ADMIN", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]] = None
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
    if user.volunteer_id:
        vol = db.query(Volunteer).filter(Volunteer.id == user.volunteer_id).first()
        out.volunteer_verified = bool(vol and vol.is_verified)
    return out


def _check_password(pw: str) -> None:
    problem = password_problem(pw)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


# ---------- public endpoints ----------
@router.get("/portals")
def list_portals():
    demo = settings.SEED_DEMO_USERS
    return {
        "demo_mode": demo,
        # Shown on the sign-in page only while demo accounts are enabled (development / project demo).
        "demo_accounts": [
            {"portal": ROLE_PORTAL[role], "username": username, "role": role, "label": label}
            for username, label, role in [
                ("citizen", "Citizen", "CITIZEN"), ("volunteer", "Volunteer", "VOLUNTEER"),
                ("operator", "Control room operator", "OPERATOR"), ("officer", "Rescue officer", "RESCUE_OFFICER"),
                ("commander", "Incident commander", "COMMANDER"), ("admin", "Administrator", "ADMIN"),
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
def login(payload: LoginRequest, db: Session = Depends(get_db)):
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
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user_out(db, user))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
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
    return TokenOut(access_token=create_access_token(user.id, user.role), user=user_out(db, user))


# ---------- signed-in user ----------
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


@router.post("/me/password")
def change_password(payload: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    _check_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    record_audit(db, user.username, "PASSWORD_CHANGED", "user", user.id, role=user.role)
    db.commit()
    return {"message": "Password changed"}


# ---------- administration ----------
@router.get("/users", response_model=dict)
def list_users(role: Optional[str] = Query(None), admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role.upper())
    users = q.order_by(User.role, User.username).all()
    return {"items": [user_out(db, u) for u in users], "count": len(users), "roles": ROLES}


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    _check_password(payload.password)
    username = payload.username.lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="That username is taken")
    if payload.role == "RESCUE_OFFICER":
        if not payload.team_id or not db.query(RescueTeam).filter(RescueTeam.id == payload.team_id).first():
            raise HTTPException(status_code=422, detail="Rescue officers must belong to an existing team (team_id)")
    user = User(username=username, full_name=payload.full_name, email=(payload.email or None), phone=payload.phone,
                role=payload.role, password_hash=hash_password(payload.password), team_id=payload.team_id)
    db.add(user)
    db.flush()
    record_audit(db, actor_name(admin), "USER_CREATED", "user", user.id, f"{username} as {payload.role}", role="ADMIN")
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (payload.is_active is False or (payload.role and payload.role != "ADMIN")):
        raise HTTPException(status_code=409, detail="You cannot disable or demote your own admin account")
    changes: List[str] = []
    for field in ("full_name", "role", "team_id", "is_active"):
        value = getattr(payload, field)
        if value is not None and getattr(user, field) != value:
            setattr(user, field, value)
            changes.append(f"{field}={value}")
    if user.role == "RESCUE_OFFICER" and not user.team_id:
        raise HTTPException(status_code=422, detail="Rescue officers must belong to a team")
    if payload.new_password:
        _check_password(payload.new_password)
        user.password_hash = hash_password(payload.new_password)
        user.failed_logins, user.locked_until = 0, None
        changes.append("password reset")
    record_audit(db, actor_name(admin), "USER_UPDATED", "user", user.id, ", ".join(changes) or "no change", role="ADMIN")
    db.commit()
    db.refresh(user)
    return user_out(db, user)


@router.get("/audit", response_model=dict)
def audit_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    admin: User = Depends(require_roles("ADMIN", "COMMANDER")),
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
