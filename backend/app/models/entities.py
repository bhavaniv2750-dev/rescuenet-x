from datetime import datetime, timezone
from sqlalchemy import (
    event,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
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
    reporter_user_id = Column(Integer, nullable=True, index=True)  # set when a logged-in user reports
    # The risk assessment as first recorded. Never edited afterwards: the commander-approval rule uses the
    # higher of these and the current values, so lowering severity or headcount cannot lift the gate.
    reported_severity = Column(String(20), nullable=True)
    reported_people_affected = Column(Integer, nullable=True)
    # Set only when a commander or administrator authorised a lower assessment (with a written reason).
    risk_downgraded_by = Column(String(100), nullable=True)
    risk_downgrade_note = Column(Text, nullable=True)
    # JSON summary of the photo analysis (PREDICTED), if a photo was analysed
    photo_analysis = Column(Text, nullable=True)
    # What a reporter is given to follow their report: a random reference (not secret) and a secret tracking code
    # whose SHA-256 is stored here. Internal ids are never shown to the public.
    public_ref = Column(String(20), nullable=True, unique=True, index=True)
    tracking_code_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class MediaAsset(Base):
    """An evidence photograph. The file is private: it is only served after an access check (services/media.py)."""
    __tablename__ = "media_assets"

    id = Column(String(32), primary_key=True)             # random 128-bit value, also the stored file's name
    incident_id = Column(String(50), nullable=True, index=True)  # empty until attached to a report
    stored_name = Column(String(80), nullable=False)
    content_type = Column(String(50), nullable=False, default="image/jpeg")
    size_bytes = Column(Integer, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=False)
    uploader_user_id = Column(Integer, nullable=True)
    uploader_hash = Column(String(32), nullable=True, index=True)  # keyed hash of the client address, never the address
    privacy = Column(String(20), nullable=False, default="PRIVATE")
    legacy_source = Column(String(200), nullable=True)    # original file name for photos imported from the old route
    created_at = Column(DateTime, default=utc_now)


@event.listens_for(Incident, "before_insert")
def _record_original_risk(mapper, connection, target):
    """Freeze the first assessment on every creation path (API, LoRa, seed data)."""
    if target.reported_severity is None:
        target.reported_severity = (target.severity or "HIGH").upper()
    if target.reported_people_affected is None:
        target.reported_people_affected = target.people_affected if target.people_affected is not None else 1


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
    assigned_incident_id = Column(String(50), nullable=True, index=True)
    verified_by = Column(String(100), nullable=True)
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
    status = Column(String(30), nullable=False, default="ACTIVE")  # ACTIVE (not yet seen by a commander), ACKNOWLEDGED (in force), RESOLVED
    delivery_channel = Column(String(50), nullable=False, default="IN_APP")
    # Number of people who tapped "seen". It does not change the alert's status.
    acknowledged_count = Column(Integer, nullable=False, default=0)
    # Set when a commander or administrator acknowledges the alert; stops escalation.
    acknowledged_by = Column(String(100), nullable=True)
    escalation_level = Column(Integer, nullable=False, default=0)
    escalated_at = Column(DateTime, nullable=True)
    # OBSERVED (issued by staff) or SIMULATED (sample data shipped with the project)
    data_label = Column(String(20), nullable=False, default="SIMULATED")
    created_at = Column(DateTime, default=utc_now)
    resolved_at = Column(DateTime, nullable=True)


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    facility_type = Column(String(50), nullable=False)  # see app.services.facilities.FACILITY_TYPES
    address = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    total_capacity = Column(Integer, nullable=False, default=100)
    current_occupancy = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="OPERATIONAL")  # OPERATIONAL, NEAR_CAPACITY, FULL
    contact = Column(String(50), nullable=False)
    # OBSERVED (entered by staff), SIMULATED (sample data shipped with the project)
    data_label = Column(String(20), nullable=False, default="SIMULATED")


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


class User(Base):
    """Login account. Role decides which portal the user signs in through and what they may do."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(60), nullable=False, unique=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=True)
    phone = Column(String(30), nullable=True)
    # ADMIN | COMMANDER | OPERATOR | RESCUE_OFFICER | VOLUNTEER | CITIZEN
    role = Column(String(20), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    team_id = Column(String(50), nullable=True)        # rescue officers: their team
    volunteer_id = Column(String(50), nullable=True)   # volunteers: their volunteer record
    is_active = Column(Boolean, nullable=False, default=True)
    failed_logins = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    # Bumped whenever the account's access must end everywhere (password change, deactivation, role/team change).
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    password_changed_at = Column(DateTime, nullable=True)
    # Contact verification (a code was entered correctly; never set merely because a code was sent)
    email_verified_at = Column(DateTime, nullable=True)
    phone_verified_at = Column(DateTime, nullable=True)
    email_changed_at = Column(DateTime, nullable=True)
    # Set by host-level recovery and admin resets of public accounts: only the password-change endpoints work until cleared
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, default=utc_now)


class AuthSession(Base):
    """One sign-in. Server-side so it can be listed and revoked. Holds no secrets: refresh tokens are in RefreshToken
    (hashed) and the client address is stored only as a keyed hash."""
    __tablename__ = "auth_sessions"

    id = Column(String(32), primary_key=True)             # random; also the `sid` claim in access tokens
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    last_used_at = Column(DateTime, nullable=False, default=utc_now)
    # Authentication assurance: PASSWORD (password only) or MFA (a second factor was completed in THIS session). A refresh
    # keeps the session, so it can never upgrade assurance. mfa_at is the last time a second factor was proven (freshness).
    assurance = Column(String(10), nullable=False, default="PASSWORD", server_default="PASSWORD")
    mfa_at = Column(DateTime, nullable=True)
    mfa_method = Column(String(10), nullable=True)   # TOTP | RECOVERY
    expires_at = Column(DateTime, nullable=False)          # absolute limit
    idle_timeout_s = Column(Integer, nullable=False)       # no refresh within this many seconds ends the session
    remember = Column(Boolean, nullable=False, default=False)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoked_reason = Column(String(40), nullable=True)
    user_agent = Column(String(200), nullable=True)
    client_hash = Column(String(32), nullable=True)


class RefreshToken(Base):
    """One refresh token of a session. Only the SHA-256 of the random token is stored. A token is used exactly once;
    presenting a used one again is treated as theft and revokes the whole session."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class OneTimeToken(Base):
    """A verification code or password-reset token. Only a hash is stored (HMAC for short numeric codes, SHA-256 for long
    random reset tokens). Single use, short lived, with an attempt counter."""
    __tablename__ = "one_time_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    purpose = Column(String(20), nullable=False)       # EMAIL_VERIFY | PHONE_VERIFY | PASSWORD_RESET
    target = Column(String(160), nullable=True)        # the address/number a verification code was issued for
    token_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)


class NotificationOutbox(Base):
    """Record of a notification handed to a transport, with an honest delivery status. The message body (which holds the
    code or link) is stored ONLY for the development outbox and is never exposed outside development."""
    __tablename__ = "notification_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    channel = Column(String(10), nullable=False)        # EMAIL | SMS
    purpose = Column(String(30), nullable=False)
    recipient_masked = Column(String(120), nullable=False)
    transport = Column(String(20), nullable=False)      # DEV_OUTBOX | SMTP | DISABLED
    # NOT_DELIVERED_DEV (stored in the dev outbox only) | ACCEPTED_BY_SMTP (server accepted it; inbox delivery unknown)
    # | FAILED | DISABLED (no transport configured). Nothing here ever means "delivered to the person".
    delivery_status = Column(String(20), nullable=False)
    detail = Column(String(200), nullable=True)
    subject = Column(String(160), nullable=True)
    body = Column(Text, nullable=True)                  # development outbox only
    created_at = Column(DateTime, nullable=False, default=utc_now)


class RateLimitEvent(Base):
    """One counted event for the shared, persistent rate limiter (works across workers that share the database)."""
    __tablename__ = "rate_limit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bucket = Column(String(40), nullable=False)
    key_hash = Column(String(32), nullable=False)       # keyed hash of the address/identifier, never the raw value
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (Index("ix_rate_limit_lookup", "bucket", "key_hash", "created_at"),)


class MfaCredential(Base):
    """A user's TOTP credential. The shared secret is stored only as authenticated ciphertext (AES-256-GCM, key from the
    environment, bound to the user id). PENDING until the user proves possession with a correct code (confirmation)."""
    __tablename__ = "mfa_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    secret_enc = Column(Text, nullable=False)
    status = Column(String(10), nullable=False, default="PENDING")   # PENDING | ACTIVE
    created_at = Column(DateTime, nullable=False, default=utc_now)
    confirmed_at = Column(DateTime, nullable=True)
    last_used_step = Column(Integer, nullable=True)                  # newest accepted 30 s step: replay prevention


class MfaRecoveryCode(Base):
    """One single-use backup code. Only an HMAC of the code is stored."""
    __tablename__ = "mfa_recovery_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    used_at = Column(DateTime, nullable=True)


class AuthChallenge(Base):
    """Short-lived, purpose-restricted proof that the PASSWORD step succeeded and a second factor is still owed. It is not a
    session and not an access token: it works only at /auth/mfa/verify, once, within minutes, with a few attempts."""
    __tablename__ = "auth_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    purpose = Column(String(20), nullable=False)        # MFA_LOGIN
    user_id = Column(Integer, nullable=False, index=True)
    remember = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
