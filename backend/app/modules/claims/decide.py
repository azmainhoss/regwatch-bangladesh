"""A person's decision on one claim (docs/specs/CLAIM_CHECKS_SPEC.md sections 4.4, 4.5, 5.2).

Every decision changes the claim, the obligation or link row it is tied to, and the circular's status
in the caller's transaction (nothing is committed here). The review screen and the old link review
endpoint both go through these functions, so they always end in the same state.

Approve, fix and reject decide a held point; ask-for-review hides a shown point until a person
decides it. A decision that releases a circular that was never announced sends the one "new
circular" alert (never for circulars that came from the archive).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.audit import service as audit
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.claims import status as S
from backend.app.modules.claims import wording as W
from backend.app.modules.claims.checks import FAIL, WAIT, run_code_checks, set_field
from backend.app.modules.documents.models import Document, DocumentVersion

DECIDABLE = (S.CHECKING, S.WAITING_FOR_PERSON, S.NOT_SHOWN)


class DecisionConflict(Exception):
    """Somebody already decided the claim, or it is not in a state this decision applies to."""

    def __init__(self, claim: Any):
        super().__init__("This point was already decided.")
        self.claim = claim


async def load_claim(db, claim_id) -> Optional[AnalysisClaim]:
    return await db.get(AnalysisClaim, claim_id)


async def document_of(db, claim: AnalysisClaim) -> Optional[Document]:
    row = (
        await db.execute(
            select(Document)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(DocumentAnalysis, DocumentAnalysis.document_version_id == DocumentVersion.id)
            .where(DocumentAnalysis.id == claim.analysis_id)
        )
    ).scalars().first()
    return row


async def latest_analysis_id(db, doc: Document):
    if not doc.current_version_id:
        return None
    return (
        await db.execute(
            select(DocumentAnalysis.id)
            .where(DocumentAnalysis.document_version_id == doc.current_version_id)
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def claims_of(db, analysis_id) -> List[AnalysisClaim]:
    return list(
        (
            await db.execute(
                select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis_id).order_by(AnalysisClaim.order_index)
            )
        ).scalars().all()
    )


ARCHIVE_RUN_ACTION = "analysis.archive_run"


def mark_archive_run(db, doc: Document) -> None:
    """Remembers that this circular was analysed on request from the archive: it never sends a "new circular" alert."""
    audit.record(
        db,
        organization_id=None,
        actor_user_id=None,
        action=ARCHIVE_RUN_ACTION,
        entity_type="document",
        entity_id=doc.id,
        before=None,
        after={"from": "archive"},
    )


async def was_archive_circular(db, doc: Document) -> bool:
    row = (
        await db.execute(
            select(AuditEvent.id)
            .where(AuditEvent.action == ARCHIVE_RUN_ACTION, AuditEvent.entity_type == "document", AuditEvent.entity_id == doc.id)
            .limit(1)
        )
    ).first()
    return row is not None


async def announce_if_released(db, doc: Document, before: str, after: str) -> None:
    """A circular that was held and is now published sends its "new circular" alert.

    The alert is recorded once per circular (its key repeats), so a later decision cannot send it again.
    Archive circulars never alert.
    """
    if before != "AWAITING_REVIEW" or not str(after or "").startswith("PUBLISHED"):
        return
    if await was_archive_circular(db, doc):
        return
    from backend.app.modules.analysis.service import _announce_circular

    await _announce_circular(db, doc)


async def settle(db, claim: AnalysisClaim, doc: Optional[Document]) -> str:
    """Brings the claim's row and the circular's status in step with the claim. Returns the circular's status."""
    await db.flush()
    await S.sync_rows(db, [claim])
    status = doc.publication_status if doc is not None else ""
    if doc is not None and str(claim.analysis_id) == str(await latest_analysis_id(db, doc)):
        before = doc.publication_status
        status = S.apply_document_status(doc, await claims_of(db, claim.analysis_id))
        await announce_if_released(db, doc, before, status)
    await db.flush()
    return status


def _event(db, user, action: str, claim: AnalysisClaim, before: Dict[str, Any], note: Optional[str] = None) -> None:
    audit.record(
        db,
        organization_id=None,
        actor_user_id=getattr(user, "id", None),
        action=action,
        entity_type="analysis_claim",
        entity_id=claim.id,
        before=before,
        after={"check_status": claim.check_status, "kind": claim.kind, "note": note},
    )


def _before(claim: AnalysisClaim) -> Dict[str, Any]:
    return {"check_status": claim.check_status, "review_queue": claim.review_queue}


def _stamp(claim: AnalysisClaim, user, note: Optional[str]) -> None:
    claim.review_queue = None
    claim.reviewed_by = getattr(user, "id", None)
    claim.reviewed_at = datetime.now(timezone.utc)
    claim.review_note = note


async def approve(db, claim: AnalysisClaim, user, note: Optional[str] = None, allow_decided: bool = False) -> AnalysisClaim:
    """The point becomes shown. A change-the-law link takes its claimed type, so it now counts."""
    if claim.check_status not in DECIDABLE and not allow_decided:
        raise DecisionConflict(claim)
    before = _before(claim)
    claim.check_status = S.APPROVED
    claim.reject_reason = None
    _stamp(claim, user, note)
    if S.is_change_link(claim):
        set_field(claim, "shown_type", str((claim.fields or {}).get("claimed_type")).upper())
    _event(db, user, "claim.approve", claim, before, note)
    doc = await document_of(db, claim)
    await settle(db, claim, doc)
    return claim


async def reject(db, claim: AnalysisClaim, user, reason: str = "OTHER", note: Optional[str] = None, allow_decided: bool = False) -> AnalysisClaim:
    """The point is never shown."""
    if claim.check_status not in DECIDABLE and not allow_decided:
        raise DecisionConflict(claim)
    before = _before(claim)
    claim.check_status = S.REJECTED
    claim.reject_reason = (reason or "OTHER")[:64]
    _stamp(claim, user, note)
    if S.is_change_link(claim) or claim.kind == "LINK":
        set_field(claim, "shown_type", "REFERENCES")
    _event(db, user, "claim.reject", claim, before, note)
    doc = await document_of(db, claim)
    await settle(db, claim, doc)
    return claim


async def ask_review(db, claim: AnalysisClaim, user) -> AnalysisClaim:
    """Hides a shown point until a person decides it."""
    if not S.is_shown(claim):
        raise DecisionConflict(claim)
    before = _before(claim)
    if claim.kind == "LINK" and S.is_change_link(claim) and claim.check_status in (S.APPROVED, S.FIXED):
        # A confirmed change must stop counting while it is looked at again.
        set_field(claim, "shown_type", "REFERENCES")
    S.ask_for_review(claim)
    claim.reviewed_by = None
    claim.reviewed_at = None
    _event(db, user, "claim.ask_review", claim, before)
    doc = await document_of(db, claim)
    await settle(db, claim, doc)
    return claim


async def ask_review_all(db, doc: Document, user) -> List[AnalysisClaim]:
    """Asks for review of every point of the circular that is shown. Returns the claims that were hidden."""
    analysis_id = await latest_analysis_id(db, doc)
    if analysis_id is None:
        return []
    hidden: List[AnalysisClaim] = []
    for claim in await claims_of(db, analysis_id):
        if claim.kind == "PROVISION" or not S.is_shown(claim):
            continue
        before = _before(claim)
        if claim.kind == "LINK" and S.is_change_link(claim) and claim.check_status in (S.APPROVED, S.FIXED):
            set_field(claim, "shown_type", "REFERENCES")
        S.ask_for_review(claim)
        claim.reviewed_by = None
        claim.reviewed_at = None
        _event(db, user, "claim.ask_review", claim, before)
        hidden.append(claim)
    if hidden:
        await db.flush()
        await S.sync_rows(db, hidden)
        S.apply_document_status(doc, await claims_of(db, analysis_id))
        await db.flush()
    return hidden


# ---------------------------------------------------------------------------
# Fix: a person corrects the point, and the checks run again on the new values
# ---------------------------------------------------------------------------
class DecisionProblem(Exception):
    """The fix cannot be saved yet. `messages` are plain sentences for the person."""

    def __init__(self, messages: List[str], checks: Optional[List[Dict[str, Any]]] = None):
        super().__init__(" ".join(messages))
        self.messages = messages
        self.checks = checks or []


FIX_FIELDS: Dict[str, Tuple[str, ...]] = {
    "SUMMARY_POINT": ("text",),
    "KEY_CHANGE": ("text",),
    "OBLIGATION": ("title", "description", "obligation_type", "who", "deadline", "deadline_text", "effective_date", "frequency", "penalty", "clause"),
    "APPLIES_TO": ("entity",),
    "EXEMPTION": ("text",),
    "DATE": ("date_kind", "date"),
    "LINK": ("claimed_type", "target_hint"),
    "PROVISION": ("number", "heading", "explanation", "provision_type"),
}
LINK_TYPES = ("AMENDS", "REPEALS", "SUPERSEDES", "REPLACES", "CLARIFIES", "REFERENCES", "IMPLEMENTS", "RELATED_TO")
DATE_KINDS = ("EFFECTIVE", "COMPLIANCE", "REPORTING")
DATE_FIELDS = ("deadline", "effective_date", "date")
REQUIRED_TEXT = {
    "SUMMARY_POINT": ("text",),
    "KEY_CHANGE": ("text",),
    "EXEMPTION": ("text",),
    "APPLIES_TO": ("entity",),
    "DATE": ("date",),
}


def clean_fields(kind: str, given: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps only the fields this kind of point has, trimmed. Raises DecisionProblem for a value that cannot be right."""
    allowed = FIX_FIELDS.get(kind, ())
    out: Dict[str, Any] = {}
    problems: List[str] = []
    for key, value in (given or {}).items():
        if key not in allowed:
            continue
        text = None if value is None else str(value).strip()
        out[key] = text or None
        if not text:
            continue
        if key in DATE_FIELDS and W.parse_iso_date(text) is None:
            problems.append("Write dates as year-month-day, for example 2026-12-31.")
        elif key == "obligation_type":
            if text.upper() in W.DUTY_WORDS:
                out[key] = text.upper()
            else:
                problems.append("Pick one of the requirement types from the list.")
        elif key in ("who", "entity"):
            if text.upper() in W.ENTITIES:
                out[key] = text.upper()
            else:
                problems.append("Pick who it applies to from the list.")
        elif key == "claimed_type":
            if text.upper() in LINK_TYPES:
                out[key] = text.upper()
            else:
                problems.append("Pick what kind of link this is from the list.")
        elif key == "date_kind":
            if text.upper() in DATE_KINDS:
                out[key] = text.upper()
            else:
                problems.append("Pick what kind of date this is from the list.")
    for key in ("claimed_type", "date_kind"):
        if key in out and not out[key]:
            problems.append("Pick one from the list.")
    for key in REQUIRED_TEXT.get(kind, ()):
        if key in out and not out[key]:
            problems.append("This point needs its wording filled in.")
    if kind == "OBLIGATION" and ("title" in out or "description" in out) and not (out.get("title") or out.get("description")):
        problems.append("A requirement needs a title or a description.")
    if problems:
        raise DecisionProblem(list(dict.fromkeys(problems)))
    return out


async def version_of(db, claim: AnalysisClaim) -> Optional[DocumentVersion]:
    return (
        await db.execute(
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.pages))
            .join(DocumentAnalysis, DocumentAnalysis.document_version_id == DocumentVersion.id)
            .where(DocumentAnalysis.id == claim.analysis_id)
        )
    ).scalars().first()


async def _replace_citations(db, claim: AnalysisClaim, index, page_id_map: Dict[int, Any]) -> None:
    from backend.app.modules.claims.build import _verification_status

    old_rows = (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id == claim.id))).scalars().all()
    for old in old_rows:
        await db.delete(old)
    await db.flush()
    claim.verification_status = _verification_status(claim.evidence or {}, index)
    span = index.resolve((claim.evidence or {}).get("quote") or [])
    if not span.ok:
        return
    for frag in span.fragments:
        page_id = page_id_map.get(frag["page_number"])
        if page_id is None:
            continue
        boxes = [b for b in span.boxes if b["page_number"] == frag["page_number"]]
        db.add(
            ClaimCitation(
                claim_id=claim.id,
                page_id=page_id,
                quoted_text=frag["text"],
                quote_span_ids=frag["sentence_ids"],
                quote_boxes=boxes,
                match_score=1.0 if claim.verification_status in ("VERIFIED_EXACT", "VERIFIED_NORMALIZED") else 0.0,
            )
        )
    await db.flush()


async def _write_back_quote(db, claim: AnalysisClaim, index, page_id_map: Dict[int, Any]) -> None:
    """A corrected quote also goes onto the obligation or link row the point is tied to."""
    span = index.resolve((claim.evidence or {}).get("quote") or [])
    if not span.ok:
        return
    page_id = page_id_map.get(span.page_number or 1)
    if claim.kind == "OBLIGATION" and claim.obligation_id:
        from backend.app.modules.obligations.models import Obligation

        row = await db.get(Obligation, claim.obligation_id)
        if row is not None:
            row.supporting_text = span.quote
            row.quote_span_ids = list((claim.evidence or {}).get("quote") or [])
            row.quote_boxes = list(span.boxes)
            if page_id is not None:
                row.page_id = page_id
    elif claim.kind == "LINK" and claim.relationship_id:
        from backend.app.modules.relationships.models import DocumentRelationship

        row = await db.get(DocumentRelationship, claim.relationship_id)
        if row is not None:
            row.supporting_quote = span.quote
            row.quote_span_ids = list((claim.evidence or {}).get("quote") or [])
            row.quote_boxes = list(span.boxes)
            if page_id is not None:
                row.source_page_id = page_id


async def fix(
    db,
    claim: AnalysisClaim,
    user,
    fields: Dict[str, Any],
    evidence_ids: Optional[List[str]] = None,
    confirm_checked: bool = False,
    note: Optional[str] = None,
) -> AnalysisClaim:
    """A person corrects the point. The checks run again on the new values; if any fails, the person must
    say they checked the page image. The claim's fingerprint stays the one of the original output, so the
    fixed point carries over to the next run of the same circular.

    Raises DecisionProblem (nothing changed in the database session's view once the caller rolls back)."""
    from backend.app.modules.analysis.sentences import SentenceIndex
    from backend.app.modules.analysis.service import pages_payload_for
    from backend.app.modules.claims import reading as claim_reading

    if claim.check_status not in DECIDABLE:
        raise DecisionConflict(claim)
    cleaned = clean_fields(claim.kind, fields)
    doc = await document_of(db, claim)
    version = await version_of(db, claim)
    if doc is None or version is None:
        raise DecisionProblem(["The circular of this point could not be found."])

    index = SentenceIndex.build(pages_payload_for(version))
    before = _before(claim)
    old_fields = dict(claim.fields or {})
    old_evidence = {k: list(v or []) for k, v in (claim.evidence or {}).items()}

    ids = [str(i).strip().strip("[]").lower() for i in (evidence_ids or []) if str(i).strip()]
    if any(i not in index.sentences for i in ids):
        raise DecisionProblem(["One of the chosen sentences is not on the page. Pick the sentences again."])

    claim.fields = {**old_fields, **cleaned}
    if ids:
        keys = list(old_evidence) or ["quote"]
        if "quote" not in keys:
            keys.append("quote")
        claim.evidence = {k: list(ids) for k in keys}
    reading = await claim_reading.ensure_reading_checks(db, [claim], index, version.pages)
    await run_code_checks(db, [claim], index, doc, version.pages, reading)

    checks = [c for c in (claim.checks or []) if c.get("result") != "NOT_RUN"]
    if any(c["name"] == "HAS_EVIDENCE" and c["result"] == FAIL for c in checks):
        raise DecisionProblem(["Tick the sentence this point comes from."], checks)
    failing = [c for c in checks if c["result"] in (FAIL, WAIT)]
    if failing and not confirm_checked:
        raise DecisionProblem([str(c.get("message") or "") for c in failing if c.get("message")], checks)

    # Saved. The fingerprint is left alone on purpose.
    if claim.original_fields is None:
        claim.original_fields = old_fields
    claim.check_status = S.FIXED
    claim.reject_reason = None
    _stamp(claim, user, note)
    if claim.kind == "LINK":
        set_field(claim, "shown_type", str((claim.fields or {}).get("claimed_type") or "REFERENCES").upper())
    if ids and ids != old_evidence.get("quote"):
        page_id_map = {p.page_number: p.id for p in version.pages}
        await _replace_citations(db, claim, index, page_id_map)
        await _write_back_quote(db, claim, index, page_id_map)
    audit.record(
        db,
        organization_id=None,
        actor_user_id=getattr(user, "id", None),
        action="claim.fix",
        entity_type="analysis_claim",
        entity_id=claim.id,
        before={**before, "fields": old_fields, "evidence": old_evidence},
        after={"check_status": claim.check_status, "kind": claim.kind, "fields": claim.fields, "note": note, "confirmed_by_person": bool(failing)},
    )
    await settle(db, claim, doc)
    return claim
