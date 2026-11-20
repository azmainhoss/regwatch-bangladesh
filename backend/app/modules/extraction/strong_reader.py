"""Last route for pages of new circulars that are still unread after both Gemini routes.

Order for every page: its own text layer -> Gemini page-image reading (main model, then the stronger
model on a sharper image) -> this module: one read of the page image by STRONG_READER_MODEL.
A page counts as unread when its reading failed, it has no text, or its text looks damaged
(text_layer_looks_damaged). If this last read fails too, the page stays READ_FAILED, the circular is
held from analysis (analysis/auto.py) and the platform team gets an alert ("pages could not be read").

Only circulars found by the live checker are handled here (archive pages are read by the normal job).
Each page gets one try; the result is recorded on the page (vision_error) so it is never retried in a loop.
Off while STRONG_READER_API_KEY or STRONG_READER_MODEL is empty: pages then go to the hold and the alert
without being marked as tried, so they are read as soon as a key is added, or by hand meanwhile
(scripts/held_pages.py).
"""
import asyncio
import base64
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.quality import ExtractionQualityAssessor, text_layer_looks_damaged
from backend.app.modules.extraction.vision import VisionResult, render_page_png

METHOD_STRONG = "STRONG_VISION"
STATUS_READ = "SUCCESS_VISION"
STATUS_READ_FAILED = "READ_FAILED"
UNREAD_STATUSES = ("NEEDS_HUMAN_REVIEW", "READ_FAILED")
LIVE_STATUS = "PUBLISHED_MACHINE_PROCESSED"
TRIED_MARK = "Last reading route:"

PROMPT = (
    "Transcribe this page of a Bangladesh Bank document exactly as printed.\n"
    "- Copy every line in reading order, in its original language and script (Bangla or English). "
    "Do not translate, summarise, correct or add anything.\n"
    "- Keep every number, date, amount, percentage and reference code exactly as printed, "
    "including Bangla digits.\n"
    "- For tables, give each row as one line with ' | ' between cells.\n"
    "- Write [illegible] for any part you cannot read.\n"
    "Reply with the page text only, no comments."
)

Reader = Callable[[bytes], Awaitable[VisionResult]]


def page_text_ok(text: Optional[str]) -> bool:
    """True when a page has text that does not look damaged."""
    text = (text or "").strip()
    if not text:
        return False
    return not text_layer_looks_damaged(ExtractionQualityAssessor.assess_page(1, text, "TEXT_LAYER"))


def page_is_read(page: Any) -> bool:
    """The rule analysis waits for: every page read (or corrected by a person) with usable text."""
    if page.is_human_corrected:
        return True
    return str(page.quality_status or "").startswith("SUCCESS") and page_text_ok(page.cleaned_text or page.raw_text)


def strong_reader_available() -> bool:
    return bool((settings.STRONG_READER_API_KEY or "").strip() and (settings.STRONG_READER_MODEL or "").strip())


async def read_page_image_strong(png: bytes) -> VisionResult:
    """One transcription of a page image by STRONG_READER_MODEL."""
    if not strong_reader_available():
        return VisionResult(success=False, error="no key for the last reading route", no_key=True)
    try:
        import anthropic
    except ImportError:
        return VisionResult(success=False, error="reader package not installed", no_key=True)
    client = anthropic.AsyncAnthropic(api_key=settings.STRONG_READER_API_KEY)
    try:
        response = await client.beta.messages.create(
            model=settings.STRONG_READER_MODEL,
            max_tokens=16000,
            output_config={"effort": "high"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.standard_b64encode(png).decode("ascii")}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
    except anthropic.RateLimitError as e:
        return VisionResult(success=False, error=f"busy: {e}", transient=True, model=settings.STRONG_READER_MODEL)
    except anthropic.APIStatusError as e:
        return VisionResult(success=False, error=f"HTTP {e.status_code}", model=settings.STRONG_READER_MODEL,
                            transient=e.status_code >= 500)
    except anthropic.APIConnectionError as e:
        return VisionResult(success=False, error=f"connection: {e}", transient=True, model=settings.STRONG_READER_MODEL)
    if response.stop_reason == "refusal":
        return VisionResult(success=False, error="declined", model=response.model)
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    if response.stop_reason == "max_tokens" or not text:
        return VisionResult(success=False, error=f"incomplete answer ({response.stop_reason})", model=response.model)
    return VisionResult(success=True, text=text, model=response.model)


async def unread_live_pages(db: AsyncSession) -> List[tuple]:
    """(page, storage_path, document) for pages of live circulars still unread and not yet tried here."""
    rows = (await db.execute(
        select(DocumentPage, DocumentVersion.storage_path, Document)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(Document.publication_status == LIVE_STATUS, Document.owner_user_id.is_(None),
               DocumentPage.is_human_corrected.is_(False),
               DocumentPage.quality_status != "PENDING_VISION")
    )).all()
    out = []
    for page, path, doc in rows:
        if page_is_read(page) or (page.vision_error or "").startswith(TRIED_MARK):
            continue
        out.append((page, path, doc))
    return out


async def _alert_held(db: AsyncSession, doc: Document, pages: List[int]) -> None:
    """Tells the platform team that a new circular is held because pages could not be read."""
    try:
        from backend.app.modules.alerts import emit as alerts_emit

        await alerts_emit.emit(
            db, kind="ADMIN_QUEUE", dedupe_key=f"ADMIN_QUEUE:pages:held:{doc.id}",
            document_id=doc.id, entity_type="admin_queue",
            payload={"queue": "pages", "count": len(pages), "document_id": str(doc.id), "pages": pages},
        )
    except Exception as e:  # the alert must never stop the reading
        logger.warning(f"Alert for held circular {doc.id} not sent: {type(e).__name__}: {e}")


async def rescue_unread_live_pages(db: AsyncSession, reader: Optional[Reader] = None) -> Dict[str, int]:
    """Gives every unread page of a live circular its last read. Returns counts."""
    reader = reader or read_page_image_strong
    summary = {"read": 0, "failed": 0, "held_circulars": 0}
    todo = await unread_live_pages(db)
    if not todo:
        return summary
    use_default = reader is read_page_image_strong
    pdfs: Dict[str, bytes] = {}
    failed_by_doc: Dict[UUID, tuple] = {}
    for page, path, doc in todo:
        if use_default and not strong_reader_available():
            result = VisionResult(success=False, error="no key for the last reading route", no_key=True)
        else:
            try:
                if path not in pdfs:
                    pdfs[path] = storage_service.get_file_bytes(path)
                png = await asyncio.to_thread(render_page_png, pdfs[path], page.page_number, settings.STRONG_READER_DPI)
                result = await reader(png)
            except Exception as e:
                result = VisionResult(success=False, error=f"{type(e).__name__}: {e}")
        if result.transient:
            continue  # busy: try again on the next round, nothing recorded
        if result.no_key:
            # No last route yet: hold it, but do not count a try, so it is read once a key is added.
            page.quality_status = STATUS_READ_FAILED
            page.vision_error = f"Waiting for the last reading route ({result.error})"[:2000]
            failed_by_doc.setdefault(doc.id, (doc, []))[1].append(page.page_number)
            summary["failed"] += 1
        elif result.success and page_text_ok(result.text):
            text = result.text.strip()
            if page.extraction_method == "TEXT_LAYER" and page.raw_text and not page.native_text:
                page.native_text = page.raw_text  # keep the text layer aside, as the image reader does
            page.raw_text = text
            page.ocr_text = text
            page.cleaned_text = re.sub(r"\n{3,}", "\n\n", text)
            page.line_boxes = None
            page.extraction_method = METHOD_STRONG
            page.quality_status = STATUS_READ
            page.quality_score = ExtractionQualityAssessor.assess_page(
                page_number=page.page_number, raw_text=text, extraction_method=METHOD_STRONG).quality_score
            page.vision_error = f"{TRIED_MARK} read by {result.model or settings.STRONG_READER_MODEL}"
            summary["read"] += 1
        else:
            why = result.error or ("text still looks damaged" if result.success else "empty answer")
            page.quality_status = STATUS_READ_FAILED
            page.vision_error = f"{TRIED_MARK} failed ({why})"[:2000]
            summary["failed"] += 1
            failed_by_doc.setdefault(doc.id, (doc, []))[1].append(page.page_number)
        page.updated_at = datetime.now(timezone.utc)
    for doc, pages in failed_by_doc.values():
        await _alert_held(db, doc, sorted(pages))
        summary["held_circulars"] += 1
        logger.warning(f"New circular {doc.reference_number or doc.id} held from analysis: "
                       f"page(s) {sorted(pages)} could not be read.")
    await db.commit()
    return summary
