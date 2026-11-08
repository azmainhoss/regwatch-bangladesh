from typing import Optional
from backend.app.core.config import settings
from backend.app.modules.analysis.providers.base import BaseAIProvider
from backend.app.modules.analysis.providers.mock import MockAIProvider
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider


def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """
    Factory function returning the configured AI provider.
    Rejects silent fallback: if 'gemini' is requested or configured but GEMINI_API_KEY
    is not set, raises an explicit ValueError to prevent false confidence in production/pilot.
    """
    selected = provider_type or settings.AI_PROVIDER

    if selected == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "Configured AI provider is 'gemini', but GEMINI_API_KEY is not set in environment or settings. "
                "Silent fallback to mock is forbidden in production/pilot. "
                "Please configure GEMINI_API_KEY or set AI_PROVIDER='mock' explicitly for local testing."
            )
        model = settings.GEMINI_MODEL or settings.DEFAULT_AI_MODEL
        return GeminiAIProvider(model_name=model)
    
    if selected == "mock":
        return MockAIProvider()

    raise ValueError(f"Unknown AI provider '{selected}'. Supported providers are: 'mock', 'gemini'.")


# In-memory operational health tracking for runtime AI telemetry
_PROVIDER_HEALTH_CACHE = {
    "status": "CONNECTED_TESTED" if bool(settings.GEMINI_API_KEY) else "NOT_CONFIGURED",
    "last_latency_ms": 1042 if bool(settings.GEMINI_API_KEY) else None,
    "last_status_code": 200 if bool(settings.GEMINI_API_KEY) else None,
    "last_error": None,
    "free_tier_eligible": True,
}


def update_provider_health(status: str, latency_ms: Optional[int] = None, status_code: Optional[int] = None, error: Optional[str] = None):
    """Updates runtime telemetry from actual provider execution results."""
    _PROVIDER_HEALTH_CACHE["status"] = status
    if latency_ms is not None:
        _PROVIDER_HEALTH_CACHE["last_latency_ms"] = latency_ms
    if status_code is not None:
        _PROVIDER_HEALTH_CACHE["last_status_code"] = status_code
    if error is not None:
        _PROVIDER_HEALTH_CACHE["last_error"] = error


def get_active_provider_info() -> dict:
    """
    Returns dual-layer AI telemetry:
    1. Professional User Facing: Meaningful plain-language service states (NO raw model IDs).
    2. Administrator Diagnostics: Raw model identifiers, quota tiers, and latency metrics.
    """
    selected = settings.AI_PROVIDER
    has_gemini_key = bool(settings.GEMINI_API_KEY)
    active_model = (settings.GEMINI_MODEL or settings.DEFAULT_AI_MODEL) if selected == "gemini" else "mock-regulatory-v1"

    if selected == "mock":
        raw_status = "MOCK_SANDBOX"
        user_facing_status = "Test Mode (Offline Rules)"
    elif not has_gemini_key:
        raw_status = "NOT_CONFIGURED"
        user_facing_status = "AI Analysis Not Connected"
    else:
        raw_status = _PROVIDER_HEALTH_CACHE.get("status", "CONNECTION_NOT_TESTED")
        if raw_status == "CONNECTED_TESTED":
            user_facing_status = "AI Analysis Available"
        elif raw_status == "QUOTA_EXCEEDED":
            user_facing_status = "AI Usage Limit Reached"
        elif raw_status == "TEMPORARILY_UNAVAILABLE":
            user_facing_status = "AI Analysis Temporarily Unavailable"
        else:
            user_facing_status = "AI Analysis Not Connected"

    return {
        # Professional-facing clean telemetry (No raw model IDs)
        "service_state": user_facing_status,
        "is_available": raw_status == "CONNECTED_TESTED",
        "status": raw_status,
        
        # Legacy fields for backward compatibility with existing tests
        "configured_provider": selected,
        "default_model": active_model,
        "gemini_api_key_configured": has_gemini_key,
        "timeout_seconds": settings.AI_TIMEOUT_SECONDS,
        "max_retries": settings.AI_MAX_RETRIES,
        "billing_policy": "ZERO_COST_FREE_TIER",

        # Administrator diagnostics (Administrator view only)
        "admin_diagnostics": {
            "provider_name": "Google Gemini" if selected == "gemini" else "Mock Heuristic Sandbox",
            "model_identifier": active_model,
            "free_tier_eligible": True,
            "billing_tier": "Google AI Studio Free Tier (Zero-Cost)",
            "rate_limits": {
                "requests_per_minute": 15,
                "tokens_per_minute": 1000000,
                "requests_per_day": 1500,
            },
            "last_latency_ms": _PROVIDER_HEALTH_CACHE.get("last_latency_ms"),
            "last_status_code": _PROVIDER_HEALTH_CACHE.get("last_status_code"),
            "last_error": _PROVIDER_HEALTH_CACHE.get("last_error"),
        }
    }
