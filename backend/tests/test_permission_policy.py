"""S1: policy invariants of the central role-to-permission matrix.

These tests are independent of the golden files: they encode the separation-of-duties rules directly, so
regenerating a golden file can never silently weaken them.
"""

import json
from pathlib import Path

import pytest

from app.core import permissions as perms
from app.core.permissions import P, ROLE_PERMISSIONS, RESTRICTED, has_permission, role_has

GOLDEN = Path(__file__).parent / "golden" / "permission_matrix.json"
ROLES = ["ADMIN", "DEVELOPER", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]


def test_every_role_is_defined_and_unknown_roles_hold_nothing():
    assert set(ROLE_PERMISSIONS) == set(ROLES)
    assert perms.permissions_for_role("HACKER") == frozenset()
    assert perms.permissions_for_role(None) == frozenset()
    assert perms.permissions_for_role("") == frozenset()


def test_every_granted_permission_is_a_declared_permission():
    for role, granted in ROLE_PERMISSIONS.items():
        assert granted <= set(perms.ALL_PERMISSIONS), (role, granted - set(perms.ALL_PERMISSIONS))


DISPATCH_FAMILY = [P.DISPATCH_ASSIGN, P.DISPATCH_APPROVE, P.TRIAGE_RUN, P.ALERT_PUBLISH, P.ALERT_RESOLVE, P.ALERT_ACK_CONTROL,
                   P.TEAM_MANAGE, P.INCIDENT_VERIFY, P.INCIDENT_EDIT_RISK, P.INCIDENT_REDUCE_RISK]


@pytest.mark.parametrize("perm", DISPATCH_FAMILY)
def test_administrator_holds_no_operational_authority(perm):
    assert not role_has("ADMIN", perm)


@pytest.mark.parametrize("perm", [P.INCIDENT_VIEW_ALL, P.INCIDENT_VIEW_ASSIGNED, P.INCIDENT_VIEW_OWN, P.EVIDENCE_VIEW_ALL,
                                  P.VOLUNTEER_VIEW, P.RECORD_VIEW, P.RECORD_EXPORT, P.SUPERVISOR_VIEW, P.FACILITY_MANAGE])
def test_administrator_cannot_read_private_operational_data(perm):
    assert not role_has("ADMIN", perm)


def test_administrator_keeps_identity_and_system_management():
    for perm in (P.USER_MANAGE, P.AUDIT_READ, P.SYSTEM_DIAGNOSTICS, P.ACCOUNT_OWN):
        assert role_has("ADMIN", perm)


def test_developer_is_diagnostics_only():
    allowed = {P.SYSTEM_DIAGNOSTICS, P.DATA_VIEW, P.SUPERVISOR_VIEW}
    public_and_self = {P.INCIDENT_REPORT, P.INCIDENT_TRACK, P.PUBLIC_READ, P.ACCOUNT_OWN, P.ALERT_SEEN}
    assert set(ROLE_PERMISSIONS["DEVELOPER"]) == allowed | public_and_self
    for perm in DISPATCH_FAMILY + [P.INCIDENT_VIEW_ALL, P.EVIDENCE_VIEW_ALL, P.VOLUNTEER_VIEW, P.RECORD_VIEW, P.USER_MANAGE,
                                   P.INCIDENT_DELETE, P.DASHBOARD_VIEW]:
        assert not role_has("DEVELOPER", perm)


def test_only_commander_can_approve_dispatch():
    assert [r for r in ROLES if role_has(r, P.DISPATCH_APPROVE)] == ["COMMANDER"]


@pytest.mark.parametrize("perm,holders", list(RESTRICTED.items()))
def test_restricted_permissions_are_held_only_by_their_listed_roles(perm, holders):
    assert {r for r in ROLES if role_has(r, perm)} == set(holders)


def test_rescue_officer_has_only_assigned_scope_for_incidents_and_evidence():
    r = ROLE_PERMISSIONS["RESCUE_OFFICER"]
    assert P.INCIDENT_VIEW_ASSIGNED in r and P.EVIDENCE_VIEW_ASSIGNED in r
    for perm in (P.INCIDENT_VIEW_ALL, P.EVIDENCE_VIEW_ALL, P.INCIDENT_VERIFY, P.DISPATCH_ASSIGN, P.DISPATCH_APPROVE,
                 P.RECORD_EXPORT, P.VOLUNTEER_VIEW, P.USER_MANAGE):
        assert perm not in r


@pytest.mark.parametrize("role", ["CITIZEN", "VOLUNTEER"])
def test_public_roles_are_limited_to_own_records_and_public_resources(role):
    r = ROLE_PERMISSIONS[role]
    assert {P.INCIDENT_VIEW_OWN, P.EVIDENCE_VIEW_OWN} <= r
    forbidden = (set(perms.ALL_PERMISSIONS) - {P.INCIDENT_REPORT, P.INCIDENT_TRACK, P.PUBLIC_READ, P.ACCOUNT_OWN, P.ALERT_SEEN,
                                               P.INCIDENT_VIEW_OWN, P.EVIDENCE_VIEW_OWN})
    assert not (r & forbidden)


def test_guests_hold_only_public_permissions_and_can_still_report_and_track():
    assert perms.GUEST_PERMISSIONS == {P.INCIDENT_REPORT, P.INCIDENT_TRACK, P.PUBLIC_READ}
    assert perms.user_permissions(None) == perms.GUEST_PERMISSIONS


def test_permissions_follow_the_current_role_attribute_only():
    class U:  # stands in for a database row
        role = "OPERATOR"
    u = U()
    assert has_permission(u, P.DISPATCH_ASSIGN) and not has_permission(u, P.DISPATCH_APPROVE)
    u.role = "ADMIN"
    assert not has_permission(u, P.DISPATCH_ASSIGN)


def test_service_level_guard_raises():
    with pytest.raises(perms.PermissionDenied):
        perms.require_for_role("AGENT", P.DISPATCH_ASSIGN)
    perms.require_for_role("COMMANDER", P.DISPATCH_APPROVE)


def test_golden_role_permission_matrix_is_up_to_date():
    current = {role: sorted(granted) for role, granted in sorted(ROLE_PERMISSIONS.items())}
    import os
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    assert json.loads(GOLDEN.read_text()) == current, (
        "The role-to-permission matrix changed. If intended, review the diff, then regenerate with UPDATE_GOLDEN=1.")
