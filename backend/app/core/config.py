import os
from typing import Annotated, List, Literal, Optional
from pydantic_settings import BaseSettings, NoDecode
from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator

# Old hardcoded signing key. Kept only so production can refuse to run with it.
LEGACY_DEFAULT_SECRET_KEY = "dev-secret-key-regwatch-bangladesh-super-secure-at-least-32-chars"
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-0123456789abcdef"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    APP_NAME: str = "Amar Circular"
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
    # Largest evidence file a bank may attach to a task.
    EVIDENCE_MAX_BYTES: int = 25 * 1024 * 1024
    # Rendered page images for the source-page viewer. A cache only: safe to delete at any time.
    # Empty means <STORAGE_LOCAL_ROOT>/page_images.
    PAGE_IMAGE_CACHE_DIR: Optional[str] = None

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
    VISION_MAX_ATTEMPTS: int = 5  # failed tries on VISION_MODEL (each on the next key) before the stronger route
    # Stronger route for a page the main model could not read: the bigger model on a sharper image.
    # Only when that also fails is the page marked READ_FAILED and listed in UNREAD_REPORT_PATH.
    # No page is ever left for a person.
    VISION_FALLBACK_MODEL: str = "gemini-3.5-flash"
    VISION_FALLBACK_DPI: int = 300
    VISION_FALLBACK_ATTEMPTS: int = 2
    # Last route for a page of a new circular that is still unread after both Gemini routes (failed,
    # empty, or text that looks damaged): one read of the page image by STRONG_READER_MODEL (set both
    # in .env). Off while either is empty: the page is then read by hand (scripts/held_pages.py).
    # If this fails too, the circular is held from analysis and the platform team gets an alert.
    STRONG_READER_API_KEY: Optional[str] = None
    # Analyse new circulars by themselves once their pages are read. Phase 1 (analysis uploaded from the laptop)
    # sets this to false. Never runs with the mock provider in production, whatever this says.
    ANALYSIS_AUTO_ENABLED: bool = True
    # Phase 1: the laptop uploads analyses it made with Claude (analysis/upload_router.py). The endpoints exist only
    # when this machine token is set; it is long, random and separate from every user login.
    ANALYSIS_UPLOAD_TOKEN: Optional[SecretStr] = None
    STRONG_READER_MODEL: Optional[str] = None
    STRONG_READER_DPI: int = 300
    UNREAD_REPORT_PATH: str = "data/unread_pages.md"
    VISION_POLL_SECONDS: int = 60  # fallback only: uploads wake the job at once
    # Pages of one circular are read a few at a time: up to VISION_CALLS_PER_KEY calls at once on
    # each key, rotating over GEMINI_API_KEY plus GEMINI_EXTRA_API_KEYS (comma-separated, optional).
    VISION_CALLS_PER_KEY: int = 2
    VISION_MAX_PARALLEL: int = 8
    GEMINI_EXTRA_API_KEYS: Optional[str] = None
    VISION_TIMEOUT_SECONDS: int = 120
    # Run the page-reading job in this process. It also runs wherever SCHEDULER_ENABLED is on.
    VISION_WORKER_ENABLED: bool = False
    MAX_PAGE_PROCESSING_TIMEOUT_SEC: int = 60

    # Circular analysis model. Swapped by config only:
    #   ANALYSIS_PROVIDER = mock | gemini | openai_compat   (old name AI_PROVIDER still read)
    #   ANALYSIS_MODEL    = model id; empty means the provider's default below (old name GEMINI_MODEL still read)
    # gemini uses GEMINI_API_KEY. openai_compat speaks plain chat-completions HTTP to
    # OPENAI_COMPAT_BASE_URL (OpenRouter, SambaNova, a local server, ...) and needs ANALYSIS_MODEL.
    ANALYSIS_PROVIDER: str = Field(default="mock", validation_alias=AliasChoices("ANALYSIS_PROVIDER", "AI_PROVIDER"))
    ANALYSIS_MODEL: Optional[str] = Field(default=None, validation_alias=AliasChoices("ANALYSIS_MODEL", "GEMINI_MODEL"))
    GEMINI_ANALYSIS_DEFAULT_MODEL: str = "gemini-3.5-flash"
    GEMINI_API_KEY: Optional[str] = None
    # Where Gemini calls go. A relay (e.g. a Cloudflare Worker) can stand in for Google's own address when Google
    # refuses the server's location; the relay checks GEMINI_RELAY_TOKEN, sent as the x-relay-token header.
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com"
    GEMINI_RELAY_TOKEN: Optional[str] = None
    OPENAI_COMPAT_BASE_URL: Optional[str] = None  # e.g. https://openrouter.ai/api/v1
    OPENAI_COMPAT_API_KEY: Optional[str] = None  # may be empty for a local server
    # How to ask for JSON: json_schema (strict schema), json_object, or none (prompt only).
    OPENAI_COMPAT_RESPONSE_FORMAT: str = "json_object"
    # Retries after a 429/503 or network error, waiting AI_RETRY_BASE_SECONDS, then x2, x4 ...
    # (capped at AI_RETRY_MAX_SECONDS). After that the call fails with a clear error.
    AI_MAX_RETRIES: int = 3
    AI_RETRY_BASE_SECONDS: float = 5.0
    AI_RETRY_MAX_SECONDS: float = 120.0
    AI_TIMEOUT_SECONDS: int = 120
    # Admin "Test connection": one tiny call on a cheap model, no retries, short timeout.
    PROBE_GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    PROBE_TIMEOUT_SECONDS: float = 15.0
    # "Ask" answers: fast model, one retry at most, shorter timeout (the matching quotes show at once).
    # Provider for "Ask" answers. Empty = the same as ANALYSIS_PROVIDER. Phase 1 uses gemini here while the
    # analysis itself is uploaded from the laptop (ANALYSIS_PROVIDER=mock, ANALYSIS_AUTO_ENABLED=false).
    ANSWER_PROVIDER: str = ""
    ANSWER_GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    ANSWER_MAX_RETRIES: int = 1
    ANSWER_TIMEOUT_SECONDS: float = 45.0
    # When the fast model is busy or fails, this model is asked at once (no waiting retry); it is
    # also asked if the fast model has not answered after ANSWER_HEDGE_SECONDS. Empty = off.
    ANSWER_FALLBACK_GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    ANSWER_HEDGE_SECONDS: float = 4.0
    ANSWER_DEADLINE_SECONDS: float = 20.0  # with the second model on: give up after this, in all

    # Talking to bb.org.bd (DECISIONS.md 1 and 2)
    # The checker uses its own name, one request at a time, at least this many seconds apart.
    BB_CRAWLER_USER_AGENT: str = "NoticeIndexBot/0.1"
    BB_REQUEST_INTERVAL_SECONDS: float = 15.0
    # How many days back the new-circular check asks the date filter for.
    BB_POLL_DAYS: int = 7
    # Back-off after repeated failed checks: starts here, doubles each time, stops rising at the max.
    BB_BACKOFF_START_MINUTES: int = 30
    BB_BACKOFF_MAX_MINUTES: int = 120  # a bot check rarely lasts long; never wait more than 2 h inside the working day

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

    # Alerts and email (docs/specs/ALERTS_SPEC.md). Email is off unless SMTP_HOST and SMTP_FROM are both set.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[SecretStr] = None  # never logged or returned
    SMTP_FROM: Optional[str] = None
    SMTP_FROM_NAME: str = "Amar Circular"
    SMTP_TLS_MODE: Literal["starttls", "ssl", "none"] = "starttls"
    SMTP_TIMEOUT_SECONDS: int = 20
    # Base address for links inside emails (no trailing slash).
    APP_PUBLIC_URL: str = "http://localhost:3000"
    # Run the alerts job in this process even when SCHEDULER_ENABLED is off. One process only.
    ALERTS_WORKER_ENABLED: bool = False
    # Hand new alerts to people right after a save is committed. Tests turn this off.
    ALERTS_KICK_AFTER_COMMIT: bool = True
    ALERTS_WORKER_POLL_SECONDS: int = 30
    ALERTS_SWEEP_MINUTES: int = 15
    ALERTS_ON_POLL_SWEEP_MINUTES: int = 10
    # Days before a deadline that raise a "due soon" alert, comma separated (each 0-90).
    ALERTS_DUE_SOON_DAYS: str = "7,1"
    ALERTS_DIGEST_TIME: str = "10:30"  # Dhaka time, inside the window the host PC is on
    ALERTS_EMAIL_MAX_ATTEMPTS: int = 6
    ALERTS_EMAIL_MAX_AGE_HOURS: int = 48
    ALERTS_PUBLISH_SWEEP_HOURS: int = 48
    ALERTS_RETENTION_DAYS: int = 180

    # Claim checks (docs/specs/CLAIM_CHECKS_SPEC.md). A circular is "new" when published within this many days.
    CLAIM_NEW_CIRCULAR_DAYS: int = 365
    # Second reading of quoted sentences on image-read pages.
    QUOTE_CHECK_MODEL: str = "gemini-3.5-flash"
    QUOTE_TIEBREAK_MODEL: str = "gemini-3.5-flash-lite"
    QUOTE_CHECK_DPI: int = 200
    QUOTE_TIEBREAK_DPI: int = 300
    QUOTE_CHECK_MAX_EDIT_SHARE: float = 0.03
    # Readers see points that did not pass every check too, marked "Check page N" (they are never hidden).
    SHOW_UNCONFIRMED_POINTS: bool = True
    QUOTE_CHECK_CROPS_PER_CALL: int = 12
    QUOTE_CHECK_MAX_ATTEMPTS: int = 3

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

    @field_validator("SMTP_FROM_NAME", "APP_PUBLIC_URL", mode="after")
    @classmethod
    def _strip(cls, value):
        return value.strip().rstrip("/") if value else value

    @property
    def due_soon_days(self) -> List[int]:
        days = set()
        for part in str(self.ALERTS_DUE_SOON_DAYS or "").split(","):
            part = part.strip()
            if part.isdigit() and 0 <= int(part) <= 90:
                days.add(int(part))
        return sorted(days) or [1]

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
