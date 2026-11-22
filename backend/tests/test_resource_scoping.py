"""S1: resource-scoped authorization. A permission alone is not enough: officers see only their team's missions and
evidence, citizens and volunteers only their own records, administrators and developers no incident data at all."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Incident, RescueRecord, RescueTeam, User
from tests.conftest import make_team, sign_in

REPORT = dict(title="Flooded lane", description="Water at knee height, family waiting", area="Bellandur", latitude=12.93,
              longitude=77.67, severity="LOW", people_affected=1)


def png():
    b = io.BytesIO(); Image.new("RGB", (32, 32), (20, 80, 200)).save(b, format="PNG"); return b.getvalue()


def client(name=None):
    c = TestClient(app)
    return sign_in(c, name) if name else c


def officer_team():
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == "officer").one().team_id
    finally:
        db.close()


def make_report(who=None, with_photo=False, **over):
    c = client(who)
    body = dict(REPORT, **over)
    if with_photo:
        up = c.post("/api/incidents/upload-image", files={"file": ("p.png", png(), "image/png")}).json()
        body["image_url"] = up["image_url"]
    r = c.post("/api/incidents/", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def assign_directly(incident_id, team_id):
    """Set the assignment in the database: scoping rules, not dispatch, are under test here."""
    db = SessionLocal()
    db.query(Incident).filter(Incident.id == incident_id).update({"assigned_team_id": team_id})
    db.commit(); db.close()


@pytest.fixture
def mission():
    inc = make_report(with_photo=True)
    other = make_report(with_photo=True)
    assign_directly(inc["id"], officer_team())
    assign_directly(other["id"], "TEAM-SOMEONE-ELSE")
    return inc, other


# ---------------------------------------------------------------- rescue officer

def test_officer_lists_only_own_team_missions(mission):
    mine, other = mission
    ids = {i["id"] for i in client("officer").get("/api/incidents/").json()["items"]}
    assert mine["id"] in ids and other["id"] not in ids
    assert all(i["assigned_team_id"] == officer_team() for i in client("officer").get("/api/incidents/").json()["items"])


def test_officer_reads_assigned_incident_but_not_others(mission):
    mine, other = mission
    c = client("officer")
    assert c.get(f"/api/incidents/{mine['id']}").status_code == 200
    assert c.get(f"/api/incidents/{other['id']}").status_code == 404
    assert c.get(f"/api/incidents/{mine['id']}/history").status_code == 200
    assert c.get(f"/api/incidents/{other['id']}/history").status_code == 404
    assert c.get("/api/incidents/INC-DOES-NOT-EXIST/history").status_code == 404


def test_officer_evidence_only_for_assigned_incidents(mission):
    mine, other = mission
    c = client("officer")
    assert c.get(mine["image_url"]).status_code == 200
    assert c.get(other["image_url"]).status_code == 404
    assert c.post(f"/api/incidents/{other['id']}/analyze-photo").status_code == 404   # no analysis of unrelated evidence


def test_officer_cannot_change_state_of_unassigned_incident_or_use_ops_states(mission):
    mine, other = mission
    c = client("officer")
    assert c.post(f"/api/incidents/{other['id']}/state", json={"to_status": "RESOLVED"}).status_code == 403
    assert c.post(f"/api/incidents/{mine['id']}/state", json={"to_status": "VERIFIED"}).status_code == 403
    assert c.post(f"/api/incidents/{mine['id']}/state", json={"to_status": "DISPATCHED"}).status_code == 403


def test_officer_my_missions_shows_only_team(mission):
    mine, other = mission
    ids = {i["id"] for i in client("officer").get("/api/incidents/mine").json()["items"]}
    assert mine["id"] in ids and other["id"] not in ids


def test_officer_records_are_scoped_to_own_team(mission):
    mine, other = mission
    team = officer_team()
    c = client("officer")
    rec = dict(incident_id=mine["id"], team_id=team, location="Bellandur", people_rescued=1, survivors=1, missing=0,
               deceased=0, severe_injuries=0, minor_injuries=0)
    assert c.post("/api/records/", json=rec).status_code == 201
    assert c.post("/api/records/", json=dict(rec, incident_id=other["id"])).status_code == 403       # not their mission
    assert c.post("/api/records/", json=dict(rec, team_id="TEAM-SOMEONE-ELSE")).status_code == 403   # not their team
    db = SessionLocal()
    db.add(RescueRecord(id="REC-OTHER-TEAM", incident_id=other["id"], team_id="TEAM-SOMEONE-ELSE", location="x",
                        people_rescued=9, survivors=9, missing=0, deceased=0, severe_injuries=0, minor_injuries=0))
    db.commit(); db.close()
    items = c.get("/api/records/").json()["items"]
    assert items and all(r["team_id"] == team for r in items)
    assert client("commander").get("/api/records/").json()["count"] > len(items)       # staff still see everything
    assert c.get("/api/records/summary").json()["total_missions"] == len(items)


def test_officer_without_a_team_sees_nothing(mission):
    db = SessionLocal()
    db.query(User).filter(User.username == "officer").update({"team_id": None}); db.commit(); db.close()
    try:
        c = client("officer")
        assert c.get("/api/incidents/").json()["items"] == []
        assert c.get(mission[0]["image_url"]).status_code == 404
    finally:
        db = SessionLocal()
        db.query(User).filter(User.username == "officer").update({"team_id": officer_team_original}); db.commit(); db.close()


officer_team_original = None


@pytest.fixture(autouse=True)
def _remember_officer_team():
    global officer_team_original
    officer_team_original = officer_team()
    yield


# ---------------------------------------------------------------- citizens and volunteers

@pytest.mark.parametrize("who", ["citizen", "volunteer"])
def test_public_roles_see_only_their_own_reports_and_photos(who):
    other = "volunteer" if who == "citizen" else "citizen"
    mine = make_report(who, with_photo=True)
    theirs = make_report(other, with_photo=True)
    c = client(who)
    assert c.get(f"/api/incidents/{mine['id']}").status_code == 200
    assert c.get(f"/api/incidents/{theirs['id']}").status_code == 404
    assert c.get(mine["image_url"]).status_code == 200
    assert c.get(theirs["image_url"]).status_code == 404
    assert {i["id"] for i in c.get("/api/incidents/mine").json()["items"]} >= {mine["id"]}
    assert theirs["id"] not in {i["id"] for i in c.get("/api/incidents/mine").json()["items"]}


@pytest.mark.parametrize("who", ["citizen", "volunteer"])
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/incidents/"), ("GET", "/api/incidents/beacons"), ("GET", "/api/teams/"), ("GET", "/api/volunteers/"),
    ("GET", "/api/records/"), ("GET", "/api/dashboard"), ("GET", "/api/agents/tasks"), ("GET", "/api/auth/users"),
    ("GET", "/api/auth/audit"), ("GET", "/api/diagnostics/"), ("GET", "/api/datasets/inventory"),
])
def test_public_roles_cannot_reach_operational_data(who, method, path):
    assert client(who).request(method, path).status_code == 403


# ---------------------------------------------------------------- administrator and developer see no incident data

@pytest.mark.parametrize("who", ["admin", "developer"])
def test_admin_and_developer_cannot_read_incidents_or_evidence(who):
    inc = make_report(with_photo=True)
    c = client(who)
    assert c.get("/api/incidents/").status_code == 403
    assert c.get(f"/api/incidents/{inc['id']}").status_code == 403
    assert c.get(f"/api/incidents/{inc['id']}/history").status_code == 403
    assert c.get(inc["image_url"]).status_code == 404          # S0 private-media rule: no evidence without incident rights
    assert c.get("/api/records/").status_code == 403
    assert c.get("/api/volunteers/").status_code == 403


def test_developer_cannot_see_user_accounts_or_dashboard_counts():
    c = client("developer")
    assert c.get("/api/auth/users").status_code == 403
    assert c.get("/api/auth/audit").status_code == 403
    assert c.get("/api/dashboard").status_code == 403
    assert c.get("/api/diagnostics/").status_code == 200


def test_diagnostics_response_holds_no_personal_data_or_secrets():
    d = client("developer").get("/api/diagnostics/")
    text = d.text.lower()
    for needle in ("rescue@2026", "pbkdf2", "reporter_contact", "@rescuenet.local", "eyj"):  # secret VALUES (warning prose may say "password")
        assert needle not in text


def test_user_listing_never_exposes_password_hashes():
    users = client("admin").get("/api/auth/users").json()["items"]
    assert users and all("password" not in " ".join(u).lower() for u in users)
    assert "pbkdf2" not in client("admin").get("/api/auth/users").text


# ---------------------------------------------------------------- S0 and guest behaviour are untouched

def test_guest_report_track_and_private_photo_rules_still_hold():
    g = client()
    up = g.post("/api/incidents/upload-image", files={"file": ("p.png", png(), "image/png")}).json()
    rep = g.post("/api/public/reports", json=dict(REPORT, image_url=up["image_url"])).json()
    assert g.get(up["image_url"]).status_code == 401
    assert g.get(f"/api/public/reports/{rep['public_ref']}", headers={"X-Tracking-Code": rep["tracking_code"]}).status_code == 200
    assert client("commander").get(up["image_url"]).status_code == 200
