import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    # "development" or "production". Anything else is refused at start-up. Production is the safe default:
    # later security milestones use this flag to switch off demo accounts and development-only helpers.
    RESCUENET_ENV: str = os.getenv("RESCUENET_ENV", "production").strip().lower()
    PROJECT_NAME: str = "Flood Digital Twin + RescueNet X 2.0"
    API_V1_STR: str = "/api"
    DEBUG: bool = True
    
    # CORS: Allow standard local Vite ports and loopback addresses
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/backend/rescuenet.db")
    
    # Dataset Directories
    WORKSPACE_ROOT: Path = BASE_DIR
    CLEAN_DATASET_DIR: Path = BASE_DIR / "flood pred detc rescue net clean dataset"
    SHAPEFILES_DIR: Path = BASE_DIR / "catchments_shapefiles_indofloods imag" / "catchments_shapefiles_indofloods"
    FLOOD_PRED_DIR: Path = BASE_DIR / "Flood Prediction Dataset"
    FLOOD_IMG_DIR: Path = BASE_DIR / "flood"
    
    # ML Models directory
    MODELS_DIR: Path = BASE_DIR / "backend" / "app" / "ml" / "artifacts"

    # Where database backups are written (taken automatically before any schema migration of an existing database).
    BACKUP_DIR: Path = Path(os.getenv("BACKUP_DIR") or str(BASE_DIR / "backend" / "backups"))

    # Uploads directory for incident attachments
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR") or str(BASE_DIR / "backend" / "uploads"))

    # ---- Public reporting and evidence photos (S0)
    MAX_IMAGE_BYTES: int = 5 * 1024 * 1024          # per uploaded image, checked before any decoding
    MAX_IMAGES_PER_REPORT: int = 5
    MAX_IMAGE_PIXELS: int = 25_000_000              # decoded size limit (decompression-bomb guard)
    IMAGE_MAX_SIDE_PX: int = 2048                   # stored images are downscaled to this
    UPLOAD_QUOTA_MB: int = int(os.getenv("UPLOAD_QUOTA_MB", "2048"))              # total evidence storage
    GUEST_UPLOAD_MB_PER_DAY: int = int(os.getenv("GUEST_UPLOAD_MB_PER_DAY", "50"))  # per client address
    MAX_UNATTACHED_UPLOADS_PER_CLIENT: int = 10     # uploads not yet attached to a report
    UNATTACHED_UPLOAD_TTL_MINUTES: int = 60         # window in which an uploaded photo can be attached to a report
    GUEST_REPORTS_PER_HOUR: int = int(os.getenv("GUEST_REPORTS_PER_HOUR", "10"))   # per client address
    GUEST_UPLOADS_PER_HOUR: int = int(os.getenv("GUEST_UPLOADS_PER_HOUR", "25"))
    USER_REPORTS_PER_HOUR: int = int(os.getenv("USER_REPORTS_PER_HOUR", "60"))      # per signed-in user
    TRACKING_LOOKUPS_PER_HOUR: int = int(os.getenv("TRACKING_LOOKUPS_PER_HOUR", "60"))
    TRACKING_FAILURES_PER_15_MIN: int = int(os.getenv("TRACKING_FAILURES_PER_15_MIN", "10"))
    RATE_LIMITS_ENABLED: bool = os.getenv("RATE_LIMITS_ENABLED", "true").lower() in ("1", "true", "yes")
    # Number of reverse proxies in front of the app. 0 = use the socket address and ignore X-Forwarded-For,
    # which a client could forge. Set to 1 behind one trusted proxy.
    TRUSTED_PROXY_COUNT: int = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

    # ---- Contact verification, password recovery, notifications, rate limits (S3)
    PUBLIC_APP_URL: str = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5175")   # base of links in emails (reset link)
    VERIFY_CODE_MINUTES: int = int(os.getenv("VERIFY_CODE_MINUTES", "10"))
    VERIFY_MAX_ATTEMPTS: int = int(os.getenv("VERIFY_MAX_ATTEMPTS", "5"))          # wrong codes before a code is void
    VERIFY_RESEND_COOLDOWN_S: int = int(os.getenv("VERIFY_RESEND_COOLDOWN_S", "60"))
    RESET_TOKEN_MINUTES: int = int(os.getenv("RESET_TOKEN_MINUTES", "30"))
    STAFF_RESET_COOLDOWN_HOURS: int = int(os.getenv("STAFF_RESET_COOLDOWN_HOURS", "24"))   # staff: no email reset soon after the email changed
    # SMTP for real email delivery. Without SMTP_HOST, development uses the labelled dev outbox (nothing is delivered)
    # and production delivers nothing. The password comes from the environment only.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")
    SMTP_STARTTLS: bool = os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes")
    SMTP_TIMEOUT_S: float = float(os.getenv("SMTP_TIMEOUT_S", "10"))
    # Rate limits (events per window, per client address unless stated). Counted in the shared database store.
    LOGIN_PER_IP_15MIN: int = int(os.getenv("LOGIN_PER_IP_15MIN", "30"))
    LOGIN_PER_ACCOUNT_15MIN: int = int(os.getenv("LOGIN_PER_ACCOUNT_15MIN", "5"))   # per supplied username/email (failures)
    REGISTER_PER_IP_HOUR: int = int(os.getenv("REGISTER_PER_IP_HOUR", "10"))
    VERIFY_SEND_PER_ACCOUNT_HOUR: int = int(os.getenv("VERIFY_SEND_PER_ACCOUNT_HOUR", "5"))
    VERIFY_CONFIRM_PER_ACCOUNT_HOUR: int = int(os.getenv("VERIFY_CONFIRM_PER_ACCOUNT_HOUR", "15"))
    FORGOT_PER_IP_HOUR: int = int(os.getenv("FORGOT_PER_IP_HOUR", "5"))
    FORGOT_PER_IDENTIFIER_HOUR: int = int(os.getenv("FORGOT_PER_IDENTIFIER_HOUR", "3"))
    RESET_PER_IP_HOUR: int = int(os.getenv("RESET_PER_IP_HOUR", "10"))

    # ---- Multi-factor authentication (S4)
    # Authenticated-encryption keys for TOTP secrets at rest. "kid:base64url-32-bytes[,kid2:...]": the FIRST key encrypts, all
    # listed keys can decrypt (rotation). A single MFA_ENCRYPTION_KEY=<base64url-32-bytes> is also accepted. REQUIRED in
    # production (start-up refuses otherwise); never stored in the database. Generate: python scripts/mfa_keys.py generate
    MFA_ENCRYPTION_KEYS: str = os.getenv("MFA_ENCRYPTION_KEYS", "") or os.getenv("MFA_ENCRYPTION_KEY", "")
    MFA_ISSUER: str = os.getenv("MFA_ISSUER", "RescueNet X")
    MFA_DRIFT_STEPS: int = int(os.getenv("MFA_DRIFT_STEPS", "1"))                      # accept +/- this many 30 s steps (max 1)
    MFA_CHALLENGE_SECONDS: int = int(os.getenv("MFA_CHALLENGE_SECONDS", "300"))        # password -> code window
    MFA_CHALLENGE_MAX_ATTEMPTS: int = int(os.getenv("MFA_CHALLENGE_MAX_ATTEMPTS", "5"))
    MFA_FRESH_MINUTES: int = int(os.getenv("MFA_FRESH_MINUTES", "10"))                 # "recent MFA" for sensitive actions
    MFA_APPROVAL_FRESH_MINUTES: int = int(os.getenv("MFA_APPROVAL_FRESH_MINUTES", "5")) # commander approval, critical alerts
    MFA_RECOVERY_CODE_COUNT: int = int(os.getenv("MFA_RECOVERY_CODE_COUNT", "10"))
    MFA_FAILS_PER_ACCOUNT_15MIN: int = int(os.getenv("MFA_FAILS_PER_ACCOUNT_15MIN", "8"))
    MFA_ATTEMPTS_PER_IP_15MIN: int = int(os.getenv("MFA_ATTEMPTS_PER_IP_15MIN", "40"))
    MFA_RECOVERY_FAILS_PER_ACCOUNT_HOUR: int = int(os.getenv("MFA_RECOVERY_FAILS_PER_ACCOUNT_HOUR", "5"))
    MFA_ENROLL_START_PER_ACCOUNT_HOUR: int = int(os.getenv("MFA_ENROLL_START_PER_ACCOUNT_HOUR", "6"))
    # Optional policy: privileged accounts must also have a verified email before operational access (state machine step).
    PRIVILEGED_REQUIRE_VERIFIED_EMAIL: bool = os.getenv("PRIVILEGED_REQUIRE_VERIFIED_EMAIL", "false").lower() in ("1", "true", "yes")
    # Host-level recovery: a password reset and an MFA reset of the same privileged account must be this far apart
    RECOVERY_COMBINATION_HOURS: int = int(os.getenv("RECOVERY_COMBINATION_HOURS", "24"))

    # Ollama Supervisor Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60.0"))

    # Authentication
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")  # empty: generated once and kept in backend/.jwt_secret
    # Access tokens are short-lived (default 15 minutes, never more than 60 whatever the setting). Longer sign-ins come
    # from rotating refresh tokens held in an HttpOnly cookie, backed by server-side session records.
    ACCESS_TOKEN_MINUTES: float = float(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    SESSION_ABSOLUTE_HOURS: float = float(os.getenv("SESSION_ABSOLUTE_HOURS", "12"))      # hard limit per sign-in
    SESSION_IDLE_MINUTES: float = float(os.getenv("SESSION_IDLE_MINUTES", "60"))          # no refresh for this long = over
    REMEMBER_ABSOLUTE_DAYS: float = float(os.getenv("REMEMBER_ABSOLUTE_DAYS", "7"))       # "keep me signed in": public roles only
    REMEMBER_IDLE_HOURS: float = float(os.getenv("REMEMBER_IDLE_HOURS", "24"))
    MAX_SESSIONS_PER_USER: int = int(os.getenv("MAX_SESSIONS_PER_USER", "10"))            # oldest are revoked beyond this
    REFRESH_COOKIE_NAME: str = "rn_refresh"
    CSRF_COOKIE_NAME: str = "rn_csrf"
    # Extra browser origins (comma separated) allowed to call the cookie-authenticated endpoints, e.g. a reverse
    # proxy's public origin. Same-origin requests are always allowed.
    TRUSTED_ORIGINS: str = os.getenv("TRUSTED_ORIGINS", "")
    # Demo accounts for every role (see README). Turn off for any real deployment.
    SEED_DEMO_USERS: bool = os.getenv("SEED_DEMO_USERS", "true").lower() in ("1", "true", "yes")
    DEMO_USER_PASSWORD: str = os.getenv("DEMO_USER_PASSWORD", "Rescue@2026")
    ADMIN_PASSWORD: str = os.getenv("RESCUENET_ADMIN_PASSWORD", "")
    # LoRa gateways are devices; when set, /api/incidents/lora requires this key in the X-Gateway-Key header.
    LORA_GATEWAY_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM)

    @property
    def access_token_minutes(self) -> float:
        return max(0.05, min(self.ACCESS_TOKEN_MINUTES, 60.0))

    @property
    def cookie_secure(self) -> bool:
        """Refresh/CSRF cookies are Secure in production; only development (plain http) may relax it."""
        return not self.is_development

    @property
    def is_production(self) -> bool:
        return self.RESCUENET_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.RESCUENET_ENV == "development"


settings = Settings()
if settings.RESCUENET_ENV not in ("development", "production"):
    raise RuntimeError(f"RESCUENET_ENV must be 'development' or 'production', got {settings.RESCUENET_ENV!r}")
