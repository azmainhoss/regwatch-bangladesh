"""Gemini address and headers in one place, so a relay can be switched on with two settings."""
from typing import Dict

from backend.app.core.config import settings


def models_url() -> str:
    """Base for model calls: <base>/v1beta/models."""
    return f"{settings.GEMINI_API_BASE.rstrip('/')}/v1beta/models"


def headers(api_key: str) -> Dict[str, str]:
    h = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    if settings.GEMINI_RELAY_TOKEN:
        h["x-relay-token"] = settings.GEMINI_RELAY_TOKEN
    return h
