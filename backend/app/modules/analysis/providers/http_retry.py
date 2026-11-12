"""Shared HTTP posting with growing waits for the analysis providers.

429 (rate limit / quota) and 5xx-busy replies (500, 502, 503, 504) and network errors are retried
up to `max_retries` times. The wait starts at `base_seconds` and doubles each time, capped at
`max_seconds`; a Retry-After header is used instead when the server sends one (also capped).
After the last retry the caller gets the last reply or error back and reports a clear failure.
"""
import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from backend.app.core.logging import logger

RETRY_STATUSES = (429, 500, 502, 503, 504)

SleepFn = Callable[[float], Awaitable[None]]


@dataclass
class PostOutcome:
    response: Optional[httpx.Response]  # last reply received (None if only network errors)
    network_error: Optional[str]  # set when the last attempt failed without a reply
    attempts: int


def backoff_delay(attempt: int, base_seconds: float, max_seconds: float, resp: Optional[httpx.Response] = None) -> float:
    """Wait before retry number `attempt + 1` (attempt is 0-based)."""
    if resp is not None:
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return max(0.0, min(float(header), max_seconds))
            except ValueError:
                pass
    return min(base_seconds * (2 ** attempt), max_seconds)


async def post_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    *,
    label: str,
    max_retries: int,
    base_seconds: float,
    max_seconds: float,
    sleep: SleepFn = asyncio.sleep,
    redact: Optional[str] = None,
) -> PostOutcome:
    max_retries = max(0, int(max_retries))
    last_resp: Optional[httpx.Response] = None
    last_net: Optional[str] = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            msg = f"{type(e).__name__}: {e}"
            last_net = redact_text(msg, redact)
            last_resp = None
            if attempt < max_retries:
                delay = backoff_delay(attempt, base_seconds, max_seconds)
                logger.warning(f"{label}: network error ({last_net}); retry {attempt + 1}/{max_retries} in {delay:.0f} s.")
                await sleep(delay)
                continue
            return PostOutcome(response=None, network_error=last_net, attempts=attempt + 1)

        last_resp, last_net = resp, None
        if resp.status_code in RETRY_STATUSES and attempt < max_retries:
            delay = backoff_delay(attempt, base_seconds, max_seconds, resp)
            logger.warning(f"{label}: HTTP {resp.status_code}; retry {attempt + 1}/{max_retries} in {delay:.0f} s.")
            await sleep(delay)
            continue
        return PostOutcome(response=resp, network_error=None, attempts=attempt + 1)
    return PostOutcome(response=last_resp, network_error=last_net, attempts=max_retries + 1)


def redact_text(text: str, secret: Optional[str]) -> str:
    if secret and text:
        return text.replace(secret, "[REDACTED]")
    return text


def parse_json_text(raw_text: str) -> Any:
    """Parses a JSON answer, tolerating ```json fences around it. Raises json.JSONDecodeError."""
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned.strip())
