import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    APP_NAME: str = "RegWatch Bangladesh"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "dev-secret-key-regwatch-bangladesh-super-secure-at-least-32-chars"
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
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_AI_MODEL: str = "gemini-2.0-flash"
    AI_MAX_RETRIES: int = 3
    AI_TIMEOUT_SECONDS: int = 60

    # Crawling & Network
    BB_CRAWLER_USER_AGENT: str = "RegWatch-Bangladesh-ResearchBot/1.0 (+compliance-research@regwatch.bd)"
    BB_REQUEST_INTERVAL_SECONDS: float = 3.0
    MAX_CONCURRENT_DOWNLOADS: int = 2

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
