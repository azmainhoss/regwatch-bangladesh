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


_lock: Optional[asyncio.Lock] = None
_lock_loop = None


def _call_lock() -> asyncio.Lock:
    """One vision call at a time per process (the lock is remade if the event loop changes)."""
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:
        _lock, _lock_loop = asyncio.Lock(), loop
    return _lock


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
    url = f"{GEMINI_URL}/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.VISION_TIMEOUT_SECONDS)
    try:
        async with _call_lock():
            last_error = "no reply"
            for attempt in range(settings.VISION_MAX_RETRIES + 1):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as e:
                    last_error = f"network error: {type(e).__name__}: {e}"
                    if attempt < settings.VISION_MAX_RETRIES:
                        await sleep(settings.VISION_RETRY_BASE_SECONDS * (2 ** attempt))
                        continue
                    break

                if resp.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < settings.VISION_MAX_RETRIES:
                        delay = _retry_delay(resp, attempt)
                        logger.info(f"Gemini vision busy ({resp.status_code}); retrying in {delay:.0f} s.")
                        await sleep(delay)
                        continue
                    break

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    break

                try:
                    lines = parse_vision_reply(resp.json())
                except (ValueError, json.JSONDecodeError) as e:
                    last_error = f"unusable answer: {e}"
                    break
                text = "\n".join(line["text"] for line in lines)
                return VisionResult(success=True, text=text, line_boxes=lines, model=model)
            return VisionResult(success=False, error=last_error, model=model)
    finally:
        if own_client:
            await client.aclose()
