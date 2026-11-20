"""What a person's page correction does to the points that quote the page (spec section 6.4, third bullet).

Every undecided point that cites the page goes back to "checking". Its quoted words are looked up in the new
page text (exactly, or after the usual normalising). Found: the point gets the new sentence IDs and its checks
run again. Not found: the point is not shown, with the reason in plain words. The corrected page counts as read
by a person, so it needs no second reading. A point a person already decided is never touched.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import decide
from backend.app.modules.claims import reading as R
from backend.app.modules.claims import status as S
from backend.app.modules.claims import wording as W
from backend.app.modules.claims.checks import FAIL, _page_of, result, run_code_checks
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.documents.models import Document, DocumentVersion

MAX_SENTENCES_IN_QUOTE = 8


def _page_ids(claim: Any, page_number: int) -> Dict[str, List[str]]:
    """Evidence key -> the sentence IDs on this page."""
    out: Dict[str, List[str]] = {}
    for key, ids in (claim.evidence or {}).items():
        mine = [i for i in ids or [] if _page_of(i) == page_number]
        if mine:
            out[key] = mine
    return out


def find_sentences(old_text: str, new_index: SentenceIndex, page_number: int) -> Optional[List[str]]:
    """The new sentence IDs that hold `old_text` (a quoted sentence), or None when the words are gone.

    Looks for the smallest run of neighbouring sentences whose text, after normalising, contains the old words.
    """
    wanted = W.norm(old_text)
    if not wanted:
        return None
    ids = new_index.order.get(page_number, [])
    texts = [W.norm(new_index.sentences[i].text) for i in ids]
    for width in range(1, MAX_SENTENCES_IN_QUOTE + 1):
        for start in range(0, len(ids) - width + 1):
            if wanted in " ".join(texts[start:start + width]):
                return ids[start:start + width]
    return None


async def reroute_after_page_correction(db, version: DocumentVersion, page: Any, old_text: str) -> int:
    """Brings the points that quote the corrected page in step with its new text. Returns how many were changed.

    Runs inside the request that saved the correction: plain code only, no reading is requested here.
    `old_text` is the page text before the correction.
    """
    from backend.app.modules.analysis.service import pages_payload_for

    # Rows still waiting for a second reading of the old text have nothing left to check.
    stale = (
        await db.execute(
            select(QuoteReadingCheck).where(QuoteReadingCheck.page_id == page.id, QuoteReadingCheck.status == "WAITING")
        )
    ).scalars().all()
    for row in stale:
        row.status = "NOT_NEEDED"

    version = (
        await db.execute(
            select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id == version.id)
        )
    ).scalars().first()
    doc = await db.get(Document, version.document_id)
    if doc is None:
        return 0
    page_number = page.page_number
    new_index = SentenceIndex.build(pages_payload_for(version))
    old_index = SentenceIndex.build([{"page_number": page_number, "raw_text": old_text, "cleaned_text": old_text, "line_boxes": None}])
    page_id_map = {p.page_number: p.id for p in version.pages}

    claims = (
        await db.execute(
            select(AnalysisClaim)
            .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
            .where(
                DocumentAnalysis.document_version_id == version.id,
                AnalysisClaim.check_status.notin_(S.DECIDED_STATUSES),
            )
        )
    ).scalars().all()

    changed = 0
    for claim in claims:
        mine = _page_ids(claim, page_number)
        if not mine:
            continue
        mapping: Dict[str, List[str]] = {}
        gone = False
        for ids in mine.values():
            for sid in ids:
                if sid in mapping:
                    continue
                old = old_index.sentences.get(sid)
                found = find_sentences(old.text, new_index, page_number) if old is not None else None
                if found is None:
                    gone = True
                    break
                mapping[sid] = found
            if gone:
                break

        claim.check_status, claim.review_queue = S.CHECKING, None
        if gone:
            claim.check_status, claim.review_queue = S.NOT_SHOWN, S.OPTIONAL
            claim.checks = [
                result("QUOTE_FOUND", FAIL, f"The quoted words are no longer on page {page_number} after its reading was corrected.")
            ]
        else:
            evidence: Dict[str, List[str]] = {}
            for key, ids in (claim.evidence or {}).items():
                new_ids: List[str] = []
                for sid in ids or []:
                    for n in mapping.get(sid, [sid]):
                        if n not in new_ids:
                            new_ids.append(n)
                evidence[key] = new_ids
            claim.evidence = evidence
            asked = any(c.get("name") == S.ASKED_FOR_REVIEW_CHECK for c in (claim.checks or []))
            reading = await R.ensure_reading_checks(db, [claim], new_index, version.pages)
            await run_code_checks(db, [claim], new_index, doc, version.pages, reading)
            S.route(claim, doc)
            if asked:
                S.ask_for_review(claim)
            await decide._replace_citations(db, claim, new_index, page_id_map)
            await decide._write_back_quote(db, claim, new_index, page_id_map)
        await decide.settle(db, claim, doc)
        changed += 1
    await db.flush()
    return changed
