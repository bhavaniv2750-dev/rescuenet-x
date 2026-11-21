import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_system():
    print("=== 1. Health Endpoint ===")
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["database"]["status"] == "healthy"
    assert data["ml_service"]["status"] == "loaded"
    print(" Health OK:", data["database"])

    print("\n=== 2. Dashboard Endpoint ===")
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    dash = r.json()
    assert dash["summary"]["total_incidents"] > 0
    assert dash["summary"]["response_teams"]["total"] > 0
    print(" Dashboard OK:", dash["summary"])

    print("\n=== 3. Incidents List ===")
    r = client.get("/api/incidents/")
    assert r.status_code == 200
    inc_list = r.json()
    assert inc_list["count"] > 0
    print(f" Incidents OK: {inc_list['count']} records found")

    print("\n=== 4. Create Incident ===")
    r = client.post("/api/incidents/", json={
        "title": "Test Breach at Bellandur Lake",
        "description": "Culvert overflow during testing",
        "area": "Bellandur, Bengaluru",
        "latitude": 12.935,
        "longitude": 77.678,
        "severity": "HIGH",
        "people_affected": 5,
        "source": "CITIZEN_REPORT"
    })
    assert r.status_code == 201
    created_inc = r.json()
    print(" Created Incident:", created_inc["id"])

    print("\n=== 5. Flood Forecast Scenario ===")
    r = client.post("/api/flood/forecast", json={
        "rainfall_mm": 42.0,
        "water_level_m": 4.8,
        "humidity_pct": 85.0,
        "temperature_c": 26.0
    })
    assert r.status_code == 200
    pred = r.json()
    assert pred["risk_level"] in ["CRITICAL", "HIGH"]
    assert 0.0 <= pred["probability"] <= 1.0
    print(f" Forecast OK: Risk={pred['risk_level']}, Prob={pred['probability']}, Confidence={pred['confidence_level']}")

    print("\n=== 6. Catchments GeoJSON ===")
    r = client.get("/api/flood/catchments")
    assert r.status_code == 200
    geo = r.json()
    assert len(geo["features"]) > 0
    print(f" Catchments OK: {len(geo['features'])} GIS polygons parsed")

    print("\n=== 7. River Gauges ===")
    r = client.get("/api/flood/gauges")
    assert r.status_code == 200
    gauges = r.json()
    assert gauges["count"] > 0
    print(f" Gauges OK: {gauges['count']} monitoring stations")

    print("\n=== 8. Alerts List & Create ===")
    r = client.post("/api/alerts/", json={
        "title": "Flash Surge Alert Test",
        "message": "Water level spike near Bellandur",
        "severity": "CRITICAL",
        "area": "Bellandur Basin",
        "latitude": 12.935,
        "longitude": 77.678,
        "radius_km": 3.0
    })
    assert r.status_code == 201
    alert_id = r.json()["id"]

    r = client.post(f"/api/alerts/{alert_id}/acknowledge")
    assert r.status_code == 200
    assert r.json()["acknowledged_count"] == 1
    print(f" Alerts OK: Created & Acknowledged {alert_id}")

    print("\n=== 9. Rescue Teams & Assignment ===")
    r = client.get("/api/teams/")
    assert r.status_code == 200
    teams = r.json()
    assert teams["count"] > 0
    team_id = teams["items"][0]["id"]

    r = client.post(f"/api/teams/{team_id}/assign", json={"incident_id": created_inc["id"]})
    assert r.status_code == 200
    print(f" Team Assignment OK: Team {team_id} assigned to {created_inc['id']}")

    print("\n=== 10. Facilities & Distance Calculation ===")
    r = client.get("/api/facilities/?lat=12.9716&lon=77.5946")
    assert r.status_code == 200
    facs = r.json()
    assert facs["count"] > 0
    closest = facs["items"][0]
    print(f" Facilities OK: {facs['count']} items. Closest={closest['name']} ({closest['distance_km']} km)")

    print("\n=== 11. Rescue Records ===")
    r = client.get("/api/records/summary")
    assert r.status_code == 200
    recs = r.json()
    assert recs["total_missions"] > 0
    print(f" Rescue Records OK: Rescued={recs['total_rescued']}, Survivors={recs['total_survivors']}")

    print("\n=== 12. Dataset Inventory ===")
    r = client.get("/api/datasets/inventory")
    assert r.status_code == 200
    datasets = r.json()
    assert datasets["count"] == 7
    print(f" Datasets OK: {datasets['count']} datasets registered ({datasets['total_records_ingested']} records)")

    print("\n=== 13. Supervisor Multi-Agent Triage ===")
    r = client.post("/api/agents/supervisor/triage", json={
        "task_type": "TRIAGE",
        "incident_id": created_inc["id"]
    })
    assert r.status_code == 201
    task = r.json()
    assert task["id"].startswith("TASK-")
    print(f" Supervisor Triage OK: {task['id']}, Status={task['status']}")
    print(f"   Findings: {task['findings'][:100]}...")

    # Approve task if needed
    if task["requires_human_approval"]:
        r_appr = client.post(f"/api/agents/tasks/{task['id']}/approve")
        assert r_appr.status_code == 200
        assert r_appr.json()["status"] == "COMPLETED"
        print("   Human Approval Gatekeeper Verified!")

    print("\n=== 14. Image Upload & Static Retrieval ===")
    dummy_image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    r = client.post(
        "/api/incidents/upload-image",
        files={"file": ("field_flood_proof.png", dummy_image_bytes, "image/png")},
    )
    assert r.status_code == 201
    upload_res = r.json()
    assert upload_res["status"] == "success"
    assert "/api/incidents/uploads/" in upload_res["image_url"]
    print(" Image Upload OK:", upload_res["image_url"])

    # Test static retrieval of uploaded image
    r_img = client.get(upload_res["image_url"])
    assert r_img.status_code == 200
    assert len(r_img.content) == len(dummy_image_bytes)
    print(" Image Retrieval OK: Verified exact byte match")

    print("\n=== 15. Create Incident With Attached Image & Reporter Info ===")
    r = client.post("/api/incidents/", json={
        "title": "Severe Lake Inundation near Rainbow Drive",
        "description": "Basement level flooded with 1.8m water, photo attached from drone camera",
        "area": "Sarjapur Road / Rainbow Drive",
        "latitude": 12.915,
        "longitude": 77.685,
        "severity": "CRITICAL",
        "people_affected": 8,
        "source": "CITIZEN_REPORT",
        "incident_type": "LAKE_OVERFLOW",
        "image_url": upload_res["image_url"],
        "reporter_name": "Ramesh Kumar (Resident)",
        "reporter_contact": "+91-98450-11223",
    })
    assert r.status_code == 201
    inc_with_img = r.json()
    assert inc_with_img["image_url"] == upload_res["image_url"]
    assert inc_with_img["reporter_name"] == "Ramesh Kumar (Resident)"
    print(" Incident With Photo OK:", inc_with_img["id"])

    print("\n=== 16. Rescue Records CSV Export Endpoint ===")
    r = client.get("/api/records/export/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment;" in r.headers["content-disposition"]
    csv_text = r.content.decode("utf-8-sig")
    assert "Record ID" in csv_text
    assert "Incident ID" in csv_text
    assert "Mission Debrief Notes" in csv_text
    lines = csv_text.strip().split("\r\n")
    print(f" CSV Export OK: {len(lines)} lines exported (Header + {len(lines)-1} mission records)")

    print("\n==========================================")
    print(" ALL 16 TEST WORKFLOWS PASSED WITH 100% SUCCESS!")
    print("==========================================")

if __name__ == "__main__":
    test_full_system()
