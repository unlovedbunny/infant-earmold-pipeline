import os
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "AuriMold API"
    API_V1_STR: str = "/api/v1"
    
    # Storage settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    TEMP_DIR: Path = BASE_DIR / "temp"
    OUTPUT_DIR: Path = BASE_DIR / "output"
    
    # Upload settings
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: set = {".stl"}
    
    # Geometry thresholds
    MIN_WALL_THICKNESS_MM: float = 1.2
    
    class Config:
        env_file = ".env"

settings = Settings()

# Ensure directories exist
os.makedirs(settings.TEMP_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
