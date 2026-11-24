"""S1: every endpoint is exercised as an anonymous caller and as each of the seven roles.

* The hand-written table below states who MUST be allowed for the sensitive endpoints; everyone else must be refused.
* The golden file records the observed outcome (401 / 403 / allow) of every endpoint for every principal, so a new
  endpoint, or a changed guard, cannot slip in unnoticed.

Requests use placeholder ids and empty bodies, so an allowed caller reaches the handler and gets 404/422 and nothing is
changed; a refused caller is stopped by the dependency before the body or the id is even looked at.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import sign_in

GOLDEN = Path(__file__).parent / "golden" / "endpoint_matrix.json"
ROLES = ["ADMIN", "DEVELOPER", "COMMANDER", "OPERATOR", "RESCUE_OFFICER", "VOLUNTEER", "CITIZEN"]
LOGIN = {"ADMIN": "admin", "DEVELOPER": "developer", "COMMANDER": "commander", "OPERATOR": "operator",
         "RESCUE_OFFICER": "officer", "VOLUNTEER": "volunteer", "CITIZEN": "citizen"}
PLACEHOLDERS = {"session_id": "0" * 32, "incident_id": "INC-NOPE", "team_id": "TEAM-NOPE", "alert_id": "ALT-NOPE", "task_id": "TASK-NOPE",
                "volunteer_id": "VOL-NOPE", "facility_id": "FAC-NOPE", "user_id": "999999", "agency_id": "999999", "invitation_id": "999999", "filename": "nope.jpg",
                "asset_id": "0" * 32, "public_ref": "RN-0000-0000-0000"}

OPS = {"COMMANDER", "OPERATOR"}
SIGNED_IN = set(ROLES)
DEPT = OPS | {"RESCUE_OFFICER"}
PUBLIC = "public"   # anyone, including anonymous callers

# (method, path) -> roles that must be allowed; anything not listed must be refused. PUBLIC = open to everyone.
MUST_ALLOW = {
    ("GET", "/api/dashboard"): {"ADMIN"} | DEPT,
    ("GET", "/api/incidents/"): DEPT,
    ("GET", "/api/incidents/beacons"): OPS,
    ("GET", "/api/incidents/mine"): {"CITIZEN", "VOLUNTEER", "RESCUE_OFFICER"},
    ("GET", "/api/incidents/{incident_id}"): DEPT | {"CITIZEN", "VOLUNTEER"},
    ("PATCH", "/api/incidents/{incident_id}"): OPS,
    ("DELETE", "/api/incidents/{incident_id}"): {"ADMIN"},
    ("POST", "/api/incidents/{incident_id}/state"): DEPT,
    ("GET", "/api/incidents/{incident_id}/history"): DEPT,
    ("POST", "/api/incidents/{incident_id}/analyze-photo"): DEPT,
    ("GET", "/api/incidents/uploads/{filename}"): SIGNED_IN,
    ("GET", "/api/media/{asset_id}"): SIGNED_IN,
    ("GET", "/api/teams/"): DEPT,
    ("POST", "/api/teams/"): OPS,
    ("PATCH", "/api/teams/{team_id}/status"): OPS,
    ("POST", "/api/teams/{team_id}/assign"): OPS,
    ("GET", "/api/agents/"): OPS | {"DEVELOPER"},
    ("GET", "/api/agents/supervisor/health"): OPS | {"DEVELOPER"},
    ("GET", "/api/agents/tasks"): OPS | {"DEVELOPER"},
    ("POST", "/api/agents/supervisor/triage"): OPS,
    ("POST", "/api/agents/tasks/{task_id}/approve"): {"COMMANDER"},
    ("POST", "/api/agents/tasks/{task_id}/decline"): {"COMMANDER"},
    ("POST", "/api/alerts/"): OPS,
    ("POST", "/api/alerts/{alert_id}/resolve"): OPS,
    ("POST", "/api/alerts/{alert_id}/acknowledge"): SIGNED_IN,
    ("GET", "/api/alerts/"): PUBLIC,
    ("GET", "/api/alerts/{alert_id}/cap"): PUBLIC,
    ("GET", "/api/volunteers/"): OPS,
    ("POST", "/api/volunteers/"): OPS,
    ("PATCH", "/api/volunteers/{volunteer_id}"): OPS,
    ("POST", "/api/volunteers/{volunteer_id}/assign"): OPS,
    ("POST", "/api/volunteers/{volunteer_id}/release"): OPS,
    ("GET", "/api/facilities/"): PUBLIC,
    ("POST", "/api/facilities/"): OPS,
    ("PATCH", "/api/facilities/{facility_id}/occupancy"): OPS,
    ("GET", "/api/records/"): DEPT,
    ("GET", "/api/records/summary"): DEPT,
    ("POST", "/api/records/"): DEPT,
    ("GET", "/api/records/export/csv"): {"COMMANDER"},
    ("GET", "/api/datasets/inventory"): OPS | {"ADMIN", "DEVELOPER"},
    ("GET", "/api/datasets/models"): OPS | {"ADMIN", "DEVELOPER"},
    ("GET", "/api/datasets/images"): OPS | {"ADMIN", "DEVELOPER"},
    ("GET", "/api/datasets/images/inspect/{filename}"): OPS | {"ADMIN", "DEVELOPER"},
    ("POST", "/api/datasets/images/preprocess/{filename}"): OPS | {"ADMIN", "DEVELOPER"},
    ("GET", "/api/vision/status"): DEPT,
    ("POST", "/api/vision/analyze"): DEPT,
    ("GET", "/api/vision/dataset/{filename}"): DEPT,
    ("GET", "/api/diagnostics/"): {"ADMIN", "DEVELOPER"},
    ("GET", "/api/auth/users"): {"ADMIN"},
    ("POST", "/api/auth/users"): {"ADMIN"},
    ("PATCH", "/api/auth/users/{user_id}"): {"ADMIN"},
    ("GET", "/api/auth/team-options"): {"ADMIN"},
    ("GET", "/api/auth/audit"): {"ADMIN", "COMMANDER"},
    ("GET", "/api/auth/me"): SIGNED_IN,
    ("POST", "/api/auth/verify/email/request"): SIGNED_IN,
    ("POST", "/api/auth/verify/email/confirm"): SIGNED_IN,
    ("POST", "/api/auth/verify/phone/request"): SIGNED_IN,
    ("POST", "/api/auth/verify/phone/confirm"): SIGNED_IN,
    ("PATCH", "/api/auth/me/contact"): SIGNED_IN,
    ("GET", "/api/auth/sessions"): SIGNED_IN,
    ("DELETE", "/api/auth/sessions/{session_id}"): SIGNED_IN,
    ("POST", "/api/auth/logout-all"): SIGNED_IN,
    ("POST", "/api/auth/users/{user_id}/revoke-sessions"): {"ADMIN"},
    ("POST", "/api/auth/me/password"): SIGNED_IN,
    # S5: agencies (organisational metadata) and invitations (privileged invitations are issued by a host operator, never here)
    ("GET", "/api/agencies"): {"ADMIN"} | OPS,
    ("GET", "/api/agencies/{agency_id}"): {"ADMIN"} | OPS,
    ("POST", "/api/agencies"): {"ADMIN"},
    ("PATCH", "/api/agencies/{agency_id}"): {"ADMIN"},
    ("PUT", "/api/agencies/members/{user_id}"): {"ADMIN"},
    ("PUT", "/api/agencies/teams/{team_id}"): {"ADMIN"},
    ("GET", "/api/invitations"): {"ADMIN"},
    ("POST", "/api/invitations/{invitation_id}/revoke"): {"ADMIN"},
    ("POST", "/api/invitations/inspect"): PUBLIC,        # needs a currently usable single-use token; unusable ones answer 404
    ("POST", "/api/invitations/accept"): PUBLIC,         # needs a currently usable single-use token; creates a RESTRICTED account
    # open by design: guest emergency reporting and tracking, public information, device intake, sign-in
    ("POST", "/api/incidents/"): PUBLIC,
    ("POST", "/api/incidents/upload-image"): PUBLIC,
    ("POST", "/api/incidents/lora"): PUBLIC,
    ("GET", "/api/incidents/lifecycle"): PUBLIC,
    ("POST", "/api/public/reports"): PUBLIC,
    ("GET", "/api/public/reports/{public_ref}"): PUBLIC,
    ("GET", "/api/flood/catchments"): PUBLIC, ("POST", "/api/flood/forecast"): PUBLIC,
    ("GET", "/api/flood/gauges"): PUBLIC, ("GET", "/api/flood/status"): PUBLIC,
    ("GET", "/api/health"): PUBLIC, ("GET", "/"): PUBLIC,
    ("GET", "/api/datasets/images/file/{filename}"): PUBLIC,
    ("POST", "/api/auth/login"): PUBLIC,
    ("POST", "/api/auth/mfa/verify"): PUBLIC,           # needs a valid single-use challenge from a successful password step
    ("GET", "/api/auth/mfa/status"): SIGNED_IN,
    ("POST", "/api/auth/mfa/enroll/start"): SIGNED_IN,
    ("POST", "/api/auth/mfa/enroll/confirm"): SIGNED_IN,
    ("POST", "/api/auth/mfa/reauth"): SIGNED_IN,
    ("POST", "/api/auth/mfa/disable"): SIGNED_IN,
    ("POST", "/api/auth/mfa/recovery-codes/regenerate"): SIGNED_IN,
    ("GET", "/api/auth/capabilities"): PUBLIC,
    ("POST", "/api/auth/password/forgot"): PUBLIC,      # always the same generic answer
    ("POST", "/api/auth/password/reset"): PUBLIC,       # needs a valid single-use token
    ("GET", "/api/dev/outbox"): PUBLIC,                 # development + loopback only; 404 elsewhere (tests/test_dev_outbox.py)
    ("POST", "/api/auth/register"): PUBLIC, ("GET", "/api/auth/portals"): PUBLIC,
}


# Authenticated by the refresh COOKIE (not the Authorization header). They would consume or end the shared principals'
# sessions, so they are not probed here; tests/test_sessions.py, test_token_rotation.py and test_csrf.py cover them.
COOKIE_AUTH = {("POST", "/api/auth/refresh"), ("POST", "/api/auth/logout")}
# logout-all really ends the caller's sessions, so only the anonymous refusal is probed (the rest is in test_sessions.py).
ANON_ONLY = {("POST", "/api/auth/logout-all")}


@pytest.fixture(scope="module")
def principals():
    out = {"anonymous": TestClient(app)}
    for role in ROLES:
        out[role] = sign_in(TestClient(app), LOGIN[role])
    return out


def endpoints(include_cookie_auth=True):
    spec = app.openapi()["paths"]
    found = sorted((m.upper(), p) for p, ms in spec.items() for m in ms)
    return found if include_cookie_auth else [e for e in found if e not in COOKIE_AUTH]


def probe(client, method, path):
    url = path
    for k, v in PLACEHOLDERS.items():
        url = url.replace("{" + k + "}", v)
    kw = {} if method in ("GET", "DELETE") else {"json": {}}
    r = client.request(method, url, **kw)
    return "401" if r.status_code == 401 else "403" if r.status_code == 403 else "allow"


@pytest.fixture(scope="module")
def observed(principals):
    out = {}
    for m, p in endpoints(include_cookie_auth=False):
        anon_only = (m, p) in ANON_ONLY
        out[f"{m} {p}"] = {who: probe(c, m, p) if (not anon_only or who == "anonymous") else "allow" for who, c in principals.items()}
    return out


def test_every_endpoint_has_an_explicit_authorization_expectation():
    missing = [e for e in endpoints() if e not in MUST_ALLOW and e not in COOKIE_AUTH]
    assert not missing, f"New endpoint(s) need a decision in MUST_ALLOW and a golden update: {missing}"
    stale = [e for e in list(MUST_ALLOW) + list(COOKIE_AUTH) if e not in set(endpoints())]
    assert not stale, f"MUST_ALLOW lists endpoints that no longer exist: {stale}"


def test_each_role_is_allowed_exactly_where_the_table_says(observed):
    problems = []
    for (method, path), allowed in MUST_ALLOW.items():
        row = observed[f"{method} {path}"]
        for who, outcome in row.items():
            expected = "allow" if allowed == PUBLIC or who in allowed else ("401" if who == "anonymous" else "403")
            if outcome != expected:
                problems.append(f"{method} {path} as {who}: expected {expected}, got {outcome}")
    assert not problems, "\n".join(problems)


def test_anonymous_callers_never_reach_a_protected_endpoint(observed):
    for key, row in observed.items():
        method, path = key.split(" ", 1)
        if MUST_ALLOW[(method, path)] != PUBLIC:
            assert row["anonymous"] == "401", key


def test_golden_endpoint_matrix_is_up_to_date(observed):
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
    assert json.loads(GOLDEN.read_text()) == observed, "Endpoint authorization changed; review, then UPDATE_GOLDEN=1."


def test_guest_reporting_and_tracking_stay_open(principals):
    anon = principals["anonymous"]
    body = dict(title="Water rising", description="Street is flooding fast", area="Hebbal", latitude=13.0, longitude=77.6,
                severity="LOW", people_affected=1)
    r = anon.post("/api/public/reports", json=body)
    assert r.status_code == 201
    t = anon.get(f"/api/public/reports/{r.json()['public_ref']}", headers={"X-Tracking-Code": r.json()["tracking_code"]})
    assert t.status_code == 200
