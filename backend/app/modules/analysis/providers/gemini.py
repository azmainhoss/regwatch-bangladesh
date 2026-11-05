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
        model = model_name or settings.DEFAULT_AI_MODEL
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
                error="GEMINI_API_KEY is not configured in environment or settings."
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
                    
                    # Estimated cost for Gemini 2.0 Flash (~$0.10 / 1M prompt tokens, ~$0.40 / 1M completion)
                    est_cost = (prompt_toks * 0.0000001) + (cand_toks * 0.0000004)

                    try:
                        parsed = json.loads(raw_text)
                        return LLMResponse(
                            raw_content=raw_text,
                            parsed_json=parsed,
                            token_usage=TokenUsage(
                                prompt_tokens=prompt_toks,
                                completion_tokens=cand_toks,
                                total_tokens=tot_toks,
                                estimated_cost_usd=round(est_cost, 6)
                            ),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=True,
                            error=None
                        )
                    except json.JSONDecodeError as jde:
                        return LLMResponse(
                            raw_content=raw_text,
                            parsed_json=None,
                            token_usage=TokenUsage(total_tokens=tot_toks),
                            model_name=self.model_name,
                            latency_ms=elapsed_ms,
                            success=False,
                            error=f"JSON parsing error: {jde}"
                        )
                else:
                    error_msg = f"Gemini API returned status {resp.status_code}: {resp.text}"
                    logger.warning(f"Gemini API attempt {attempt + 1} failed: {error_msg}")
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
            except Exception as e:
                logger.error(f"Gemini API request error on attempt {attempt + 1}: {e}")
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
