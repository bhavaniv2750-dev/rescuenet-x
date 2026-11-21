from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from app.db.session import Base

def utc_now():
    return datetime.now(timezone.utc)

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    area = Column(String(150), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False, default="HIGH")  # CRITICAL, HIGH, MODERATE, LOW
    people_affected = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="REPORTED")  # see app.services.incident_lifecycle.STATES
    source = Column(String(50), nullable=False, default="CITIZEN_REPORT")  # CITIZEN_REPORT, MESH_SOS, SENSOR_TELEMETRY, OPERATOR
    device_battery_pct = Column(Integer, nullable=True)
    mesh_hops = Column(Integer, nullable=True)
    assigned_team_id = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)
    reporter_name = Column(String(100), nullable=True)
    reporter_contact = Column(String(50), nullable=True)
    incident_type = Column(String(50), nullable=True, default="FLOODING")
    # OBSERVED (real report), PREDICTED (model output) or SIMULATED (demo/test data)
    data_label = Column(String(20), nullable=False, default="OBSERVED")
    beacon_id = Column(String(50), nullable=True, index=True)
    location_method = Column(String(20), nullable=True)  # GPS, TRILATERATION, MANUAL
    verified_by = Column(String(100), nullable=True)
    duplicate_of = Column(String(50), nullable=True)
    # Depth as judged by the person reporting: ANKLE, KNEE, WAIST, CHEST_OR_DEEPER or UNKNOWN
    reported_water_depth = Column(String(20), nullable=True)
    # JSON summary of the photo analysis (PREDICTED), if a photo was analysed
    photo_analysis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class Beacon(Base):
    """Registry of LoRa distress beacons."""

    __tablename__ = "beacons"

    beacon_id = Column(String(50), primary_key=True, index=True)
    hotspot = Column(String(120), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    last_battery_pct = Column(Integer, nullable=True)
    last_hops = Column(Integer, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    data_label = Column(String(20), nullable=False, default="SIMULATED")


class AuditLog(Base):
    """Append-only record of consequential actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(100), nullable=False, default="system")
    role = Column(String(30), nullable=False, default="SYSTEM")
    action = Column(String(60), nullable=False, index=True)
    target_type = Column(String(40), nullable=False)
    target_id = Column(String(60), nullable=False, index=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, index=True)


class RescueTeam(Base):
    __tablename__ = "rescue_teams"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    callsign = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="AVAILABLE")  # AVAILABLE, DEPLOYED, STANDBY
    vehicle_type = Column(String(100), nullable=False)
    members_count = Column(Integer, nullable=False, default=4)
    skills = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    base_station = Column(String(100), nullable=False)
    contact_number = Column(String(50), nullable=False)


class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(100), nullable=False)
    skills = Column(String(200), nullable=False)
    area = Column(String(100), nullable=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="AVAILABLE")  # AVAILABLE, ASSIGNED, STANDBY
    registered_at = Column(DateTime, default=utc_now)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="HIGH")  # CRITICAL, HIGH, WARNING, INFO
    area = Column(String(150), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_km = Column(Float, nullable=False, default=3.0)
    status = Column(String(30), nullable=False, default="ACTIVE")  # ACTIVE, ACKNOWLEDGED, RESOLVED
    delivery_channel = Column(String(50), nullable=False, default="SIMULATED_CAP_ALERT")
    acknowledged_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now)
    resolved_at = Column(DateTime, nullable=True)


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    facility_type = Column(String(50), nullable=False)  # HOSPITAL, SHELTER, RELIEF_CAMP, RESCUE_HQ
    address = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    total_capacity = Column(Integer, nullable=False, default=100)
    current_occupancy = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="OPERATIONAL")  # OPERATIONAL, NEAR_CAPACITY, FULL
    contact = Column(String(50), nullable=False)


class RescueRecord(Base):
    __tablename__ = "rescue_records"

    id = Column(String(50), primary_key=True, index=True)
    incident_id = Column(String(50), nullable=False, index=True)
    team_id = Column(String(50), nullable=False)
    location = Column(String(150), nullable=False)
    people_rescued = Column(Integer, nullable=False, default=0)
    survivors = Column(Integer, nullable=False, default=0)
    missing = Column(Integer, nullable=False, default=0)
    deceased = Column(Integer, nullable=False, default=0)
    severe_injuries = Column(Integer, nullable=False, default=0)
    minor_injuries = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, default=utc_now)


class SupervisorTask(Base):
    __tablename__ = "supervisor_tasks"

    id = Column(String(50), primary_key=True, index=True)
    task_type = Column(String(50), nullable=False)  # TRIAGE, RESCUE_DISPATCH, EVACUATION_ROUTE, SITUATION_REPORT
    title = Column(String(150), nullable=False)
    status = Column(String(30), nullable=False, default="COMPLETED")  # COMPLETED, PENDING_APPROVAL, EXECUTING, FAILED
    agent_flow = Column(String(250), nullable=False)
    input_summary = Column(Text, nullable=False)
    findings = Column(Text, nullable=False)
    recommendations = Column(Text, nullable=False)
    requires_human_approval = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(100), nullable=True)
    incident_id = Column(String(50), nullable=True, index=True)
    suggested_team_id = Column(String(50), nullable=True)
    suggested_facility_id = Column(String(50), nullable=True)
    decision_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class DatasetRegistry(Base):
    __tablename__ = "dataset_registry"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    category = Column(String(50), nullable=False)
    records_count = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="READY")
    coverage = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    last_synced = Column(DateTime, default=utc_now)
