"""Incident lifecycle, approval gate, LoRa intake and trilateration."""

import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_team, sign_in
from app.services import incident_lifecycle as lifecycle
from app.services.trilateration import rssi_to_distance_m, trilaterate

client = sign_in(TestClient(app), "commander")


def _new_incident(people=1, severity="LOW"):
    r = client.post("/api/incidents/", json={
        "title": "Test waterlogging", "description": "Water entering ground floor homes",
        "area": "Bellandur", "latitude": 12.926, "longitude": 77.676,
        "severity": severity, "people_affected": people, "source": "CITIZEN_APP",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _move(inc_id, to, **extra):
    return client.post(f"/api/incidents/{inc_id}/state", json={"to_status": to, **extra})


def test_lifecycle_endpoint_lists_all_states():
    body = client.get("/api/incidents/lifecycle").json()
    assert body["states"] == lifecycle.STATES
    assert body["transitions"]["ON_SCENE"] == ["RESOLVED"]


def test_valid_path_to_resolved_and_history():
    inc = _new_incident()
    for s in ["UNDER_VERIFICATION", "VERIFIED"]:
        r = _move(inc, s, actor="tester")
        assert r.status_code == 200, (s, r.text)
    # Dispatch happens together with a team assignment, not by editing the status.
    team = make_team(client)
    assert client.post(f"/api/teams/{team}/assign", json={"incident_id": inc}).status_code == 200
    for s in ["IN_TRANSIT", "ON_SCENE", "RESOLVED"]:
        r = _move(inc, s, actor="tester")
        assert r.status_code == 200, (s, r.text)
    assert r.json()["verified_by"] == "commander"  # the signed-in user, not a name the caller supplies
    hist = client.get(f"/api/incidents/{inc}/history").json()
    actions = [h["action"] for h in hist["items"]]
    assert actions[0] == "INCIDENT_REPORTED"
    assert actions.count("INCIDENT_STATE_CHANGE") == 6


def test_invalid_transition_rejected():
    inc = _new_incident()
    assert _move(inc, "RESOLVED").status_code == 409
    assert _move(inc, "NOT_A_STATE").status_code == 422


def test_duplicate_needs_reference():
    first, second = _new_incident(), _new_incident()
    assert _move(second, "DUPLICATE").status_code == 422
    r = _move(second, "DUPLICATE", duplicate_of=first)
    assert r.status_code == 200 and r.json()["duplicate_of"] == first
    assert _move(second, "VERIFIED").status_code == 409  # terminal


def test_gate_blocks_direct_dispatch_of_high_impact_incident():
    inc = _new_incident(people=8, severity="HIGH")
    assert _move(inc, "VERIFIED").status_code == 200
    assert _move(inc, "DISPATCHED").status_code == 409
    teams = client.get("/api/teams/", params={"status": "AVAILABLE"}).json()["items"]
    if teams:
        r = client.post(f"/api/teams/{teams[0]['id']}/assign", json={"incident_id": inc})
        assert r.status_code == 409


def test_triage_then_decline_and_approve():
    inc = _new_incident(people=6, severity="CRITICAL")
    _move(inc, "VERIFIED")
    task = client.post("/api/agents/supervisor/triage", json={"task_type": "TRIAGE", "incident_id": inc}).json()
    assert task["status"] == "PENDING_APPROVAL" and task["incident_id"] == inc
    assert client.get(f"/api/incidents/{inc}").json()["status"] == "PENDING_APPROVAL"
    # Operator cannot skip the commander.
    assert _move(inc, "DISPATCHED").status_code == 409

    declined = client.post(f"/api/agents/tasks/{task['id']}/decline", json={"note": "route flooded"}).json()
    assert declined["status"] == "DECLINED"
    assert client.get(f"/api/incidents/{inc}").json()["status"] == "REJECTED"

    assert _move(inc, "QUEUED").status_code == 200
    task2 = client.post("/api/agents/supervisor/triage", json={"task_type": "TRIAGE", "incident_id": inc}).json()
    approved = client.post(f"/api/agents/tasks/{task2['id']}/approve", json={"commander": "Someone Else"}).json()
    assert approved["status"] == "APPROVED"
    assert "(commander)" in approved["approved_by"] and "Someone Else" not in approved["approved_by"]
    assert client.get(f"/api/incidents/{inc}").json()["status"] == "DISPATCHED"
    # A decided task cannot be decided again.
    assert client.post(f"/api/agents/tasks/{task2['id']}/approve").status_code == 409


def test_lora_packet_with_gps_creates_then_refreshes():
    pkt = {"beacon_id": "BCN-TEST-1", "latitude": 12.93, "longitude": 77.62, "hop_count": 2,
           "battery_pct": 64, "emergency_level": "HIGH", "casualty_estimate": 3, "area": "Koramangala"}
    r1 = client.post("/api/incidents/lora", json=pkt)
    assert r1.status_code == 201 and r1.json()["created"] is True
    inc = r1.json()["incident"]
    assert inc["data_label"] == "SIMULATED" and inc["location_method"] == "GPS" and inc["source"] == "MESH_SOS"
    r2 = client.post("/api/incidents/lora", json={**pkt, "battery_pct": 50, "casualty_estimate": 5})
    assert r2.json()["created"] is False
    assert r2.json()["incident"]["id"] == inc["id"]
    assert r2.json()["incident"]["device_battery_pct"] == 50
    beacons = client.get("/api/incidents/beacons").json()
    assert any(b["beacon_id"] == "BCN-TEST-1" and b["last_battery_pct"] == 50 for b in beacons["items"])
    assert beacons["count"] >= 35


def test_lora_packet_outside_karnataka_rejected():
    pkt = {"beacon_id": "BCN-TEST-2", "latitude": 19.07, "longitude": 72.87, "hop_count": 1,
           "battery_pct": 80, "emergency_level": "LOW", "casualty_estimate": 1}
    assert client.post("/api/incidents/lora", json=pkt).status_code == 422


def test_lora_packet_without_gps_needs_three_gateways():
    pkt = {"beacon_id": "BCN-TEST-3", "hop_count": 1, "battery_pct": 80, "emergency_level": "LOW",
           "casualty_estimate": 1, "gateway_readings": [
               {"gateway_id": "GW1", "latitude": 12.93, "longitude": 77.62, "rssi_dbm": -90}]}
    assert client.post("/api/incidents/lora", json=pkt).status_code == 422


def _offset(lat, lon, dx, dy):
    return lat + math.degrees(dy / 6_371_000), lon + math.degrees(dx / (6_371_000 * math.cos(math.radians(lat))))


def test_trilateration_recovers_position_from_exact_ranges():
    true_lat, true_lon = 12.9352, 77.6245
    gws = [_offset(true_lat, true_lon, dx, dy) for dx, dy in [(-800, -600), (900, -400), (100, 1000), (-500, 700)]]
    readings = []
    for glat, glon in gws:
        d = math.hypot(*[(glat - true_lat) * 111_195, (glon - true_lon) * 111_195 * math.cos(math.radians(true_lat))])
        readings.append((glat, glon, d))
    lat, lon, rms = trilaterate(readings)
    err = math.hypot((lat - true_lat) * 111_195, (lon - true_lon) * 111_195 * math.cos(math.radians(true_lat)))
    assert err < 5 and rms < 5


def test_rssi_distance_model_is_monotonic():
    assert rssi_to_distance_m(-40) == pytest.approx(1.0)
    assert rssi_to_distance_m(-100) > rssi_to_distance_m(-80) > rssi_to_distance_m(-60)


def test_trilateration_rejects_collinear_gateways():
    with pytest.raises(ValueError):
        trilaterate([(12.90, 77.60, 500), (12.91, 77.60, 500), (12.92, 77.60, 500)])


def test_lora_trilateration_end_to_end():
    gws = [("GW-A", 12.930, 77.615), ("GW-B", 12.940, 77.630), ("GW-C", 12.925, 77.635)]
    readings = [{"gateway_id": g, "latitude": la, "longitude": lo, "rssi_dbm": -105} for g, la, lo in gws]
    pkt = {"beacon_id": "BCN-TEST-4", "hop_count": 3, "battery_pct": 40, "emergency_level": "MODERATE",
           "casualty_estimate": 2, "gateway_readings": readings}
    r = client.post("/api/incidents/lora", json=pkt)
    assert r.status_code == 201, r.text
    assert r.json()["location_method"] == "TRILATERATION"
    inc = r.json()["incident"]
    assert 12.92 < inc["latitude"] < 12.945 and 77.61 < inc["longitude"] < 77.64


def test_lora_gateway_key_is_enforced_when_configured(monkeypatch):
    from app.core.config import settings

    pkt = {"beacon_id": "BCN-KEY-1", "latitude": 12.93, "longitude": 77.62, "hop_count": 1,
           "battery_pct": 70, "emergency_level": "LOW", "casualty_estimate": 1}
    monkeypatch.setattr(settings, "LORA_GATEWAY_KEY", "s3cret-key")
    anon = TestClient(app)  # gateways are devices: no user sign-in
    assert anon.post("/api/incidents/lora", json=pkt).status_code == 401
    assert anon.post("/api/incidents/lora", json=pkt, headers={"X-Gateway-Key": "wrong"}).status_code == 401
    assert anon.post("/api/incidents/lora", json=pkt, headers={"X-Gateway-Key": "s3cret-key"}).status_code == 201
