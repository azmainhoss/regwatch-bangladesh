"""Runs document analysis in the background so the web request returns at once.

POST /documents/{id}/analyze starts a job and answers "RUNNING" straight away. The circular page
asks GET /documents/{id}/analysis-status every few seconds and redraws when the job is DONE or
FAILED. The durable record of each run is the analysis lease (ACTIVE / RELEASED / FAILED); the
plain-language failure reason is kept in memory for this process.

When the page texts and the model are the same as the last saved analysis, nothing is sent to the
model again (state UNCHANGED), unless the caller forces a new run.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.core.logging import logger
from backend.app.modules.analysis.models import AnalysisLease, DocumentAnalysis

RUNNING = "RUNNING"
DONE = "DONE"
FAILED = "FAILED"
UNCHANGED = "UNCHANGED"
IDLE = "IDLE"
WAITING_FOR_PAGES = "WAITING_FOR_PAGES"

_tasks: Dict[UUID, asyncio.Task] = {}
_info: Dict[UUID, Dict[str, Any]] = {}


def plain_reason(error: str) -> str:
    """A failure reason a person can read, with no codes."""
    e = (error or "").lower()
    if "already in progress" in e or "locked by worker" in e:
        return "An analysis is already running for this circular."
    if "429" in e or "quota" in e or "rate limit" in e:
        return "The AI service's free limit is used up for now. Try again later."
    if "503" in e or "overloaded" in e or "could not be reached" in e or "timeout" in e or "busy" in e:
        return "The AI service is busy right now. Try again in a few minutes."
    if "not configured" in e or "not set" in e or "authentication" in e:
        return "The AI service is not set up on the server."
    if "still being read" in e:
        return "Some pages are still being read. The analysis can run once they are done."
    if "pages are missing" in e or "no version" in e:
        return "This circular has no readable pages yet."
    return "The analysis could not finish. Earlier results are kept."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(session_factory, document_id: UUID, provider_name: Optional[str], force_human_review: bool) -> None:
    from backend.app.modules.analysis.service import AnalysisService
    try:
        async with session_factory() as db:
            await AnalysisService.analyze_document_version(
                db=db,
                document_id=document_id,
                provider_name=provider_name,
                force_human_review=force_human_review,
            )
        _info[document_id] = {"state": DONE, "finished_at": _now(), "message": None,
                              "started_at": _info.get(document_id, {}).get("started_at")}
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Background analysis failed for document {document_id}: {type(e).__name__}")
        _info[document_id] = {"state": FAILED, "finished_at": _now(), "message": plain_reason(str(e)),
                              "started_at": _info.get(document_id, {}).get("started_at")}
    finally:
        _tasks.pop(document_id, None)


async def unchanged_since_last_run(db, document_id: UUID, provider_name: Optional[str]) -> bool:
    """True when the latest saved analysis used the same model on the same page texts."""
    from backend.app.modules.analysis.providers.factory import get_ai_provider
    from backend.app.modules.analysis.service import input_fingerprint, pages_payload_for
    from backend.app.modules.documents.models import Document, DocumentVersion

    doc = await db.get(Document, document_id)
    if not doc or not doc.current_version_id:
        return False
    latest = (await db.execute(
        select(DocumentAnalysis)
        .where(DocumentAnalysis.document_version_id == doc.current_version_id)
        .order_by(DocumentAnalysis.created_at.desc())
        .limit(1)
    )).scalars().first()
    if not latest or not isinstance(latest.structured_payload, dict):
        return False
    saved = latest.structured_payload.get("input_sha256")
    if not saved:
        return False
    version = (await db.execute(
        select(DocumentVersion).options(selectinload(DocumentVersion.pages))
        .where(DocumentVersion.id == doc.current_version_id)
    )).scalar_one_or_none()
    if not version or not version.pages:
        return False
    try:
        model = get_ai_provider(provider_name).model_name
    except ValueError:
        return False
    return saved == input_fingerprint(model, pages_payload_for(version))


def start(document_id: UUID, provider_name: Optional[str] = None, force_human_review: bool = False,
          session_factory=None) -> Dict[str, Any]:
    """Starts a background analysis unless one is already running in this process."""
    if document_id in _tasks and not _tasks[document_id].done():
        return status_from_memory(document_id)
    if session_factory is None:
        from backend.app.database.session import AsyncSessionLocal
        session_factory = AsyncSessionLocal
    _info[document_id] = {"state": RUNNING, "started_at": _now(), "finished_at": None, "message": None}
    _tasks[document_id] = asyncio.create_task(_run(session_factory, document_id, provider_name, force_human_review))
    return status_from_memory(document_id)


def mark_waiting_for_pages(document_id: UUID, waiting: int) -> Dict[str, Any]:
    _info[document_id] = {"state": WAITING_FOR_PAGES, "started_at": None, "finished_at": _now(),
                          "message": f"{waiting} {'page is' if waiting == 1 else 'pages are'} still being read. "
                                     "The analysis can run once they are done."}
    return status_from_memory(document_id)


def mark_unchanged(document_id: UUID) -> Dict[str, Any]:
    _info[document_id] = {"state": UNCHANGED, "started_at": None, "finished_at": _now(),
                          "message": "Nothing changed since the last analysis, so it was not run again."}
    return status_from_memory(document_id)


def status_from_memory(document_id: UUID) -> Dict[str, Any]:
    info = dict(_info.get(document_id) or {"state": IDLE, "started_at": None, "finished_at": None, "message": None})
    info["document_id"] = str(document_id)
    return info


async def status(db, document_id: UUID) -> Dict[str, Any]:
    """This process's view first; otherwise the durable lease record (survives a restart)."""
    if document_id in _info:
        return status_from_memory(document_id)
    lease = (await db.execute(select(AnalysisLease).where(AnalysisLease.document_id == document_id))).scalar_one_or_none()
    out = {"document_id": str(document_id), "state": IDLE, "started_at": None, "finished_at": None, "message": None}
    if lease is None:
        return out
    expires_at = lease.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if lease.status == "ACTIVE" and expires_at and expires_at > datetime.now(timezone.utc):
        out.update(state=RUNNING, started_at=lease.acquired_at.isoformat() if lease.acquired_at else None)
    elif lease.status == "FAILED":
        out.update(state=FAILED, message="The last analysis could not finish. Earlier results are kept.",
                   finished_at=lease.heartbeat_at.isoformat() if lease.heartbeat_at else None)
    return out


async def wait(document_id: UUID) -> None:
    """Waits for this document's job to end (used by tests and scripts)."""
    task = _tasks.get(document_id)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
