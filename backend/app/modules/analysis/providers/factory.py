from typing import Optional
from backend.app.core.config import settings
from backend.app.modules.analysis.providers.base import BaseAIProvider
from backend.app.modules.analysis.providers.mock import MockAIProvider
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider


def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """
    Factory function returning the configured AI provider.
    Defaults to MockAIProvider if no API key is configured or if AI_PROVIDER='mock'.
    """
    selected = provider_type or settings.AI_PROVIDER

    if selected == "gemini" and settings.GEMINI_API_KEY:
        return GeminiAIProvider(model_name=settings.DEFAULT_AI_MODEL)
    
    # Fallback to deterministic mock provider
    return MockAIProvider()
