"""The checked view of a circular: what a reader may see, and what is held back (spec sections 4.3, 5.1, 6.2).

`build_view` answers `GET /documents/{id}/claims`. For readers it holds only points that passed their
checks (or a person approved), and for every hidden point only its section, page and a plain state: the
point's own wording is never sent. Administrators ask for `all=1` and also get hidden points, their
checks and the reasons in plain words.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.modules.analysis.models import AnalysisClaim, AnalysisLease, DocumentAnalysis
from backend.app.modules.claims import status as S
from backend.app.modules.claims.checks import FAIL, PASS, WAIT
from backend.app.modules.documents.models import Document, DocumentPage

SECTIONS = ("summary", "changes", "requirements", "applies_to", "exemptions", "dates", "links", "clauses")
SECTION_OF_KIND = {
    "SUMMARY_POINT": "summary",
    "KEY_CHANGE": "changes",
    "OBLIGATION": "requirements",
    "APPLIES_TO": "applies_to",
    "EXEMPTION": "exemptions",
    "DATE": "dates",
    "LINK": "links",
    "PROVISION": "clauses",
}
# Fields a reader may see per kind. Link wording (claimed type and so on) stays on the server.
READER_FIELDS = {
    "SUMMARY_POINT": ("text",),
    "KEY_CHANGE": ("text",),
    "OBLIGATION": ("title", "description", "obligation_type", "who", "deadline", "deadline_text", "effective_date", "frequency", "penalty", "clause"),
    "APPLIES_TO": ("entity",),
    "EXEMPTION": ("text",),
    "DATE": ("date_kind", "date"),
    "LINK": (),
    "PROVISION": ("number", "heading", "explanation", "provision_type"),
}
HIDDEN_STATE = {S.CHECKING: "checking", S.WAITING_FOR_PERSON: "waiting_for_team", S.NOT_SHOWN: "not_shown"}


async def latest_analysis(db, doc: Document) -> Optional[DocumentAnalysis]:
    if not doc.current_version_id:
        return None
    return (
        await db.execute(
            select(DocumentAnalysis)
            .where(DocumentAnalysis.document_version_id == doc.current_version_id)
            .order_by(DocumentAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


async def analysing(db, doc: Document) -> bool:
    lease = (await db.execute(select(AnalysisLease).where(AnalysisLease.document_id == doc.id))).scalars().first()
    if lease is None or lease.status != "ACTIVE" or lease.expires_at is None:
        return False
    expires = lease.expires_at if lease.expires_at.tzinfo else lease.expires_at.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


def _quote(claim: AnalysisClaim) -> str:
    return " ... ".join(c.quoted_text for c in claim.citations if c.quoted_text)


def _boxes(claim: AnalysisClaim) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in claim.citations:
        if isinstance(c.quote_boxes, list):
            out.extend(b for b in c.quote_boxes if isinstance(b, dict))
    return out


def _page_number(claim: AnalysisClaim, pages: Dict[str, int]) -> Optional[int]:
    for c in claim.citations:
        n = pages.get(str(c.page_id))
        if n:
            return n
    return None


def _result(claim: AnalysisClaim, name: str) -> Optional[str]:
    for c in claim.checks or []:
        if c.get("name") == name:
            return c.get("result")
    return None


def lines_are_on_the_page(claim: AnalysisClaim) -> bool:
    """True when the quote was found word for word on a page that has been read cleanly."""
    return _result(claim, "QUOTE_FOUND") == PASS and _result(claim, "PAGE_READ") == PASS


def plain_checks(claim: AnalysisClaim) -> List[Dict[str, str]]:
    return [
        {"name": str(c.get("name")), "result": str(c.get("result")), "message": str(c.get("message") or "")}
        for c in (claim.checks or [])
        if c.get("result") != "NOT_RUN"
    ]


def why_not_shown(claim: AnalysisClaim) -> List[str]:
    """The failed checks' plain messages (or what the claim waits for)."""
    out = [str(c.get("message")) for c in (claim.checks or []) if c.get("result") == FAIL and c.get("message")]
    if not out and any(c.get("result") == WAIT for c in (claim.checks or [])):
        out = ["The quoted lines are still being checked against the page image."]
    if not out and S.is_change_link(claim):
        out = ["It changes which rule is in force; a person confirms these."]
    return out


def _reader_fields(claim: AnalysisClaim) -> Dict[str, Any]:
    keep = READER_FIELDS.get(claim.kind, ())
    fields = claim.fields or {}
    return {k: fields.get(k) for k in keep if fields.get(k) not in (None, "")}


async def _link_targets(db, claims: List[AnalysisClaim], user) -> Dict[str, Dict[str, Any]]:
    """For each shown link claim: the circular it names, when the reader may read that circular."""
    from backend.app.modules.relationships.models import DocumentRelationship
    from backend.app.modules.relationships.status import load_visible_docs

    link_claims = [c for c in claims if c.kind == "LINK"]
    if not link_claims:
        return {}
    rel_ids = [c.relationship_id for c in link_claims if c.relationship_id]
    rel_target: Dict[str, Any] = {}
    if rel_ids:
        rows = (await db.execute(select(DocumentRelationship).where(DocumentRelationship.id.in_(rel_ids)))).scalars().all()
        rel_target = {str(r.id): r.target_document_id for r in rows}
    wanted = {}
    for c in link_claims:
        target = (c.fields or {}).get("target_document_id") or rel_target.get(str(c.relationship_id))
        if target:
            wanted[str(c.id)] = target
    readable = await load_visible_docs(db, list(wanted.values()), user)
    out: Dict[str, Dict[str, Any]] = {}
    for c in link_claims:
        target = wanted.get(str(c.id))
        doc = readable.get(str(target)) if target else None
        out[str(c.id)] = {
            "target_document_id": str(doc.id) if doc else None,
            "target_reference": (doc.reference_number if doc and doc.reference_number else None) or (c.fields or {}).get("target_hint"),
        }
    return out


def _item(claim: AnalysisClaim, pages: Dict[str, int], targets: Dict[str, Dict[str, Any]], admin: bool) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": str(claim.id),
        "kind": claim.kind,
        "fields": dict(claim.fields or {}) if admin else _reader_fields(claim),
        "quote": _quote(claim),
        "page_number": _page_number(claim, pages),
        "quote_boxes": _boxes(claim),
        "checked_by": "TEAM" if claim.check_status in (S.APPROVED, S.FIXED) else "CHECKS",
    }
    if claim.kind == "OBLIGATION" and claim.obligation_id:
        item["obligation_id"] = str(claim.obligation_id)
    if claim.kind == "LINK":
        target = targets.get(str(claim.id), {})
        item["link"] = {
            "target_document_id": target.get("target_document_id"),
            "target_reference": target.get("target_reference"),
            "shown_type": S.shown_link_type(claim) if S.is_shown(claim) else "REFERENCES",
        }
    if admin:
        item.update(
            status=claim.check_status,
            shown=S.is_shown(claim),
            review_queue=claim.review_queue,
            is_high_stakes=bool(claim.is_high_stakes),
            checks=plain_checks(claim),
            why=why_not_shown(claim) if claim.check_status not in S.SHOWN_STATUSES else [],
            quote_sentence_ids=list((claim.evidence or {}).get("quote") or []),
        )
        if claim.kind == "LINK" and claim.relationship_id:
            item["relationship_id"] = str(claim.relationship_id)
    return item


def _counts(claims: List[AnalysisClaim]) -> Dict[str, int]:
    """Counts of the points a reader can see on the circular page (clauses are not shown there)."""
    return S.counts([c for c in claims if c.kind != "PROVISION"])


async def _checking_info(db, doc: Document, checking: int) -> Dict[str, Any]:
    info = {"minutes_left": 0, "paused_until": None}
    if not checking:
        return info
    from backend.app.modules.analysis.auto import reading_status

    try:
        r = await reading_status(db, doc)
    except Exception:
        r = {}
    info["minutes_left"] = max(1, int(r.get("minutes_left") or 0))
    if str(r.get("state", "")).startswith("PAUSED"):
        info["paused_until"] = r.get("resumes_at")
    return info


async def build_view(db, doc: Document, user, admin: bool = False) -> Dict[str, Any]:
    running = await analysing(db, doc)
    analysis = await latest_analysis(db, doc)
    empty = {
        "document_id": str(doc.id),
        "state": "ANALYSING" if running else "NO_ANALYSIS",
        "counts": {"total": 0, "shown": 0, "checking": 0, "waiting_for_team": 0, "not_shown": 0},
        "checking": {"minutes_left": 0, "paused_until": None},
        "sections": {s: [] for s in SECTIONS},
        "hidden": [],
    }
    if analysis is None:
        return empty

    claims = list(
        (
            await db.execute(
                select(AnalysisClaim)
                .options(selectinload(AnalysisClaim.citations))
                .where(AnalysisClaim.analysis_id == analysis.id)
                .order_by(AnalysisClaim.order_index)
            )
        ).scalars().all()
    )
    claims = [c for c in claims if c.check_status != S.REJECTED]
    # An analysis made before claims were built has only unchecked placeholders: nothing is shown from it.
    pages = {
        str(pid): n
        for pid, n in (
            await db.execute(select(DocumentPage.id, DocumentPage.page_number).where(DocumentPage.document_version_id == doc.current_version_id))
        ).all()
    }
    shown_claims = [c for c in claims if (admin or c.kind != "PROVISION") and (admin or S.is_shown(c))]
    targets = await _link_targets(db, [c for c in shown_claims if c.kind == "LINK"], user)

    sections: Dict[str, List[Dict[str, Any]]] = {s: [] for s in SECTIONS}
    hidden: List[Dict[str, Any]] = []
    for claim in claims:
        section = SECTION_OF_KIND.get(claim.kind)
        if section is None:
            continue
        if admin:
            sections[section].append(_item(claim, pages, targets, True))
            continue
        if claim.kind == "PROVISION":
            continue
        if S.is_shown(claim):
            sections[section].append(_item(claim, pages, targets, False))
        else:
            allowed = lines_are_on_the_page(claim)
            hidden.append(
                {
                    "section": section,
                    "page_number": _page_number(claim, pages),
                    "state": HIDDEN_STATE.get(claim.check_status, "not_shown"),
                    "quote_boxes": _boxes(claim) if allowed else [],
                }
            )
    counts = _counts(claims)
    return {
        "document_id": str(doc.id),
        "state": "ANALYSING" if running else "READY",
        "counts": counts,
        "checking": await _checking_info(db, doc, counts["checking"]),
        "sections": sections,
        "hidden": hidden,
    }


def claim_summary(claim: AnalysisClaim, pages: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """An administrator's copy of one claim (for decision answers)."""
    return _item(claim, pages or {}, {}, True)
