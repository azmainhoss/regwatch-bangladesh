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
        return GeminiAIProvider(model_name=settings.DEFAULT_AI_MODEL)
    
    if selected == "mock":
        return MockAIProvider()

    raise ValueError(f"Unknown AI provider '{selected}'. Supported providers are: 'mock', 'gemini'.")


def get_active_provider_info() -> dict:
    """Returns safe metadata regarding active AI provider for operator consoles."""
    selected = settings.AI_PROVIDER
    has_gemini_key = bool(settings.GEMINI_API_KEY)
    
    return {
        "configured_provider": selected,
        "default_model": settings.DEFAULT_AI_MODEL,
        "gemini_api_key_configured": has_gemini_key,
        "status": "LIVE_VERIFIED" if (selected == "gemini" and has_gemini_key) else ("MOCK_SANDBOX" if selected == "mock" else "NOT_VERIFIED_MISSING_CREDENTIALS"),
        "timeout_seconds": settings.AI_TIMEOUT_SECONDS,
        "max_retries": settings.AI_MAX_RETRIES
    }
