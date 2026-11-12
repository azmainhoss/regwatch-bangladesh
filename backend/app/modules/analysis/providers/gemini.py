"""Google Gemini analysis provider (REST generateContent).

- Sends a responseSchema (structured JSON output) when the caller passes a schema.
- Retries 429, 5xx-busy replies and network errors with growing waits (see http_retry), up to
  AI_MAX_RETRIES times, then fails with a clear error. An unreadable JSON answer is retried the
  same way.
- One key, GEMINI_API_KEY, is all it needs.
"""
import asyncio
import json
import time
from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.analysis.providers import health
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage
from backend.app.modules.analysis.providers.http_retry import (
    SleepFn,
    backoff_delay,
    parse_json_text,
    post_with_backoff,
    redact_text,
)

PROVIDER_NAME = "gemini"

_GEMINI_SCHEMA_KEYS = {"type", "properties", "items", "required", "nullable", "enum", "description", "format"}


def to_gemini_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a plain JSON schema (single types, `nullable` flags) to Gemini's responseSchema form."""
    out: Dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_KEYS:
            continue
        if key == "type":
            out["type"] = str(value).upper()
        elif key == "properties":
            out["properties"] = {name: to_gemini_schema(sub) for name, sub in value.items()}
        elif key == "items":
            out["items"] = to_gemini_schema(value)
        else:
            out[key] = value
    return out


class GeminiAIProvider(BaseAIProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        sleep: SleepFn = asyncio.sleep,
    ):
        model = model_name or settings.ANALYSIS_MODEL or settings.GEMINI_ANALYSIS_DEFAULT_MODEL
        super().__init__(model_name=model)
        self.api_key = api_key or settings.GEMINI_API_KEY
        self._client = client
        self._sleep = sleep

    def _fail(self, error: str, raw: str = "", latency_ms: int = 0, status_code: Optional[int] = None,
              usage: Optional[TokenUsage] = None) -> LLMResponse:
        health.record_call(PROVIDER_NAME, self.model_name, False, latency_ms, status_code, error)
        return LLMResponse(
            raw_content=raw,
            parsed_json=None,
            token_usage=usage or TokenUsage(),
            model_name=self.model_name,
            latency_ms=latency_ms,
            success=False,
            error=error,
        )

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                raw_content="",
                parsed_json=None,
                token_usage=TokenUsage(),
                model_name=self.model_name,
                latency_ms=0,
                success=False,
                error="GEMINI_API_KEY is not configured in backend/.env or environment."
            )

        endpoint = f"{self.BASE_URL}/{self.model_name}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "responseMimeType": "application/json",
        }
        if json_schema:
            generation_config["responseSchema"] = to_gemini_schema(json_schema)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": generation_config,
        }

        max_retries = max(0, settings.AI_MAX_RETRIES)
        start = time.time()
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS)
        try:
            # Outer loop only repeats when a 200 reply held unreadable JSON.
            parse_attempt = 0
            while True:
                outcome = await post_with_backoff(
                    client, endpoint, payload, headers,
                    label=f"Gemini {self.model_name}",
                    max_retries=max_retries,
                    base_seconds=settings.AI_RETRY_BASE_SECONDS,
                    max_seconds=settings.AI_RETRY_MAX_SECONDS,
                    sleep=self._sleep,
                    redact=self.api_key,
                )
                elapsed_ms = int((time.time() - start) * 1000)
                resp = outcome.response

                if resp is None:
                    return self._fail(
                        f"Gemini could not be reached after {outcome.attempts} attempts: {outcome.network_error}",
                        latency_ms=elapsed_ms,
                    )

                if resp.status_code == 429:
                    return self._fail(
                        f"Gemini rate limit or quota reached (HTTP 429); gave up after {outcome.attempts} attempts.",
                        raw=redact_text(resp.text, self.api_key), latency_ms=elapsed_ms, status_code=429,
                    )
                if resp.status_code == 503:
                    return self._fail(
                        f"Gemini is overloaded (HTTP 503); gave up after {outcome.attempts} attempts.",
                        raw=redact_text(resp.text, self.api_key), latency_ms=elapsed_ms, status_code=503,
                    )
                if resp.status_code in (401, 403):
                    return self._fail(
                        f"Gemini authentication failed (HTTP {resp.status_code}). Check GEMINI_API_KEY.",
                        raw="[REDACTED_AUTH_ERROR]", latency_ms=elapsed_ms, status_code=resp.status_code,
                    )
                if resp.status_code != 200:
                    clean = redact_text(resp.text, self.api_key)
                    return self._fail(
                        f"Gemini API returned status {resp.status_code}: {clean[:500]}",
                        raw=clean, latency_ms=elapsed_ms, status_code=resp.status_code,
                    )

                try:
                    data = resp.json()
                except ValueError:
                    return self._fail("Gemini returned a reply that is not JSON.", raw=resp.text[:2000],
                                      latency_ms=elapsed_ms, status_code=200)

                usage_meta = data.get("usageMetadata", {}) or {}
                usage = TokenUsage(
                    prompt_tokens=usage_meta.get("promptTokenCount", 0) or 0,
                    completion_tokens=usage_meta.get("candidatesTokenCount", 0) or 0,
                    total_tokens=usage_meta.get("totalTokenCount", 0) or 0,
                    estimated_cost_usd=0.0,
                )
                candidates = data.get("candidates") or []
                if not candidates:
                    reason = (data.get("promptFeedback") or {}).get("blockReason")
                    return self._fail(
                        "No candidate response returned by Gemini." + (f" Block reason: {reason}." if reason else ""),
                        latency_ms=elapsed_ms, status_code=200, usage=usage,
                    )
                parts = (candidates[0].get("content") or {}).get("parts") or []
                raw_text = "".join(p.get("text", "") for p in parts)

                try:
                    parsed = parse_json_text(raw_text)
                except json.JSONDecodeError as jde:
                    if parse_attempt < max_retries:
                        delay = backoff_delay(parse_attempt, settings.AI_RETRY_BASE_SECONDS, settings.AI_RETRY_MAX_SECONDS)
                        logger.warning(f"Gemini answer was not valid JSON ({jde}); asking again in {delay:.0f} s.")
                        parse_attempt += 1
                        await self._sleep(delay)
                        continue
                    return self._fail(
                        f"JSON parsing error: {jde} (finishReason={candidates[0].get('finishReason')})",
                        raw=raw_text, latency_ms=elapsed_ms, status_code=200, usage=usage,
                    )

                health.record_call(PROVIDER_NAME, self.model_name, True, elapsed_ms, 200)
                return LLMResponse(
                    raw_content=raw_text,
                    parsed_json=parsed,
                    token_usage=usage,
                    model_name=self.model_name,
                    latency_ms=elapsed_ms,
                    success=True,
                    error=None,
                )
        except Exception as e:  # never let a provider bug look like a result
            clean = redact_text(str(e), self.api_key)
            logger.error(f"Gemini request error: {clean}")
            return self._fail(f"Gemini request error: {clean}", latency_ms=int((time.time() - start) * 1000))
        finally:
            if own_client:
                await client.aclose()
