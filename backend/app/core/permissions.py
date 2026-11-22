"""Named permissions and the single role-to-permission matrix.

Every authorization decision in the backend asks one question: "does this user's role hold permission X?"
(plus, for resource-scoped permissions, "is this the user's own / assigned resource?"). Nothing outside this file
decides what a role may do. Navigation in the frontend is a convenience only; the API enforces everything.

Separation of duties (deliberate, enforced by tests/test_permission_policy.py):
* ADMIN manages identities and the system. It holds NO dispatch, triage, commander-approval or alert-publication
  permission and cannot see incident details or evidence photographs.
* DEVELOPER holds diagnostics only. No citizen/incident data, no operational rescue controls.
* DISPATCH APPROVAL belongs to COMMANDER alone.
* RESCUE_OFFICER sees only missions (and their evidence) assigned to their own team.
* CITIZEN and VOLUNTEER reach only their own records plus public resources.

Not covered here (later milestones): MFA and verified-contact requirements for privileged roles (S3/S4), per-user
grants and revocations (S5), and the draft/review/approve alert workflow (Phase E).
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional


class P:
    """Permission names."""
    # --- public / self-service (guests hold the first group without signing in)
    INCIDENT_REPORT = "incident.report"            # report an emergency (also open to guests, rate-limited)
    INCIDENT_TRACK = "incident.track"              # follow a report with its tracking code
    PUBLIC_READ = "public.read"                    # alerts, shelters, flood status/forecast, public datasets
    ACCOUNT_OWN = "account.own"                    # own profile and password
    ALERT_SEEN = "alert.seen"                      # mark an alert as seen (counts only, never changes status)
    INCIDENT_VIEW_OWN = "incident.view_own"        # reports the user filed
    EVIDENCE_VIEW_OWN = "evidence.view_own"
    # --- incidents
    INCIDENT_VIEW_ALL = "incident.view_all"
    INCIDENT_VIEW_ASSIGNED = "incident.view_assigned"
    INCIDENT_VERIFY = "incident.verify"            # verification, queueing, rejection, duplicates, any lifecycle step
    INCIDENT_PROGRESS = "incident.progress"        # field progress (in transit/on scene/resolved) on assigned missions
    INCIDENT_EDIT_RISK = "incident.edit_risk"      # raise severity / headcount
    INCIDENT_REDUCE_RISK = "incident.reduce_risk"  # lower the risk of an approval-gated incident, with a reason
    INCIDENT_DELETE = "incident.delete"
    # --- evidence
    EVIDENCE_VIEW_ALL = "evidence.view_all"
    EVIDENCE_VIEW_ASSIGNED = "evidence.view_assigned"
    EVIDENCE_ANALYZE = "evidence.analyze"
    # --- supervisor, squads, dispatch
    SUPERVISOR_VIEW = "supervisor.view"
    TRIAGE_RUN = "triage.run"
    TEAM_VIEW = "team.view"
    TEAM_MANAGE = "team.manage"
    DISPATCH_ASSIGN = "dispatch.assign"            # assign a squad to an incident that does not need approval
    DISPATCH_APPROVE = "dispatch.approve"          # commander approval; the only way a gated incident is dispatched
    BEACON_VIEW = "beacon.view"
    # --- alerts
    ALERT_PUBLISH = "alert.publish"
    ALERT_RESOLVE = "alert.resolve"
    ALERT_ACK_CONTROL = "alert.acknowledge_control"
    # --- resources
    VOLUNTEER_VIEW = "volunteer.view"
    VOLUNTEER_VERIFY = "volunteer.verify"
    VOLUNTEER_MANAGE = "volunteer.manage"
    FACILITY_MANAGE = "facility.manage"
    # --- records
    RECORD_VIEW = "record.view"
    RECORD_CREATE = "record.create"
    RECORD_EXPORT = "record.export"
    # --- information
    DASHBOARD_VIEW = "dashboard.view"
    DATA_VIEW = "data.view"
    VISION_ANALYZE = "vision.analyze"
    # --- administration and development
    USER_MANAGE = "user.manage"
    AUDIT_READ = "audit.read"
    SYSTEM_DIAGNOSTICS = "system.diagnostics"


ALL_PERMISSIONS = sorted(v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str))

# Held by an anonymous visitor (no account). Enforced by the routes that are deliberately open.
GUEST_PERMISSIONS: FrozenSet[str] = frozenset({P.INCIDENT_REPORT, P.INCIDENT_TRACK, P.PUBLIC_READ})

_SIGNED_IN = {P.INCIDENT_REPORT, P.INCIDENT_TRACK, P.PUBLIC_READ, P.ACCOUNT_OWN, P.ALERT_SEEN}

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "CITIZEN": frozenset(_SIGNED_IN | {P.INCIDENT_VIEW_OWN, P.EVIDENCE_VIEW_OWN}),
    "VOLUNTEER": frozenset(_SIGNED_IN | {P.INCIDENT_VIEW_OWN, P.EVIDENCE_VIEW_OWN}),
    "RESCUE_OFFICER": frozenset(_SIGNED_IN | {
        P.INCIDENT_VIEW_ASSIGNED, P.INCIDENT_PROGRESS, P.EVIDENCE_VIEW_ASSIGNED, P.EVIDENCE_ANALYZE,
        P.TEAM_VIEW, P.RECORD_VIEW, P.RECORD_CREATE, P.DASHBOARD_VIEW, P.VISION_ANALYZE,
    }),
    "OPERATOR": frozenset(_SIGNED_IN | {
        P.INCIDENT_VIEW_ALL, P.INCIDENT_VERIFY, P.INCIDENT_EDIT_RISK,
        P.EVIDENCE_VIEW_ALL, P.EVIDENCE_ANALYZE,
        P.SUPERVISOR_VIEW, P.TRIAGE_RUN, P.TEAM_VIEW, P.TEAM_MANAGE, P.DISPATCH_ASSIGN, P.BEACON_VIEW,
        P.ALERT_PUBLISH, P.ALERT_RESOLVE,
        P.VOLUNTEER_VIEW, P.VOLUNTEER_VERIFY, P.VOLUNTEER_MANAGE, P.FACILITY_MANAGE,
        P.RECORD_VIEW, P.RECORD_CREATE, P.DASHBOARD_VIEW, P.DATA_VIEW, P.VISION_ANALYZE,
    }),
    "COMMANDER": frozenset(_SIGNED_IN | {
        P.INCIDENT_VIEW_ALL, P.INCIDENT_VERIFY, P.INCIDENT_EDIT_RISK, P.INCIDENT_REDUCE_RISK,
        P.EVIDENCE_VIEW_ALL, P.EVIDENCE_ANALYZE,
        P.SUPERVISOR_VIEW, P.TRIAGE_RUN, P.TEAM_VIEW, P.TEAM_MANAGE, P.DISPATCH_ASSIGN, P.DISPATCH_APPROVE, P.BEACON_VIEW,
        P.ALERT_PUBLISH, P.ALERT_RESOLVE, P.ALERT_ACK_CONTROL,
        P.VOLUNTEER_VIEW, P.VOLUNTEER_VERIFY, P.VOLUNTEER_MANAGE, P.FACILITY_MANAGE,
        P.RECORD_VIEW, P.RECORD_CREATE, P.RECORD_EXPORT, P.DASHBOARD_VIEW, P.DATA_VIEW, P.VISION_ANALYZE,
        P.AUDIT_READ,
    }),
    # Identity and system management only. Deliberately no incident, evidence, dispatch, triage, approval or alert rights.
    "ADMIN": frozenset(_SIGNED_IN | {
        P.USER_MANAGE, P.AUDIT_READ, P.SYSTEM_DIAGNOSTICS, P.DASHBOARD_VIEW, P.DATA_VIEW, P.INCIDENT_DELETE,
    }),
    # Diagnostics only. No citizen data, no rescue controls.
    "DEVELOPER": frozenset(_SIGNED_IN | {P.SYSTEM_DIAGNOSTICS, P.DATA_VIEW, P.SUPERVISOR_VIEW}),
}

ROLES = list(ROLE_PERMISSIONS)

# Accounts an administrator may create, reset and promote into. Every other role carries operational or system authority,
# so an administrator must never be able to obtain those credentials or grant those roles directly (privilege escalation).
PUBLIC_ROLES = ("CITIZEN", "VOLUNTEER")
PRIVILEGED_ROLES = tuple(r for r in ROLES if r not in PUBLIC_ROLES)

# Permissions no role other than the listed ones may ever hold (policy test: a change here must be deliberate).
RESTRICTED: Dict[str, FrozenSet[str]] = {
    P.DISPATCH_APPROVE: frozenset({"COMMANDER"}),
    P.DISPATCH_ASSIGN: frozenset({"COMMANDER", "OPERATOR"}),
    P.TRIAGE_RUN: frozenset({"COMMANDER", "OPERATOR"}),
    P.ALERT_PUBLISH: frozenset({"COMMANDER", "OPERATOR"}),
    P.USER_MANAGE: frozenset({"ADMIN"}),
}


class PermissionDenied(Exception):
    """Raised by service-level checks; routes turn it into HTTP 403."""

    def __init__(self, permission: str, role: Optional[str]):
        super().__init__(f"{role or 'This caller'} does not hold permission {permission}")
        self.permission, self.role = permission, role


def permissions_for_role(role: Optional[str]) -> FrozenSet[str]:
    return ROLE_PERMISSIONS.get((role or "").upper(), frozenset())


def role_has(role: Optional[str], permission: str) -> bool:
    return permission in permissions_for_role(role)


def user_permissions(user) -> FrozenSet[str]:
    """Permissions of a user object. Always derived from the role currently stored in the database."""
    if user is None:
        return GUEST_PERMISSIONS
    return permissions_for_role(getattr(user, "role", None))


def has_permission(user, permission: str) -> bool:
    return permission in user_permissions(user)


def require_for_role(role: Optional[str], permission: str) -> None:
    """Service-level guard (defence in depth): raises PermissionDenied if the acting role lacks the permission."""
    if not role_has(role, permission):
        raise PermissionDenied(permission, role)
