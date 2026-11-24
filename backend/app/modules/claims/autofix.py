"""Self-correction of figures from two agreeing page readings (no person involved).

When both independent second readings of a sentence agree with each other and differ from our text only in
figures our text layer does not confirm (reading status CORRECTED, see reading.figure_fixes), our reading is
the wrong one. The claim that quotes it gets the corrected figures in its wording and in the quote shown to
readers; the wording before the fix is kept in `original_fields` and the change is noted in `review_note`.
The checks then run on the corrected sentence (checks.sentence_text), so the point is shown when it passes.
"""
import re
from typing import Any, Dict, Iterable, List

from sqlalchemy import select

from backend.app.modules.analysis.models import ClaimCitation
from backend.app.modules.claims.checks import CheckContext, all_evidence_ids
from backend.app.modules.claims import wording as W
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.claims.reading import apply_figure_fixes, fixes_of

NOTE_PREFIX = "Figures corrected from two agreeing page readings:"

SPREAD_STATUSES = ("MISREAD", "UNCLEAR", "WAITING")  # never over a reading that confirmed our figure (CLEAN)
CONTEXT_LEFT, CONTEXT_RIGHT, CONTEXT_MIN = 8, 4, 6


def _ascii(text: str) -> str:
    return (text or "").translate(W._BANGLA_DIGITS)


def _squash(text: str) -> str:
    """Normalised text without spaces, with every apostrophe as ' (for comparing what stands around a figure)."""
    t = W.norm(text)
    for ch in "’‘`´":
        t = t.replace(ch, "'")
    return re.sub(r"\s+", "", t)


def contexts(text: str, figure: str) -> List[tuple]:
    """(left, right) of each whole occurrence of the figure: the 8 characters before it and the 4 after, squashed."""
    a = _ascii(text)
    out = []
    for m in re.finditer(rf"(?<![\d.]){re.escape(figure)}(?![\d])", a):
        left, right = _squash(a[: m.start()])[-CONTEXT_LEFT:], _squash(a[m.end():])[:CONTEXT_RIGHT]
        out.append((left, right))
    return out


async def load_fixes(db, pages: Iterable[Any], reading: Dict[str, str], index: Any = None) -> Dict[str, List[List[str]]]:
    """Sentence ID -> figure fixes for one circular.

    Direct: the sentences whose two readings agreed (status CORRECTED). Spread: another sentence of the same
    circular that prints the same figure in the same surroundings (the 8 characters before and 4 after it, e.g.
    "(ল’রিভিউ)১৭৭/২০২৬") gets the same fix, when its own reading did not confirm our figure (no CLEAN) and the
    text layer does not confirm it either. A plain "177" elsewhere, or the same year in other words, is never
    changed.
    """
    page_ids = [p.id for p in pages]
    if not page_ids:
        return {}
    rows = (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.page_id.in_(page_ids)))).scalars().all()
    out: Dict[str, List[List[str]]] = {}
    proven = []  # (old, new, left, right)
    for row in rows:
        if row.status != "CORRECTED":
            continue
        fixes = fixes_of(row)
        if not fixes:
            continue
        out[row.sentence_id] = fixes
        for old, new in fixes:
            for left, right in contexts(row.our_text or "", old):
                if len(left) >= CONTEXT_MIN:
                    proven.append((old, new, left, right))
    if not proven or index is None:
        return out
    for row in rows:
        sid = row.sentence_id
        if sid in out or row.status not in SPREAD_STATUSES or sid not in index.sentences:
            continue
        text = index.sentences[sid].text
        sure = {re.sub(r"\D", "", str(c)) for c in (row.numbers_confirmed or []) if not str(c).startswith("date:")}
        found: List[List[str]] = []
        for old, new, left, right in proven:
            if re.sub(r"\D", "", old) in sure or [old, new] in found:
                continue
            if (left, right) in contexts(text, old):
                found.append([old, new])
        if found:
            out[sid] = found
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
