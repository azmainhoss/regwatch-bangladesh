"""Background job that reads PENDING_VISION pages from their page image (DECISIONS.md 10).

Uploads and downloads never wait for Gemini: the ingest stores those pages empty with status
PENDING_VISION, and this job reads them later, one page and one call at a time.

- success: text and per-line boxes stored, status SUCCESS_VISION;
- no GEMINI_API_KEY: nothing is touched, the pages keep waiting;
- failure: the attempt is counted and the error kept; after VISION_MAX_ATTEMPTS failed jobs
  the page goes to a person (NEEDS_HUMAN_REVIEW). Its text stays empty either way.
Pages a person corrected are never touched.
"""
import asyncio
import re
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.documents.models import DocumentPage, DocumentVersion
from backend.app.modules.extraction.quality import ExtractionQualityAssessor
from backend.app.modules.extraction.service import (
    METHOD_VISION,
    STATUS_NEEDS_REVIEW,
    STATUS_PENDING_VISION,
    STATUS_VISION,
)
from backend.app.modules.extraction.vision import VisionResult, read_page_image, render_page_png

PageReader = Callable[[bytes], Awaitable[VisionResult]]


async def process_pending_vision_pages(
    db: AsyncSession,
    limit: Optional[int] = None,
    reader: Optional[PageReader] = None,
    version_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Reads waiting pages, oldest first (only one version's pages when version_id is given).
    Returns counts of what happened."""
    summary = {"read": 0, "failed": 0, "sent_to_review": 0, "waiting_no_key": 0}
    if reader is None:
        if not settings.GEMINI_API_KEY:
            pending = (await db.execute(
                select(DocumentPage.id).where(DocumentPage.quality_status == STATUS_PENDING_VISION)
            )).all()
            summary["waiting_no_key"] = len(pending)
            return summary
        reader = read_page_image

    query = (
        select(DocumentPage.id, DocumentVersion.storage_path)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .where(
            DocumentPage.quality_status == STATUS_PENDING_VISION,
            DocumentPage.is_human_corrected.is_(False),
        )
        .order_by(DocumentPage.created_at, DocumentPage.page_number)
    )
    if version_id is not None:
        query = query.where(DocumentPage.document_version_id == version_id)
    if limit:
        query = query.limit(limit)
    rows = (await db.execute(query)).all()

    pdf_cache: Dict[str, bytes] = {}
    for page_id, storage_path in rows:
        page = await db.get(DocumentPage, page_id)
        if page is None or page.quality_status != STATUS_PENDING_VISION or page.is_human_corrected:
            continue
        try:
            if storage_path not in pdf_cache:
                pdf_cache = {storage_path: storage_service.get_file_bytes(storage_path)}
            png = await asyncio.to_thread(render_page_png, pdf_cache[storage_path], page.page_number)
            result = await reader(png)
        except Exception as e:  # missing file, broken PDF, unexpected error: count it as a failed try
            result = VisionResult(success=False, error=f"{type(e).__name__}: {e}")

        if result.no_key:
            summary["waiting_no_key"] += 1
            break

        if result.success and result.text.strip():
            text = result.text.strip()
            page.raw_text = text
            page.ocr_text = text
            page.cleaned_text = re.sub(r"\n{3,}", "\n\n", text)
            page.line_boxes = result.line_boxes
            page.extraction_method = METHOD_VISION
            page.quality_status = STATUS_VISION
            page.quality_score = ExtractionQualityAssessor.assess_page(
                page_number=page.page_number, raw_text=text, extraction_method=METHOD_VISION
            ).quality_score
            page.vision_error = None
            summary["read"] += 1
        else:
            page.vision_attempts = (page.vision_attempts or 0) + 1
            page.vision_error = (result.error or "empty answer")[:2000]
            if page.vision_attempts >= settings.VISION_MAX_ATTEMPTS:
                page.quality_status = STATUS_NEEDS_REVIEW
                summary["sent_to_review"] += 1
            summary["failed"] += 1
            logger.warning(f"Page-image reading failed for page {page.page_number} ({page.vision_attempts} tries): {page.vision_error}")
        await db.commit()

    if any(summary[k] for k in ("read", "failed")):
        logger.info(f"Page-image reading job: {summary}")
    return summary


class VisionWorker:
    """Runs the page-image job every VISION_POLL_SECONDS, or sooner when kicked after an ingest."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory
        self._task: Optional[asyncio.Task] = None
        self._wake: Optional[asyncio.Event] = None
        self._running = False

    def kick(self) -> None:
        if self._wake is not None:
            self._wake.set()

    async def start(self) -> None:
        if self._running:
            return
        if self._session_factory is None:
            from backend.app.database.session import AsyncSessionLocal
            self._session_factory = AsyncSessionLocal
        self._running = True
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        logger.info("Page-image reading job started.")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                async with self._session_factory() as session:
                    await process_pending_vision_pages(session, limit=20)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Page-image reading job failed: {e}")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=settings.VISION_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            self._wake.clear()


vision_worker = VisionWorker()
