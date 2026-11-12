import os
from typing import Annotated, List, Optional
from pydantic_settings import BaseSettings, NoDecode
from pydantic import AliasChoices, Field, field_validator, model_validator

# Old hardcoded signing key. Kept only so production can refuse to run with it.
LEGACY_DEFAULT_SECRET_KEY = "dev-secret-key-regwatch-bangladesh-super-secure-at-least-32-chars"
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-0123456789abcdef"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    APP_NAME: str = "RegWatch Bangladesh"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    # JWT signing key. Read from SECRET_KEY or JWT_SECRET. Required in production.
    SECRET_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET"))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/regwatch.db"
    SYNC_DATABASE_URL: str = "sqlite:///./data/regwatch.db"

    # Redis & Background Tasks
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Document Storage
    STORAGE_DRIVER: str = "local"  # local or s3
    STORAGE_LOCAL_ROOT: str = "./storage"
    ORIGINALS_STORAGE_NAMESPACE: str = "originals"
    EVIDENCE_STORAGE_NAMESPACE: str = "evidence"

    # S3 Configuration
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: str = "regwatch-documents"
    S3_REGION: str = "ap-southeast-1"

    # OCR and Extraction
    TESSERACT_CMD: str = "/opt/homebrew/bin/tesseract"
    TESSDATA_PREFIX: str = "/opt/homebrew/share/tessdata"
    OCR_DEFAULT_LANG: str = "eng"
    MAX_PAGE_PROCESSING_TIMEOUT_SEC: int = 60

    # AI Provider Configuration
    AI_PROVIDER: str = "mock"  # mock, gemini, openai, anthropic
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_AI_MODEL: str = "gemini-3.8-flash"
    AI_MAX_RETRIES: int = 3
    AI_TIMEOUT_SECONDS: int = 60

    # Crawling & Network
    BB_CRAWLER_USER_AGENT: str = "RegWatch-Bangladesh-ResearchBot/1.0 (+compliance-research@regwatch.bd)"
    BB_REQUEST_INTERVAL_SECONDS: float = 3.0
    MAX_CONCURRENT_DOWNLOADS: int = 2
    SOURCE_MONITORING_INTERVAL_SECONDS: int = 900

    # Startup behaviour
    # Load the demo seed fixture into an empty database at startup. Never runs in production.
    SEED_ON_STARTUP: bool = False
    # Run the background source monitoring scheduler in this process.
    # Turn off on all but one process when running several workers.
    SCHEDULER_ENABLED: bool = True

    # CORS: comma separated list (or JSON list) of exact origins allowed to call the API.
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {
        "env_file": [".env", "backend/.env"],
        "case_sensitive": True,
        "extra": "ignore"
    }

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                import json
                return [str(v).strip() for v in json.loads(raw) if str(v).strip()]
            return [part.strip() for part in raw.split(",") if part.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return (self.ENVIRONMENT or "").strip().lower() in ("production", "prod")

    @model_validator(mode="after")
    def _check_secret_key(self):
        if self.is_production:
            if not self.SECRET_KEY or self.SECRET_KEY == LEGACY_DEFAULT_SECRET_KEY or self.SECRET_KEY == DEV_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY (or JWT_SECRET) must be set to a private value when ENVIRONMENT=production."
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters long in production.")
        elif not self.SECRET_KEY:
            self.SECRET_KEY = DEV_SECRET_KEY
        return self


settings = Settings()
