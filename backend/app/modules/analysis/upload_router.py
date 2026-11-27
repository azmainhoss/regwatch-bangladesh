"""Phase 1 analysis upload: the laptop analyses new circulars with Claude and sends the answers here.

The laptop never copies the database. It asks which circulars wait for analysis, fetches one circular's text with
sentence IDs, and uploads that one answer. The answer goes through the same checks and the same analysis pipeline
as a live model's answer (manual_answers.py), so every point is checked before readers see it.

Auth: a machine token (ANALYSIS_UPLOAD_TOKEN, at least 32 characters) sent as "Authorization: Bearer <token>".
Without a valid token configured the routes answer 404, as if they did not exist. User logins never work here.
"""
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.database.session import get_async_db
from backend.app.modules.analysis.manual_answers import MODEL_NAME, AnswerFileProvider, check_answer
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.analysis.service import AnalysisService, pages_payload_for
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.extraction.quality import ExtractionQualityAssessor, text_layer_looks_damaged
from backend.app.modules.identity.deps import get_current_superuser
from backend.app.modules.identity.models import User

router = APIRouter(prefix="/analysis-upload", tags=["Analysis upload (Phase 1)"])

MAX_ANSWER_BYTES = 2_000_000  # the longest answers so far are about 100 KB
MIN_TOKEN_LENGTH = 32
STALE_AFTER_HOURS = 24


def _configured_token() -> Optional[str]:
    raw = settings.ANALYSIS_UPLOAD_TOKEN.get_secret_value() if settings.ANALYSIS_UPLOAD_TOKEN else ""
    return raw if len(raw) >= MIN_TOKEN_LENGTH else None


async def require_upload_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = _configured_token()
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    scheme, _, given = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(given.strip().encode(), expected.encode()):
        logger.warning("Analysis upload: request with a missing or wrong token was refused.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid upload token",
                            headers={"WWW-Authenticate": "Bearer"})


def page_text_unusable(text_value: Optional[str]) -> bool:
    """A page that was not read has no usable text when it is empty or its text looks damaged."""
    t = (text_value or "").strip()
    if not t:
        return True
    return text_layer_looks_damaged(ExtractionQualityAssessor.assess_page(1, t, "TEXT_LAYER"))


# Shared Bangladesh Bank circulars whose current version has no analysis yet, newest first.
_PENDING_SQL = text("""
select d.id, d.reference_number, d.title, d.publication_date, d.current_version_id,
  (select count(*) from document_pages p where p.document_version_id = d.current_version_id) as pages,
  (select coalesce(sum(length(coalesce(p.cleaned_text, p.raw_text, ''))), 0) from document_pages p
     where p.document_version_id = d.current_version_id) as chars,
  (select count(*) from document_pages p where p.document_version_id = d.current_version_id
     and p.quality_status = 'PENDING_VISION' and coalesce(p.is_human_corrected, 0) = 0) as waiting
from documents d
where coalesce(d.is_synthetic_fixture, 0) = 0 and d.owner_user_id is null and d.current_version_id is not null
  and not exists (select 1 from document_analyses a where a.document_version_id = d.current_version_id)
order by d.publication_date desc, d.title
limit :limit
""")

_STUCK_SQL = text("""
select p.document_version_id, coalesce(nullif(p.cleaned_text, ''), p.raw_text, '')
from document_pages p
where p.document_version_id = :vid and p.quality_status in ('NEEDS_HUMAN_REVIEW', 'READ_FAILED')
  and coalesce(p.is_human_corrected, 0) = 0
""")


async def _current_version(db: AsyncSession, doc: Document) -> DocumentVersion:
    version = (await db.execute(
        select(DocumentVersion).options(selectinload(DocumentVersion.pages))
        .where(DocumentVersion.id == doc.current_version_id)
    )).scalar_one_or_none()
    if not version or not version.pages:
        raise HTTPException(status_code=409, detail="This circular has no pages yet.")
    return version


async def _shared_document(db: AsyncSession, document_id: UUID) -> Document:
    doc = await db.get(Document, document_id)
    if not doc or doc.owner_user_id is not None or doc.is_synthetic_fixture or not doc.current_version_id:
        raise HTTPException(status_code=404, detail="No such circular.")
    return doc


def _unread_pages(version: DocumentVersion) -> int:
    waiting = sum(1 for p in version.pages if p.quality_status == "PENDING_VISION" and not p.is_human_corrected)
    stuck = sum(
        1 for p in version.pages
        if p.quality_status in ("NEEDS_HUMAN_REVIEW", "READ_FAILED") and not p.is_human_corrected
        and page_text_unusable(p.cleaned_text or p.raw_text)
    )
    return waiting + stuck


@router.get("/pending", dependencies=[Depends(require_upload_token)])
async def pending_circulars(
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Circulars ready for analysis: every page has usable text and the current version has no analysis."""
    rows = (await db.execute(_PENDING_SQL, {"limit": limit * 3})).mappings().all()
    ready: List[Dict[str, Any]] = []
    for r in rows:
        if r["waiting"]:
            continue
        stuck = (await db.execute(_STUCK_SQL, {"vid": r["current_version_id"]})).all()
        if any(page_text_unusable(t) for _vid, t in stuck):
            continue
        ready.append({
            "document_id": str(UUID(str(r["id"]).replace("-", ""))),
            "reference_number": r["reference_number"],
            "title": r["title"],
            "publication_date": str(r["publication_date"]) if r["publication_date"] else None,
            "pages": r["pages"],
            "chars": r["chars"],
        })
        if len(ready) >= limit:
            break
    return {"circulars": ready}


@router.get("/circulars/{document_id}/text", dependencies=[Depends(require_upload_token)])
async def circular_text(document_id: UUID, db: AsyncSession = Depends(get_async_db)) -> Dict[str, Any]:
    """The circular as the analysis sees it: every sentence with its ID, page by page."""
    doc = await _shared_document(db, document_id)
    version = await _current_version(db, doc)
    if _unread_pages(version):
        raise HTTPException(status_code=409, detail="Some pages of this circular are not read yet.")
    index = SentenceIndex.build(pages_payload_for(version))
    header = (f"# {doc.title}\n# reference: {doc.reference_number or '-'} | listed date: {doc.publication_date} | "
              f"pages: {len(version.pages)} | document: {doc.id}\n\n")
    return {
        "document_id": str(doc.id),
        "version_id": str(version.id),
        "reference_number": doc.reference_number,
        "title": doc.title,
        "text": header + index.render_for_prompt(),
    }


@router.post("/circulars/{document_id}/analysis", dependencies=[Depends(require_upload_token)])
async def upload_analysis(
    document_id: UUID,
    request: Request,
    replace: bool = Query(False, description="Replace an analysis the current version already has"),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Loads one answer through the normal checks. Problems come back as a list, and nothing is saved."""
    raw_bytes = await request.body()
    if len(raw_bytes) > MAX_ANSWER_BYTES:
        raise HTTPException(status_code=413, detail="The answer is too large.")
    try:
        raw = raw_bytes.decode("utf-8")
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=422, detail={"problems": ["ERROR not valid JSON"]})

    doc = await _shared_document(db, document_id)
    version = await _current_version(db, doc)
    if _unread_pages(version):
        raise HTTPException(status_code=409, detail="Some pages of this circular are not read yet.")
    existing = (await db.execute(
        select(func.count()).select_from(DocumentAnalysis).where(DocumentAnalysis.document_version_id == version.id)
    )).scalar_one()
    if existing and not replace:
        raise HTTPException(status_code=409, detail="This circular already has an analysis. Send replace=true to replace it.")

    problems = check_answer(payload, SentenceIndex.build(pages_payload_for(version)))
    if problems:
        raise HTTPException(status_code=422, detail={"problems": problems[:100]})

    try:
        analysis = await AnalysisService.analyze_document_version(
            db, doc.id, provider=AnswerFileProvider(payload, raw))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    rows = (await db.execute(
        select(AnalysisClaim.check_status, func.count()).where(AnalysisClaim.analysis_id == analysis.id)
        .group_by(AnalysisClaim.check_status)
    )).all()
    points = {k: n for k, n in rows}
    try:  # who it applies to, from the new analysis (For you)
        from backend.app.modules.audience.service import refresh_document
        await refresh_document(db, doc.id)
        await db.commit()
    except Exception as e:  # never fail an upload over this
        logger.warning(f"Audience refresh failed for {doc.id}: {e}")
    logger.info(f"Analysis upload: loaded {doc.reference_number or doc.id}, points {points}")
    return {"document_id": str(doc.id), "analysis_id": str(analysis.id), "points": points}


async def last_upload_at(db: AsyncSession) -> Optional[datetime]:
    """When the laptop last sent an analysis (the newest analysis made from an uploaded answer)."""
    value = (await db.execute(
        select(func.max(DocumentAnalysis.created_at)).where(DocumentAnalysis.model_name == MODEL_NAME)
    )).scalar_one_or_none()
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


@router.get("/admin-status")
async def admin_status(
    _admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """For the admin console: is the laptop sending analyses, and how many circulars wait for one."""
    last = await last_upload_at(db)
    waiting = (await db.execute(text("""
        select count(*) from documents d
        where coalesce(d.is_synthetic_fixture, 0) = 0 and d.owner_user_id is null and d.current_version_id is not null
          and not exists (select 1 from document_analyses a where a.document_version_id = d.current_version_id)
          and d.publication_date >= :since
    """), {"since": "2024-11-14"})).scalar_one()
    hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600 if last else None
    return {
        "enabled": _configured_token() is not None,
        "last_upload_at": last.isoformat() if last else None,
        "hours_since_last_upload": round(hours, 1) if hours is not None else None,
        "stale": hours is None or hours > STALE_AFTER_HOURS,
        "recent_circulars_waiting": waiting,
    }
