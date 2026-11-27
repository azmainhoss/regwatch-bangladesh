"""Keeps a circular's analysis when Bangladesh Bank re-uploads the same PDF with small fixes (owner, 2026-11-28).

Bangladesh Bank sometimes replaces a published PDF with a corrected copy: a reformatted date, a fixed cross-reference
("Error! Reference source not found." -> "Appendix-1"). The site stores that as a new version, which has no analysis,
so the circular fell back to "Analysing". When every page of the new version reads the same as the analysed one
(at least MIN_SIMILARITY of its words, same page count), the analysis, its points' page links, provisions and
obligations move to the new version. Anything that really changed waits for a fresh analysis, as before.
"""
from __future__ import annotations

import difflib
import logging
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.service import STATUS_PENDING_VISION
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.provisions.models import Provision

logger = logging.getLogger(__name__)

MIN_SIMILARITY = 0.97


def page_similarity(a: str, b: str) -> float:
    """Word-level likeness of two page texts (line wrapping is ignored)."""
    wa, wb = (a or "").split(), (b or "").split()
    if not wa and not wb:
        return 1.0
    return difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio()


async def _pages(db: AsyncSession, version_id) -> List[DocumentPage]:
    return list((await db.execute(
        select(DocumentPage).where(DocumentPage.document_version_id == version_id).order_by(DocumentPage.page_number)
    )).scalars())


def _text(p: DocumentPage) -> str:
    return p.human_corrected_text or p.cleaned_text or ""


async def carry_document(db: AsyncSession, doc: Document) -> bool:
    """Moves the latest analysis of an older version onto the current one when the text is unchanged. Does not commit."""
    cur_id = doc.current_version_id
    if cur_id is None:
        return False
    if (await db.execute(select(DocumentAnalysis.id).where(DocumentAnalysis.document_version_id == cur_id))).first():
        return False
    prev = (await db.execute(
        select(DocumentAnalysis)
        .join(DocumentVersion, DocumentVersion.id == DocumentAnalysis.document_version_id)
        .where(DocumentVersion.document_id == doc.id, DocumentVersion.id != cur_id)
        .order_by(DocumentAnalysis.created_at.desc())
        .limit(1)
    )).scalars().first()
    if prev is None:
        return False
    new_pages, old_pages = await _pages(db, cur_id), await _pages(db, prev.document_version_id)
    if not new_pages or len(new_pages) != len(old_pages):
        return False
    if any(p.quality_status == STATUS_PENDING_VISION for p in new_pages):
        return False  # Bangla/scanned pages not read yet: try again on a later run
    worst = min(page_similarity(_text(o), _text(n)) for o, n in zip(old_pages, new_pages))
    if worst < MIN_SIMILARITY:
        return False

    old_vid = prev.document_version_id
    page_map: Dict = {o.id: n.id for o, n in zip(old_pages, new_pages)}
    prev.document_version_id = cur_id
    for model in (Provision, Obligation):
        for row in (await db.execute(select(model).where(model.document_version_id == old_vid))).scalars():
            row.document_version_id = cur_id
            row.page_id = page_map.get(row.page_id, row.page_id)
    claims = list((await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == prev.id))).scalars())
    claim_ids = [c.id for c in claims]
    if claim_ids:
        for cit in (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id.in_(claim_ids)))).scalars():
            cit.page_id = page_map.get(cit.page_id, cit.page_id)
    from backend.app.modules.claims import status as claim_status
    claim_status.apply_document_status(doc, claims)
    await db.flush()
    logger.info(f"Kept the analysis of {doc.reference_number}: new PDF reads the same (lowest page match {worst:.3f})")
    return True


async def carry_unchanged_analyses(db: AsyncSession, limit: int = 50) -> int:
    """Every public circular whose current version lacks an analysis that an older version has. Commits."""
    has_current = select(DocumentAnalysis.id).where(DocumentAnalysis.document_version_id == Document.current_version_id)
    has_older = (
        select(DocumentAnalysis.id)
        .join(DocumentVersion, DocumentVersion.id == DocumentAnalysis.document_version_id)
        .where(DocumentVersion.document_id == Document.id)
    )
    docs = (await db.execute(
        select(Document).where(~has_current.exists(), has_older.exists()).limit(limit)
    )).scalars().all()
    moved = 0
    for doc in docs:
        try:
            if await carry_document(db, doc):
                moved += 1
        except Exception as ex:  # one bad circular must not stop the rest
            await db.rollback()
            logger.warning(f"Could not keep the analysis of {doc.reference_number}: {ex}")
    await db.commit()
    return moved
