"""Backend-driven workspaces and navigation (S6).

The server decides which workspace a caller has and which navigation entries exist for them; the frontend only renders what it
is told. Everything is derived from PERMISSIONS (app/core/permissions.py) and the caller's authentication state
(app/services/auth_state.py), never from a role name, so a role change or a restricted state changes the result immediately.

Two experiences
* PUBLIC        guests, citizens, volunteers: flood information and emergency reporting.
* PROFESSIONAL  rescue officers, operators, commanders, administrators, developers: the console. Membership in the console grants
                no operational authority by itself: each entry below needs its own permission, and the API enforces the same
                permissions on every request. Administrators and developers see only their real responsibilities (identity/system
                administration, diagnostics): they are given no incident, dispatch, triage or alert entries.

A navigation entry that is not in the answer does not exist for the caller. Navigation is a convenience: the API remains the final
authorisation boundary for every request (tests/test_endpoint_authorization.py).

The payload contains identifiers and booleans only: no incident, citizen, evidence or credential data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.core.config import settings
from app.core.permissions import P, PRIVILEGED_ROLES, user_permissions
from app.services import auth_state as astate

PUBLIC, PROFESSIONAL = "PUBLIC", "PROFESSIONAL"
PUBLIC_PREFIX, PROFESSIONAL_PREFIX = "/public", "/console"

# Entries a professional with an operational OR administrative responsibility sees (developers are diagnostics-only: excluded).
RESPONSIBILITY = (P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED, P.USER_MANAGE)
FIELD_OR_COMMAND = (P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED)


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str                       # also the page name used by the existing frontend views
    section: str
    experiences: Tuple[str, ...]
    any_of: Tuple[str, ...]          # at least one of these permissions
    signed_in: bool = False          # needs an account (not a guest)
    slug: str = ""

    def path(self, experience: str) -> str:
        if self.id == "home":
            return "/"
        if self.id == "account":
            return "/account"
        prefix = PUBLIC_PREFIX if experience == PUBLIC else PROFESSIONAL_PREFIX
        return f"{prefix}/{self.slug or self.id}"


CATALOGUE: List[NavItem] = [
    # ---- public experience
    NavItem("home", "Home", "Flood watch", (PUBLIC,), (P.PUBLIC_READ,)),
    NavItem("flood-twin", "Flood Digital Twin", "Flood watch", (PUBLIC,), (P.PUBLIC_READ,)),
    NavItem("forecasting", "Flood Forecasting", "Flood watch", (PUBLIC,), (P.PUBLIC_READ,)),
    NavItem("alerts", "Emergency Alerts", "Flood watch", (PUBLIC,), (P.PUBLIC_READ,)),
    NavItem("facilities", "Facilities & Shelters", "Flood watch", (PUBLIC,), (P.PUBLIC_READ,), slug="shelters"),
    NavItem("report-emergency", "Report Emergency", "Help", (PUBLIC,), (P.INCIDENT_REPORT,), slug="report"),
    NavItem("my-reports", "My Reports", "Account", (PUBLIC,), (P.INCIDENT_VIEW_OWN,), signed_in=True),
    # ---- professional console
    NavItem("overview", "Overview", "Command", (PROFESSIONAL,), (P.INCIDENT_VIEW_ALL,)),
    NavItem("operations", "Rescue Operations", "Command", (PROFESSIONAL,), (P.INCIDENT_VIEW_ALL,)),
    NavItem("missions", "My Missions", "Command", (PROFESSIONAL,), (P.INCIDENT_VIEW_ASSIGNED,)),
    NavItem("ai-supervisor", "AI Supervisor", "Command", (PROFESSIONAL,), (P.TRIAGE_RUN,), slug="supervisor"),
    NavItem("alerts", "Emergency Alerts", "Command", (PROFESSIONAL,), RESPONSIBILITY),
    NavItem("flood-twin", "Flood Digital Twin", "Intelligence", (PROFESSIONAL,), FIELD_OR_COMMAND),
    NavItem("forecasting", "Flood Forecasting", "Intelligence", (PROFESSIONAL,), RESPONSIBILITY),
    NavItem("data-models", "Data & Models", "Intelligence", (PROFESSIONAL,), (P.DATA_VIEW,), slug="data"),
    NavItem("volunteers", "Volunteer Coordination", "Resources", (PROFESSIONAL,), (P.VOLUNTEER_VIEW,)),
    NavItem("facilities", "Facilities & Shelters", "Resources", (PROFESSIONAL,), RESPONSIBILITY, slug="shelters"),
    NavItem("records", "Rescue Records", "Resources", (PROFESSIONAL,), (P.RECORD_VIEW,)),
    NavItem("incident-reports", "Incident Reports", "Resources", (PROFESSIONAL,), (P.INCIDENT_VERIFY,), slug="incidents"),
    NavItem("report-emergency", "Report Emergency", "Resources", (PROFESSIONAL,), (P.INCIDENT_VIEW_ASSIGNED,), slug="report"),
    NavItem("admin-console", "Admin Console", "System", (PROFESSIONAL,), (P.USER_MANAGE,), slug="admin"),
    NavItem("agencies", "Agencies & Invitations", "System", (PROFESSIONAL,), (P.AGENCY_MANAGE,)),
    NavItem("audit-log", "Audit Log", "System", (PROFESSIONAL,), (P.AUDIT_READ,), slug="audit"),
    NavItem("diagnostics", "Diagnostics", "System", (PROFESSIONAL,), (P.SYSTEM_DIAGNOSTICS,)),
    NavItem("settings", "Settings", "System", (PROFESSIONAL,), (P.USER_MANAGE,)),
    # ---- shared by both experiences
    NavItem("account", "My Account", "Account", (PUBLIC, PROFESSIONAL), (P.ACCOUNT_OWN,), signed_in=True),
]

# First allowed entry of this list is where the user lands.
HOME_ORDER = ["missions", "overview", "admin-console", "diagnostics", "home"]

SHARED_PATHS = {"/": "public home", "/account": "account and security (both experiences)"}
SECTION_ORDER = ["Flood watch", "Help", "Command", "Intelligence", "Resources", "System", "Account"]

# What the UI may offer, as booleans derived from permissions (never from the role name).
CAPABILITIES: Dict[str, Tuple[str, ...]] = {
    "report_incident": (P.INCIDENT_REPORT,),
    "view_own_reports": (P.INCIDENT_VIEW_OWN,),
    "view_incidents": FIELD_OR_COMMAND,
    "operations_console": (P.INCIDENT_VIEW_ALL,),
    "manage_incidents": (P.INCIDENT_VERIFY,),
    "run_triage": (P.TRIAGE_RUN,),
    "approve_dispatch": (P.DISPATCH_APPROVE,),
    "manage_alerts": (P.ALERT_PUBLISH,),
    "manage_volunteers": (P.VOLUNTEER_MANAGE,),
    "manage_facilities": (P.FACILITY_MANAGE,),
    "view_records": (P.RECORD_VIEW,),
    "export_records": (P.RECORD_EXPORT,),
    "manage_users": (P.USER_MANAGE,),
    "manage_agencies": (P.AGENCY_MANAGE,),
    "read_audit": (P.AUDIT_READ,),
    "view_diagnostics": (P.SYSTEM_DIAGNOSTICS,),
}

STEP_FOR_STATE = {
    astate.PASSWORD_CHANGE_PENDING: "CHANGE_PASSWORD",
    astate.CONTACT_VERIFICATION_PENDING: "VERIFY_CONTACT",
    astate.MFA_ENROLLMENT_PENDING: "ENROLL_MFA",
    astate.MFA_CHALLENGE_PENDING: "SIGN_IN_WITH_MFA",
}


def experience_for(role: Optional[str]) -> str:
    return PROFESSIONAL if role in PRIVILEGED_ROLES else PUBLIC


def all_paths() -> List[str]:
    paths = set()
    for item in CATALOGUE:
        for exp in item.experiences:
            paths.add(item.path(exp))
    return sorted(paths)


def remaining_steps(user, mfa_enabled: bool) -> List[str]:
    """Activation steps still ahead for this account, in order (informational; the state machine enforces them)."""
    steps: List[str] = []
    if user.must_change_password:
        steps.append("CHANGE_PASSWORD")
    contact = astate.contact_verification_pending(user)
    if contact:
        steps.append("VERIFY_CONTACT")
    if user.role in PRIVILEGED_ROLES and not mfa_enabled:
        steps.append("ENROLL_MFA")
    return steps


def _fresh(session) -> bool:
    if session is None or session.assurance != "MFA" or session.mfa_at is None:
        return False
    return datetime.now(timezone.utc).replace(tzinfo=None) - session.mfa_at <= timedelta(minutes=settings.MFA_FRESH_MINUTES)


def build_workspace(user=None, state: Optional[str] = None, session=None, mfa_enabled: bool = False) -> Dict[str, Any]:
    """The workspace of a guest (user None) or of a signed-in user in the given authentication state."""
    role = getattr(user, "role", None)
    experience = experience_for(role)
    authenticated = user is not None and state == astate.AUTHENTICATED
    perms: FrozenSet[str] = user_permissions(user) if (user is None or authenticated) else frozenset()
    signed_in = user is not None

    # Guests and AUTHENTICATED sessions get entries; a session in a restricted state (password change, contact verification, MFA)
    # gets none: nothing operational is offered until activation is complete.
    items = [it for it in CATALOGUE
             if (authenticated or user is None) and experience in it.experiences and (signed_in or not it.signed_in)
             and set(it.any_of) & perms]
    sections: List[Dict[str, Any]] = []
    for title in SECTION_ORDER:
        group = [{"id": it.id, "label": it.label, "path": it.path(experience)} for it in items if it.section == title]
        if group:
            sections.append({"id": title.lower().replace(" ", "-"), "title": title, "items": group})
    ids = [it.id for it in items]
    home_id = next((h for h in HOME_ORDER if h in ids), ids[0] if ids else None)
    home_item = next((it for it in items if it.id == home_id), None)

    level = "NONE" if user is None else (getattr(session, "assurance", None) or "PASSWORD")
    caps = {name: bool(set(needed) & perms) for name, needed in CAPABILITIES.items()}
    return {
        "experience": experience,
        "authenticated": authenticated,
        "activation": {
            "state": state or astate.UNAUTHENTICATED,
            "complete": authenticated or user is None,
            "restricted_reason": STEP_FOR_STATE.get(state or "", None),
            "remaining_steps": remaining_steps(user, mfa_enabled) if signed_in and not authenticated else [],
        },
        "assurance": {
            "level": level,
            "mfa_enabled": bool(mfa_enabled),
            "mfa_required": role in PRIVILEGED_ROLES,
            "recent_mfa": _fresh(session),
        },
        "agency_id": getattr(user, "agency_id", None) if authenticated else None,
        "team_id": getattr(user, "team_id", None) if authenticated else None,
        "capabilities": caps,
        "navigation": {"sections": sections, "ids": ids, "home": home_item.path(experience) if home_item else None,
                       "home_id": home_id},
        "known_paths": all_paths(),
    }
