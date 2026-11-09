import asyncio
import json
import time
from typing import Any, Dict, List, Optional
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage


class GeminiAIProvider(BaseAIProvider):
    """
    Google Gemini AI Provider integration using official REST endpoint
    with structured JSON schema enforcement, token tracking, and retries.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        model = model_name or settings.GEMINI_MODEL or settings.DEFAULT_AI_MODEL
        super().__init__(model_name=model)
        self.api_key = api_key or settings.GEMINI_API_KEY

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
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        # Construct Gemini API payload
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json"
            }
        }

        start_time = time.time()
        max_retries = settings.AI_MAX_RETRIES

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)

                elapsed_ms = int((time.time() - start_time) * 1000)

                if resp.status_code == 200:
                    from backend.app.modules.analysis.providers.factory import update_provider_health
                    update_provider_health(status="CONNECTED_TESTED", latency_ms=elapsed_ms, status_code=200)

                    resp_data = resp.json()
                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        return LLMResponse(
                            raw_content="",
                            parsed_json=None,
                            token_usage=TokenUsage(),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=False,
                            error="No candidate response returned by Gemini."
                        )

                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    
                    # Extract usage metadata
                    usage = resp_data.get("usageMetadata", {})
                    prompt_toks = usage.get("promptTokenCount", 0)
                    cand_toks = usage.get("candidatesTokenCount", 0)
                    tot_toks = usage.get("totalTokenCount", 0)
                    
                    # Strictly Zero-Cost for Google AI Studio Free Tier
                    est_cost = 0.0

                    # Strip any markdown fences if model returned them
                    cleaned = raw_text.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()

                    try:
                        parsed = json.loads(cleaned)
                        return LLMResponse(
                            raw_content=raw_text,
                            parsed_json=parsed,
                            token_usage=TokenUsage(
                                prompt_tokens=prompt_toks,
                                completion_tokens=cand_toks,
                                total_tokens=tot_toks,
                                estimated_cost_usd=est_cost
                            ),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=True,
                            error=None
                        )
                    except json.JSONDecodeError as jde:
                        logger.warning(f"Gemini API attempt {attempt + 1}: JSONDecodeError: {jde}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1.0)
                            continue
                        return LLMResponse(
                            raw_content=raw_text,
                            parsed_json=None,
                            token_usage=TokenUsage(total_tokens=tot_toks),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=False,
                            error=f"JSON parsing error: {jde}"
                        )
                elif resp.status_code == 429:
                    from backend.app.modules.analysis.providers.factory import update_provider_health
                    error_msg = (
                        "Gemini free-tier quota exhausted or rate limit reached (HTTP 429). "
                        "Execution halted to strictly honor Zero-Cost policy. Please retry after quota reset."
                    )
                    update_provider_health(status="QUOTA_EXCEEDED", latency_ms=elapsed_ms, status_code=429, error=error_msg)
                    logger.warning(f"Gemini API attempt {attempt + 1}: {error_msg}")
                    return LLMResponse(
                        raw_content=resp.text,
                        parsed_json=None,
                        token_usage=TokenUsage(),
                        model_name=self.model_name,
                        latency_ms=elapsed_ms,
                        success=False,
                        error=error_msg
                    )
                elif resp.status_code == 503:
                    error_msg = (
                        "Gemini free-tier service temporarily overloaded (HTTP 503). "
                        "Zero-cost policy prevents paid fallback. Please retry shortly."
                    )
                    logger.warning(f"Gemini API attempt {attempt + 1}: {error_msg}")
                    if attempt == max_retries - 1:
                        return LLMResponse(
                            raw_content=resp.text,
                            parsed_json=None,
                            token_usage=TokenUsage(),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=False,
                            error=error_msg
                        )
                elif resp.status_code in (401, 403):
                    error_msg = (
                        f"Gemini authentication failed (HTTP {resp.status_code}). "
                        "Please verify your Google AI Studio API key in backend/.env."
                    )
                    logger.error(error_msg)
                    return LLMResponse(
                        raw_content="[REDACTED_AUTH_ERROR]",
                        parsed_json=None,
                        token_usage=TokenUsage(),
                        model_name=self.model_name,
                        latency_ms=elapsed_ms,
                        success=False,
                        error=error_msg
                    )
                else:
                    clean_text = resp.text.replace(self.api_key, "[REDACTED]") if self.api_key else resp.text
                    error_msg = f"Gemini API returned status {resp.status_code}: {clean_text}"
                    logger.warning(f"Gemini API attempt {attempt + 1} failed: {error_msg}")
                    if attempt == max_retries - 1:
                        return LLMResponse(
                            raw_content=clean_text,
                            parsed_json=None,
                            token_usage=TokenUsage(),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=False,
                            error=error_msg
                        )
            except Exception as e:
                clean_err = str(e).replace(self.api_key, "[REDACTED]") if self.api_key else str(e)
                logger.error(f"Gemini API request error on attempt {attempt + 1}: {clean_err}")
                if attempt == max_retries - 1:
                    return LLMResponse(
                        raw_content="",
                        parsed_json=None,
                        token_usage=TokenUsage(),
                        model_name=self.model_name,
                        latency_ms=int((time.time() - start_time) * 1000),
                        success=False,
                        error=str(e)
                    )

        return LLMResponse(
            raw_content="",
            parsed_json=None,
            token_usage=TokenUsage(),
            model_name=self.model_name,
            latency_ms=0,
            success=False,
            error="Exhausted maximum retry attempts."
        )
