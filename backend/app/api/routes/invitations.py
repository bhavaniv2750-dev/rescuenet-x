"""Invitation endpoints (S5). See app/services/provisioning.py for the whole model.

There is deliberately NO endpoint that issues an invitation: privileged invitations are issued by a host operator
(scripts/account_admin.py invite). Administrators can only list and revoke them.
"""

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import actor_name, ensure_recent_mfa, require_permission
from app.api.routes.auth import TokenOut, USERNAME_PATTERN, _check_password, start_session
from app.core.config import settings
from app.core.permissions import P
from app.db.session import get_db
from app.models.entities import Agency, Invitation, User
from app.services import provisioning as prov
from app.services import rate_limit
from app.services import sessions as sess
from app.services import verification as ver
from app.services.audit import record_audit
from app.services.notifications import mask_email

router = APIRouter()


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AcceptIn(TokenIn):
    username: str = Field(pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=30)


def _invalid() -> HTTPException:
    # One answer for unknown, expired, revoked, used and raced invitations.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=prov.INVALID)


@router.post("/inspect")
def inspect(payload: TokenIn, request: Request, db: Session = Depends(get_db)):
    """What a recipient needs to see before accepting. Reveals nothing unless the token is currently usable."""
    rate_limit.check("invite-inspect", rate_limit.client_fingerprint(request), settings.INVITE_INSPECT_PER_IP_HOUR, 3600)
    inv = prov.find_by_token(db, payload.token)
    if not prov.usable(inv):
        raise _invalid()
    agency = db.get(Agency, inv.agency_id) if inv.agency_id else None
    return {"role": inv.role, "agency": agency.name if agency else None, "recipient": mask_email(inv.recipient_email),
            "expires_at": inv.expires_at,
            "steps": ["Choose your own password", "Verify your email address", "Set up multi-factor authentication"]}


@router.post("/accept", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def accept(payload: AcceptIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create the account the invitation was issued for. The owner chooses username and password; the role, agency, team and
    email address come from the invitation only. The new session is RESTRICTED: no operational permission until contact
    verification and MFA enrolment are complete."""
    rate_limit.check("invite-accept", rate_limit.client_fingerprint(request), settings.INVITE_ACCEPT_PER_IP_HOUR, 3600)
    _check_password(payload.password)
    phone = ver.normalise_phone(payload.phone) if payload.phone else None
    username = payload.username.lower()
    try:
        user = prov.accept(db, payload.token, username=username, full_name=payload.full_name.strip(), password=payload.password, phone=phone)
        db.commit()
    except prov.InvitationError:
        db.rollback()
        raise _invalid()
    except ValueError:
        raise HTTPException(status_code=409, detail="That username is taken. Choose another.")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is taken. Choose another.")
    db.refresh(user)
    return start_session(db, user, request, response)


def _inv_out(db: Session, inv: Invitation) -> dict:
    agency = db.get(Agency, inv.agency_id) if inv.agency_id else None
    return {"id": inv.id, "role": inv.role, "recipient": mask_email(inv.recipient_email), "agency": agency.name if agency else None,
            "team_id": inv.team_id, "status": prov.invitation_status(inv), "created_at": inv.created_at,
            "expires_at": inv.expires_at, "created_by": inv.created_by, "used_at": inv.used_at, "revoked_at": inv.revoked_at}


@router.get("", response_model=dict)
@router.get("/", response_model=dict, include_in_schema=False)
def list_invitations(admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    rows = db.query(Invitation).order_by(Invitation.id.desc()).limit(200).all()
    return {"items": [_inv_out(db, r) for r in rows], "count": len(rows),
            "note": "Invitations for staff roles are issued by a server operator, not from this console."}


@router.post("/{invitation_id}/revoke")
def revoke_invitation(invitation_id: int, admin: User = Depends(require_permission(P.USER_MANAGE)), db: Session = Depends(get_db)):
    ensure_recent_mfa(admin)
    inv = db.get(Invitation, invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    changed = prov.revoke(db, inv, actor_name(admin), admin.role)
    db.commit()
    return {"revoked": changed, "status": prov.invitation_status(db.get(Invitation, invitation_id))}
