import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
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

    # Uploads directory for incident attachments
    UPLOAD_DIR: Path = BASE_DIR / "backend" / "uploads"

    # Ollama Supervisor Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60.0"))

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
