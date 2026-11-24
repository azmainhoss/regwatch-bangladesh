"""Background job for the second reading of quoted sentences (docs/specs/CLAIM_CHECKS_SPEC.md sections 6.4 and 7).

`process_pending_quote_checks(db, limit)` is called at the start of each batch by the page reader
(`backend/scripts/read_pages.py`) and by the web app's own reading job, before any page of an older
circular is read. It never runs inside a web request.

It takes the waiting checks of the newest circulars first, one page at a time, and hands each page to
`claims.reading.check_page`. When a page is done, every claim that quotes it is checked again: the claim
leaves "checking" once its last quoted sentence has its answer. A claim a person already decided is
never touched.
"""
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import decide
from backend.app.modules.claims import reading as R
from backend.app.modules.claims import status as S
from backend.app.modules.claims.checks import FAIL, WAIT, all_evidence_ids, CheckContext, _page_of, run_code_checks
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.institutions.models import InstitutionDepartment

DEFAULT_PAGE_LIMIT = 20

Sender = Callable[..., Awaitable[Any]]


def new_summary() -> Dict[str, Any]:
    return {
        "pages": 0, "checked": 0, "clean": 0, "misread": 0, "unclear": 0, "corrected": 0, "not_needed": 0,
        "failed": 0, "calls": 0, "waiting_busy": 0, "waiting_no_key": 0, "out_of_quota": False,
        "claims_rerouted": 0, "batch_full": False,
    }


async def _department_codes(db) -> List[str]:
    rows = (await db.execute(select(InstitutionDepartment.code).distinct())).scalars().all()
    return [c for c in rows if c]


async def pending_page_ids(db, limit: int) -> List[Any]:
    """Pages with a waiting check, newest circular first (current versions only)."""
    rows = (
        await db.execute(
            select(QuoteReadingCheck.page_id)
            .join(DocumentPage, DocumentPage.id == QuoteReadingCheck.page_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(QuoteReadingCheck.status == "WAITING", Document.current_version_id == DocumentVersion.id)
            .group_by(QuoteReadingCheck.page_id, Document.publication_date, DocumentPage.page_number)
            .order_by(Document.publication_date.desc(), DocumentPage.page_number)
            .limit(limit)
        )
    ).all()
    return [r[0] for r in rows]


async def reroute_claims_for_page(db, version_id, page_number: int) -> int:
    """Checks again every undecided claim of this circular that quotes the page and has a second-reading result (waiting or failed)."""
    version = (
        await db.execute(
            select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id == version_id)
        )
    ).scalars().first()
    if version is None:
        return 0
    doc = await db.get(Document, version.document_id)
    if doc is None:
        return 0

    from backend.app.modules.analysis.service import pages_payload_for

    index = SentenceIndex.build(pages_payload_for(version))
    claims = (
        await db.execute(
            select(AnalysisClaim)
            .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
            .where(
                DocumentAnalysis.document_version_id == version_id,
                AnalysisClaim.check_status.notin_(S.DECIDED_STATUSES),
            )
        )
    ).scalars().all()
    ctx = CheckContext(index=index)
    done = 0
    for claim in claims:
        if not any(c.get("name") == "QUOTE_READING" and c.get("result") in (WAIT, FAIL) for c in (claim.checks or [])):
            continue
        if not any(_page_of(sid) == page_number for sid in all_evidence_ids(claim, ctx)):
            continue
        asked = any(c.get("name") == S.ASKED_FOR_REVIEW_CHECK for c in (claim.checks or []))
        reading = await R.ensure_reading_checks(db, [claim], index, version.pages)
        await run_code_checks(db, [claim], index, doc, version.pages, reading)
        S.route(claim, doc)
        if asked:
            S.ask_for_review(claim)
        await decide.settle(db, claim, doc)
        done += 1
    return done


async def reroute_other_pages(db, version_id, skip_page: int) -> int:
    """Checks again the points on every other image-read page of the circular."""
    numbers = (
        await db.execute(select(DocumentPage.page_number).where(DocumentPage.document_version_id == version_id))
    ).scalars().all()
    done = 0
    for n in sorted(set(numbers)):
        if n != skip_page:
            done += await reroute_claims_for_page(db, version_id, n)
    return done


async def process_pending_quote_checks(
    db,
    limit: int = DEFAULT_PAGE_LIMIT,
    send: Optional[Sender] = None,
) -> Dict[str, Any]:
    """Gives the waiting quoted sentences their second reading. `limit` is the most pages handled in one run.

    Busy and out-of-quota replies leave the checks waiting and count no attempt.
    """
    summary = new_summary()
    page_ids = await pending_page_ids(db, limit)
    summary["batch_full"] = len(page_ids) >= limit
    if not page_ids:
        return summary
    if send is None:
        from backend.app.modules.extraction.vision import gemini_keys

        if not gemini_keys():
            summary["waiting_no_key"] = len(page_ids)
            return summary
        send = R.send_images
    codes = await _department_codes(db)

    for page_id in page_ids:
        page = await db.get(DocumentPage, page_id)
        if page is None:
            continue
        rows = (
            await db.execute(
                select(QuoteReadingCheck)
                .where(QuoteReadingCheck.page_id == page_id, QuoteReadingCheck.status == "WAITING")
                .order_by(QuoteReadingCheck.sentence_id)
            )
        ).scalars().all()
        version = await db.get(DocumentVersion, page.document_version_id)
        try:
            pdf_bytes = storage_service.get_file_bytes(version.storage_path) if version is not None else b""
        except Exception as e:  # missing file: a real failure of these checks, not of the service
            logger.warning(f"Second reading skipped for page {page.page_number}: {type(e).__name__}")
            pdf_bytes = b""
        page_summary = await R.check_page(page, rows, pdf_bytes, send, codes)
        for key in ("checked", "clean", "misread", "unclear", "corrected", "not_needed", "failed", "calls", "waiting_busy"):
            summary[key] += page_summary.get(key, 0)
        summary["pages"] += 1
        await db.commit()
        if page_summary.get("checked") or page_summary.get("not_needed"):
            summary["claims_rerouted"] += await reroute_claims_for_page(db, page.document_version_id, page.page_number)
            await db.commit()
        if page_summary.get("corrected"):
            # A proven figure correction can spread to the same figure on the circular's other pages.
            summary["claims_rerouted"] += await reroute_other_pages(db, page.document_version_id, page.page_number)
            await db.commit()
        if page_summary.get("no_key"):
            summary["waiting_no_key"] += len(rows)
            break
        if page_summary.get("out_of_quota"):
            summary["out_of_quota"] = True
            break
        if page_summary.get("stop"):
            break
    if summary["calls"] or summary["checked"]:
        logger.info(f"Second reading job: {summary}")
    return summary


async def quote_checks_waiting_total(db) -> int:
    return (
        await db.execute(select(func.count()).select_from(QuoteReadingCheck).where(QuoteReadingCheck.status == "WAITING"))
    ).scalar_one()
