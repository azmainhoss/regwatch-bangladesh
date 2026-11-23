"""Per-claim status, routing, document status and row sync (spec sections 3.5, 4.1-4.2, 4.4-4.6).

Statuses (`AnalysisClaim.check_status`):
  CHECKING             a check cannot decide yet (hidden, placeholder line)
  PASSED               every applicable check passed (shown)
  WAITING_FOR_PERSON   in the review queue (hidden, except a passed change-the-law link, shown as "Mentions")
  NOT_SHOWN            failed a check, no person required (hidden, placeholder line)
  APPROVED / FIXED     a person decided (shown)
  REJECTED             a person rejected it (never shown, no placeholder)
"""
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.modules.claims import wording as W
from backend.app.modules.claims.checks import FAIL, LINK_EXTRA_CHECKS, PASS, WAIT, set_field
from backend.app.modules.compliance import rules

CHECKING = "CHECKING"
PASSED = "PASSED"
WAITING_FOR_PERSON = "WAITING_FOR_PERSON"
NOT_SHOWN = "NOT_SHOWN"
APPROVED = "APPROVED"
FIXED = "FIXED"
REJECTED = "REJECTED"

SHOWN_STATUSES = (PASSED, APPROVED, FIXED)
DECIDED_STATUSES = (APPROVED, FIXED, REJECTED)
REQUIRED = "REQUIRED"
OPTIONAL = "OPTIONAL"

# Document statuses this module never changes.
PROTECTED_DOCUMENT_STATUSES = ("WITHDRAWN", "SUPERSEDED", "EXTRACTION_FAILED")

ASKED_FOR_REVIEW_CHECK = "ASKED_FOR_REVIEW"


def _parse(value: Any) -> Optional[date]:
    return W.parse_iso_date(value)


def _fields(claim: Any) -> Dict[str, Any]:
    return claim.fields or {}


def is_change_link(claim: Any) -> bool:
    return claim.kind == "LINK" and str(_fields(claim).get("claimed_type") or "").upper() in W.CHANGE_TYPES


def own_dates(claim: Any) -> List[date]:
    """The dates a claim states about itself: a deadline, an effective date, or a DATE point's date."""
    f = _fields(claim)
    values: List[Any] = []
    if claim.kind == "OBLIGATION":
        values = [f.get("deadline"), f.get("effective_date")]
    elif claim.kind == "DATE":
        values = [f.get("date")]
    return [d for d in (_parse(v) for v in values) if d is not None]


def future_deadline(claim: Any, today: date) -> bool:
    return any(d > today for d in own_dates(claim))


def compute_high_stakes(claim: Any, today: date) -> bool:
    """Section 3.5."""
    f = _fields(claim)
    if claim.kind == "OBLIGATION":
        if str(f.get("obligation_type") or "").upper() in ("MANDATORY", "PROHIBITION", "REPORTING"):
            return True
        if f.get("penalty"):
            return True
        deadline = _parse(f.get("deadline"))
        if deadline is not None and deadline > today:
            return True
    if claim.kind == "DATE" and f.get("date_kind") in ("COMPLIANCE", "REPORTING"):
        d = _parse(f.get("date"))
        if d is not None and d > today:
            return True
    if is_change_link(claim):
        return True
    return False


def is_new_circular(doc: Any, today: date) -> bool:
    published = getattr(doc, "publication_date", None)
    if published is None:
        return True  # unknown date: treat as new, so a failure goes to a person
    return (today - published) <= timedelta(days=settings.CLAIM_NEW_CIRCULAR_DAYS)


def judged_checks(claim: Any) -> List[Dict[str, Any]]:
    """The checks that decide the claim. For a link, the checks that only decide how it is called are left out."""
    checks = claim.checks or []
    if claim.kind == "LINK":
        return [c for c in checks if c["name"] not in LINK_EXTRA_CHECKS]
    return list(checks)


def link_extras_all_pass(claim: Any) -> bool:
    extras = [c for c in (claim.checks or []) if c["name"] in LINK_EXTRA_CHECKS]
    return bool(extras) and all(c["result"] == PASS for c in extras)


def route(claim: Any, doc: Any, today: Optional[date] = None, force_review: bool = False) -> None:
    """Sets `check_status`, `review_queue` and `is_high_stakes` from the check results (table 4.2).

    Claims a person already decided are not routed again.
    """
    if claim.check_status in DECIDED_STATUSES:
        return
    today = today or rules.today_dhaka()
    claim.is_high_stakes = compute_high_stakes(claim, today)
    new = is_new_circular(doc, today)
    results = [c["result"] for c in judged_checks(claim)]

    # No point ever waits for a person (user's rule): a point that fails a check is hidden, and a
    # change-the-law link that passed every check is shown as "Mentions" (link_shown_type).
    if FAIL in results:
        claim.check_status, claim.review_queue = NOT_SHOWN, None
        return
    if WAIT in results:
        claim.check_status, claim.review_queue = CHECKING, None
        return
    if force_review:
        # Analysed while a page was not read cleanly: hide its points until it is analysed again.
        claim.check_status, claim.review_queue = NOT_SHOWN, None
        return
    claim.check_status, claim.review_queue = PASSED, None


def ask_for_review(claim: Any) -> None:
    """Hides a shown point until a person decides it."""
    claim.checks = [c for c in (claim.checks or []) if c["name"] != ASKED_FOR_REVIEW_CHECK] + [
        {"name": ASKED_FOR_REVIEW_CHECK, "result": FAIL, "message": "A person asked for this point to be checked."}
    ]
    claim.check_status, claim.review_queue = WAITING_FOR_PERSON, REQUIRED


def is_shown(claim: Any) -> bool:
    """True when a customer may see the claim."""
    if claim.check_status in SHOWN_STATUSES:
        return True
    return waiting_link_is_mention(claim)


def waiting_link_is_mention(claim: Any) -> bool:
    """A change-the-law link that passed every check is shown as 'Mentions' while it waits for a person."""
    if claim.kind != "LINK" or claim.check_status != WAITING_FOR_PERSON or not is_change_link(claim):
        return False
    if _fields(claim).get("shown_type") != "REFERENCES":
        return False
    return not any(c["result"] in (FAIL, WAIT) for c in (claim.checks or []))


def shown_link_type(claim: Any) -> str:
    """The type a customer sees for a link: the claimed type only after a person confirmed it."""
    f = _fields(claim)
    return f.get("shown_type") or "REFERENCES"


# ---------------------------------------------------------------------------
# Document status (4.4)
# ---------------------------------------------------------------------------
def document_status(current: Optional[str], claims: Iterable[Any]) -> Optional[str]:
    """The publication status the claims give the circular. None means 'leave it as it is'."""
    if current in PROTECTED_DOCUMENT_STATUSES:
        return None
    claims = list(claims)
    if any(c.check_status == WAITING_FOR_PERSON and c.review_queue == REQUIRED for c in claims):
        return "AWAITING_REVIEW"
    if any(c.check_status in DECIDED_STATUSES for c in claims):
        return "PUBLISHED_HUMAN_REVIEWED"
    return "PUBLISHED_MACHINE_VERIFIED"


def apply_document_status(doc: Any, claims: Iterable[Any]) -> str:
    new = document_status(doc.publication_status, claims)
    if new is not None:
        doc.publication_status = new
    return doc.publication_status


def counts(claims: Iterable[Any]) -> Dict[str, int]:
    """Plain counts for a circular. Rejected claims are not counted at all."""
    out = {"total": 0, "shown": 0, "checking": 0, "waiting_for_team": 0, "not_shown": 0}
    for c in claims:
        if c.check_status == REJECTED:
            continue
        out["total"] += 1
        if is_shown(c):
            out["shown"] += 1
        elif c.check_status == CHECKING:
            out["checking"] += 1
        elif c.check_status == WAITING_FOR_PERSON:
            out["waiting_for_team"] += 1
        else:
            out["not_shown"] += 1
    return out


# ---------------------------------------------------------------------------
# Obligation and link rows follow their claims (4.5)
# ---------------------------------------------------------------------------
def _change_type_confirmed(claim: Any) -> bool:
    f = _fields(claim)
    return claim.check_status in (APPROVED, FIXED) and str(f.get("shown_type") or "").upper() == str(f.get("claimed_type") or "").upper()


def obligation_row_status(claim: Any) -> str:
    if claim.check_status == REJECTED:
        return "REJECTED"
    return "VERIFIED" if claim.check_status in SHOWN_STATUSES else "PENDING_REVIEW"


def link_row_status(claim: Any) -> str:
    if claim.check_status == REJECTED:
        return "REJECTED"
    if _change_type_confirmed(claim):
        return "VERIFIED"
    # A link whose claimed type changes another rule never counts as VERIFIED without a person, even when
    # it is shown only as a mention: the row keeps the claimed type, and in-force code reads VERIFIED rows.
    if is_shown(claim) and not is_change_link(claim):
        return "VERIFIED"
    return "PENDING_REVIEW"


async def sync_rows(db, claims: Iterable[Any]) -> None:
    """Makes each obligation and link row agree with its claim. A FIXED claim writes its fields back."""
    from backend.app.modules.obligations.models import Obligation
    from backend.app.modules.relationships.models import DocumentRelationship

    claims = [c for c in claims if c.kind in ("OBLIGATION", "LINK")]
    obl_ids = [c.obligation_id for c in claims if c.kind == "OBLIGATION" and c.obligation_id]
    rel_ids = [c.relationship_id for c in claims if c.kind == "LINK" and c.relationship_id]
    obligations = {}
    relationships = {}
    if obl_ids:
        rows = (await db.execute(select(Obligation).where(Obligation.id.in_(obl_ids)))).scalars().all()
        obligations = {str(r.id): r for r in rows}
    if rel_ids:
        rows = (await db.execute(select(DocumentRelationship).where(DocumentRelationship.id.in_(rel_ids)))).scalars().all()
        relationships = {str(r.id): r for r in rows}

    for claim in claims:
        f = _fields(claim)
        if claim.kind == "OBLIGATION":
            row = obligations.get(str(claim.obligation_id))
            if row is None:
                continue
            row.verification_status = obligation_row_status(claim)
            if claim.check_status == FIXED:
                if f.get("title"):
                    row.title = f["title"]
                if f.get("description"):
                    row.requirement_description = f["description"]
                if f.get("obligation_type"):
                    row.obligation_type = f["obligation_type"]
                row.applicability_summary = f.get("who") or ""
                deadline = _parse(f.get("deadline"))
                row.explicit_deadline = deadline
                row.deadline_description = f.get("deadline_text") or f.get("deadline")
                if f.get("frequency"):
                    row.frequency = f["frequency"]
        else:
            row = relationships.get(str(claim.relationship_id))
            if row is None:
                continue
            row.verification_status = link_row_status(claim)
            if claim.check_status == FIXED and f.get("claimed_type"):
                row.relationship_type = str(f["claimed_type"]).upper()
                if f.get("target_hint"):
                    row.target_reference_hint = str(f["target_hint"])[:255]
            target = f.get("target_document_id")
            if target and row.target_document_id is None:
                try:
                    row.target_document_id = UUID(str(target))
                except ValueError:
                    pass


def shown_text_for_summary(claims: Iterable[Any]) -> str:
    """The shown summary points joined by a space (kept in `DocumentAnalysis.executive_summary`)."""
    ordered = sorted((c for c in claims if c.kind == "SUMMARY_POINT" and is_shown(c)), key=lambda c: c.order_index or 0)
    return " ".join((_fields(c).get("text") or "").strip() for c in ordered if _fields(c).get("text"))


# ---------------------------------------------------------------------------
# A person's earlier decisions carry over (4.6)
# ---------------------------------------------------------------------------
async def carry_over(db, version_id: Any, exclude_analysis_id: Any, claims: List[Any]) -> int:
    """Copies a person's decision onto each new claim whose fingerprint matches a decided claim of the previous analysis.

    Returns how many claims carried a decision.
    """
    from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis

    previous = (
        await db.execute(
            select(DocumentAnalysis)
            .where(DocumentAnalysis.document_version_id == version_id, DocumentAnalysis.id != exclude_analysis_id)
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if previous is None:
        return 0
    old = (
        await db.execute(
            select(AnalysisClaim).where(
                AnalysisClaim.analysis_id == previous.id,
                AnalysisClaim.check_status.in_(DECIDED_STATUSES),
                AnalysisClaim.fingerprint.is_not(None),
            )
        )
    ).scalars().all()
    by_fp: Dict[str, Any] = {}
    for c in sorted(old, key=lambda c: c.reviewed_at.timestamp() if c.reviewed_at else 0):
        by_fp[c.fingerprint] = c  # the latest decision wins
    carried = 0
    for claim in claims:
        match = by_fp.get(claim.fingerprint)
        if match is None:
            continue
        claim.check_status = match.check_status
        claim.review_queue = None
        claim.reviewed_by = match.reviewed_by
        claim.reviewed_at = match.reviewed_at
        claim.review_note = match.review_note
        claim.reject_reason = match.reject_reason
        claim.carried_from_claim_id = match.id
        claim.original_fields = match.original_fields
        if match.check_status == FIXED:
            claim.fields = dict(match.fields or {})
            claim.evidence = dict(match.evidence or {})
        elif claim.kind == "LINK" and match.check_status == APPROVED and (match.fields or {}).get("shown_type"):
            set_field(claim, "shown_type", match.fields["shown_type"])
        carried += 1
    return carried
