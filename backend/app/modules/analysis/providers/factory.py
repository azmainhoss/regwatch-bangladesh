from typing import Optional

from backend.app.core.config import settings
from backend.app.modules.analysis.providers import health
from backend.app.modules.analysis.providers.base import BaseAIProvider
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider
from backend.app.modules.analysis.providers.mock import MockAIProvider
from backend.app.modules.analysis.providers.openai_compat import OpenAICompatibleProvider

SUPPORTED_PROVIDERS = ("mock", "gemini", "openai_compat")
_ALIASES = {
    "openai": "openai_compat",
    "openai-compat": "openai_compat",
    "openai_compatible": "openai_compat",
    "openai-compatible": "openai_compat",
}

MOCK_MODEL = "mock-regulatory-v1"


def normalize_provider_name(name: Optional[str]) -> str:
    key = (name or "").strip().lower()
    return _ALIASES.get(key, key)


def configured_model(provider: str) -> str:
    """The model the configured provider will use."""
    if provider == "gemini":
        return settings.ANALYSIS_MODEL or settings.GEMINI_ANALYSIS_DEFAULT_MODEL
    if provider == "openai_compat":
        return settings.ANALYSIS_MODEL or ""
    return MOCK_MODEL


def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """
    Returns the configured AI provider (ANALYSIS_PROVIDER, or the name passed in).
    Rejects silent fallback: a real provider that is missing its settings raises ValueError
    rather than quietly using the mock.
    """
    selected = normalize_provider_name(provider_type or settings.ANALYSIS_PROVIDER)

    if selected == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "Configured AI provider is 'gemini', but GEMINI_API_KEY is not set in environment or settings. "
                "Silent fallback to mock is forbidden in production/pilot. "
                "Please configure GEMINI_API_KEY or set ANALYSIS_PROVIDER='mock' explicitly for local testing."
            )
        return GeminiAIProvider(model_name=configured_model("gemini"))

    if selected == "openai_compat":
        missing = [name for name, value in (
            ("OPENAI_COMPAT_BASE_URL", settings.OPENAI_COMPAT_BASE_URL),
            ("ANALYSIS_MODEL", settings.ANALYSIS_MODEL),
        ) if not value]
        if missing:
            raise ValueError(
                f"Configured AI provider is 'openai_compat', but {', '.join(missing)} is not set. "
                "Silent fallback to mock is forbidden."
            )
        return OpenAICompatibleProvider(model_name=settings.ANALYSIS_MODEL)

    if selected == "mock":
        return MockAIProvider()

    raise ValueError(
        f"Unknown AI provider '{selected}'. Supported providers are: {', '.join(SUPPORTED_PROVIDERS)}."
    )


def update_provider_health(status: str, latency_ms: Optional[int] = None, status_code: Optional[int] = None,
                           error: Optional[str] = None):
    """Records the outcome of a real check against the configured provider."""
    provider = normalize_provider_name(settings.ANALYSIS_PROVIDER)
    health.record_call(
        provider, configured_model(provider), status == health.CONNECTED_TESTED,
        latency_ms, status_code, error, status=status,
    )


def _is_configured(provider: str) -> bool:
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    if provider == "openai_compat":
        return bool(settings.OPENAI_COMPAT_BASE_URL and settings.ANALYSIS_MODEL)
    return provider == "mock"


_USER_FACING = {
    health.CONNECTED_TESTED: "AI Analysis Available",
    health.QUOTA_EXCEEDED: "AI Usage Limit Reached",
    health.TEMPORARILY_UNAVAILABLE: "AI Analysis Temporarily Unavailable",
    health.AUTH_FAILED: "AI Analysis Not Connected",
    health.CALL_FAILED: "AI Analysis Not Working",
    health.NOT_TESTED: "AI Connection Not Checked Yet",
}


def get_active_provider_info() -> dict:
    """
    Provider status from real calls only. Until a real call to the configured provider and model
    has happened in this process, the status is NOT_TESTED and nothing else is claimed.
    """
    selected = normalize_provider_name(settings.ANALYSIS_PROVIDER)
    model = configured_model(selected)
    last = health.health_for(selected, model)

    if selected == "mock":
        raw_status = "MOCK_SANDBOX"
        user_facing_status = "Test Mode (Offline Rules)"
    elif selected not in SUPPORTED_PROVIDERS or not _is_configured(selected):
        raw_status = "NOT_CONFIGURED"
        user_facing_status = "AI Analysis Not Connected"
    else:
        raw_status = last["status"]
        user_facing_status = _USER_FACING.get(raw_status, "AI Analysis Not Connected")

    provider_names = {
        "gemini": "Google Gemini",
        "openai_compat": "OpenAI-compatible endpoint",
        "mock": "Mock Heuristic Sandbox",
    }

    return {
        "service_state": user_facing_status,
        "is_available": raw_status == "CONNECTED_TESTED",
        "status": raw_status,
        "configured_provider": selected,
        "default_model": model,
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "timeout_seconds": settings.AI_TIMEOUT_SECONDS,
        "max_retries": settings.AI_MAX_RETRIES,
        "last_checked_at": last["checked_at"],
        "admin_diagnostics": {
            "provider_name": provider_names.get(selected, selected),
            "model_identifier": model,
            "base_url": settings.OPENAI_COMPAT_BASE_URL if selected == "openai_compat" else None,
            "last_checked_at": last["checked_at"],
            "last_latency_ms": last["last_latency_ms"],
            "last_status_code": last["last_status_code"],
            "last_error": last["last_error"],
        },
    }
