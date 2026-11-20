"""Reads a page image with Gemini (DECISIONS.md 10).

Every Bangla, legacy-font or scanned page is rendered to a 200 dpi PNG and sent to Gemini
(VISION_MODEL, default gemini-3.5-flash-lite) with one fixed prompt. Gemini returns the exact
transcription line by line, each line with a box (box_2d: [ymin, xmin, ymax, xmax], 0-1000).

Only one call runs at a time in a process. 429 and 503 replies are retried with backoff.
Without GEMINI_API_KEY, or when the call fails, the caller keeps the page as PENDING_VISION
with empty text so a later job can try again. Nothing is ever filled in with placeholder text.
"""
import asyncio
import base64
import itertools
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
import pymupdf as fitz

from backend.app.core.config import settings
from backend.app.core.logging import logger

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRY_STATUSES = (429, 503)

VISION_PROMPT = (
    "Transcribe this page of a Bangladesh Bank document exactly as printed.\n"
    "- Copy every line in reading order, in its original language and script (Bangla or English). "
    "Do not translate, summarise, correct or add anything.\n"
    "- Keep every number, date, amount, percentage and reference code exactly as printed, "
    "including Bangla digits.\n"
    "- For tables, give each row as one line with ' | ' between cells.\n"
    "- Write [illegible] for any part you cannot read.\n"
    "- For each line, give its box_2d as [ymin, xmin, ymax, xmax] on a 0-1000 scale of the page.\n"
    "Return only the JSON."
)

RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "text": {"type": "STRING"},
                    "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                },
                "required": ["text", "box_2d"],
            },
        }
    },
    "required": ["lines"],
}


@dataclass
class VisionResult:
    success: bool
    text: str = ""
    line_boxes: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    model: Optional[str] = None
    no_key: bool = False
    # The service was busy, rate-limited or out of today's quota: not the page's fault, so the
    # page keeps waiting and no failed try is counted.
    transient: bool = False
    quota_exhausted: bool = False
    # The answer of a call made with `read_images_json`: the JSON the model returned.
    data: Any = None
    # True when no request was made at all (every key had used up its quota for the day already).
    not_sent: bool = False


_lock: Optional[asyncio.Lock] = None
_lock_loop = None


_key_gates: dict = {}
# Keys that used up today's free quota, with the time the quota comes back (UTC).
_exhausted_until: dict = {}


def _next_quota_reset():
    """Free daily quotas reset at midnight Pacific time; 08:05 UTC is safely after it."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    reset = now.replace(hour=8, minute=5, second=0, microsecond=0)
    if reset <= now:
        reset += timedelta(days=1)
    return reset


def mark_key_exhausted(api_key: str, model: Optional[str] = None) -> None:
    """Free daily quotas are counted per key and per model, so the rest is noted for that pair only."""
    _exhausted_until[(api_key, model or settings.VISION_MODEL)] = _next_quota_reset()


def available_gemini_keys(model: Optional[str] = None) -> list:
    """The keys that still have quota today for this model (the page-reading model by default)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    model = model or settings.VISION_MODEL
    return [k for k in gemini_keys() if not (_exhausted_until.get((k, model)) and _exhausted_until[(k, model)] > now)]


def _is_daily_quota(resp) -> bool:
    body = (resp.text or "")[:4000]
    return resp.status_code == 429 and ("PerDay" in body or "per day" in body.lower())


def gemini_keys() -> list:
    """GEMINI_API_KEY first, then any extra keys, without repeats."""
    keys = [settings.GEMINI_API_KEY] if settings.GEMINI_API_KEY else []
    for k in (settings.GEMINI_EXTRA_API_KEYS or "").split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def _call_lock(api_key: str = "") -> asyncio.Semaphore:
    """At most VISION_CALLS_PER_KEY calls at once per key (remade if the event loop changes)."""
    global _lock_loop
    loop = asyncio.get_running_loop()
    if _lock_loop is not loop:
        _key_gates.clear()
        _lock_loop = loop
    gate = _key_gates.get(api_key)
    if gate is None:
        gate = asyncio.Semaphore(max(1, settings.VISION_CALLS_PER_KEY))
        _key_gates[api_key] = gate
    return gate


def render_page_png(pdf_bytes: bytes, page_number: int, dpi: Optional[int] = None) -> bytes:
    """Renders one 1-indexed page to PNG bytes."""
    dpi = dpi or settings.VISION_DPI
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")


def _clean_box(box: Any) -> Optional[List[int]]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        values = [max(0, min(1000, int(round(float(v))))) for v in box]
    except (TypeError, ValueError):
        return None
    return values


def parse_vision_reply(reply: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pulls the lines out of a Gemini generateContent reply. Raises ValueError if unusable."""
    candidates = reply.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    raw = "".join(p.get("text", "") for p in parts).strip()
    if not raw:
        raise ValueError(f"Gemini returned an empty answer (finishReason={candidates[0].get('finishReason')}).")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    data = json.loads(raw)
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise ValueError("Gemini answer has no 'lines' list.")
    out = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).rstrip()
        if not text.strip():
            continue
        out.append({"text": text, "box_2d": _clean_box(item.get("box_2d"))})
    if not out:
        raise ValueError("Gemini answer has no text lines.")
    return out


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), 300.0)
        except ValueError:
            pass
    return settings.VISION_RETRY_BASE_SECONDS * (2 ** attempt)


async def _generate(
    payload: Dict[str, Any],
    api_key: str,
    model: str,
    client: Optional[httpx.AsyncClient],
    sleep: Callable[[float], Awaitable[None]],
):
    """Posts one generateContent request with this key. Returns (reply JSON, None) on success or (None, failed VisionResult).

    Takes the key's place at the gate, retries 429 and 503 with backoff, and rests the key for the day
    on a daily-quota reply (for this model only).
    """
    url = f"{GEMINI_URL}/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.VISION_TIMEOUT_SECONDS)
    try:
        async with _call_lock(api_key):
            last_error = "no reply"
            busy = False
            for attempt in range(settings.VISION_MAX_RETRIES + 1):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as e:
                    last_error = f"network error: {type(e).__name__}: {e}"
                    busy = True
                    if attempt < settings.VISION_MAX_RETRIES:
                        await sleep(settings.VISION_RETRY_BASE_SECONDS * (2 ** attempt))
                        continue
                    break

                if _is_daily_quota(resp):
                    mark_key_exhausted(api_key, model)
                    logger.info("A Gemini key used up today's free quota; it rests until the daily reset.")
                    return None, VisionResult(success=False, error="daily limit reached", model=model,
                                              transient=True, quota_exhausted=True)
                if resp.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {resp.status_code}"
                    busy = True
                    if attempt < settings.VISION_MAX_RETRIES:
                        delay = _retry_delay(resp, attempt)
                        logger.info(f"Gemini vision busy ({resp.status_code}); retrying in {delay:.0f} s.")
                        await sleep(delay)
                        continue
                    break

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    busy = False
                    break

                try:
                    return resp.json(), None
                except ValueError as e:
                    last_error = f"unusable answer: {e}"
                    busy = False
                    break
            return None, VisionResult(success=False, error=last_error, model=model, transient=busy)
    finally:
        if own_client:
            await client.aclose()


async def read_page_image(
    png_bytes: bytes,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> VisionResult:
    """Sends one page image to Gemini and returns its lines, text and boxes."""
    api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
    model = model or settings.VISION_MODEL
    if not api_key:
        return VisionResult(success=False, error="GEMINI_API_KEY is not set.", model=model, no_key=True)

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png_bytes).decode("ascii")}},
                {"text": VISION_PROMPT},
            ],
        }],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    reply, failed = await _generate(payload, api_key, model, client, sleep)
    if failed is not None:
        return failed
    try:
        lines = parse_vision_reply(reply)
    except (ValueError, json.JSONDecodeError) as e:
        return VisionResult(success=False, error=f"unusable answer: {e}", model=model, transient=False)
    text = "\n".join(line["text"] for line in lines)
    return VisionResult(success=True, text=text, line_boxes=lines, model=model)


_key_turn = itertools.count()


def parse_json_reply(reply: Dict[str, Any]) -> Any:
    """The JSON a Gemini reply carries as text. Raises ValueError if there is none."""
    candidates = reply.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    raw = "".join(p.get("text", "") for p in parts).strip()
    if not raw:
        raise ValueError(f"Gemini returned an empty answer (finishReason={candidates[0].get('finishReason')}).")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


async def read_images_json(
    images: List[bytes],
    prompt: str,
    schema: Dict[str, Any],
    model: str,
    api_key: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> VisionResult:
    """Sends several images and one instruction in a single call; the JSON answer comes back in `data`.

    Uses the same key rotation, per-key gates, retry and daily-quota handling as page reading. Without
    `api_key` it rotates over the keys that still have quota today for this model; a key that runs out
    is rested (for this model only) and the next one is tried. Busy and out-of-quota answers are
    `transient`: the caller counts no failed try.
    """
    if api_key is not None:
        keys = [api_key] if api_key else []
    else:
        keys = available_gemini_keys(model)
        if keys:
            turn = next(_key_turn) % len(keys)
            keys = keys[turn:] + keys[:turn]
        elif gemini_keys():
            return VisionResult(success=False, error="daily limit reached", model=model, transient=True,
                                quota_exhausted=True, not_sent=True)
    if not keys:
        return VisionResult(success=False, error="GEMINI_API_KEY is not set.", model=model, no_key=True)

    parts: List[Dict[str, Any]] = [
        {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png).decode("ascii")}} for png in images
    ]
    parts.append({"text": prompt})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json", "responseSchema": schema},
    }
    last = VisionResult(success=False, error="no reply", model=model, transient=True)
    for key in keys:
        reply, failed = await _generate(payload, key, model, client, sleep)
        if failed is None:
            try:
                return VisionResult(success=True, data=parse_json_reply(reply), model=model)
            except (ValueError, json.JSONDecodeError) as e:
                return VisionResult(success=False, error=f"unusable answer: {e}", model=model, transient=False)
        last = failed
        if not failed.quota_exhausted:
            return failed
    return last
