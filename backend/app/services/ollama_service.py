import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.geo_service import geo_service

logger = logging.getLogger("rescuenet.ollama")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two geographic coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


class OllamaSupervisorOutput(BaseModel):
    """Structured reasoning output expected from the local Ollama LLM."""
    incident_analysis: str = Field(description="Tactical analysis of the situation based strictly on verified facts")
    evidence_and_freshness: str = Field(description="Assessment of data freshness, source reliability, and telemetry state")
    risk_assessment: str = Field(description="Assessed risk level: CRITICAL, HIGH, MODERATE, or LOW")
    suggested_team_id: Optional[str] = Field(default=None, description="Exact ID of the suggested rescue team from candidate list")
    suggested_facility_id: Optional[str] = Field(default=None, description="Exact ID of the suggested facility from candidate list")
    recommended_actions: List[str] = Field(default_factory=list, description="Ordered tactical steps for responders")
    requires_approval: bool = Field(default=True, description="Whether human commander authorization is required")
    approval_rationale: str = Field(default="", description="Safety rationale for approval requirement")


class SupervisorInferenceResult(BaseModel):
    """Combined output containing advisory reasoning, validated entities, and execution metadata."""
    model_name: str
    model_status: str  # ONLINE, OFFLINE, TIMEOUT, PARSE_FALLBACK
    inference_duration_s: float
    raw_response: Optional[str] = None
    structured_output: OllamaSupervisorOutput
    validated_team_id: Optional[str] = None
    validated_team_name: Optional[str] = None
    validated_facility_id: Optional[str] = None
    validated_facility_name: Optional[str] = None
    validation_notes: List[str] = Field(default_factory=list)
    enforced_requires_approval: bool
    findings_formatted: str
    recommendations_formatted: str


class OllamaSupervisorService:
    """
    Local-first LLM Supervisor Service powered by Ollama (Qwen 4B Instruct).
    Acts as an advisory reasoning component with strict deterministic safety bounds.
    """

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    def check_health(self) -> Dict[str, Any]:
        """Verify Ollama server connectivity and model availability."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    model_found = any(self.model in m for m in models)
                    return {
                        "available": True,
                        "model": self.model,
                        "model_installed": model_found,
                        "installed_models": models,
                        "base_url": self.base_url,
                    }
                return {
                    "available": False,
                    "model": self.model,
                    "model_installed": False,
                    "error": f"Ollama HTTP {res.status_code}",
                    "base_url": self.base_url,
                }
        except Exception as e:
            return {
                "available": False,
                "model": self.model,
                "model_installed": False,
                "error": str(e),
                "base_url": self.base_url,
            }

    def _build_context(
        self,
        incident: Optional[Any],
        target_lat: float,
        target_lon: float,
        target_title: str,
        target_area: str,
        people_count: int,
        task_type: str,
        instruction: Optional[str],
        available_teams: List[Any],
        candidate_facilities: List[Any],
        nearest_gauge: Optional[Dict[str, Any]],
        gauge_dist_km: float,
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Construct prompt context using real persisted records without synthetic sensor injection."""
        
        # Build team lookup map and descriptions
        teams_map = {}
        teams_desc_lines = []
        for t in available_teams:
            dist = haversine_km(target_lat, target_lon, t.latitude, t.longitude)
            teams_map[t.id] = t
            teams_desc_lines.append(
                f"- ID: {t.id} | Name: '{t.name}' | Vehicle: {t.vehicle_type} | Skills: {t.skills} | Distance: {dist:.1f} km | Status: {t.status}"
            )
        teams_context = "\n".join(teams_desc_lines) if teams_desc_lines else "None currently AVAILABLE."

        # Build facility lookup map and descriptions
        facilities_map = {}
        fac_desc_lines = []
        for f in candidate_facilities:
            dist = haversine_km(target_lat, target_lon, f.latitude, f.longitude)
            open_beds = max(0, f.total_capacity - f.current_occupancy)
            facilities_map[f.id] = f
            fac_desc_lines.append(
                f"- ID: {f.id} | Name: '{f.name}' | Type: {f.facility_type} | Distance: {dist:.1f} km | Open Beds: {open_beds} (Capacity: {f.total_capacity})"
            )
        facilities_context = "\n".join(fac_desc_lines) if fac_desc_lines else "No operational facilities found."

        # Build gauge context
        if nearest_gauge:
            gauge_context = (
                f"Nearest IndoFloods Gauge Station: '{nearest_gauge.get('station_name')}' on river '{nearest_gauge.get('river')}' "
                f"({gauge_dist_km:.1f} km away). Warning Level: {nearest_gauge.get('warning_level_m')}m, "
                f"Danger Level: {nearest_gauge.get('danger_level_m')}m. [Live Telemetry: No unverified rainfall/water-level sensor readings bound to incident]."
            )
        else:
            gauge_context = "Geospatial Catchments: No immediate river gauge within 100km. [Live Telemetry: Telemetry sensor not attached]."

        # Build incident context
        if incident:
            created_str = (
                incident.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if getattr(incident, "created_at", None)
                else "Unknown"
            )
            incident_context = (
                f"INCIDENT RECORD (Verified Persisted Entity):\n"
                f"- Incident ID: {incident.id}\n"
                f"- Title: {incident.title}\n"
                f"- Area: {incident.area}\n"
                f"- Coordinates: Latitude {target_lat:.4f}, Longitude {target_lon:.4f}\n"
                f"- Reported Trapped / Affected People: {people_count}\n"
                f"- Incident Severity: {incident.severity}\n"
                f"- Reporting Source: {incident.source}\n"
                f"- Current Status: {incident.status}\n"
                f"- Description: {incident.description}\n"
                f"- Reported At: {created_str}\n"
            )
        else:
            incident_context = (
                f"PROSPECTIVE ASSESSMENT (No specific incident record selected):\n"
                f"- Target Area: {target_area}\n"
                f"- Reference Coordinates: Latitude {target_lat:.4f}, Longitude {target_lon:.4f}\n"
                f"- Affected People: 0 reported\n"
                f"- Context: Area monitoring and general preparedness review.\n"
            )

        prompt = (
            f"You are the RescueNet X 2.0 Autonomous Multi-Agent Supervisor reasoning engine for emergency flood management in Karnataka / Bengaluru.\n"
            f"Analyze the following verified emergency context and return a structured JSON response.\n\n"
            f"### CRITICAL OPERATIONAL RULES:\n"
            f"1. You MUST ONLY suggest rescue teams and facilities from the verified lists below. NEVER invent or hallucinate Team IDs or Facility IDs. If none are appropriate, output null.\n"
            f"2. NEVER invent sensor readings, rainfall data, river levels, or claim completed field actions.\n"
            f"3. Strict Safety Gatekeeper Rule: If 5 or more people are affected or severity is CRITICAL or HIGH, require_approval MUST be true.\n"
            f"4. Return STRICT valid JSON only. Do not enclose in markdown ticks if possible, or output a single JSON object.\n\n"
            f"### CONTEXT DATA:\n"
            f"{incident_context}\n"
            f"GEOSPATIAL & TELEMETRY:\n{gauge_context}\n\n"
            f"AVAILABLE RESCUE SQUADS:\n{teams_context}\n\n"
            f"CANDIDATE FACILITIES & SHELTERS:\n{facilities_context}\n\n"
            f"MISSION DIRECTIVE:\n"
            f"- Task Type: {task_type}\n"
            f"- Specific Instructions: {instruction or 'Perform full tactical triage and resource recommendation.'}\n\n"
            f"### REQUIRED JSON FORMAT:\n"
            f"{{\n"
            f'  "incident_analysis": "<concise tactical analysis of the situation based solely on facts>",\n'
            f'  "evidence_and_freshness": "<evaluation of evidence, timestamp freshness, and telemetry note>",\n'
            f'  "risk_assessment": "<CRITICAL | HIGH | MODERATE | LOW>",\n'
            f'  "suggested_team_id": "<exact ID from available squads list or null>",\n'
            f'  "suggested_facility_id": "<exact ID from candidate facilities list or null>",\n'
            f'  "recommended_actions": [\n'
            f'    "<action 1: specific dispatch/positioning instruction>",\n'
            f'    "<action 2: facility staging instruction>",\n'
            f'    "<action 3: warning broadcast or precaution>"\n'
            f"  ],\n"
            f'  "requires_approval": <true | false>,\n'
            f'  "approval_rationale": "<reason commander approval is required or not>"\n'
            f"}}\n"
        )

        return prompt, teams_map, facilities_map

    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Robustly extract JSON object from text, handling potential LLM markdown fencing."""
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback regex search for outer-most json braces
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise

    async def run_supervisor_reasoning(
        self,
        incident: Optional[Any],
        target_lat: float,
        target_lon: float,
        target_title: str,
        target_area: str,
        people_count: int,
        task_type: str,
        instruction: Optional[str],
        available_teams: List[Any],
        candidate_facilities: List[Any],
        nearest_gauge: Optional[Dict[str, Any]],
        gauge_dist_km: float,
    ) -> SupervisorInferenceResult:
        """
        Execute advisory reasoning via local Ollama instance with timeout and deterministic fallback.
        """
        prompt, teams_map, facilities_map = self._build_context(
            incident=incident,
            target_lat=target_lat,
            target_lon=target_lon,
            target_title=target_title,
            target_area=target_area,
            people_count=people_count,
            task_type=task_type,
            instruction=instruction,
            available_teams=available_teams,
            candidate_facilities=candidate_facilities,
            nearest_gauge=nearest_gauge,
            gauge_dist_km=gauge_dist_km,
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "num_predict": 512,
            },
        }

        t_start = time.time()
        model_status = "ONLINE"
        raw_resp = ""
        structured: Optional[OllamaSupervisorOutput] = None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw_resp = data.get("response", "")
                    parsed_dict = self._extract_json_from_text(raw_resp)
                    structured = OllamaSupervisorOutput.model_validate(parsed_dict)
                else:
                    model_status = f"HTTP_{res.status_code}"
                    logger.warning(f"Ollama returned HTTP {res.status_code}")
        except httpx.TimeoutException:
            model_status = "TIMEOUT"
            logger.warning(f"Ollama request timed out after {self.timeout}s")
        except Exception as e:
            model_status = "OFFLINE"
            logger.warning(f"Ollama inference failed: {e}")

        duration = round(time.time() - t_start, 2)

        # Fallback if Ollama failed or output invalid
        if not structured:
            risk = "CRITICAL" if people_count >= 8 else "HIGH" if people_count >= 4 else "MODERATE" if people_count >= 1 else "LOW"
            structured = OllamaSupervisorOutput(
                incident_analysis=(
                    f"Deterministic safety evaluation: Incident in {target_area} affecting {people_count} people. "
                    f"Local Ollama Qwen 4B supervisor is currently {model_status}."
                ),
                evidence_and_freshness=(
                    f"Persisted database record. Nearest river gauge is {nearest_gauge.get('station_name') if nearest_gauge else 'N/A'} "
                    f"at {gauge_dist_km:.1f} km. Real-time telemetry not attached."
                ),
                risk_assessment=risk,
                suggested_team_id=available_teams[0].id if available_teams else None,
                suggested_facility_id=candidate_facilities[0].id if candidate_facilities else None,
                recommended_actions=[
                    f"Dispatch nearest available water rescue unit to ({target_lat:.4f}, {target_lon:.4f}).",
                    "Alert receiving emergency facility for incoming intake.",
                    "Verify on-ground flood depth via field responders before broadcast.",
                ],
                requires_approval=people_count >= 5 or risk in ["CRITICAL", "HIGH"],
                approval_rationale="Safety gatekeeper policy enforced due to offline/timeout fallback.",
            )

        # -------------------------------------------------------------
        # Step 4: Strict Deterministic Validation of LLM-suggested IDs
        # -------------------------------------------------------------
        validation_notes = []
        validated_team_id = None
        validated_team_name = None

        if structured.suggested_team_id and structured.suggested_team_id in teams_map:
            validated_team_id = structured.suggested_team_id
            validated_team_name = teams_map[validated_team_id].name
            validation_notes.append(f"Team ID '{validated_team_id}' verified as AVAILABLE in database.")
        else:
            # LLM hallucinated, suggested an invalid ID, or none suggested
            if structured.suggested_team_id:
                validation_notes.append(
                    f"REJECTED hallucinated/invalid team ID '{structured.suggested_team_id}'."
                )
            if available_teams:
                # Deterministically bind the geographically closest available team
                closest_team = min(
                    available_teams,
                    key=lambda t: haversine_km(target_lat, target_lon, t.latitude, t.longitude),
                )
                validated_team_id = closest_team.id
                validated_team_name = closest_team.name
                validation_notes.append(
                    f"Deterministically assigned closest available team '{closest_team.name}' ({closest_team.id})."
                )
            else:
                validation_notes.append("No response teams currently AVAILABLE in database.")

        validated_facility_id = None
        validated_facility_name = None
        if structured.suggested_facility_id and structured.suggested_facility_id in facilities_map:
            validated_facility_id = structured.suggested_facility_id
            validated_facility_name = facilities_map[validated_facility_id].name
            validation_notes.append(f"Facility ID '{validated_facility_id}' verified as OPERATIONAL in database.")
        else:
            if structured.suggested_facility_id:
                validation_notes.append(
                    f"REJECTED hallucinated/invalid facility ID '{structured.suggested_facility_id}'."
                )
            if candidate_facilities:
                # Deterministically bind closest operational facility with capacity
                closest_fac = min(
                    candidate_facilities,
                    key=lambda f: haversine_km(target_lat, target_lon, f.latitude, f.longitude),
                )
                validated_facility_id = closest_fac.id
                validated_facility_name = closest_fac.name
                validation_notes.append(
                    f"Deterministically assigned nearest operational facility '{closest_fac.name}' ({closest_fac.id})."
                )

        # -------------------------------------------------------------
        # Deterministic Safety Gatekeeper Enforcement
        # -------------------------------------------------------------
        # Mandatory policy: Human authorization required for high-risk, large-casualty, or dispatch/alert tasks
        policy_triggers = (
            people_count >= 5
            or structured.risk_assessment.upper() in ["CRITICAL", "HIGH"]
            or (incident and incident.severity.upper() in ["CRITICAL", "HIGH"])
            or task_type.upper() in ["RESCUE_DISPATCH", "ALERT_ASSESSMENT"]
        )
        enforced_requires_approval = bool(policy_triggers or structured.requires_approval)

        # Build clean, comprehensive findings and recommendations
        gauge_info = (
            f"Nearest River Gauge: {nearest_gauge['station_name']} ({nearest_gauge['river']}) at {gauge_dist_km:.1f} km."
            if nearest_gauge else "No river gauge within 100km."
        )

        model_note = f"Local Ollama Qwen 4B Instruct ({self.model}) — inference {duration:.2f}s [Status: {model_status}]"

        findings_formatted = (
            f"[1] Incident Analysis: {structured.incident_analysis}\n"
            f"[2] Evidence & Data Freshness: {structured.evidence_and_freshness} | {gauge_info} [Real-time sensor telemetry: No unverified readings injected].\n"
            f"[3] Risk Assessment: {structured.risk_assessment.upper()} (Affected People: {people_count}).\n"
            f"[4] AI Engine: {model_note}."
        )

        actions_str = "\n".join(f"   • {act}" for act in structured.recommended_actions) if structured.recommended_actions else "   • Dispatch squad to scene."
        validation_str = " | ".join(validation_notes)

        recommendations_formatted = (
            f"[1] Recommended Squad: {validated_team_name or 'None'} ({validated_team_id or 'N/A'})\n"
            f"[2] Evacuation Facility: {validated_facility_name or 'None'} ({validated_facility_id or 'N/A'})\n"
            f"[3] Tactical Action Plan:\n{actions_str}\n"
            f"[4] DB Verification: {validation_str}\n"
            f"[5] Safety Policy: {'MANDATORY HUMAN AUTHORIZATION REQUIRED before dispatch/alert broadcast.' if enforced_requires_approval else 'Automated tactical assignment approved.'}"
        )

        return SupervisorInferenceResult(
            model_name=self.model,
            model_status=model_status,
            inference_duration_s=duration,
            raw_response=raw_resp,
            structured_output=structured,
            validated_team_id=validated_team_id,
            validated_team_name=validated_team_name,
            validated_facility_id=validated_facility_id,
            validated_facility_name=validated_facility_name,
            validation_notes=validation_notes,
            enforced_requires_approval=enforced_requires_approval,
            findings_formatted=findings_formatted,
            recommendations_formatted=recommendations_formatted,
        )


ollama_supervisor_service = OllamaSupervisorService()

