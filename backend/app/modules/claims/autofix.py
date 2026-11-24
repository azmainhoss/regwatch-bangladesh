"""Self-correction of figures from two agreeing page readings (no person involved).

When both independent second readings of a sentence agree with each other and differ from our text only in
figures our text layer does not confirm (reading status CORRECTED, see reading.figure_fixes), our reading is
the wrong one. The claim that quotes it gets the corrected figures in its wording and in the quote shown to
readers; the wording before the fix is kept in `original_fields` and the change is noted in `review_note`.
The checks then run on the corrected sentence (checks.sentence_text), so the point is shown when it passes.
"""
from typing import Any, Dict, Iterable, List

from sqlalchemy import select

from backend.app.modules.analysis.models import ClaimCitation
from backend.app.modules.claims.checks import CheckContext, all_evidence_ids
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.claims.reading import apply_figure_fixes, fixes_of

NOTE_PREFIX = "Figures corrected from two agreeing page readings:"


async def load_fixes(db, pages: Iterable[Any], reading: Dict[str, str]) -> Dict[str, List[List[str]]]:
    """Sentence ID -> figure fixes, for the CORRECTED readings of these pages."""
    page_ids = [p.id for p in pages]
    wanted = {sid for sid, status in reading.items() if status == "CORRECTED"}
    if not page_ids or not wanted:
        return {}
    rows = (
        await db.execute(
            select(QuoteReadingCheck).where(QuoteReadingCheck.page_id.in_(page_ids), QuoteReadingCheck.status == "CORRECTED")
        )
    ).scalars().all()
    out: Dict[str, List[List[str]]] = {}
    for row in rows:
        if row.sentence_id in wanted:
            fixes = fixes_of(row)
            if fixes:
                out[row.sentence_id] = fixes
    return out


def _fix_value(value: Any, fixes: List[List[str]]) -> Any:
    if isinstance(value, str):
        return apply_figure_fixes(value, fixes)
    if isinstance(value, list):
        return [_fix_value(v, fixes) for v in value]
    if isinstance(value, dict):
        return {k: _fix_value(v, fixes) for k, v in value.items()}
    return value


async def apply_reading_fixes(db, claim: Any, ctx: CheckContext) -> bool:
    """Puts the corrected figures into the claim's wording and quote. True when something changed."""
    fixes: List[List[str]] = []
    for sid in all_evidence_ids(claim, ctx):
        for pair in ctx.fixes.get(sid, []):
            if pair not in fixes:
                fixes.append(pair)
    if not fixes:
        return False
    changed = False
    fields = dict(claim.fields or {})
    new_fields = _fix_value(fields, fixes)
    if new_fields != fields:
        if claim.original_fields is None:
            claim.original_fields = fields
        claim.fields = new_fields
        changed = True
    if getattr(claim, "id", None) is not None:
        citations = (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id == claim.id))).scalars().all()
        for c in citations:
            fixed = apply_figure_fixes(c.quoted_text, fixes)
            if fixed != c.quoted_text:
                c.quoted_text = fixed
                changed = True
    if changed:
        note = f"{NOTE_PREFIX} " + ", ".join(f"{a} -> {b}" for a, b in fixes)
        if not (claim.review_note or "").startswith(NOTE_PREFIX):
            claim.review_note = note
    return changed
