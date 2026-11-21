"""Volunteer verification and assignment; facility types and capacity status."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.facilities import capacity_status
from tests.conftest import sign_in

ops = sign_in(TestClient(app), "operator")


def _dispatched_incident():
    inc = ops.post("/api/incidents/", json={
        "title": "Volunteer test", "description": "Street flooded", "area": "Hebbal",
        "latitude": 13.03, "longitude": 77.59, "severity": "LOW", "people_affected": 1}).json()["id"]
    assert ops.post(f"/api/incidents/{inc}/state", json={"to_status": "VERIFIED"}).status_code == 200
    assert ops.post(f"/api/incidents/{inc}/state", json={"to_status": "DISPATCHED"}).status_code == 200
    return inc


def _new_volunteer(verified):
    v = ops.post("/api/volunteers/", json={"name": "Test Volunteer", "phone": "9000000000",
                 "email": f"{uuid.uuid4().hex[:6]}@example.com", "skills": "First aid", "area": "Hebbal"}).json()
    if verified:
        assert ops.patch(f"/api/volunteers/{v['id']}", json={"is_verified": True}).status_code == 200
    return v["id"]


def test_unverified_volunteer_cannot_be_assigned():
    inc, vid = _dispatched_incident(), _new_volunteer(verified=False)
    r = ops.post(f"/api/volunteers/{vid}/assign", json={"incident_id": inc})
    assert r.status_code == 409 and "not verified" in r.json()["detail"]


def test_verified_volunteer_assign_release_and_audit():
    inc, vid = _dispatched_incident(), _new_volunteer(verified=True)
    r = ops.post(f"/api/volunteers/{vid}/assign", json={"incident_id": inc})
    assert r.status_code == 200
    assert r.json()["status"] == "ASSIGNED" and r.json()["assigned_incident_id"] == inc
    assert r.json()["verified_by"] == "operator"
    assert ops.post(f"/api/volunteers/{vid}/assign", json={"incident_id": inc}).status_code == 409  # already assigned
    assert ops.patch(f"/api/volunteers/{vid}", json={"status": "STANDBY"}).status_code == 409
    assert ops.patch(f"/api/volunteers/{vid}", json={"is_verified": False}).status_code == 409
    rel = ops.post(f"/api/volunteers/{vid}/release")
    assert rel.status_code == 200 and rel.json()["status"] == "AVAILABLE" and rel.json()["assigned_incident_id"] is None
    actions = [h["action"] for h in ops.get(f"/api/incidents/{inc}/history").json()["items"]]
    assert "VOLUNTEER_ASSIGNED" in actions and "VOLUNTEER_RELEASED" in actions


def test_status_patch_cannot_fake_an_assignment():
    vid = _new_volunteer(verified=False)
    assert ops.patch(f"/api/volunteers/{vid}", json={"status": "ASSIGNED"}).status_code == 422


def test_cannot_assign_to_an_incident_that_is_not_active():
    vid = _new_volunteer(verified=True)
    inc = ops.post("/api/incidents/", json={"title": "Not yet", "description": "Just reported", "area": "Hebbal",
                   "latitude": 13.03, "longitude": 77.59, "severity": "LOW", "people_affected": 1}).json()["id"]
    assert ops.post(f"/api/volunteers/{vid}/assign", json={"incident_id": inc}).status_code == 409


def test_volunteers_are_freed_when_the_incident_resolves():
    inc, vid = _dispatched_incident(), _new_volunteer(verified=True)
    assert ops.post(f"/api/volunteers/{vid}/assign", json={"incident_id": inc}).status_code == 200
    for to in ("ON_SCENE", "RESOLVED"):
        assert ops.post(f"/api/incidents/{inc}/state", json={"to_status": to}).status_code == 200
    vols = {v["id"]: v for v in ops.get("/api/volunteers/").json()["items"]}
    assert vols[vid]["status"] == "AVAILABLE" and vols[vid]["assigned_incident_id"] is None


def test_citizen_cannot_manage_volunteers():
    citizen = sign_in(TestClient(app), "citizen")
    assert citizen.get("/api/volunteers/").status_code == 403
    assert citizen.post("/api/volunteers/VOL-101/assign", json={"incident_id": "INC-1"}).status_code == 403


def test_capacity_status_rule():
    assert capacity_status(0, 100) == "OPERATIONAL"
    assert capacity_status(89, 100) == "OPERATIONAL"
    assert capacity_status(90, 100) == "NEAR_CAPACITY"
    assert capacity_status(100, 100) == "FULL"


def test_new_facility_types_exist_and_are_labelled_simulated():
    items = ops.get("/api/facilities/").json()["items"]
    types = {f["facility_type"] for f in items}
    assert {"FIRE_STATION", "POLICE_STATION", "SCHOOL"} <= types
    assert all(f["data_label"] == "SIMULATED" for f in items if f["id"].startswith(("FAC-FIRE", "FAC-POLI", "FAC-SCHO")))


def test_facility_validation_and_derived_status():
    body = {"name": "Test shelter", "facility_type": "shelter", "address": "Hebbal", "latitude": 13.03,
            "longitude": 77.59, "total_capacity": 50, "current_occupancy": 46, "contact": "112"}
    r = ops.post("/api/facilities/", json=body)
    assert r.status_code == 201
    assert r.json()["status"] == "NEAR_CAPACITY" and r.json()["data_label"] == "OBSERVED"
    fid = r.json()["id"]
    assert ops.post("/api/facilities/", json={**body, "facility_type": "SPACESHIP"}).status_code == 422
    assert ops.post("/api/facilities/", json={**body, "current_occupancy": 80}).status_code == 422
    up = ops.patch(f"/api/facilities/{fid}/occupancy", json={"current_occupancy": 50})
    assert up.status_code == 200 and up.json()["status"] == "FULL"
    assert ops.patch(f"/api/facilities/{fid}/occupancy", json={"current_occupancy": 99}).status_code == 422
    assert ops.patch(f"/api/facilities/{fid}/occupancy", json={"current_occupancy": 10}).json()["status"] == "OPERATIONAL"


def test_volunteer_ids_do_not_collide_between_signup_and_staff_entry():
    c = TestClient(app)
    ids = set()
    for i in range(3):
        reg = c.post("/api/auth/register", json={"role": "VOLUNTEER", "username": f"vol{uuid.uuid4().hex[:6]}",
                     "full_name": "Sign Up Volunteer", "password": "Strong#Pass1", "phone": "9111111111",
                     "skills": "Swimming", "area": "Whitefield"}).json()["user"]["volunteer_id"]
        staff = _new_volunteer(verified=False)
        ids.update({reg, staff})
    assert len(ids) == 6
