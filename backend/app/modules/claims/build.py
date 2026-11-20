"""One claim per shown item of an analysis (docs/specs/CLAIM_CHECKS_SPEC.md section 3.1).

`build_claims` turns the analysis answer into plain drafts: the fields to show, the sentence IDs
that are the evidence for each field, and a fingerprint that stays the same when the same point
comes back unchanged in a later run. Nothing here checks anything; see `checks.py`.
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.modules.analysis.citations import CitationValidator
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims.wording import entity_for, norm

KINDS = ("SUMMARY_POINT", "KEY_CHANGE", "OBLIGATION", "APPLIES_TO", "EXEMPTION", "DATE", "LINK", "PROVISION")

# Values that are worked out by the checks, so they are left out of the fingerprint.
FINGERPRINT_SKIP = ("shown_type", "target_document_id")

DATE_KINDS = (
    ("effective_date", "EFFECTIVE"),
    ("compliance_deadline", "COMPLIANCE"),
    ("reporting_deadline", "REPORTING"),
)

CLAIM_TYPE_FOR_KIND = {"PROVISION": "PROVISION_ASSERTION"}


@dataclass
class ClaimDraft:
    kind: str
    fields: Dict[str, Any]
    evidence: Dict[str, List[str]]
    order_index: int = 0
    # Position of the source item in its payload list (obligations, relationships, provisions).
    source_index: Optional[int] = None
    statement: str = ""
    fingerprint: str = ""
    verification_status: str = "UNVERIFIED"
    # Filled in by the checks and by routing. A saved claim row has the same attributes.
    checks: List[Dict[str, Any]] = field(default_factory=list)
    check_status: str = "CHECKING"
    review_queue: Optional[str] = None
    is_high_stakes: bool = False
    obligation_id: Any = None
    relationship_id: Any = None
    reviewed_by: Any = None
    reviewed_at: Any = None
    review_note: Optional[str] = None
    reject_reason: Optional[str] = None
    carried_from_claim_id: Any = None
    original_fields: Optional[Dict[str, Any]] = None


def _ids(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: List[str] = []
    for v in value:
        s = str(v).strip().strip("[]").lower()
        if s and s not in out:
            out.append(s)
    return out


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def claim_fingerprint(kind: str, evidence: Dict[str, List[str]], fields: Dict[str, Any]) -> str:
    """SHA-256 (internal only) of kind + sorted evidence sentence IDs + normalised fields."""
    ids = sorted({i for v in (evidence or {}).values() for i in (v or [])})
    kept = {
        k: norm(str(v)) if v is not None else ""
        for k, v in sorted((fields or {}).items())
        if k not in FINGERPRINT_SKIP
    }
    raw = json.dumps({"kind": kind, "ids": ids, "fields": kept}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quote_ids(item: Dict[str, Any], key: str) -> List[str]:
    """Evidence IDs of an item. An item whose IDs could not all be resolved has no evidence at all."""
    if item.get("needs_human_review"):
        return []
    return _ids(item.get(key))


def _with_fallback(evidence: Dict[str, List[str]], keys) -> Dict[str, List[str]]:
    quote = evidence.get("quote", [])
    for k in keys:
        if not evidence.get(k):
            evidence[k] = list(quote)
    return evidence


def _verification_status(evidence: Dict[str, List[str]], index: SentenceIndex) -> str:
    ids = evidence.get("quote") or []
    if not ids:
        return "UNVERIFIED"
    span = index.resolve(ids)
    if not span.ok:
        return "UNVERIFIED"
    res = CitationValidator.validate_item_quote(span.quote, span.page_number or 1, index.pages, span.fragments)
    return res.status


def build_claims(payload: Dict[str, Any], index: SentenceIndex, doc: Any = None) -> List[ClaimDraft]:
    """The claims of one analysis, in reading order. `payload` is the answer after `apply_quote_ids`."""
    drafts: List[ClaimDraft] = []

    def add(kind: str, fields: Dict[str, Any], evidence: Dict[str, List[str]], statement: str, source_index: Optional[int] = None) -> None:
        draft = ClaimDraft(
            kind=kind,
            fields=fields,
            evidence=evidence,
            order_index=len(drafts),
            source_index=source_index,
            statement=(statement or kind)[:4000],
        )
        draft.fingerprint = claim_fingerprint(kind, evidence, fields)
        draft.verification_status = _verification_status(evidence, index)
        if kind == "LINK":
            draft.fields["shown_type"] = "REFERENCES"
        drafts.append(draft)

    summary = payload.get("executive_summary") if isinstance(payload.get("executive_summary"), dict) else {}
    for kind, key in (("SUMMARY_POINT", "summary_points"), ("KEY_CHANGE", "key_changes")):
        for item in summary.get(key) or []:
            if not isinstance(item, dict):
                continue
            text = _text(item.get("text"))
            if not text:
                continue
            add(kind, {"text": text}, {"quote": _quote_ids(item, "evidence_ids")}, text)

    for i, obl in enumerate(payload.get("obligations") or []):
        if not isinstance(obl, dict):
            continue
        who_raw = _text(obl.get("responsible_entity"))
        evidence = _with_fallback(
            {
                "quote": _quote_ids(obl, "quote_span_ids"),
                "who": _ids(obl.get("who_ids")),
                "deadline": _ids(obl.get("deadline_ids")),
                "effective_date": _ids(obl.get("effective_date_ids")),
                "penalty": _ids(obl.get("consequence_ids")),
            },
            ("who", "deadline", "effective_date", "penalty"),
        )
        fields = {
            "title": _text(obl.get("title")),
            "description": _text(obl.get("requirement_description")),
            "obligation_type": _text(obl.get("obligation_type")) or "MANDATORY",
            "who": entity_for(who_raw) or who_raw,
            "deadline": _text(obl.get("explicit_deadline")),
            # A deadline that is not a calendar date, in plain words ("within 15 days after each quarter end").
            "deadline_text": _text(obl.get("deadline_text")),
            "effective_date": _text(obl.get("effective_date")),
            "frequency": _text(obl.get("reporting_frequency")),
            "penalty": _text(obl.get("consequence")),
            "clause": _text(obl.get("clause_reference")),
        }
        add("OBLIGATION", fields, evidence, fields["title"] or fields["description"] or "Requirement", source_index=i)

    applicability = payload.get("applicability") if isinstance(payload.get("applicability"), dict) else {}
    for item in applicability.get("covered") or []:
        if not isinstance(item, dict):
            continue
        entity_raw = _text(item.get("entity"))
        if not entity_raw:
            continue
        add("APPLIES_TO", {"entity": entity_for(entity_raw) or entity_raw},
            {"quote": _quote_ids(item, "evidence_ids")}, entity_raw)
    for item in applicability.get("exemptions") or []:
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text"))
        if not text:
            continue
        add("EXEMPTION", {"text": text}, {"quote": _quote_ids(item, "evidence_ids")}, text)

    deadlines = payload.get("deadlines") if isinstance(payload.get("deadlines"), dict) else {}
    for key, date_kind in DATE_KINDS:
        item = deadlines.get(key)
        if isinstance(item, dict):
            value, ev = _text(item.get("date")), _quote_ids(item, "evidence_ids")
        else:
            value, ev = _text(item), []
        if not value:
            continue
        add("DATE", {"date_kind": date_kind, "date": value}, {"quote": ev}, f"{date_kind} {value}")

    for i, rel in enumerate(payload.get("relationships") or []):
        if not isinstance(rel, dict):
            continue
        claimed = (_text(rel.get("relationship_type")) or "REFERENCES").upper()
        hint = _text(rel.get("target_reference_hint"))
        add(
            "LINK",
            {"claimed_type": claimed, "shown_type": "REFERENCES", "target_hint": hint, "target_document_id": None},
            {"quote": _quote_ids(rel, "quote_span_ids")},
            f"{claimed} {hint or ''}".strip(),
            source_index=i,
        )

    for i, prov in enumerate(payload.get("provisions") or []):
        if not isinstance(prov, dict):
            continue
        fields = {
            "number": _text(prov.get("provision_number")),
            "heading": _text(prov.get("heading")),
            "explanation": _text(prov.get("normalized_explanation")),
            "provision_type": _text(prov.get("provision_type")),
        }
        add("PROVISION", fields, {"quote": _quote_ids(prov, "quote_span_ids")},
            fields["explanation"] or fields["heading"] or "Provision claim", source_index=i)

    _fill_who_from_sole_addressee(drafts)
    return drafts


def _fill_who_from_sole_addressee(drafts: List[ClaimDraft]) -> None:
    """A requirement that does not name who must act falls on the circular's addressee. When the circular covers
    exactly one kind of institution, such a requirement gets that kind, with the sentence that names it as evidence,
    so the who check still tests it against the page (AUTORESEARCH_LOG round 13)."""
    covered: Dict[str, List[str]] = {}
    for d in drafts:
        if d.kind == "APPLIES_TO" and d.fields.get("entity") and (d.evidence or {}).get("quote"):
            covered.setdefault(d.fields["entity"], list(d.evidence["quote"]))
    if len(covered) != 1:
        return
    entity, ids = next(iter(covered.items()))
    for d in drafts:
        if d.kind == "OBLIGATION" and not d.fields.get("who"):
            d.fields["who"] = entity
            d.evidence["who"] = list(ids)
            d.fingerprint = claim_fingerprint(d.kind, d.evidence, d.fields)


async def save_claims(db, analysis: Any, drafts: List[ClaimDraft], index: SentenceIndex, page_id_map: Dict[int, Any]) -> List[Any]:
    """Saves the drafts as claim rows with one citation row per run of quoted sentences."""
    from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation

    rows: List[Any] = []
    for d in drafts:
        row = AnalysisClaim(
            analysis_id=analysis.id,
            claim_type=CLAIM_TYPE_FOR_KIND.get(d.kind, f"{d.kind}_ASSERTION"),
            statement=d.statement or d.kind,
            verification_status=d.verification_status,
            kind=d.kind,
            order_index=d.order_index,
            fields=d.fields,
            evidence=d.evidence,
            checks=d.checks,
            check_status=d.check_status,
            review_queue=d.review_queue,
            is_high_stakes=d.is_high_stakes,
            obligation_id=d.obligation_id,
            relationship_id=d.relationship_id,
            fingerprint=d.fingerprint,
            carried_from_claim_id=d.carried_from_claim_id,
            original_fields=d.original_fields,
            reviewed_by=d.reviewed_by,
            reviewed_at=d.reviewed_at,
            review_note=d.review_note,
            reject_reason=d.reject_reason,
        )
        db.add(row)
        await db.flush()
        span = index.resolve(d.evidence.get("quote") or [])
        if span.ok:
            for frag in span.fragments:
                page_id = page_id_map.get(frag["page_number"])
                if page_id is None:
                    continue
                boxes = [b for b in span.boxes if b["page_number"] == frag["page_number"]]
                db.add(ClaimCitation(
                    claim_id=row.id,
                    page_id=page_id,
                    quoted_text=frag["text"],
                    quote_span_ids=frag["sentence_ids"],
                    quote_boxes=boxes,
                    match_score=1.0 if d.verification_status in ("VERIFIED_EXACT", "VERIFIED_NORMALIZED") else 0.0,
                ))
        rows.append(row)
    return rows
