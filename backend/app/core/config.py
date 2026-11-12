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

    # Page reading (DECISIONS.md 6 and 10)
    # English pages with a clean text layer are read locally with PyMuPDF. Bangla, legacy-font
    # and scanned pages are read by Gemini from a page image (key: GEMINI_API_KEY), one call at
    # a time, by a background job. Without a key those pages wait as PENDING_VISION.
    VISION_MODEL: str = "gemini-3.5-flash-lite"
    VISION_DPI: int = 200
    VISION_MAX_RETRIES: int = 4  # retries inside one call on 429/503, with backoff
    VISION_RETRY_BASE_SECONDS: float = 5.0
    VISION_MAX_ATTEMPTS: int = 5  # failed jobs on one page before it goes to a person
    VISION_POLL_SECONDS: int = 60
    VISION_TIMEOUT_SECONDS: int = 120
    # Run the page-reading job in this process. It also runs wherever SCHEDULER_ENABLED is on.
    VISION_WORKER_ENABLED: bool = False
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

    # Talking to bb.org.bd (DECISIONS.md 1 and 2)
    # The checker uses its own name, one request at a time, at least this many seconds apart.
    BB_CRAWLER_USER_AGENT: str = "RegWatchBot/0.1"
    BB_REQUEST_INTERVAL_SECONDS: float = 15.0
    # How many days back the new-circular check asks the date filter for.
    BB_POLL_DAYS: int = 7
    # Back-off after repeated failed checks: starts here, doubles each time, stops rising at the max.
    BB_BACKOFF_START_MINUTES: int = 30
    BB_BACKOFF_MAX_MINUTES: int = 360

    # Monitoring schedule, in MONITOR_TIMEZONE local time.
    # The host PC is only on inside the window, so nothing is scheduled outside it.
    MONITOR_TIMEZONE: str = "Asia/Dhaka"
    MONITOR_WINDOW_START: int = 10  # hour, inclusive
    MONITOR_WINDOW_END: int = 18  # hour, exclusive
    POLL_INTERVAL_WORKDAY_MINUTES: int = 10  # Sun-Thu
    POLL_INTERVAL_WEEKEND_MINUTES: int = 60  # Fri-Sat
    RECONCILE_TIME: str = "17:50"  # daily full-list check
    # Weekly re-check of archived PDFs (Python weekday: Mon=0 ... Fri=4, Sat=5, Sun=6).
    RECHECK_WEEKDAY: int = 4
    RECHECK_TIME: str = "11:00"

    # Startup behaviour
    # Load the demo seed fixture into an empty database at startup. Never runs in production.
    SEED_ON_STARTUP: bool = False
    # Run the background source monitoring scheduler in this process.
    # Turn off on all but one process when running several workers.
    SCHEDULER_ENABLED: bool = False  # turn on explicitly on the one machine that collects

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
