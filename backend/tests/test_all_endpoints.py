import asyncio
import sys
import time
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.api.routes import (
    alerts,
    dashboard,
    datasets,
    facilities,
    flood,
    health,
    incidents,
    records,
    teams,
    volunteers,
    agents,
)
from app.schemas.domain import (
    FloodScenarioInput,
    IncidentCreate,
    AlertCreate,
    SupervisorTaskRequest,
)
from app.api.routes.teams import TeamAssignRequest

def run_all_tests():
    db = SessionLocal()
    try:
        print("=== 1. Health Endpoint ===")
        t0 = time.time()
        h_res = health.health_check(db=db)
        print(f" Health OK in {time.time()-t0:.3f}s: Status={h_res['status']}, ML={h_res['ml_service']['status']}")
        assert h_res["status"] == "healthy"
        assert h_res["database"]["status"] == "healthy"

        print("\n=== 2. Dashboard Endpoint ===")
        t0 = time.time()
        d_res = dashboard.get_dashboard(db=db)
        print(f" Dashboard OK in {time.time()-t0:.3f}s: Total Incidents={d_res['summary']['total_incidents']}")
        assert d_res["summary"]["total_incidents"] > 0

        print("\n=== 3. Incidents List & Create ===")
        t0 = time.time()
        inc_list = incidents.list_incidents(db=db)
        print(f" Incidents List OK in {time.time()-t0:.3f}s: {inc_list['count']} items")

        new_inc = incidents.create_incident(
            payload=IncidentCreate(
                title="Verified Bellandur Overflow Probe",
                description="Culvert discharge testing with real sensors",
                area="Bellandur, Bengaluru",
                latitude=12.935,
                longitude=77.678,
                severity="HIGH",
                people_affected=4,
                source="CITIZEN_REPORT",
            ),
            db=db,
        )
        print(f" Created Incident OK: ID={new_inc.id}, Severity={new_inc.severity}")

        print("\n=== 4. Flood ML Forecast Scenario (Scikit-Learn Random Forest) ===")
        t0 = time.time()
        forecast_res = flood.run_flood_scenario_forecast(
            scenario=FloodScenarioInput(
                rainfall_mm=45.0,
                water_level_m=4.9,
                humidity_pct=88.0,
                temperature_c=25.5,
            )
        )
        print(f" ML Forecast OK in {time.time()-t0:.3f}s: Risk={forecast_res['risk_level']}, Prob={forecast_res['probability']}, Horizon 30m={forecast_res['horizon_30m']}")
        assert forecast_res["risk_level"] in ["CRITICAL", "HIGH"]
        assert 0.0 <= forecast_res["probability"] <= 1.0

        print("\n=== 5. GIS Catchments & River Gauges ===")
        t0 = time.time()
        catchments = flood.get_catchments()
        gauges = flood.get_river_gauges()
        print(f" GIS OK in {time.time()-t0:.3f}s: {len(catchments['features'])} catchments, {gauges['count']} monitoring gauges")
        assert len(catchments["features"]) > 0
        assert gauges["count"] > 0

        print("\n=== 6. Alerts List & Acknowledge ===")
        t0 = time.time()
        new_alert = alerts.create_alert(
            payload=AlertCreate(
                title="Storm Surge Flood Warning",
                message="Flash surge runoff approaching low-lying arterial underpass",
                severity="CRITICAL",
                area="Bellandur Basin",
                latitude=12.935,
                longitude=77.678,
                radius_km=3.0,
            ),
            db=db,
        )
        ack = alerts.acknowledge_alert(alert_id=new_alert.id, db=db)
        print(f" Alerts OK in {time.time()-t0:.3f}s: Created {new_alert.id}, Acknowledged Count={ack.acknowledged_count}")

        print("\n=== 7. Rescue Teams & Assignment ===")
        t0 = time.time()
        teams_list = teams.list_teams(db=db)
        team = teams_list["items"][0]
        assigned = teams.assign_team_to_incident(
            team_id=team.id,
            payload=TeamAssignRequest(incident_id=new_inc.id),
            db=db,
        )
        print(f" Teams OK in {time.time()-t0:.3f}s: Team {team.id} assigned, status={assigned['team_status']}")

        print("\n=== 8. Facilities Distance Query ===")
        t0 = time.time()
        facs = facilities.list_facilities(user_lat=12.9716, user_lon=77.5946, db=db)
        print(f" Facilities OK in {time.time()-t0:.3f}s: {facs['count']} facilities, Closest={facs['items'][0].name}")

        print("\n=== 9. Rescue Records Summary & CSV Export ===")
        t0 = time.time()
        rec_summary = records.get_records_summary(db=db)
        csv_resp = records.export_records_csv(db=db)
        print(f" Records OK in {time.time()-t0:.3f}s: Rescued={rec_summary['total_rescued']}, CSV Content Length={len(csv_resp.body)} bytes")

        print("\n=== 10. Dataset Inventory & Provenance Verification ===")
        t0 = time.time()
        inv = datasets.get_dataset_inventory(db=db)
        print(f" Inventory OK in {time.time()-t0:.3f}s: {inv['count']} datasets registered, {inv['total_records_ingested']} records ingested")
        print(f"   Flood images verified: {inv['flood_images_verified']} (Unique: {inv['flood_images_unique']}, Duplicates: {inv['duplicate_images_count']})")
        assert inv["count"] == 7
        assert inv["flood_images_verified"] == 809
        assert inv["flood_images_unique"] == 808

        print("\n=== 11. Machine Learning Models Status ===")
        t0 = time.time()
        models_status = datasets.get_models_status()
        print(f" Models Status OK in {time.time()-t0:.3f}s: {models_status['count']} models registered")
        rf_model = next(m for m in models_status["models"] if m["id"] == "model-rf-hydrology")
        cv_model = next(m for m in models_status["models"] if m["id"] == "model-cv-flood-vision")
        assert rf_model["is_loaded"] is True
        assert rf_model["prediction_endpoint"] == "/api/flood/forecast"
        assert cv_model["is_loaded"] is False
        assert cv_model["prediction_endpoint"] is None
        print(f"   RF Model: Loaded={rf_model['is_loaded']}, Endpoint={rf_model['prediction_endpoint']}")
        print(f"   CV Model: Status={cv_model['status']}, Preprocessing={cv_model['preprocessing_endpoint']}")

        print("\n=== 12. Paginated Flood Images Browser ===")
        t0 = time.time()
        page_res = datasets.get_flood_images_paginated(page=1, page_size=12, format="all", collection="all")
        print(f" Paginated Images OK in {time.time()-t0:.3f}s: {len(page_res['images'])} images on page 1 of {page_res['total_pages']} (Total: {page_res['total_available']})")
        assert page_res["total_available"] == 809
        assert page_res["unique_available"] == 808

        print("\n=== 13. File Serving Endpoint & Path Traversal Guard ===")
        sample_img = page_res["images"][0]["filename"]
        file_resp = datasets.serve_flood_image(sample_img)
        assert file_resp.status_code == 200
        print(f" File Serving OK: '{sample_img}' served with Content-Type={file_resp.media_type}")

        try:
            datasets.serve_flood_image("../../etc/passwd")
            assert False, "Path traversal should have been blocked"
        except Exception as e:
            print(f" Path Traversal Blocked OK: {e}")

        print("\n=== 14. Technical Image Metadata Inspection ===")
        t0 = time.time()
        insp_res = datasets.inspect_image_metadata(sample_img)
        print(f" Inspection OK in {time.time()-t0:.3f}s: {insp_res['filename']} ({insp_res['dimensions']['width']}x{insp_res['dimensions']['height']} px), Format={insp_res['format']}")
        assert insp_res["computer_vision"]["model_status"] == "Model not configured"
        assert insp_res["computer_vision"]["has_trained_weights"] is False

        print("\n=== 15. Computer Vision Preprocessing Validation ===")
        t0 = time.time()
        prep_res = datasets.preprocess_flood_image(sample_img)
        print(f" Preprocessing OK in {time.time()-t0:.3f}s: Target Tensor={prep_res['target_tensor_shape']}, Scale={prep_res['scaling']['scale_factor']}")
        assert prep_res["preprocessing_status"] == "SUCCESS"
        assert prep_res["model_integration"]["model_status"] == "Model not configured"
        assert prep_res["model_integration"]["inference_executed"] is False

        print("\n=== 16. Supervisor Autonomous Multi-Agent Triage ===")
        t0 = time.time()
        task = asyncio.run(
            agents.execute_supervisor_triage(
                payload=SupervisorTaskRequest(
                    task_type="TRIAGE",
                    incident_id=new_inc.id,
                ),
                db=db,
            )
        )
        print(f" Supervisor Agent OK in {time.time()-t0:.3f}s: Task {task.id}, Status={task.status}")
        print(f"   Findings: {task.findings[:90]}...")
        if task.requires_human_approval:
            appr = agents.approve_supervisor_task(task_id=task.id, db=db)
            print(f"   Human Gatekeeper Approval Verified: Status={appr.status}")

        print("\n============================================================")
        print(" ALL 16 END-TO-END APPLICATION & DATASET WORKFLOWS PASSED!")
        print("============================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_all_tests()
