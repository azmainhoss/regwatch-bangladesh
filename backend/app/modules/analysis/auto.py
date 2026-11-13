"""Analysis waits until every page of a circular has been read.

- `pages_waiting` counts pages still queued for image reading; analysis refuses to run while any wait,
  so it never works on empty Bangla or scanned pages.
- `analyze_ready_live_circulars` runs after page reading: new circulars found by the live checker
  (status PUBLISHED_MACHINE_PROCESSED, shared library, no analysis yet) are analysed as soon as all
  their pages are read. Archive circulars (status EXTRACTED) are never analysed automatically.
"""
import time
from typing import Dict, List
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.modules.analysis.models import DocumentAnalysis
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.extraction.service import STATUS_PENDING_VISION

LIVE_STATUS = "PUBLISHED_MACHINE_PROCESSED"
RETRY_AFTER_SECONDS = 3600
_last_try: Dict[UUID, float] = {}


async def pages_waiting(db: AsyncSession, version_id) -> int:
    return (await db.execute(
        select(func.count()).select_from(DocumentPage).where(
            DocumentPage.document_version_id == version_id,
            DocumentPage.quality_status == STATUS_PENDING_VISION,
            DocumentPage.is_human_corrected.is_(False),
        )
    )).scalar_one()


async def ready_live_circulars(db: AsyncSession, limit: int = 3) -> List[UUID]:
    waiting = exists().where(
        DocumentPage.document_version_id == Document.current_version_id,
        DocumentPage.quality_status == STATUS_PENDING_VISION,
        DocumentPage.is_human_corrected.is_(False),
    )
    analysed = exists().where(DocumentAnalysis.document_version_id == Document.current_version_id)
    rows = (await db.execute(
        select(Document.id)
        .where(
            Document.publication_status == LIVE_STATUS,
            Document.owner_user_id.is_(None),
            Document.current_version_id.is_not(None),
            ~waiting,
            ~analysed,
        )
        .order_by(Document.publication_date.desc())
        .limit(limit * 4)
    )).scalars().all()
    now = time.time()
    return [d for d in rows if now - _last_try.get(d, 0) > RETRY_AFTER_SECONDS][:limit]


async def analyze_ready_live_circulars(session_factory, limit: int = 3) -> int:
    """Analyses live-found circulars whose pages are now all read. Returns how many were analysed."""
    from backend.app.modules.analysis.service import AnalysisService

    async with session_factory() as db:
        ids = await ready_live_circulars(db, limit)
    done = 0
    for doc_id in ids:
        _last_try[doc_id] = time.time()
        try:
            async with session_factory() as db:
                await AnalysisService.analyze_document_version(db=db, document_id=doc_id)
            done += 1
            logger.info(f"Analysed new circular {doc_id} after its pages were read.")
        except Exception as e:
            logger.warning(f"Analysis of new circular {doc_id} deferred: {type(e).__name__}")
    return done


DEFAULT_PAGES_PER_MINUTE = 6.0


async def reading_status(db: AsyncSession, doc: Document) -> dict:
    """What a circular is waiting for, in plain terms, with a rough time estimate."""
    import json
    from datetime import datetime, timedelta, timezone

    from backend.app.core.config import settings
    from backend.app.modules.documents.models import DocumentVersion
    from backend.app.modules.extraction.vision import available_gemini_keys, gemini_keys
    from backend.app.modules.extraction.vision_jobs import PAGE_READER_LOCK, page_reader_running

    version_id = doc.current_version_id
    total = (await db.execute(select(func.count()).select_from(DocumentPage)
                              .where(DocumentPage.document_version_id == version_id))).scalar_one()
    waiting = await pages_waiting(db, version_id) if version_id else 0
    out = {"document_id": str(doc.id), "pages_total": total, "pages_waiting": waiting,
           "pages_ahead": 0, "minutes_left": 0, "state": "DONE", "resumes_at": None,
           "analysis_after": "AUTOMATIC" if doc.publication_status == LIVE_STATUS else
                             ("LATER" if doc.publication_status == "EXTRACTED" else "ON_REQUEST")}
    if not waiting:
        return out

    # Pages of newer circulars are read first.
    ahead = (await db.execute(
        select(func.count()).select_from(DocumentPage)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentPage.quality_status == STATUS_PENDING_VISION,
               DocumentPage.is_human_corrected.is_(False),
               Document.publication_date > doc.publication_date)
    )).scalar_one()
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent = (await db.execute(select(func.count()).select_from(DocumentPage).where(
        DocumentPage.quality_status == "SUCCESS_VISION", DocumentPage.updated_at >= since))).scalar_one()
    rate = max(recent / 15.0, DEFAULT_PAGES_PER_MINUTE if recent == 0 else 1.0)
    out.update(pages_ahead=ahead, minutes_left=max(1, round((ahead + waiting) / rate)),
               state="READING" if ahead < 20 else "QUEUED")

    # Out of today's free reading quota, or nothing running to read pages.
    reader = {}
    if page_reader_running():
        try:
            reader = json.loads(PAGE_READER_LOCK.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reader = {}
        if reader.get("state") == "waiting for quota":
            out.update(state="PAUSED_DAILY_LIMIT", resumes_at=reader.get("quota_back_at"))
    elif not gemini_keys():
        out.update(state="PAUSED_NO_KEY")
    elif not (settings.VISION_WORKER_ENABLED or settings.SCHEDULER_ENABLED):
        out.update(state="PAUSED_NOT_RUNNING")
    elif not available_gemini_keys():
        from backend.app.modules.extraction.vision import _next_quota_reset
        out.update(state="PAUSED_DAILY_LIMIT", resumes_at=_next_quota_reset().isoformat())
    return out
