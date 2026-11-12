import pytest
from unittest.mock import AsyncMock, patch
import httpx

from backend.app.core.config import settings
from backend.app.modules.analysis.providers.factory import get_ai_provider, get_active_provider_info
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider


async def _no_sleep(_seconds: float) -> None:
    return None


def test_gemini_provider_configuration():
    """Gemini provider uses the key and model it is given."""
    provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key="test-key-12345")
    assert provider.model_name == "gemini-3.5-flash"
    assert provider.api_key == "test-key-12345"

    info = get_active_provider_info()
    assert "configured_provider" in info
    assert "default_model" in info


def test_gemini_default_model_is_not_a_dead_model(monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_MODEL", None)
    provider = GeminiAIProvider(api_key="k")
    assert provider.model_name == settings.GEMINI_ANALYSIS_DEFAULT_MODEL
    assert "3.8" not in provider.model_name


@pytest.mark.asyncio
async def test_gemini_missing_key_error():
    """Gemini provider must cleanly report missing key without raising unhandled crash."""
    provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key=None)
    provider.api_key = None  # Ensure empty

    res = await provider.generate_structured_json(
        system_prompt="Test system",
        user_prompt="Test user"
    )
    assert res.success is False
    assert "GEMINI_API_KEY is not configured" in res.error


@pytest.mark.asyncio
async def test_gemini_rate_limit_gives_up_with_clear_error(monkeypatch):
    """HTTP 429 every time: retried a capped number of times, then a clear failure."""
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 2)
    provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key="mock-secret-key", sleep=_no_sleep)

    mock_resp = httpx.Response(
        status_code=429,
        text='{"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as post:
        res = await provider.generate_structured_json(system_prompt="Test system", user_prompt="Test user")
    assert res.success is False
    assert "HTTP 429" in res.error
    assert "3 attempts" in res.error
    assert post.await_count == 3
    assert res.token_usage.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_gemini_service_unavailable_503_handling(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 1)
    provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key="mock-secret-key", sleep=_no_sleep)

    mock_resp = httpx.Response(
        status_code=503,
        text='{"error": {"code": 503, "message": "The service is temporarily unavailable."}}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.generate_structured_json(system_prompt="Test system", user_prompt="Test user")
    assert res.success is False
    assert "HTTP 503" in res.error


@pytest.mark.asyncio
async def test_gemini_api_key_redaction_in_errors():
    """Error reporting must strictly redact the API key."""
    fake_key = "AIzaSy_PRIVATE_SUPER_SECRET_KEY_12345"
    provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key=fake_key, sleep=_no_sleep)

    mock_resp = httpx.Response(
        status_code=400,
        text=f'Invalid request with key={fake_key}',
        request=httpx.Request("POST", "http://test")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.generate_structured_json(system_prompt="Test", user_prompt="Test")
    assert res.success is False
    assert fake_key not in res.error
    assert "[REDACTED]" in res.error


def test_factory_rejection_of_silent_fallback():
    """If provider is explicitly set to gemini without key, it must raise ValueError."""
    with patch.object(settings, "ANALYSIS_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", None):
            with pytest.raises(ValueError, match="Silent fallback to mock is forbidden"):
                get_ai_provider("gemini")
