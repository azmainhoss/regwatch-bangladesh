"""Plain code checks on each claim (docs/specs/CLAIM_CHECKS_SPEC.md section 3.3).

Each check gives PASS, FAIL, WAIT (cannot decide yet) or NOT_RUN, with a plain message for the
review screen. Everything here is deterministic code: no network, no model.
`check_claim` works on anything with `kind`, `fields` and `evidence` (a draft or a saved claim row).
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.app.modules.analysis.citations import STATE_VERIFIED_EXACT, STATE_VERIFIED_NORMALIZED, CitationValidator
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import wording as W
from backend.app.modules.extraction.quality import VISION_METHODS
from backend.app.modules.relationships import linking

PASS, FAIL, WAIT, NOT_RUN = "PASS", "FAIL", "WAIT", "NOT_RUN"

# Checks that only decide how a link is shown (mention or the stronger type). Their failure never hides the link.
LINK_EXTRA_CHECKS = ("CHANGE_WORDS", "CLARIFY_WORDS", "TARGET_FOUND", "TARGET_OLDER")

IMAGE_READ_METHODS = VISION_METHODS  # pages read from their image, not from the PDF text layer
UNREAD_QUALITY = ("NEEDS_HUMAN_REVIEW", "PENDING_VISION", "READ_FAILED")

DUTY_ADJECTIVE = {
    "MANDATORY": "must be done",
    "PROHIBITION": "must not be done",
    "PERMISSION": "is allowed",
    "REPORTING": "must be reported",
    "APPROVAL": "needs approval",
    "RECORD_RETENTION": "records must be kept",
    "DISCLOSURE": "must be disclosed",
    "CONDITIONAL": "applies on a condition",
    "RECOMMENDATION": "is advised",
}


@dataclass
class PageInfo:
    page_number: int
    quality_status: str = "SUCCESS_NATIVE"
    is_human_corrected: bool = False
    extraction_method: str = "TEXT_LAYER"

    @property
    def needs_reading_check(self) -> bool:
        return self.extraction_method in IMAGE_READ_METHODS and not self.is_human_corrected

    @property
    def not_read(self) -> bool:
        return self.quality_status in UNREAD_QUALITY and not self.is_human_corrected


@dataclass
class CheckContext:
    index: SentenceIndex
    pages: Dict[int, PageInfo] = field(default_factory=dict)
    issue_date: Optional[date] = None
    # sentence ID -> status of its second reading (rows for the current page text only)
    reading: Dict[str, str] = field(default_factory=dict)
    # target hint -> (library document id or None, its publication date or None)
    link_targets: Dict[str, Tuple[Any, Optional[date]]] = field(default_factory=dict)
    # sentence ID -> [[old, new], ...] figure fixes from two agreeing page readings (reading status CORRECTED)
    fixes: Dict[str, List[List[str]]] = field(default_factory=dict)

    @property
    def addressee_text(self) -> str:
        """The top of page 1, where a circular names who it is sent to: up to the greeting ("Dear Sir",
        "প্রিয় মহোদয়"), at least the first 8 sentences, at most 1,500 characters."""
        parts: List[str] = []
        size = 0
        for n, i in enumerate(self.index.order.get(1, [])):
            text = self.index.sentences[i].text
            low = W.norm(text)
            if n >= 8 and (size >= 1500 or any(g in low for g in W.GREETINGS)):
                break
            parts.append(text)
            size += len(text)
            if n >= 8 and any(g in low for g in W.GREETINGS):
                break
        return " ".join(parts)


def result(name: str, res: str, message: str = "") -> Dict[str, Any]:
    return {"name": name, "result": res, "message": message}


def _page_of(sentence_id: str) -> int:
    try:
        return int(sentence_id.split(".")[0].lstrip("p"))
    except (ValueError, IndexError):
        return 1


def known_ids(claim: Any, ctx: CheckContext, key: str = "quote") -> List[str]:
    ids = (claim.evidence or {}).get(key) or (claim.evidence or {}).get("quote") or []
    return [i for i in ids if i in ctx.index.sentences]


def sentence_text(ctx: CheckContext, sid: str) -> str:
    """A sentence as printed: our reading, with the figures two agreeing page readings corrected."""
    text = ctx.index.sentences[sid].text
    if sid in ctx.fixes:
        from backend.app.modules.claims.reading import apply_figure_fixes

        text = apply_figure_fixes(text, ctx.fixes[sid])
    return text


def evidence_text(claim: Any, ctx: CheckContext, key: str = "quote") -> str:
    return " ".join(sentence_text(ctx, i) for i in known_ids(claim, ctx, key))


def all_evidence_ids(claim: Any, ctx: CheckContext) -> List[str]:
    out: List[str] = []
    for ids in (claim.evidence or {}).values():
        for i in ids or []:
            if i in ctx.index.sentences and i not in out:
                out.append(i)
    return out


def _first_page(claim: Any, ctx: CheckContext, key: str = "quote") -> int:
    ids = known_ids(claim, ctx, key)
    return _page_of(ids[0]) if ids else 1


# ---------------------------------------------------------------------------
# Checks that apply to every claim
# ---------------------------------------------------------------------------
def check_has_evidence(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    if known_ids(claim, ctx, "quote"):
        return result("HAS_EVIDENCE", PASS)
    return result("HAS_EVIDENCE", FAIL, "This point does not say which sentence it comes from.")


def check_quote_found(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    ids = known_ids(claim, ctx, "quote")
    span = ctx.index.resolve(ids)
    if not span.ok:
        return result("QUOTE_FOUND", FAIL, f"The quoted words are not on page {_first_page(claim, ctx)}.")
    for frag in span.fragments:
        res = CitationValidator.validate_quote_across_document(frag["text"], ctx.index.pages, frag["page_number"])
        if res.status not in (STATE_VERIFIED_EXACT, STATE_VERIFIED_NORMALIZED):
            return result("QUOTE_FOUND", FAIL, f"The quoted words are not on page {frag['page_number']}.")
    return result("QUOTE_FOUND", PASS)


def check_page_read(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    for sid in all_evidence_ids(claim, ctx):
        info = ctx.pages.get(_page_of(sid))
        if info is not None and info.not_read:
            return result("PAGE_READ", FAIL, f"Page {info.page_number} has not been read cleanly yet.")
    return result("PAGE_READ", PASS)


def check_quote_reading(claim: Any, ctx: CheckContext) -> Optional[Dict[str, Any]]:
    """None when no evidence sentence is on an image-read page."""
    statuses: List[Tuple[str, int]] = []
    for sid in all_evidence_ids(claim, ctx):
        page = _page_of(sid)
        info = ctx.pages.get(page)
        if info is None or not info.needs_reading_check:
            continue
        statuses.append((ctx.reading.get(sid, "WAITING"), page))
    if not statuses:
        return None
    for status, page in statuses:
        if status == "MISREAD":
            return result("QUOTE_READING", FAIL, f"The second reading of page {page} does not match ours.")
    for status, page in statuses:
        if status == "UNCLEAR":
            return result("QUOTE_READING", FAIL, f"Part of page {page} could not be read clearly.")
    for status, page in statuses:
        if status not in ("CLEAN", "NOT_NEEDED", "CORRECTED"):
            return result("QUOTE_READING", WAIT, f"Waiting for the second reading of page {page}.")
    return result("QUOTE_READING", PASS)


# ---------------------------------------------------------------------------
# Dates and numbers
# ---------------------------------------------------------------------------
def _date_check(value: Any, text: str, issue_date: Optional[date], allow_immediate: bool) -> Optional[str]:
    """None when the date is written in the text, else the message."""
    parsed = W.parse_iso_date(value)
    if parsed is None:
        return f"The date {value} is not in the quoted sentences."
    if parsed in W.dates_in(text):
        return None
    if allow_immediate and issue_date is not None and parsed == issue_date and W.has_immediate_effect(text):
        return None
    return f"The date {W.date_words(parsed)} is not in the quoted sentences."


def check_dates(claim: Any, ctx: CheckContext) -> Optional[Dict[str, Any]]:
    kind, f = claim.kind, claim.fields or {}
    problems: List[str] = []
    if kind == "OBLIGATION":
        for key, immediate_ok in (("deadline", False), ("effective_date", True)):
            if f.get(key):
                msg = _date_check(f[key], evidence_text(claim, ctx, key), ctx.issue_date, immediate_ok)
                if msg:
                    problems.append(msg)
        if f.get("deadline_text"):
            have = W.dates_in(evidence_text(claim, ctx, "deadline"))
            for d in sorted(W.dates_in(f["deadline_text"])):
                if d not in have:
                    problems.append(f"The date {W.date_words(d)} is not in the quoted sentences.")
        applies = bool(f.get("deadline") or f.get("effective_date") or W.dates_in(f.get("deadline_text") or ""))
    elif kind == "DATE":
        applies = bool(f.get("date"))
        if applies:
            msg = _date_check(f["date"], evidence_text(claim, ctx), ctx.issue_date, f.get("date_kind") == "EFFECTIVE")
            if msg:
                problems.append(msg)
    elif kind in ("SUMMARY_POINT", "KEY_CHANGE", "EXEMPTION"):
        written = sorted(W.dates_in(f.get("text") or ""))
        applies = bool(written)
        have = W.dates_in(evidence_text(claim, ctx))
        for d in written:
            if d not in have:
                problems.append(f"The date {W.date_words(d)} is not in the quoted sentences.")
    else:
        return None
    if not applies:
        return None
    if problems:
        return result("DATES", FAIL, problems[0])
    return result("DATES", PASS)


def _number_pairs(claim: Any, ctx: CheckContext) -> List[Tuple[str, str]]:
    """(text, evidence text) pairs whose numbers must match."""
    f = claim.fields or {}
    if claim.kind in ("SUMMARY_POINT", "KEY_CHANGE", "EXEMPTION"):
        return [(f.get("text") or "", evidence_text(claim, ctx))]
    if claim.kind == "OBLIGATION":
        quote = evidence_text(claim, ctx)
        pairs = [(f.get("title") or "", quote), (f.get("description") or "", quote)]
        if f.get("penalty"):
            pairs.append((f["penalty"], evidence_text(claim, ctx, "penalty")))
        if f.get("deadline_text"):
            pairs.append((f["deadline_text"], evidence_text(claim, ctx, "deadline")))
        return pairs
    return []


def check_numbers(claim: Any, ctx: CheckContext) -> Optional[Dict[str, Any]]:
    pairs = _number_pairs(claim, ctx)
    if not pairs:
        return None
    any_numbers = False
    for text, ev in pairs:
        wanted = W.numbers_in(text)
        if not wanted:
            continue
        any_numbers = True
        have = W.numbers_in(ev)
        for number in wanted:
            if number not in have:
                return result("NUMBERS", FAIL, f"The number {number} is not in the quoted sentences.")
    return result("NUMBERS", PASS) if any_numbers else None


# ---------------------------------------------------------------------------
# Wording of requirements
# ---------------------------------------------------------------------------
def check_duty_wording(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    typ = str((claim.fields or {}).get("obligation_type") or "").upper()
    quote = evidence_text(claim, ctx)
    words = W.DUTY_WORDS.get(typ)
    if words is None:
        return result("DUTY_WORDING", FAIL, "The kind of requirement is not one we recognise.")
    if typ == "PERMISSION":
        ok = W.has_permission_word(quote)
    elif typ == "PROHIBITION":
        ok = (W.has_any(quote, words) or W.has_any(quote, W.CAP_WORDS, mode="stem")
              or W.has_any(quote, W.ONLY_WORDS))
    else:
        ok = W.has_any(quote, words)
    strong_no = W.has_any(quote, W.STRONG_PROHIBITION)
    if ok and typ not in ("PROHIBITION", "CONDITIONAL", "RECOMMENDATION") and strong_no:
        return result("DUTY_WORDING", FAIL, "The point says this must be done, but the quote says it must not.")
    if not ok:
        if typ == "PERMISSION" and strong_no:
            return result("DUTY_WORDING", FAIL, "The point says this is allowed, but the quote says it is not.")
        if typ == "PROHIBITION":
            return result("DUTY_WORDING", FAIL, "The point says this must not be done, but the quote does not say so.")
        return result("DUTY_WORDING", FAIL, f"The point says this {DUTY_ADJECTIVE.get(typ, 'applies')}, but the quote does not say so.")
    return result("DUTY_WORDING", PASS)


def check_who(claim: Any, ctx: CheckContext) -> Optional[Dict[str, Any]]:
    f = claim.fields or {}
    if claim.kind == "OBLIGATION":
        value, key = f.get("who"), "who"
    elif claim.kind == "APPLIES_TO":
        value, key = f.get("entity"), "quote"
    else:
        return None
    if claim.kind == "OBLIGATION" and not value:
        return None
    msg = "Who must do this is not named in the circular."
    entity = W.entity_for(value)
    if entity is None:
        return result("WHO", FAIL, msg)
    addressee = ctx.addressee_text
    if W.alias_in(entity, evidence_text(claim, ctx, key)) or W.alias_in(entity, addressee):
        return result("WHO", PASS)
    if entity in W.SCHEDULED_BANK_KINDS and W.has_any(addressee, W.ADDRESSEE_ALL_SCHEDULED, mode="stem"):
        return result("WHO", PASS)
    return result("WHO", FAIL, msg)


def check_exempt_words(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    if W.has_any(evidence_text(claim, ctx), W.EXEMPT_WORDS, mode="stem"):
        return result("EXEMPT_WORDS", PASS)
    return result("EXEMPT_WORDS", FAIL, "The quote does not state an exception.")


ALL_CHANGE_WORDS = tuple(dict.fromkeys(w for words in W.CHANGE_WORDS.values() for w in words))


def check_overclaim(claim: Any, ctx: CheckContext) -> Optional[Dict[str, Any]]:
    text = (claim.fields or {}).get("text") or ""
    if not W.has_any(text, ALL_CHANGE_WORDS, mode="stem"):
        return None
    if W.has_any(evidence_text(claim, ctx), ALL_CHANGE_WORDS, mode="stem"):
        return result("OVERCLAIM", PASS)
    return result("OVERCLAIM", FAIL, "The point says a rule changed, but the quote does not.")


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------
def _search_form(text: str) -> str:
    """Quote text in the same shape as a normalised reference, without cutting at 'dated'."""
    s = linking._prepare(text)
    s = linking._NO_WORD.sub(" no ", s)
    s = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", "/", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"[^\w/]+", " ", s).replace("_", " ")
    s = re.sub(r"(?<![\d/])0+(?=\d)", "", s)
    s = re.sub(r"(?<=/)0+(?=\d)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def check_target_named(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    keys = linking.reference_keys((claim.fields or {}).get("target_hint"))
    quote = _search_form(evidence_text(claim, ctx))
    for key in keys:
        if re.search(r"(?<![\w/])" + re.escape(key) + r"(?![\w/])", quote):
            return result("TARGET_NAMED", PASS)
    return result("TARGET_NAMED", FAIL, "The other circular is not named in the quote.")


def check_change_words(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    claimed = str((claim.fields or {}).get("claimed_type") or "").upper()
    if W.has_any(evidence_text(claim, ctx), W.CHANGE_WORDS.get(claimed, ()), mode="stem"):
        return result("CHANGE_WORDS", PASS)
    return result("CHANGE_WORDS", FAIL, "The quote does not use words that change another rule.")


def check_clarify_words(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    if W.has_any(evidence_text(claim, ctx), W.CLARIFY_WORDS, mode="stem"):
        return result("CLARIFY_WORDS", PASS)
    return result("CLARIFY_WORDS", FAIL, "The quote does not say it clarifies another rule.")


def _target(claim: Any, ctx: CheckContext) -> Tuple[Any, Optional[date]]:
    return ctx.link_targets.get((claim.fields or {}).get("target_hint") or "", (None, None))


def check_target_found(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    if _target(claim, ctx)[0] is not None:
        return result("TARGET_FOUND", PASS)
    return result("TARGET_FOUND", FAIL, "The other circular is not in the library, or more than one matches.")


def check_target_older(claim: Any, ctx: CheckContext) -> Dict[str, Any]:
    target_date = _target(claim, ctx)[1]
    if target_date is not None and ctx.issue_date is not None and target_date < ctx.issue_date:
        return result("TARGET_OLDER", PASS)
    return result("TARGET_OLDER", FAIL, "The other circular is not older than this one.")


def link_shown_type(claim: Any, checks: List[Dict[str, Any]]) -> str:
    """What a link may be called before a person looks at it: only 'Mentions' (REFERENCES), or
    'Clarifies' when its quote uses clarify words. A change-the-law type waits for a person."""
    claimed = str((claim.fields or {}).get("claimed_type") or "REFERENCES").upper()
    by_name = {c["name"]: c["result"] for c in checks}
    if claimed == "CLARIFIES" and by_name.get("CLARIFY_WORDS") == PASS:
        return "CLARIFIES"
    return "REFERENCES"


# ---------------------------------------------------------------------------
# Running everything
# ---------------------------------------------------------------------------
def check_claim(claim: Any, ctx: CheckContext) -> List[Dict[str, Any]]:
    """Every check that applies to this claim, in a fixed order."""
    out: List[Dict[str, Any]] = [check_has_evidence(claim, ctx)]
    if out[0]["result"] == PASS:
        out.append(check_quote_found(claim, ctx))
        out.append(check_page_read(claim, ctx))
        reading = check_quote_reading(claim, ctx)
        if reading:
            out.append(reading)

        kind = claim.kind
        extra: List[Optional[Dict[str, Any]]] = []
        if kind in ("OBLIGATION", "DATE", "SUMMARY_POINT", "KEY_CHANGE", "EXEMPTION"):
            extra.append(check_dates(claim, ctx))
        if kind in ("SUMMARY_POINT", "KEY_CHANGE", "EXEMPTION", "OBLIGATION"):
            extra.append(check_numbers(claim, ctx))
        if kind == "OBLIGATION":
            extra.append(check_duty_wording(claim, ctx))
        if kind in ("OBLIGATION", "APPLIES_TO"):
            extra.append(check_who(claim, ctx))
        if kind == "EXEMPTION":
            extra.append(check_exempt_words(claim, ctx))
        if kind in ("SUMMARY_POINT", "KEY_CHANGE"):
            extra.append(check_overclaim(claim, ctx))
        if kind == "LINK":
            claimed = str((claim.fields or {}).get("claimed_type") or "").upper()
            extra.append(check_target_named(claim, ctx))
            if claimed in W.CHANGE_TYPES:
                extra.append(check_change_words(claim, ctx))
                extra.append(check_target_found(claim, ctx))
                extra.append(check_target_older(claim, ctx))
            elif claimed == "CLARIFIES":
                extra.append(check_clarify_words(claim, ctx))
        out.extend(e for e in extra if e)
    out.append(result("MEANING", NOT_RUN))
    return out


def page_infos(pages) -> Dict[int, PageInfo]:
    return {
        p.page_number: PageInfo(
            page_number=p.page_number,
            quality_status=p.quality_status or "SUCCESS_NATIVE",
            is_human_corrected=bool(p.is_human_corrected),
            extraction_method=p.extraction_method or "TEXT_LAYER",
        )
        for p in pages
    }


async def load_link_targets(db, claims, exclude_document_id) -> Dict[str, Tuple[Any, Optional[date]]]:
    """For each link claim: the one shared-library circular its hint names (and its date), or (None, None)."""
    from sqlalchemy import select
    from backend.app.modules.documents.models import Document

    hints = {
        (c.fields or {}).get("target_hint")
        for c in claims
        if c.kind == "LINK" and (c.fields or {}).get("target_hint")
    }
    if not hints:
        return {}
    index = await linking._shared_reference_index(db)
    found: Dict[str, Any] = {}
    for hint in hints:
        found[hint] = linking._unique_match(linking.reference_keys(hint), index, exclude=exclude_document_id)
    ids = {v for v in found.values() if v is not None}
    dates: Dict[Any, Optional[date]] = {}
    if ids:
        rows = (await db.execute(select(Document.id, Document.publication_date).where(Document.id.in_(ids)))).all()
        dates = {r[0]: r[1] for r in rows}
    return {h: (v, dates.get(v) if v is not None else None) for h, v in found.items()}


def set_field(claim: Any, key: str, value: Any) -> None:
    """Changes one field. The whole dict is replaced so a saved row notices the change."""
    claim.fields = {**(claim.fields or {}), key: value}


def apply_checks(claim: Any, ctx: CheckContext) -> None:
    checks = check_claim(claim, ctx)
    claim.checks = checks
    if claim.kind == "LINK" and claim.check_status not in ("APPROVED", "FIXED", "REJECTED"):
        set_field(claim, "shown_type", link_shown_type(claim, checks))
        target_id = _target(claim, ctx)[0]
        if target_id is not None:
            set_field(claim, "target_document_id", str(target_id))


async def run_code_checks(db, claims, index: SentenceIndex, doc: Any, pages, reading: Optional[Dict[str, str]] = None) -> CheckContext:
    """Runs the code checks on every claim. Fast: no network, so it runs inside the analysis job."""
    ctx = CheckContext(
        index=index,
        pages=page_infos(pages),
        issue_date=getattr(doc, "publication_date", None),
        reading=dict(reading or {}),
        link_targets=await load_link_targets(db, claims, getattr(doc, "id", None)),
    )
    if db is not None and ctx.pages and any(p.needs_reading_check for p in ctx.pages.values()):
        from backend.app.modules.claims.autofix import apply_reading_fixes, load_fixes

        ctx.fixes = await load_fixes(db, pages, ctx.reading, index)
        if ctx.fixes:
            for claim in claims:
                await apply_reading_fixes(db, claim, ctx)
    for claim in claims:
        apply_checks(claim, ctx)
    return ctx
