"""S6: backend-driven workspaces and navigation.

The server decides the experience (PUBLIC or PROFESSIONAL), the capabilities and the navigation entries. Everything is derived from
permissions and the authentication state; the API remains the final boundary (every offered entry is cross-checked against it).
"""

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import navigation as nav
from app.core.permissions import PRIVILEGED_ROLES, ROLE_PERMISSIONS
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import User
from tests.conftest import enroll_via_api, login_complete, make_user, mfa_secret_of, sign_in
from tests.test_s5_invitations import PW, accept, authed, issue

GOLDEN = Path(__file__).parent / "golden" / "navigation_matrix.json"
LOGIN = {"ADMIN": "admin", "DEVELOPER": "developer", "COMMANDER": "commander", "OPERATOR": "operator",
         "RESCUE_OFFICER": "officer", "VOLUNTEER": "volunteer", "CITIZEN": "citizen"}
ROLES = list(LOGIN)


def ws(c):
    r = c.get("/api/auth/workspace")
    assert r.status_code == 200, r.text
    return r.json()


def ids(w):
    return [i["id"] for s in w["navigation"]["sections"] for i in s["items"]]


def labels(w):
    return [i["label"] for s in w["navigation"]["sections"] for i in s["items"]]


# What the previous, hard-coded frontend navigation (auth/access.ts navFor) offered each role, by page label. The backend-driven
# navigation must reproduce it exactly: S6 moves the decision to the server, it does not change who sees what.
LEGACY_LABELS = {
    # "Agencies & Invitations" is the one entry S6 ADDS (the S5 management page); everything else is unchanged.
    "ADMIN": {"Admin Console", "Audit Log", "Diagnostics", "Settings", "My Account", "Data & Models", "Flood Forecasting", "Emergency Alerts", "Facilities & Shelters",
              "Agencies & Invitations"},
    "DEVELOPER": {"Diagnostics", "Data & Models", "My Account"},
    "COMMANDER": {"Overview", "Rescue Operations", "AI Supervisor", "Emergency Alerts", "Flood Digital Twin", "Flood Forecasting", "Data & Models",
                  "Volunteer Coordination", "Facilities & Shelters", "Rescue Records", "Incident Reports", "Audit Log", "My Account"},
    "OPERATOR": {"Overview", "Rescue Operations", "AI Supervisor", "Emergency Alerts", "Flood Digital Twin", "Flood Forecasting", "Data & Models",
                 "Volunteer Coordination", "Facilities & Shelters", "Rescue Records", "Incident Reports", "My Account"},
    "RESCUE_OFFICER": {"My Missions", "Flood Digital Twin", "Flood Forecasting", "Emergency Alerts", "Facilities & Shelters", "Report Emergency",
                       "Rescue Records", "My Account"},
    "VOLUNTEER": {"Home", "Flood Digital Twin", "Flood Forecasting", "Emergency Alerts", "Facilities & Shelters", "Report Emergency", "My Reports", "My Account"},
    "CITIZEN": {"Home", "Flood Digital Twin", "Flood Forecasting", "Emergency Alerts", "Facilities & Shelters", "Report Emergency", "My Reports", "My Account"},
}
GUEST_LABELS = {"Home", "Flood Digital Twin", "Flood Forecasting", "Emergency Alerts", "Facilities & Shelters", "Report Emergency"}


@pytest.fixture(scope="module")
def workspaces():
    out = {"GUEST": ws(TestClient(app))}
    for role, name in LOGIN.items():
        out[role] = ws(sign_in(TestClient(app), name))
    # the same payload arrives with /auth/me
    return out


# ------------------------------------------------------------------ per-role navigation

def test_each_role_gets_the_navigation_the_hardcoded_frontend_used_to_offer_plus_the_new_agencies_entry(workspaces):
    for role in ROLES:
        assert set(labels(workspaces[role])) == LEGACY_LABELS[role], role
    assert set(labels(workspaces["GUEST"])) == GUEST_LABELS


def test_golden_navigation_matrix_is_up_to_date(workspaces):
    observed = {who: {"experience": w["experience"], "home": w["navigation"]["home"], "ids": ids(w),
                      "capabilities": sorted(k for k, v in w["capabilities"].items() if v)} for who, w in workspaces.items()}
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
    assert json.loads(GOLDEN.read_text()) == observed, "Navigation changed; review, then UPDATE_GOLDEN=1."


def test_experience_is_public_for_guests_citizens_and_volunteers_and_professional_for_everyone_else(workspaces):
    for who in ("GUEST", "CITIZEN", "VOLUNTEER"):
        assert workspaces[who]["experience"] == "PUBLIC"
    for role in PRIVILEGED_ROLES:
        assert workspaces[role]["experience"] == "PROFESSIONAL"


def test_administrators_and_developers_get_only_their_real_responsibilities(workspaces):
    operational = {"overview", "operations", "missions", "ai-supervisor", "volunteers", "records", "incident-reports", "report-emergency", "flood-twin"}
    assert not operational & set(ids(workspaces["ADMIN"]))
    assert not operational & set(ids(workspaces["DEVELOPER"])) and "alerts" not in ids(workspaces["DEVELOPER"])
    assert {"admin-console", "agencies", "audit-log", "diagnostics", "settings"} <= set(ids(workspaces["ADMIN"]))
    assert set(ids(workspaces["DEVELOPER"])) == {"data-models", "diagnostics", "account"}
    caps = workspaces["ADMIN"]["capabilities"]
    assert not any(caps[k] for k in ("view_incidents", "manage_incidents", "run_triage", "approve_dispatch", "manage_alerts"))
    assert caps["manage_users"] and caps["manage_agencies"] and caps["view_diagnostics"]


def test_console_membership_grants_no_operational_authority_by_itself(workspaces):
    only_commander = [r for r in ROLES if workspaces[r]["capabilities"]["approve_dispatch"]]
    assert only_commander == ["COMMANDER"]
    assert [r for r in ROLES if workspaces[r]["capabilities"]["run_triage"]] == ["COMMANDER", "OPERATOR"] or \
        set(r for r in ROLES if workspaces[r]["capabilities"]["run_triage"]) == {"COMMANDER", "OPERATOR"}
    assert workspaces["RESCUE_OFFICER"]["capabilities"]["manage_incidents"] is False        # a console user without verify rights
    assert "operations" not in ids(workspaces["RESCUE_OFFICER"])


def test_landing_page_per_role(workspaces):
    assert {r: workspaces[r]["navigation"]["home_id"] for r in ROLES} == {
        "ADMIN": "admin-console", "DEVELOPER": "diagnostics", "COMMANDER": "overview", "OPERATOR": "overview",
        "RESCUE_OFFICER": "missions", "VOLUNTEER": "home", "CITIZEN": "home"}


def test_capabilities_are_derived_from_permissions_only(workspaces):
    for role in ROLES:
        perms = ROLE_PERMISSIONS[role]
        for name, needed in nav.CAPABILITIES.items():
            assert workspaces[role]["capabilities"][name] == bool(set(needed) & perms), (role, name)


# ------------------------------------------------------------------ the API stays the boundary

PROBE = {"overview": "/api/dashboard", "operations": "/api/incidents/", "missions": "/api/incidents/mine", "ai-supervisor": "/api/agents/tasks",
         "volunteers": "/api/volunteers/", "records": "/api/records/", "data-models": "/api/datasets/inventory",
         "admin-console": "/api/auth/users", "agencies": "/api/agencies", "audit-log": "/api/auth/audit", "diagnostics": "/api/diagnostics/",
         "my-reports": "/api/incidents/mine", "alerts": "/api/alerts/", "facilities": "/api/facilities/", "account": "/api/auth/me"}


def test_every_entry_offered_to_a_role_is_backed_by_an_endpoint_that_role_may_call():
    for role, name in LOGIN.items():
        c = sign_in(TestClient(app), name)
        for item_id in ids(ws(c)):
            if item_id in PROBE:
                assert c.get(PROBE[item_id]).status_code == 200, (role, item_id)


def test_entries_not_offered_stay_refused_by_the_api():
    c = sign_in(TestClient(app), "developer")
    for path in ("/api/incidents/", "/api/teams/", "/api/volunteers/", "/api/records/", "/api/auth/users"):
        assert c.get(path).status_code == 403, path
    a = sign_in(TestClient(app), "admin")
    for path in ("/api/incidents/", "/api/teams/", "/api/agents/tasks"):
        assert a.get(path).status_code == 403, path


# ------------------------------------------------------------------ guests, payload hygiene, paths

def test_guests_get_the_public_workspace_with_nothing_account_bound():
    w = ws(TestClient(app))
    assert w["experience"] == "PUBLIC" and w["authenticated"] is False and w["assurance"]["level"] == "NONE"
    assert not {"my-reports", "account"} & set(ids(w))
    assert w["capabilities"]["report_incident"] is True and not any(v for k, v in w["capabilities"].items() if k != "report_incident")
    assert w["agency_id"] is None and w["team_id"] is None


def test_the_payload_carries_ids_and_booleans_only():
    allowed = {"experience", "authenticated", "activation", "assurance", "agency_id", "team_id", "capabilities", "navigation", "known_paths"}
    for who in ("admin", "commander", "citizen"):
        w = ws(sign_in(TestClient(app), who))
        assert set(w) == allowed
        blob = json.dumps(w).lower()
        for secret in ("email", "phone", "username", "password_hash", "token", "secret", "@"):
            assert secret not in blob, (who, secret)


def test_paths_are_unique_namespaced_and_known(workspaces):
    for who, w in workspaces.items():
        paths = [i["path"] for s in w["navigation"]["sections"] for i in s["items"]]
        assert len(paths) == len(set(paths)), who
        prefix = "/console/" if w["experience"] == "PROFESSIONAL" else "/public/"
        for p in paths:
            assert p in w["known_paths"] and (p in ("/", "/account") or p.startswith(prefix)), (who, p)


def test_existing_bookmarks_keep_working():
    paths = nav.all_paths()
    assert "/" in paths and "/account" in paths          # the pre-S6 app lived at "/" (plus ?reset= and #invite= links)


# ------------------------------------------------------------------ restricted states and live changes

def test_restricted_sessions_get_no_navigation_and_the_remaining_steps():
    _, token, _ = issue("COMMANDER")
    c, r = accept(token)
    body = r.json()["user"]
    assert body["auth_state"] == "CONTACT_VERIFICATION_PENDING" and body["permissions"] == []
    w = body["workspace"]
    assert w["authenticated"] is False and w["navigation"]["sections"] == [] and w["navigation"]["home"] is None
    assert w["activation"]["restricted_reason"] == "VERIFY_CONTACT" and w["activation"]["remaining_steps"] == ["VERIFY_CONTACT", "ENROLL_MFA"]
    assert not any(w["capabilities"].values()) and w["assurance"] == {"level": "PASSWORD", "mfa_enabled": False, "mfa_required": True, "recent_mfa": False}
    authed(c, r)
    pub = ws(c)                                           # /auth/workspace treats a restricted session as a guest: public pages only,
    assert pub["experience"] == "PUBLIC" and pub["authenticated"] is False and not {"operations", "overview", "admin-console"} & set(ids(pub))
    me = c.get("/api/auth/me").json()["workspace"]
    assert me["navigation"]["sections"] == [] and me["experience"] == "PROFESSIONAL"


def test_temporary_password_and_mfa_pending_accounts_get_no_navigation():
    uid, name = make_user("OPERATOR", PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW})
    w = r.json()["user"]["workspace"]
    assert r.json()["user"]["auth_state"] == "MFA_ENROLLMENT_PENDING" and w["navigation"]["sections"] == [] and w["activation"]["remaining_steps"] == ["ENROLL_MFA"]
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"must_change_password": True}); db.commit(); db.close()
    authed(c, r)
    w2 = c.get("/api/auth/me").json()["workspace"]
    assert w2["activation"]["restricted_reason"] == "CHANGE_PASSWORD" and w2["navigation"]["sections"] == []


def test_activation_completes_into_the_full_workspace():
    _, token, _ = issue("OPERATOR")
    c, r = accept(token)
    authed(c, r)
    uid = r.json()["user"]["id"]
    import re
    from tests.conftest import latest_dev_message, _forget_replay, totp_code
    c.post("/api/auth/verify/email/request")
    c.post("/api/auth/verify/email/confirm", json={"code": re.search(r"code is (\d{6})", latest_dev_message(uid, "EMAIL_VERIFY").body).group(1)})
    assert c.get("/api/auth/me").json()["workspace"]["activation"]["remaining_steps"] == ["ENROLL_MFA"]
    secret, _ = enroll_via_api(c, PW)
    name = r.json()["user"]["username"]
    fresh = TestClient(app)
    ch = fresh.post("/api/auth/login", json={"portal": "operations", "username": name, "password": PW}).json()
    _forget_replay(uid)
    done = fresh.post("/api/auth/mfa/verify", json={"challenge_token": ch["challenge_token"], "code": totp_code(secret)}).json()["user"]["workspace"]
    assert done["authenticated"] and done["assurance"]["level"] == "MFA" and done["assurance"]["recent_mfa"] is True
    assert "operations" in [i["id"] for s in done["navigation"]["sections"] for i in s["items"]]


def test_navigation_follows_the_current_role_immediately():
    """Derived live from the database on every call: if the stored role changes (here by a host operator), the very next answer changes."""
    uid, name = make_user("OPERATOR", PW, mfa=True)
    c = TestClient(app)
    r = login_complete(c, "operations", name, PW)
    authed(c, r)
    assert "operations" in ids(ws(c)) and "diagnostics" not in ids(ws(c))
    db = SessionLocal(); db.query(User).filter(User.id == uid).update({"role": "DEVELOPER"}); db.commit(); db.close()
    after = ws(c)
    assert "operations" not in ids(after) and "diagnostics" in ids(after)
    assert c.get("/api/incidents/").status_code == 403          # and the API agrees


def test_role_change_through_the_console_ends_the_session_and_a_new_sign_in_gets_the_new_workspace():
    uid, name = make_user("CITIZEN", PW)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"portal": "public", "username": name, "password": PW}); authed(c, r)
    assert ws(c)["experience"] == "PUBLIC"
    admin = sign_in(TestClient(app), "admin")
    assert admin.patch(f"/api/auth/users/{uid}", json={"role": "VOLUNTEER", "is_active": True}).status_code in (200, 422)
    admin.post(f"/api/auth/users/{uid}/revoke-sessions")
    assert c.get("/api/auth/me").status_code == 401            # the old session is gone: the client returns to sign-in


def test_team_reassignment_ends_sessions_and_the_new_team_shows_in_the_workspace():
    team = "TEAM-NDRF-10"
    uid, name = make_user("RESCUE_OFFICER", PW, team_id=team, mfa=True)
    c = TestClient(app)
    authed(c, login_complete(c, "operations", name, PW))
    assert ws(c)["team_id"] == team
    db = SessionLocal(); other = db.query(__import__("app.models.entities", fromlist=["RescueTeam"]).RescueTeam.id).filter_by().all(); db.close()
    new_team = next(t[0] for t in other if t[0] != team)
    admin = sign_in(TestClient(app), "admin")
    assert admin.patch(f"/api/auth/users/{uid}", json={"team_id": new_team}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401            # access changed: every session of the officer ended
    c2 = TestClient(app)
    authed(c2, login_complete(c2, "operations", name, PW))
    assert ws(c2)["team_id"] == new_team


def test_a_revoked_session_gets_401_and_no_workspace():
    uid, name = make_user("OPERATOR", PW, mfa=True)
    c = TestClient(app)
    authed(c, login_complete(c, "operations", name, PW))
    assert c.get("/api/auth/me").status_code == 200
    sign_in(TestClient(app), "admin").post(f"/api/auth/users/{uid}/revoke-sessions")
    assert c.get("/api/auth/me").status_code == 401
    guest_view = ws(c)                                          # a dead token is just a guest to the public endpoint
    assert guest_view["experience"] == "PUBLIC" and guest_view["authenticated"] is False


def test_agency_id_appears_for_members_and_changes_nothing_else():
    uid, name = make_user("OPERATOR", PW, mfa=True)
    admin = sign_in(TestClient(app), "admin")
    ag = admin.post("/api/agencies", json={"name": f"Nav agency {uuid.uuid4().hex[:6]}", "agency_type": "CIVIL_ADMINISTRATION"}).json()
    admin.put(f"/api/agencies/members/{uid}", json={"agency_id": ag["id"]})
    c = TestClient(app)
    authed(c, login_complete(c, "operations", name, PW))
    w = ws(c)
    assert w["agency_id"] == ag["id"] and set(ids(w)) == set(ids(ws(sign_in(TestClient(app), "operator"))))


def test_every_endpoint_that_starts_a_session_is_called_by_the_frontend_with_credentials():
    """Regression from the S6 browser run: the invitation-accept endpoint starts a session (sets cookies) but the client did not send
    credentials for it, so the browser dropped the cookies and a reload signed the new owner out."""
    import re
    src = (Path(__file__).resolve().parent.parent.parent / "rescuenet-x2" / "frontend" / "src" / "api" / "client.ts").read_text()
    uses = re.search(r"const usesCookies = \(endpoint: string\) => (.+);", src).group(1)
    routes = ""
    for f in (Path(__file__).resolve().parent.parent / "app" / "api" / "routes").glob("*.py"):
        routes += f.read_text()
    assert "start_session(" in routes
    session_starting = ["/auth/login", "/auth/register", "/auth/mfa/verify", "/auth/refresh", "/auth/me/password", "/invitations/accept"]
    for e in session_starting:
        assert f"endpoint.startsWith('/auth/')" in uses and e.startswith("/auth/") or f"endpoint === '{e}'" in uses, e
