from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMResponse(BaseModel):
    raw_content: str
    parsed_json: Optional[Dict[str, Any]] = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    model_name: str
    latency_ms: int = 0
    success: bool = True
    error: Optional[str] = None


class BaseAIProvider(ABC):
    """
    Abstract base class for provider-independent LLM inference.
    Supports structured JSON extraction, cost tracking, and retry logic.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    async def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        """
        Executes inference and returns a validated JSON dictionary response.
        """
        pass
