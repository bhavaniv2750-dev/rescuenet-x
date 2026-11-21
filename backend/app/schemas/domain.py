import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ================= Incidents =================
_DEPTH_PATTERN = "(?i)^(ANKLE|KNEE|WAIST|CHEST_OR_DEEPER|UNKNOWN)$"


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=3, max_length=2000)
    area: str = Field(min_length=2, max_length=150)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    severity: str = Field(default="HIGH", pattern="^(CRITICAL|HIGH|MODERATE|LOW|critical|high|moderate|low)$")
    people_affected: int = Field(default=1, ge=1, le=100000)
    source: str = Field(default="CITIZEN_REPORT")
    incident_type: Optional[str] = "FLOODING"
    image_url: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None
    reported_water_depth: Optional[str] = Field(default=None, pattern=_DEPTH_PATTERN)

_STATUS_PATTERN = (
    "(?i)^(REPORTED|UNDER_VERIFICATION|VERIFIED|QUEUED|TRIAGE_IN_PROGRESS|PENDING_APPROVAL|DISPATCHED|"
    "IN_TRANSIT|ON_SCENE|RESOLVED|DUPLICATE|REJECTED|CANCELLED|ASSIGNED|IN_PROGRESS)$"
)


class IncidentStatusUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=_STATUS_PATTERN)
    assigned_team_id: Optional[str] = None
    severity: Optional[str] = None
    people_affected: Optional[int] = None
    image_url: Optional[str] = None

class IncidentOut(BaseModel):
    id: str
    title: str
    description: str
    area: str
    latitude: float
    longitude: float
    severity: str
    people_affected: int
    status: str
    source: str
    incident_type: Optional[str] = "FLOODING"
    image_url: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None
    device_battery_pct: Optional[int] = None
    mesh_hops: Optional[int] = None
    assigned_team_id: Optional[str] = None
    data_label: Optional[str] = "OBSERVED"
    beacon_id: Optional[str] = None
    location_method: Optional[str] = None
    verified_by: Optional[str] = None
    duplicate_of: Optional[str] = None
    reported_water_depth: Optional[str] = None
    photo_analysis: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("photo_analysis", mode="before")
    @classmethod
    def _parse_photo_analysis(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v


class IncidentStateChange(BaseModel):
    to_status: str = Field(pattern=_STATUS_PATTERN)
    actor: str = Field(default="operator", max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)
    duplicate_of: Optional[str] = None


class GatewayReading(BaseModel):
    gateway_id: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    rssi_dbm: float = Field(ge=-150.0, le=0.0)


class LoRaPacket(BaseModel):
    beacon_id: str = Field(min_length=2, max_length=50)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    hop_count: int = Field(default=1, ge=0, le=32)
    battery_pct: int = Field(ge=0, le=100)
    emergency_level: str = Field(default="HIGH", pattern="(?i)^(CRITICAL|HIGH|MODERATE|LOW)$")
    casualty_estimate: int = Field(default=1, ge=1, le=10000)
    area: Optional[str] = Field(default=None, max_length=150)
    gateway_readings: List[GatewayReading] = Field(default_factory=list)
    is_simulated: bool = True


class BeaconOut(BaseModel):
    beacon_id: str
    hotspot: str
    latitude: float
    longitude: float
    last_battery_pct: Optional[int] = None
    last_hops: Optional[int] = None
    last_seen: Optional[datetime] = None
    data_label: str

    model_config = ConfigDict(from_attributes=True)


class AuditOut(BaseModel):
    id: int
    actor: str
    role: str
    action: str
    target_type: str
    target_id: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================= Rescue Teams =================
class RescueTeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    callsign: str = Field(min_length=2, max_length=50)
    vehicle_type: str = Field(min_length=2, max_length=100)
    members_count: int = Field(default=4, ge=1, le=50)
    skills: str = Field(min_length=2, max_length=200)
    latitude: float
    longitude: float
    base_station: str
    contact_number: str

class RescueTeamOut(BaseModel):
    id: str
    name: str
    callsign: str
    status: str
    vehicle_type: str
    members_count: int
    skills: str
    latitude: float
    longitude: float
    base_station: str
    contact_number: str

    model_config = ConfigDict(from_attributes=True)


# ================= Volunteers =================
class VolunteerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=50)
    email: str = Field(min_length=5, max_length=100)
    skills: str = Field(min_length=2, max_length=200)
    area: str = Field(min_length=2, max_length=100)

class VolunteerOut(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    skills: str
    area: str
    is_verified: bool
    status: str
    registered_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================= Alerts =================
class AlertCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=5, max_length=2000)
    severity: str = Field(default="HIGH", pattern="^(CRITICAL|HIGH|WARNING|INFO|critical|high|warning|info)$")
    area: str = Field(min_length=2, max_length=150)
    latitude: float
    longitude: float
    radius_km: float = Field(default=3.0, ge=0.1, le=100.0)

class AlertOut(BaseModel):
    id: str
    title: str
    message: str
    severity: str
    area: str
    latitude: float
    longitude: float
    radius_km: float
    status: str
    delivery_channel: str
    acknowledged_count: int
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ================= Facilities =================
class FacilityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    facility_type: str = Field(min_length=2, max_length=50)
    address: str = Field(min_length=2, max_length=200)
    latitude: float
    longitude: float
    total_capacity: int = Field(default=100, ge=1)
    current_occupancy: int = Field(default=0, ge=0)
    contact: str

class FacilityOut(BaseModel):
    id: str
    name: str
    facility_type: str
    address: str
    latitude: float
    longitude: float
    total_capacity: int
    current_occupancy: int
    status: str
    contact: str
    distance_km: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ================= Rescue Records =================
class RescueRecordCreate(BaseModel):
    incident_id: str
    team_id: str
    location: str
    people_rescued: int = Field(default=0, ge=0)
    survivors: int = Field(default=0, ge=0)
    missing: int = Field(default=0, ge=0)
    deceased: int = Field(default=0, ge=0)
    severe_injuries: int = Field(default=0, ge=0)
    minor_injuries: int = Field(default=0, ge=0)
    notes: Optional[str] = ""

class RescueRecordOut(BaseModel):
    id: str
    incident_id: str
    team_id: str
    location: str
    people_rescued: int
    survivors: int
    missing: int
    deceased: int
    severe_injuries: int
    minor_injuries: int
    notes: Optional[str] = None
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================= Supervisor Tasks =================
class SupervisorTaskRequest(BaseModel):
    task_type: str = Field(default="TRIAGE")  # TRIAGE, RESCUE_DISPATCH, EVACUATION_ROUTE, SITUATION_REPORT
    incident_id: Optional[str] = None
    area: Optional[str] = None
    instruction: Optional[str] = None

class SupervisorTaskDecision(BaseModel):
    commander: str = Field(default="Human Commander Authorization (Console OP-01)", max_length=120)
    note: Optional[str] = Field(default=None, max_length=500)


class SupervisorTaskOut(BaseModel):
    id: str
    task_type: str
    title: str
    status: str
    agent_flow: str
    input_summary: str
    findings: str
    recommendations: str
    requires_human_approval: bool
    approved_by: Optional[str] = None
    incident_id: Optional[str] = None
    suggested_team_id: Optional[str] = None
    suggested_facility_id: Optional[str] = None
    decision_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================= Flood Forecasting & ML =================
class FloodScenarioInput(BaseModel):
    rainfall_mm: float = Field(ge=0.0, le=400.0, description="Hourly rainfall in mm")
    water_level_m: float = Field(ge=0.0, le=25.0, description="River/drainage water level in meters")
    humidity_pct: float = Field(default=80.0, ge=0.0, le=100.0, description="Relative humidity in percentage")
    temperature_c: float = Field(default=28.0, ge=-10.0, le=60.0, description="Ambient temperature in Celsius")

class ContributingFactor(BaseModel):
    factor: str
    impact: str
    weight: float

class FloodPredictionResult(BaseModel):
    risk_level: str  # LOW, MODERATE, HIGH, CRITICAL
    probability: float  # Calibrated probability 0.00 to 1.00
    horizon_30m: float
    horizon_45m: float
    horizon_60m: float
    confidence_level: str
    contributing_factors: List[ContributingFactor]
    model_name: str
    is_simulated: bool
    data_source: str
    evaluation_metrics: dict[str, Any]
    advisory: str
