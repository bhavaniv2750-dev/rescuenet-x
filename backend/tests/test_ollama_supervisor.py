"""
Pytest test suite for RescueNet X 2.0 - Phase 1: Ollama Supervisor Integration.

Includes:
- Deterministic unit tests with mocked Ollama API responses
- Structured schema validation, malformed JSON recovery, timeout degradation
- Rejection of hallucinated team/facility IDs and binding of real database records
- Safety gatekeeper enforcement (unauthorized dispatch prevention)
- Separate integration test targeting the genuine local Ollama API
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.api.routes.agents import approve_supervisor_task, execute_supervisor_triage
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import Facility, Incident, RescueTeam, SupervisorTask
from app.schemas.domain import SupervisorTaskRequest
from app.services.ollama_service import (
    OllamaSupervisorOutput,
    OllamaSupervisorService,
    haversine_km,
    ollama_supervisor_service,
)


@pytest.fixture
def db_session():
    """Provide a database session fixture and clean up on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def api_client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as client:
        yield client


# =====================================================================
# Unit Tests (Deterministic with Mocked Ollama API)
# =====================================================================

def test_ollama_health_mock():
    """Test Ollama health check reporting available and installed model."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen3:4b-instruct"}, {"name": "qwen2.5:3b"}]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        svc = OllamaSupervisorService()
        health = svc.check_health()
        assert health["available"] is True
        assert health["model_installed"] is True
        assert "qwen3:4b-instruct" in health["installed_models"]


def test_ollama_structured_response_unit(db_session):
    """Test parsing and validating structured Ollama output with Pydantic."""
    incident = db_session.query(Incident).filter(Incident.id == "INC-1042").first()
    assert incident is not None, "Fixture INC-1042 must exist in database"

    available_teams = db_session.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").all()
    candidate_facs = db_session.query(Facility).filter(Facility.status == "OPERATIONAL").all()

    mock_llm_json = {
        "incident_analysis": "Severe low-lying inundation trapped 12 civilians in basements.",
        "evidence_and_freshness": "Field report verified 8 minutes ago. Gauge monitoring station 4.8km away.",
        "risk_assessment": "CRITICAL",
        "suggested_team_id": available_teams[0].id if available_teams else None,
        "suggested_facility_id": candidate_facs[0].id if candidate_facs else None,
        "recommended_actions": [
            "Deploy motorized inflatable rescue raft squad.",
            "Establish secondary staging perimeter.",
            "Stage 12 beds at receiving emergency shelter."
        ],
        "requires_approval": True,
        "approval_rationale": "High-risk life safety operation with >= 5 civilians involved."
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(mock_llm_json)}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = asyncio.run(
            ollama_supervisor_service.run_supervisor_reasoning(
                incident=incident,
                target_lat=incident.latitude,
                target_lon=incident.longitude,
                target_title=incident.title,
                target_area=incident.area,
                people_count=incident.people_affected,
                task_type="TRIAGE",
                instruction="Full tactical triage",
                available_teams=available_teams,
                candidate_facilities=candidate_facs,
                nearest_gauge={"station_name": "Ulsoor Lake Gauge", "river": "Dakshina Pinakini", "warning_level_m": 2.5, "danger_level_m": 4.0},
                gauge_dist_km=4.8,
            )
        )

        assert result.model_status == "ONLINE"
        assert isinstance(result.structured_output, OllamaSupervisorOutput)
        assert result.structured_output.risk_assessment == "CRITICAL"
        assert len(result.structured_output.recommended_actions) == 3
        assert result.validated_team_id == available_teams[0].id
        assert result.enforced_requires_approval is True
        assert "CRITICAL" in result.findings_formatted


def test_invalid_json_handling_unit():
    """Test extractor robustness against markdown code fences, embedded JSON, and corrupt payloads."""
    svc = OllamaSupervisorService()

    # 1. Markdown code block
    fenced = '```json\n{"incident_analysis": "OK", "evidence_and_freshness": "Fresh", "risk_assessment": "HIGH", "suggested_team_id": null, "suggested_facility_id": null, "recommended_actions": ["Dispatch squad"], "requires_approval": true, "approval_rationale": "High risk"}\n```'
    parsed_fenced = svc._extract_json_from_text(fenced)
    assert parsed_fenced["risk_assessment"] == "HIGH"

    # 2. Embedded JSON in conversational filler
    embedded = 'Here is the tactical output:\n{"incident_analysis": "Embedded", "evidence_and_freshness": "Fresh", "risk_assessment": "LOW", "suggested_team_id": null, "suggested_facility_id": null, "recommended_actions": [], "requires_approval": false, "approval_rationale": "None"}\nPlease review carefully.'
    parsed_embedded = svc._extract_json_from_text(embedded)
    assert parsed_embedded["risk_assessment"] == "LOW"

    # 3. Non-JSON string raises JSONDecodeError
    with pytest.raises(json.JSONDecodeError):
        svc._extract_json_from_text("Completely unparseable text without braces")


def test_ollama_timeout_handling_mock(db_session):
    """Test graceful fallback when Ollama request exceeds configured timeout."""
    import httpx

    available_teams = db_session.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").all()
    candidate_facs = db_session.query(Facility).filter(Facility.status == "OPERATIONAL").all()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Read timed out")):
        result = asyncio.run(
            ollama_supervisor_service.run_supervisor_reasoning(
                incident=None,
                target_lat=12.9716,
                target_lon=77.5946,
                target_title="Timeout Incident",
                target_area="Shivajinagar",
                people_count=6,
                task_type="TRIAGE",
                instruction="Test timeout recovery",
                available_teams=available_teams,
                candidate_facilities=candidate_facs,
                nearest_gauge=None,
                gauge_dist_km=99.0,
            )
        )

        assert result.model_status == "TIMEOUT"
        assert "TIMEOUT" in result.findings_formatted or "Deterministic safety evaluation" in result.findings_formatted
        assert result.validated_team_id is not None
        assert result.enforced_requires_approval is True


def test_unknown_rescue_team_id_rejection_mock(db_session):
    """Test strict rejection of hallucinated team and facility IDs."""
    available_teams = db_session.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").all()
    candidate_facs = db_session.query(Facility).filter(Facility.status == "OPERATIONAL").all()

    hallucinated_json = {
        "incident_analysis": "Flooding reported.",
        "evidence_and_freshness": "Recent",
        "risk_assessment": "MODERATE",
        "suggested_team_id": "TEAM-PHANTOM-99",  # Hallucinated ID
        "suggested_facility_id": "FAC-IMAGINARY-7",  # Hallucinated ID
        "recommended_actions": ["Dispatch phantom team"],
        "requires_approval": False,
        "approval_rationale": "Moderate risk"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(hallucinated_json)}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = asyncio.run(
            ollama_supervisor_service.run_supervisor_reasoning(
                incident=None,
                target_lat=12.9716,
                target_lon=77.5946,
                target_title="Hallucination Test",
                target_area="Majestic",
                people_count=2,
                task_type="TRIAGE",
                instruction="Test ID validation",
                available_teams=available_teams,
                candidate_facilities=candidate_facs,
                nearest_gauge=None,
                gauge_dist_km=10.0,
            )
        )

        # Hallucinated IDs must be rejected
        assert result.validated_team_id != "TEAM-PHANTOM-99"
        assert result.validated_facility_id != "FAC-IMAGINARY-7"
        assert result.validated_team_id in [t.id for t in available_teams]
        assert any("REJECTED hallucinated/invalid team ID 'TEAM-PHANTOM-99'" in note for note in result.validation_notes)
        assert any("REJECTED hallucinated/invalid facility ID 'FAC-IMAGINARY-7'" in note for note in result.validation_notes)


def test_no_incident_scenario_mock(db_session):
    """Test prospective area assessment without a pre-registered incident."""
    mock_llm_json = {
        "incident_analysis": "Prospective area assessment for Koramangala. No active trapped citizens reported.",
        "evidence_and_freshness": "General catchment risk observation.",
        "risk_assessment": "LOW",
        "suggested_team_id": None,
        "suggested_facility_id": None,
        "recommended_actions": ["Pre-stage drainage pumps near stormwater drain."],
        "requires_approval": False,
        "approval_rationale": "Area monitoring only"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(mock_llm_json)}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        req = SupervisorTaskRequest(
            task_type="SITUATION_REPORT",
            incident_id=None,
            area="Koramangala 4th Block",
            instruction="Prospective drainage risk review",
        )
        task_out = asyncio.run(execute_supervisor_triage(payload=req, db=db_session))

        assert task_out.id.startswith("TASK-")
        assert "Koramangala" in task_out.title
        assert "Affected: 0" in task_out.input_summary


def test_unauthorized_dispatch_prevention(db_session):
    """Test deterministic safety gate enforcement preventing unauthorized dispatch on high-risk incidents."""
    # Even if LLM claimed requires_approval = False, high affected count (12) must enforce approval
    mock_llm_json = {
        "incident_analysis": "Critical flood affecting 12 residents.",
        "evidence_and_freshness": "Live field report",
        "risk_assessment": "CRITICAL",
        "suggested_team_id": "TEAM-NDRF-10",
        "suggested_facility_id": "FAC-HOSP-01",
        "recommended_actions": ["Deploy water rescue squads"],
        "requires_approval": False,  # LLM erroneously attempts to bypass approval
        "approval_rationale": "None"
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(mock_llm_json)}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        req = SupervisorTaskRequest(
            task_type="RESCUE_DISPATCH",
            incident_id="INC-1042",
            instruction="Immediate squad dispatch authorization check",
        )
        task_out = asyncio.run(execute_supervisor_triage(payload=req, db=db_session))

        # Gatekeeper MUST override LLM output
        assert task_out.requires_human_approval is True
        assert task_out.status == "PENDING_APPROVAL"
        assert task_out.approved_by is None

        # Commander authorization workflow
        approved = approve_supervisor_task(task_id=task_out.id, db=db_session)
        assert approved.status == "APPROVED"
        assert approved.requires_human_approval is False
        assert "Human Commander Authorization" in approved.approved_by


def test_fastapi_endpoints_contract_mock(api_client):
    """Test full HTTP endpoints for supervisor health, roster, and triage with schema validation."""
    mock_llm_json = {
        "incident_analysis": "Yemalur overflow crossing ring road.",
        "evidence_and_freshness": "Verified sensor and field telemetry.",
        "risk_assessment": "HIGH",
        "suggested_team_id": "TEAM-KSFES-07",
        "suggested_facility_id": "FAC-SHELTER-02",
        "recommended_actions": ["Deploy perimeter boat patrol", "Reserve shelter intake"],
        "requires_approval": True,
        "approval_rationale": "Roadway inundation with active traffic."
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(mock_llm_json)}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        # 1. Health endpoint
        r_health = api_client.get("/api/agents/supervisor/health")
        assert r_health.status_code == 200
        assert "available" in r_health.json()

        # 2. Agents roster endpoint
        r_agents = api_client.get("/api/agents/")
        assert r_agents.status_code == 200
        agents_data = r_agents.json()
        assert "llm_supervisor" in agents_data
        assert agents_data["llm_supervisor"]["provider"] == "Ollama Local Inference"

        # 3. Triage execution endpoint
        r_triage = api_client.post(
            "/api/agents/supervisor/triage",
            json={
                "task_type": "TRIAGE",
                "incident_id": "INC-1041",
                "instruction": "Test HTTP triage pipeline",
            },
        )
        assert r_triage.status_code == 201
        data = r_triage.json()
        assert data["id"].startswith("TASK-")
        assert "findings" in data
        assert "recommendations" in data


# =====================================================================
# Separate Integration Test (Genuine Local Ollama Inference)
# =====================================================================

def test_real_local_ollama_integration(db_session):
    """
    Separate integration test executing genuine local Ollama reasoning.
    Skips cleanly if the local Ollama daemon is offline or inaccessible.
    """
    health = ollama_supervisor_service.check_health()
    if not health.get("available"):
        pytest.skip(f"Local Ollama daemon not reachable at {ollama_supervisor_service.base_url}: {health.get('error')}")

    incident = db_session.query(Incident).filter(Incident.id == "INC-1042").first()
    if not incident:
        pytest.skip("Fixture incident INC-1042 missing from database")

    available_teams = db_session.query(RescueTeam).filter(RescueTeam.status == "AVAILABLE").all()
    candidate_facs = db_session.query(Facility).filter(Facility.status == "OPERATIONAL").all()

    result = asyncio.run(
        ollama_supervisor_service.run_supervisor_reasoning(
            incident=incident,
            target_lat=incident.latitude,
            target_lon=incident.longitude,
            target_title=incident.title,
            target_area=incident.area,
            people_count=incident.people_affected,
            task_type="TRIAGE",
            instruction="Execute live integration triage with local Qwen model",
            available_teams=available_teams,
            candidate_facilities=candidate_facs,
            nearest_gauge={"station_name": "Ulsoor Lake Gauge", "river": "Dakshina Pinakini", "warning_level_m": 2.5, "danger_level_m": 4.0},
            gauge_dist_km=4.8,
        )
    )

    assert result.model_status == "ONLINE"
    assert result.inference_duration_s > 0
    assert isinstance(result.structured_output, OllamaSupervisorOutput)
    assert result.structured_output.risk_assessment in ["CRITICAL", "HIGH", "MODERATE", "LOW"]
    if available_teams:
        assert result.validated_team_id in [t.id for t in available_teams]
