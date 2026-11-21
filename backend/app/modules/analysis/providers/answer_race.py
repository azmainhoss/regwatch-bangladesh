"""Fast "Ask" answers on a busy free tier.

The fast model often replies "busy" (HTTP 503) on the free tier, and the normal retry waits 5 s
first. For a person waiting on the Ask screen that is too slow, so here:
- the fast model is asked once, with no waiting retry;
- if it fails, a second model is asked straight away (and after that the fast model once more);
- if a call has not answered after `hedge_seconds`, the next one is started alongside it;
- the first good answer wins and the other call is cancelled.
At most three calls per question and two at a time, all within `deadline_seconds`. The answer itself is checked by the caller as before.
"""
import asyncio
import time
from typing import Any, Dict, Optional

from backend.app.core.logging import logger
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage


class RacingAnswerProvider(BaseAIProvider):
    def __init__(self, primary: BaseAIProvider, fallback: Optional[BaseAIProvider], hedge_seconds: float,
                 deadline_seconds: Optional[float] = None):
        super().__init__(model_name=primary.model_name)
        self.primary = primary
        self.fallback = fallback
        self.hedge_seconds = hedge_seconds
        self.deadline_seconds = deadline_seconds

    async def generate_structured_json(self, system_prompt: str, user_prompt: str,
                                       json_schema: Optional[Dict[str, Any]] = None,
                                       temperature: float = 0.0) -> LLMResponse:
        """Gives up after `deadline_seconds` in all: the matching quotes are already on screen."""
        start = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                self._race(system_prompt, user_prompt, json_schema, temperature), timeout=self.deadline_seconds,
            )
        except asyncio.TimeoutError:
            resp = LLMResponse(raw_content="", parsed_json=None, token_usage=TokenUsage(), model_name=self.model_name,
                               latency_ms=int((time.monotonic() - start) * 1000), success=False,
                               error=f"No answer within {self.deadline_seconds:.0f} s.")
        logger.info(f"Ask answer: {'ok' if resp.success else 'failed'} from {resp.model_name} "
                    f"in {time.monotonic() - start:.1f} s")
        return resp

    async def _race(self, system_prompt: str, user_prompt: str, json_schema: Optional[Dict[str, Any]],
                    temperature: float) -> LLMResponse:
        def ask(p: BaseAIProvider) -> asyncio.Task:
            return asyncio.create_task(p.generate_structured_json(
                system_prompt=system_prompt, user_prompt=user_prompt, json_schema=json_schema, temperature=temperature,
            ))

        if self.fallback is None:
            return await ask(self.primary)
        # Fast model, then the second model, then the fast model once more; never more than two at once.
        queue = [self.primary, self.fallback, self.primary]
        running = {ask(queue.pop(0))}
        last: Optional[LLMResponse] = None
        try:
            while running:
                done, running = await asyncio.wait(
                    running, timeout=self.hedge_seconds if queue and len(running) < 2 else None,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in done:
                    last = t.result()
                    if last.success:
                        return last
                # A failure, or no answer yet after hedge_seconds: start the next call now.
                if queue and len(running) < 2:
                    running.add(ask(queue.pop(0)))
            return last
        finally:
            for t in running:
                t.cancel()
