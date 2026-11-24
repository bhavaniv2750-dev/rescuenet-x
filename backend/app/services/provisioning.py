"""Invitations and host-level provisioning of privileged accounts (S5).

Who can do what
* ISSUE an invitation for a privileged role: only a person with shell access to the server (scripts/account_admin.py invite).
  There is no web endpoint that issues one, so an administrator in the web console cannot create operational authority,
  not even for themselves ("self-invite").
* INSPECT / ACCEPT: whoever holds the single-use token, at /api/invitations/*. Acceptance creates the account with the
  invited role, agency, team and EMAIL ADDRESS; the new owner chooses their own password. Nothing else is taken from the
  request. The account then has no permissions until: contact verification (a code sent to the invited address) -> MFA
  enrolment -> a full MFA session (auth_state.py).
* REVOKE: a host operator or an administrator (revocation only removes access).

Tokens: 256-bit random, shown once, only the SHA-256 is stored. Acceptance claims the invitation with one conditional UPDATE inside
the same transaction that creates the account, so two simultaneous acceptances cannot both succeed.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import PRIVILEGED_ROLES
from app.core.security import hash_password, password_problem
from app.models.entities import Agency, Invitation, RescueTeam, User
from app.services import verification as ver
from app.services.audit import record_audit

MAX_INVITATION_HOURS = 168
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INVALID = "This invitation is invalid, expired or already used. Ask the person who invited you for a new one."


class InvitationError(Exception):
    """Carries a message that is safe to show. Acceptance failures are deliberately generic."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def one_time_password() -> str:
    while True:
        pw = secrets.token_urlsafe(14)
        if password_problem(pw) is None:
            return pw


def invitation_status(inv: Invitation, now: Optional[datetime] = None) -> str:
    now = now or _now()
    if inv.used_at is not None:
        return "ACCEPTED"
    if inv.revoked_at is not None:
        return "REVOKED"
    if inv.expires_at <= now:
        return "EXPIRED"
    return "PENDING"


def invitation_link(token: str) -> str:
    # The token travels in the URL FRAGMENT, which browsers never send to a server (so it stays out of access logs).
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}/#invite={token}"


def issue_invitation(db: Session, *, role: str, email: str, actor: str, reason: str, agency_id: Optional[int] = None,
                     team_id: Optional[str] = None, hours: Optional[int] = None) -> tuple[Invitation, str]:
    """Create an invitation. Returns (row, plaintext token); the token exists nowhere else. Caller commits."""
    if role not in PRIVILEGED_ROLES:
        raise InvitationError("Invitations are for privileged roles only. Citizens and volunteers register themselves.")
    address = ver.normalise_email(email)
    if not address or len(address) > 120 or not EMAIL_RE.match(address):
        raise InvitationError("A valid recipient email address is required.")
    if agency_id is not None:
        agency = db.get(Agency, agency_id)
        if agency is None or not agency.is_active:
            raise InvitationError("That agency does not exist or is inactive.")
    if role == "RESCUE_OFFICER":
        if not (team_id and db.get(RescueTeam, team_id)):
            raise InvitationError("A rescue officer invitation needs an existing team id.")
    else:
        team_id = None
    life = hours if hours is not None else settings.INVITATION_HOURS
    if not 1 <= life <= MAX_INVITATION_HOURS:
        raise InvitationError(f"Invitation lifetime must be between 1 and {MAX_INVITATION_HOURS} hours.")
    token = secrets.token_urlsafe(32)
    inv = Invitation(token_hash=token_hash(token), role=role, recipient_email=address, agency_id=agency_id, team_id=team_id,
                     created_by=actor[:80], reason=(reason or "")[:300], created_at=_now(), expires_at=_now() + timedelta(hours=life))
    db.add(inv)
    db.flush()
    record_audit(db, actor, "INVITATION_ISSUED", "invitation", inv.id,
                 f"{role} to {address}; agency {agency_id}; team {team_id}; expires {inv.expires_at:%Y-%m-%d %H:%M}Z; reason: {reason}"[:480],
                 role="HOST_OPERATOR")
    return inv, token


def find_by_token(db: Session, token: str) -> Optional[Invitation]:
    return db.query(Invitation).filter(Invitation.token_hash == token_hash(token)).first()


def usable(inv: Optional[Invitation]) -> bool:
    return inv is not None and invitation_status(inv) == "PENDING"


def revoke(db: Session, inv: Invitation, actor: str, role: str) -> bool:
    """Revoke a pending invitation (idempotent: False when it was no longer pending). Caller commits."""
    res = db.execute(update(Invitation).where(Invitation.id == inv.id, Invitation.used_at.is_(None), Invitation.revoked_at.is_(None))
                     .values(revoked_at=_now(), revoked_by=actor[:80]))
    if res.rowcount != 1:
        return False
    record_audit(db, actor, "INVITATION_REVOKED", "invitation", inv.id, f"{inv.role} to {inv.recipient_email}", role=role)
    return True


def accept(db: Session, token: str, *, username: str, full_name: str, password: str, phone: Optional[str]) -> User:
    """Claim the invitation and create the account in ONE transaction. Raises InvitationError(INVALID) for every unusable
    invitation (unknown, expired, revoked, used, race lost) so failures reveal nothing. The caller commits (or rolls back)."""
    inv = find_by_token(db, token)
    if not usable(inv):
        raise InvitationError(INVALID)
    claimed = db.execute(update(Invitation)
                         .where(Invitation.id == inv.id, Invitation.used_at.is_(None), Invitation.revoked_at.is_(None),
                                Invitation.expires_at > _now())
                         .values(used_at=_now()))
    if claimed.rowcount != 1:
        db.rollback()
        raise InvitationError(INVALID)
    if db.query(User).filter(User.username == username).first():
        db.rollback()
        raise ValueError("username-taken")
    agency_id = inv.agency_id
    if agency_id is not None:
        agency = db.get(Agency, agency_id)
        if agency is None or not agency.is_active:
            agency_id = None            # an agency deactivated since issuing: the account is created without it
    user = User(username=username, full_name=full_name, role=inv.role, email=inv.recipient_email, phone=phone,
                password_hash=hash_password(password), team_id=inv.team_id, agency_id=agency_id,
                contact_verification_required=True, password_changed_at=_now())
    db.add(user)
    db.flush()
    db.execute(update(Invitation).where(Invitation.id == inv.id).values(accepted_user_id=user.id))
    record_audit(db, username, "INVITATION_ACCEPTED", "invitation", inv.id, f"{inv.role}; account {user.id}; created by {inv.created_by}",
                 role=inv.role)
    record_audit(db, username, "PRIVILEGED_ACCOUNT_ACTIVATED_PENDING", "user", user.id,
                 "awaiting contact verification and MFA enrolment before any operational access", role=inv.role)
    return user
