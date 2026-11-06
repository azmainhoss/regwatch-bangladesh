import pytest
from unittest.mock import AsyncMock, patch
import httpx

from backend.app.core.config import settings
from backend.app.modules.analysis.providers.factory import get_ai_provider, get_active_provider_info
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider


def test_gemini_provider_configuration_and_zero_cost_policy():
    """Verify Gemini provider uses configured key, model, and enforces zero-cost."""
    provider = GeminiAIProvider(model_name="gemini-3.8-flash", api_key="test-key-12345")
    assert provider.model_name == "gemini-3.8-flash"
    assert provider.api_key == "test-key-12345"

    info = get_active_provider_info()
    assert "configured_provider" in info
    assert "default_model" in info
    assert info["billing_policy"] == "ZERO_COST_FREE_TIER"


@pytest.mark.asyncio
async def test_gemini_missing_key_error():
    """Gemini provider must cleanly report missing key without raising unhandled crash."""
    provider = GeminiAIProvider(model_name="gemini-3.8-flash", api_key=None)
    provider.api_key = None  # Ensure empty

    res = await provider.generate_structured_json(
        system_prompt="Test system",
        user_prompt="Test user"
    )
    assert res.success is False
    assert "GEMINI_API_KEY is not configured" in res.error


@pytest.mark.asyncio
async def test_gemini_rate_limit_and_quota_exhaustion_handling():
    """HTTP 429 must be handled as free-tier quota exhaustion without silent paid retry."""
    provider = GeminiAIProvider(model_name="gemini-3.8-flash", api_key="mock-secret-key")

    mock_resp = httpx.Response(
        status_code=429,
        text='{"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.generate_structured_json(
            system_prompt="Test system",
            user_prompt="Test user"
        )
        assert res.success is False
        assert "Gemini free-tier quota exhausted or rate limit reached (HTTP 429)" in res.error
        assert "Zero-Cost policy" in res.error
        assert res.token_usage.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_gemini_service_unavailable_503_handling():
    """HTTP 503 must explain free-tier service temporary overload without failing over to paid."""
    provider = GeminiAIProvider(model_name="gemini-3.8-flash", api_key="mock-secret-key")

    mock_resp = httpx.Response(
        status_code=503,
        text='{"error": {"code": 503, "message": "The service is temporarily unavailable."}}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.generate_structured_json(
            system_prompt="Test system",
            user_prompt="Test user"
        )
        assert res.success is False
        assert "Gemini free-tier service temporarily overloaded (HTTP 503)" in res.error


@pytest.mark.asyncio
async def test_gemini_api_key_redaction_in_errors():
    """Error reporting must strictly redact the API key."""
    fake_key = "AIzaSy_PRIVATE_SUPER_SECRET_KEY_12345"
    provider = GeminiAIProvider(model_name="gemini-3.8-flash", api_key=fake_key)

    mock_resp = httpx.Response(
        status_code=400,
        text=f'Invalid request with key={fake_key}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.generate_structured_json(
            system_prompt="Test",
            user_prompt="Test"
        )
        assert res.success is False
        assert fake_key not in res.error
        assert "[REDACTED]" in res.error


def test_factory_rejection_of_silent_fallback():
    """If provider is explicitly set to gemini without key, it must raise ValueError."""
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", None):
            with pytest.raises(ValueError, match="Silent fallback to mock is forbidden"):
                get_ai_provider("gemini")

