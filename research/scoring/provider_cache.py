"""A provider that sits between the app's analysis pipeline and the real model.

- Same request (system prompt, schema, final user prompt) for the same row, candidate and model: the saved
  answer is returned and no model call is made.
- Free-tier replies that only mean "not now" (rate limit, busy, daily quota) are never saved as answers:
  the call waits and goes on with the next key, or stops the run when every key is used up for today.
- An answer that is empty is saved as EMPTY so it is counted (scorer spec 3.6), never retried silently.
- Modes: "run" (call the model when nothing is saved), "cache_only" (never call; used to rescore) and
  "capture" (never call; remember the request, used for pricing and batch files).

The pipeline swallows exceptions from its provider, so this class reports its state in attributes
(`stop_reason`, `miss`, `captured`, `last_kind`) and answers with a failed response; the runner reads them.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import common
import quota

from backend.app.core.config import settings
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage

BUSY_WAIT_SECONDS = 60
MAX_BUSY_MINUTES = 45  # all keys busy for this long: stop the run (rows are not recorded as failures)


def _is_daily_quota(resp: LLMResponse) -> bool:
    text = f"{resp.error or ''} {resp.raw_content or ''}"
    return "429" in text and ("PerDay" in text or "per day" in text.lower())


def classify_failure(resp: LLMResponse) -> str:
    """daily | busy | auth | real"""
    text = f"{resp.error or ''}".lower()
    if _is_daily_quota(resp):
        return "daily"
    if "429" in text or "rate limit" in text or "quota" in text:
        return "busy"
    if "503" in text or "overloaded" in text or "could not be reached" in text or "busy or failing" in text:
        return "busy"
    if "status 500" in text or "status 502" in text or "status 504" in text:
        return "busy"
    if "authentication failed" in text or "refused the key" in text or "not configured" in text:
        return "auth"
    return "real"


def cache_key_name(unit: str, candidate: str, model: str, prompt_hash: str, input_hash: str) -> str:
    return common.safe_name(f"{unit}__{candidate}__{model}__{prompt_hash[:10]}__{input_hash[:10]}") + ".json"


class CachingProvider(BaseAIProvider):
    def __init__(self, cand: "common.Candidate", unit: str, mode: str = "run", force: bool = False,
                 cache_root: Optional[Path] = None, real_providers: Optional[List[BaseAIProvider]] = None,
                 sleep=asyncio.sleep, allow_spend: bool = False):
        super().__init__(model_name=cand.model or "mock-regulatory-v1")
        self.cand = cand
        self.unit = unit
        self.mode = mode
        self.force = force
        self.cache_root = cache_root or common.cache_dir()
        self._real = real_providers
        self._sleep = sleep
        self._turn = 0
        self.allow_spend = allow_spend
        # What happened, for the runner:
        self.calls_made = 0  # calls sent to a model in this run
        self.cache_hit = False
        self.miss = False
        self.stop_reason: Optional[str] = None
        self.captured: Optional[Dict[str, Any]] = None
        self.last_kind = "OK"
        self.cache_file: Optional[Path] = None
        self.prompt_hash = ""
        self.input_hash = ""

    # -- real providers -------------------------------------------------------------------------
    def _make_real(self) -> List[BaseAIProvider]:
        if self._real is not None:
            return self._real
        c = self.cand
        s = c.settings
        if c.provider == "mock":
            from backend.app.modules.analysis.providers.mock import MockAIProvider
            self._real = [MockAIProvider()]
        elif c.provider == "gemini":
            from backend.app.modules.analysis.providers.gemini import GeminiAIProvider
            from backend.app.modules.extraction import vision
            env = s.get("api_key_env")
            keys = [os.environ.get(env, "")] if env else vision.gemini_keys()
            keys = [k for k in keys if k]
            if not keys:
                raise common.ScorerError("No Gemini key found (GEMINI_API_KEY and GEMINI_EXTRA_API_KEYS in .env).")
            self._real = [GeminiAIProvider(model_name=c.model, api_key=k) for k in keys]
        else:
            from backend.app.modules.analysis.providers.openai_compat import OpenAICompatibleProvider
            env = s.get("api_key_env")
            key = os.environ.get(env, "") if env else (settings.OPENAI_COMPAT_API_KEY or "")
            if env and not key:
                raise common.ScorerError(f"The key variable {env} is not set.")
            self._real = [OpenAICompatibleProvider(
                model_name=c.model, base_url=s.get("base_url"), api_key=key, response_format=s.get("response_format"),
            )]
        return self._real

    def _key_of(self, prov: BaseAIProvider) -> str:
        return getattr(prov, "api_key", "") or ""

    def _exhausted(self, prov: BaseAIProvider) -> bool:
        from backend.app.modules.extraction import vision
        key = self._key_of(prov)
        until = vision._exhausted_until.get((key, self.cand.model))
        return bool(key and until and until > datetime.now(timezone.utc))

    # -- the call -------------------------------------------------------------------------------
    async def generate_structured_json(self, system_prompt: str, user_prompt: str,
                                       json_schema: Optional[Dict[str, Any]] = None,
                                       temperature: float = 0.0) -> LLMResponse:
        schema_text = json.dumps(json_schema or {}, sort_keys=True)
        self.prompt_hash = common.sha(f"{system_prompt}\n#schema {schema_text}\n#temp {temperature}")
        self.input_hash = common.sha(user_prompt)
        self.cache_file = self.cache_root / cache_key_name(self.unit, self.cand.name, self.cand.model,
                                                            self.prompt_hash, self.input_hash)
        if self.mode == "capture":
            self.captured = {"system": system_prompt, "user": user_prompt, "schema": json_schema, "temperature": temperature,
                             "prompt_hash": self.prompt_hash, "input_hash": self.input_hash,
                             "cache_file": self.cache_file.name}
            return self._failed("Request captured; no model call was made.")

        if self.cache_file.exists() and not self.force:
            try:
                entry = common.read_json(self.cache_file)
                resp = LLMResponse(**entry["response"])
                self.cache_hit = True
                self.last_kind = entry.get("kind", "OK")
                return resp
            except (OSError, ValueError, KeyError, TypeError):
                pass  # unreadable entry: treat as not saved

        if self.mode == "cache_only":
            self.miss = True
            return self._failed("No saved answer for this request.")

        if self.cand.paid and not self.allow_spend:
            self.stop_reason = "This candidate is paid. Price it first and run it as a batch with --yes-spend."
            return self._failed(self.stop_reason)

        return await self._call_real(system_prompt, user_prompt, json_schema, temperature)

    def _failed(self, message: str) -> LLMResponse:
        return LLMResponse(raw_content="", parsed_json=None, model_name=self.model_name, success=False, error=message)

    async def _call_real(self, system_prompt, user_prompt, json_schema, temperature) -> LLMResponse:
        provs = self._make_real()
        waited = 0.0
        while True:
            live = [p for p in provs if not self._exhausted(p)]
            if not live:
                self.stop_reason = (f"Every free key is used up for today on {self.cand.model}. "
                                    f"The quota comes back about {quota.reset_time_text()}.")
                return self._failed(self.stop_reason)
            busy_all = True
            for i in range(len(live)):
                prov = live[(self._turn + i) % len(live)]
                self.calls_made += 1
                resp = await prov.generate_structured_json(system_prompt, user_prompt, json_schema, temperature)
                if resp.success:
                    self._turn += i + 1
                    return self._save(resp, system_prompt, user_prompt)
                kind = classify_failure(resp)
                if kind == "daily":
                    from backend.app.modules.extraction import vision
                    key = self._key_of(prov)
                    if key:
                        vision.mark_key_exhausted(key, self.cand.model)
                        quota.save()
                    continue
                if kind == "busy":
                    continue
                if kind == "auth":
                    self.stop_reason = f"The model refused the key: {resp.error}"
                    return self._failed(self.stop_reason)
                busy_all = False
                self.last_kind = "ERROR"
                return resp  # a real failure: the runner records it for this row; nothing is saved
            if not [p for p in provs if not self._exhausted(p)]:
                continue  # the loop above will report the daily stop
            if busy_all:
                if waited >= MAX_BUSY_MINUTES * 60:
                    self.stop_reason = "The model service stayed busy or rate limited; stopping so nothing is recorded as a failure."
                    return self._failed(self.stop_reason)
                await self._sleep(BUSY_WAIT_SECONDS)
                waited += BUSY_WAIT_SECONDS

    def _save(self, resp: LLMResponse, system_prompt: str, user_prompt: str) -> LLMResponse:
        usable = isinstance(resp.parsed_json, dict) and bool(resp.parsed_json)
        self.last_kind = "OK" if usable else "EMPTY"
        entry = {
            "kind": self.last_kind,
            "unit": self.unit,
            "candidate": self.cand.name,
            "model": self.cand.model,
            "prompt_hash": self.prompt_hash,
            "input_hash": self.input_hash,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "response": resp.model_dump(),
        }
        common.write_json(self.cache_file, entry)
        return resp


def token_usage_of(entry_response: Dict[str, Any]) -> TokenUsage:
    return TokenUsage(**(entry_response.get("token_usage") or {}))
