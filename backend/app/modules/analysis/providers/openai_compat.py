"""OpenAI-compatible chat-completions provider (plain HTTP).

Works with any server that speaks POST {base_url}/chat/completions: OpenRouter, SambaNova, a
local llama.cpp / vLLM / Ollama server, or OpenAI itself. Chosen by config only:

    ANALYSIS_PROVIDER=openai_compat
    OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
    OPENAI_COMPAT_API_KEY=...            (may be empty for a local server)
    ANALYSIS_MODEL=some/model-id
    OPENAI_COMPAT_RESPONSE_FORMAT=json_object | json_schema | none

Retries and waits are the same as the Gemini provider (http_retry).
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
    parse_json_text,
    post_with_backoff,
    redact_text,
)

PROVIDER_NAME = "openai_compat"


def to_openai_strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Plain JSON schema -> OpenAI strict json_schema (nullable as a type list, every key required)."""
    out: Dict[str, Any] = {}
    kind = schema.get("type")
    if kind:
        out["type"] = [kind, "null"] if schema.get("nullable") else kind
    if "enum" in schema:
        out["enum"] = schema["enum"]
    if "description" in schema:
        out["description"] = schema["description"]
    if kind == "object":
        props = schema.get("properties", {})
        out["properties"] = {name: to_openai_strict_schema(sub) for name, sub in props.items()}
        out["required"] = list(props.keys())
        out["additionalProperties"] = False
    if kind == "array" and "items" in schema:
        out["items"] = to_openai_strict_schema(schema["items"])
    return out


class OpenAICompatibleProvider(BaseAIProvider):
    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        response_format: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        sleep: SleepFn = asyncio.sleep,
    ):
        super().__init__(model_name=model_name or settings.ANALYSIS_MODEL or "")
        self.base_url = (base_url or settings.OPENAI_COMPAT_BASE_URL or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.OPENAI_COMPAT_API_KEY
        self.response_format = (response_format or settings.OPENAI_COMPAT_RESPONSE_FORMAT or "json_object").lower()
        self._client = client
        self._sleep = sleep

    def _fail(self, error: str, raw: str = "", latency_ms: int = 0, status_code: Optional[int] = None,
              usage: Optional[TokenUsage] = None, record: bool = True) -> LLMResponse:
        if record:
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

    def _payload(self, system_prompt: str, user_prompt: str, json_schema: Optional[Dict[str, Any]],
                 temperature: float) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if self.response_format == "json_schema" and json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": to_openai_strict_schema(json_schema)},
            }
        elif self.response_format in ("json_object", "json_schema"):
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        if not self.base_url or not self.model_name:
            return self._fail(
                "OpenAI-compatible provider needs OPENAI_COMPAT_BASE_URL and ANALYSIS_MODEL.", record=False
            )

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = self._payload(system_prompt, user_prompt, json_schema, temperature)

        start = time.time()
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS)
        try:
            outcome = await post_with_backoff(
                client, url, payload, headers,
                label=f"{self.base_url} {self.model_name}",
                max_retries=settings.AI_MAX_RETRIES,
                base_seconds=settings.AI_RETRY_BASE_SECONDS,
                max_seconds=settings.AI_RETRY_MAX_SECONDS,
                sleep=self._sleep,
                redact=self.api_key,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            resp = outcome.response
            if resp is None:
                return self._fail(
                    f"Model server could not be reached after {outcome.attempts} attempts: {outcome.network_error}",
                    latency_ms=elapsed_ms,
                )
            if resp.status_code != 200:
                clean = redact_text(resp.text, self.api_key)
                if resp.status_code in (401, 403):
                    msg = f"Model server refused the key (HTTP {resp.status_code}). Check OPENAI_COMPAT_API_KEY."
                    clean = "[REDACTED_AUTH_ERROR]"
                elif resp.status_code == 429:
                    msg = f"Model server rate limit or quota reached (HTTP 429); gave up after {outcome.attempts} attempts."
                elif resp.status_code >= 500:
                    msg = f"Model server busy or failing (HTTP {resp.status_code}); gave up after {outcome.attempts} attempts."
                else:
                    msg = f"Model server returned status {resp.status_code}: {clean[:500]}"
                return self._fail(msg, raw=clean, latency_ms=elapsed_ms, status_code=resp.status_code)

            try:
                data = resp.json()
            except ValueError:
                return self._fail("Model server reply is not JSON.", raw=resp.text[:2000],
                                  latency_ms=elapsed_ms, status_code=200)

            usage_raw = data.get("usage") or {}
            usage = TokenUsage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0) or 0,
                completion_tokens=usage_raw.get("completion_tokens", 0) or 0,
                total_tokens=usage_raw.get("total_tokens", 0) or 0,
            )
            choices = data.get("choices") or []
            if not choices:
                return self._fail("Model server returned no choices.", latency_ms=elapsed_ms, status_code=200, usage=usage)
            content = (choices[0].get("message") or {}).get("content") or ""
            try:
                parsed = parse_json_text(content)
            except json.JSONDecodeError as jde:
                return self._fail(
                    f"JSON parsing error: {jde} (finish_reason={choices[0].get('finish_reason')})",
                    raw=content, latency_ms=elapsed_ms, status_code=200, usage=usage,
                )

            health.record_call(PROVIDER_NAME, self.model_name, True, elapsed_ms, 200)
            return LLMResponse(
                raw_content=content,
                parsed_json=parsed,
                token_usage=usage,
                model_name=self.model_name,
                latency_ms=elapsed_ms,
                success=True,
            )
        except Exception as e:
            clean = redact_text(str(e), self.api_key)
            logger.error(f"OpenAI-compatible request error: {clean}")
            return self._fail(f"Model server request error: {clean}", latency_ms=int((time.time() - start) * 1000))
        finally:
            if own_client:
                await client.aclose()
