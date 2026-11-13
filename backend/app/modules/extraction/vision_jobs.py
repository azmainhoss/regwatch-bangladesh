"""Background job that reads PENDING_VISION pages from their page image (DECISIONS.md 10).

Uploads and downloads never wait for Gemini: the ingest stores those pages empty with status
PENDING_VISION, and this job reads them as soon as it is woken: a few pages at once, rotating over
the Gemini keys (at most VISION_CALLS_PER_KEY calls at once on each key).

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
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.quality import ExtractionQualityAssessor
from backend.app.modules.extraction.service import (
    METHOD_VISION,
    STATUS_NEEDS_REVIEW,
    STATUS_PENDING_VISION,
    STATUS_VISION,
)
from backend.app.modules.extraction.vision import VisionResult, available_gemini_keys, read_page_image, render_page_png

# While the always-on reader (backend/scripts/read_pages.py) runs, it keeps this file fresh and
# the web app's own job stands aside, so no page is read twice.
from pathlib import Path as _Path
PAGE_READER_LOCK = _Path("data") / "page_reader.lock"


def page_reader_running() -> bool:
    import time
    try:
        return time.time() - PAGE_READER_LOCK.stat().st_mtime < 900
    except OSError:
        return False


PageReader = Callable[[bytes], Awaitable[VisionResult]]


async def process_pending_vision_pages(
    db: AsyncSession,
    limit: Optional[int] = None,
    reader: Optional[PageReader] = None,
    version_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Reads waiting pages, oldest first (only one version's pages when version_id is given).
    Returns counts of what happened."""
    summary = {"read": 0, "failed": 0, "sent_to_review": 0, "waiting_no_key": 0, "waiting_busy": 0,
               "batch_full": False, "out_of_quota": False}
    default_reader = False
    if reader is None:
        if not settings.GEMINI_API_KEY:
            pending = (await db.execute(
                select(DocumentPage.id).where(DocumentPage.quality_status == STATUS_PENDING_VISION)
            )).all()
            summary["waiting_no_key"] = len(pending)
            return summary
        reader = read_page_image
    default_reader = reader is read_page_image

    query = (
        select(DocumentPage.id, DocumentVersion.storage_path)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .where(
            DocumentPage.quality_status == STATUS_PENDING_VISION,
            DocumentPage.is_human_corrected.is_(False),
        )
        .join(Document, Document.id == DocumentVersion.document_id)
        # Newest circulars first, so a new circular is never stuck behind the old archive.
        .order_by(Document.publication_date.desc(), DocumentPage.created_at, DocumentPage.page_number)
    )
    if version_id is not None:
        query = query.where(DocumentPage.document_version_id == version_id)
    if limit:
        query = query.limit(limit)
    rows = (await db.execute(query)).all()
    summary["batch_full"] = bool(limit) and len(rows) >= limit

    keys = available_gemini_keys() if default_reader else []
    if default_reader and not keys:
        summary["out_of_quota"] = True
        return summary
    parallel = max(1, min(settings.VISION_MAX_PARALLEL, max(1, len(keys)) * max(1, settings.VISION_CALLS_PER_KEY)))
    pdf_cache: Dict[str, bytes] = {}

    async def _read(slot: int, page_number: int, storage_path: str) -> VisionResult:
        try:
            if storage_path not in pdf_cache:
                pdf_cache[storage_path] = storage_service.get_file_bytes(storage_path)
            png = await asyncio.to_thread(render_page_png, pdf_cache[storage_path], page_number)
            if default_reader and keys:
                live = available_gemini_keys() or keys
                return await read_page_image(png, api_key=live[slot % len(live)])
            return await reader(png)
        except Exception as e:  # missing file, broken PDF, unexpected error: count it as a failed try
            return VisionResult(success=False, error=f"{type(e).__name__}: {e}")

    stop = False
    for start in range(0, len(rows), parallel):
        batch = []
        for page_id, storage_path in rows[start:start + parallel]:
            page = await db.get(DocumentPage, page_id)
            if page is None or page.quality_status != STATUS_PENDING_VISION or page.is_human_corrected:
                continue
            batch.append((page, storage_path))
        if not batch:
            continue
        results = await asyncio.gather(*[
            _read(i, page.page_number, path) for i, (page, path) in enumerate(batch)
        ])
        for (page, _path), result in zip(batch, results):
            if result.no_key:
                summary["waiting_no_key"] += 1
                stop = True
                continue
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
            elif result.transient:
                # Busy, rate-limited or out of quota: the page keeps waiting, no failed try counted.
                summary["waiting_busy"] += 1
                if result.quota_exhausted and default_reader and not available_gemini_keys():
                    summary["out_of_quota"] = True
                    stop = True
            else:
                page.vision_attempts = (page.vision_attempts or 0) + 1
                page.vision_error = (result.error or "empty answer")[:2000]
                if page.vision_attempts >= settings.VISION_MAX_ATTEMPTS:
                    page.quality_status = STATUS_NEEDS_REVIEW
                    summary["sent_to_review"] += 1
                summary["failed"] += 1
                logger.warning(f"Page-image reading failed for page {page.page_number} ({page.vision_attempts} tries): {page.vision_error}")
        # Commit after each batch, so the circular page shows the new text straight away.
        await db.commit()
        if stop:
            break

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
                if page_reader_running():
                    summary = {}
                else:
                    async with self._session_factory() as session:
                        summary = await process_pending_vision_pages(session, limit=20)
                # A backlog (such as the archive) is read batch after batch without waiting,
                # until it is done or every key is out of today's quota.
                if summary.get("read"):
                    # New circulars from the live checker are analysed once all their pages are read.
                    from backend.app.modules.analysis.auto import analyze_ready_live_circulars
                    await analyze_ready_live_circulars(self._session_factory)
                if summary.get("batch_full") and not summary.get("out_of_quota") and summary.get("read"):
                    continue
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
