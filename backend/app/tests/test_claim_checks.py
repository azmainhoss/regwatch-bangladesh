"""Claim checks, chunk 1 (docs/specs/CLAIM_CHECKS_SPEC.md): wording helpers, the code checks,
routing, document status, carry-over of a person's decision, and the analysis service end to end."""
import copy
import json
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.alerts.models import AlertEvent
from backend.app.modules.analysis import prompts
from backend.app.modules.analysis import service as analysis_service
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import checks as C
from backend.app.modules.claims import status as S
from backend.app.modules.claims import wording as W
from backend.app.modules.claims.build import ClaimDraft, claim_fingerprint
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.compliance import rules
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.tests.factories import make_document

D = date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_ctx(text: str, issue=D(2026, 1, 1), **kw) -> C.CheckContext:
    index = SentenceIndex.build([{"page_number": 1, "raw_text": text, "cleaned_text": text, "line_boxes": None}])
    ctx = C.CheckContext(index=index, pages={1: C.PageInfo(1)}, issue_date=issue)
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def sids(ctx: C.CheckContext, *fragments: str):
    out = []
    for frag in fragments:
        hits = [s.id for s in ctx.index.sentences.values() if frag.lower() in s.text.lower()]
        assert hits, f"no sentence contains {frag!r}"
        out.append(hits[0])
    return out


def draft(kind, fields, ctx, quote, **extra_evidence) -> ClaimDraft:
    evidence = {"quote": sids(ctx, *([quote] if isinstance(quote, str) else quote))}
    for key, frag in extra_evidence.items():
        evidence[key] = sids(ctx, frag)
    return ClaimDraft(kind=kind, fields=dict(fields), evidence=evidence)


def result_of(d: ClaimDraft, ctx: C.CheckContext, name: str):
    C.apply_checks(d, ctx)
    found = [c for c in d.checks if c["name"] == name]
    return found[0]["result"] if found else None


def by_name(d: ClaimDraft):
    return {c["name"]: c["result"] for c in d.checks}


# ---------------------------------------------------------------------------
# Wording: dates and numbers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("due on 31/12/2024", D(2024, 12, 31)),
    ("due on 31-12-2024", D(2024, 12, 31)),
    ("due on 31.12.2024", D(2024, 12, 31)),
    ("due 31 December 2024", D(2024, 12, 31)),
    ("due on 3rd Sept 2024", D(2024, 9, 3)),
    ("due December 31, 2024", D(2024, 12, 31)),
    ("due 2024-12-31", D(2024, 12, 31)),
    ("১ জানুয়ারি ২০২৫ তারিখের মধ্যে", D(2025, 1, 1)),
    ("৩১/১২/২০২৪", D(2024, 12, 31)),
    ("৩১ ডিসেম্বর ২০২৪", D(2024, 12, 31)),
    ("১৫ সেপ্টেম্বর ২০২৫", D(2025, 9, 15)),
    ("due 5/3/24", D(2024, 3, 5)),
    ("due 5/3/99", D(1999, 3, 5)),
])
def test_dates_in_reads_each_format_day_first(text, expected):
    assert W.dates_in(text) == {expected}


def test_dates_in_ignores_bangla_calendar_dates_and_bad_dates():
    assert W.dates_in("১৫ বৈশাখ ১৪৩১") == set()
    assert W.dates_in("31/02/2024") == set()
    assert W.dates_in("no date here, only 12 banks") == set()


def test_immediate_effect_phrases():
    assert W.has_immediate_effect("This comes into force with immediate effect.")
    assert W.has_immediate_effect("এই নির্দেশ অবিলম্বে কার্যকর হবে।")
    assert W.has_immediate_effect("জারির তারিখ হতে কার্যকর")
    assert not W.has_immediate_effect("This comes into force next year.")


def test_numbers_in_matches_across_scripts_and_formats():
    assert W.numbers_in("a rate of 2.5%") == W.numbers_in("হার ২.৫%")
    assert "2.5%" in W.numbers_in("২.৫%")
    assert "100000" in W.numbers_in("Tk 1,00,000 only")
    assert "12" in W.numbers_in("within twelve months")
    assert "5.5" in W.numbers_in("5.50 banks")
    # dates are not numbers
    assert W.numbers_in("by 31 December 2024") == {}


def test_numbers_check_passes_and_fails():
    ctx = make_ctx("Banks must keep a ratio of 2.5% of deposits. Report within twelve months.")
    ok = draft("SUMMARY_POINT", {"text": "Banks keep 2.5% of deposits within 12 months."}, ctx, ["ratio of 2.5%", "twelve months"])
    assert result_of(ok, ctx, "NUMBERS") == "PASS"
    bad = draft("SUMMARY_POINT", {"text": "Banks keep 3% of deposits."}, ctx, "ratio of 2.5%")
    assert result_of(bad, ctx, "NUMBERS") == "FAIL"
    msg = [c for c in bad.checks if c["name"] == "NUMBERS"][0]["message"]
    assert msg == "The number 3% is not in the quoted sentences."
    bn = make_ctx("ব্যাংককে ২.৫% হারে রাখতে হবে।")
    same = draft("SUMMARY_POINT", {"text": "Rate is 2.5%."}, bn, "২.৫%")
    assert result_of(same, bn, "NUMBERS") == "PASS"


def test_dates_check():
    ctx = make_ctx("Banks shall report by 31 December 2026. This applies with immediate effect.")
    ok = draft("OBLIGATION", {"obligation_type": "MANDATORY", "deadline": "2026-12-31"}, ctx, "report by")
    assert result_of(ok, ctx, "DATES") == "PASS"
    bad = draft("OBLIGATION", {"obligation_type": "MANDATORY", "deadline": "2027-01-31"}, ctx, "report by")
    assert result_of(bad, ctx, "DATES") == "FAIL"
    assert [c for c in bad.checks if c["name"] == "DATES"][0]["message"] == "The date 31 January 2027 is not in the quoted sentences."
    # an effective date equal to the issue date passes on an immediate-effect phrase
    eff = draft("DATE", {"date_kind": "EFFECTIVE", "date": "2026-01-01"}, ctx, "immediate effect")
    assert result_of(eff, ctx, "DATES") == "PASS"
    other = draft("DATE", {"date_kind": "EFFECTIVE", "date": "2026-02-01"}, ctx, "immediate effect")
    assert result_of(other, ctx, "DATES") == "FAIL"
    # a date written in a summary line must be in its quote
    summ = draft("SUMMARY_POINT", {"text": "Report due 30 November 2026."}, ctx, "report by")
    assert result_of(summ, ctx, "DATES") == "FAIL"


# ---------------------------------------------------------------------------
# Duty wording and who
# ---------------------------------------------------------------------------
def test_duty_wording():
    bn_ctx = make_ctx("এই কাজ করা যাবে না।")
    prohibition = draft("OBLIGATION", {"obligation_type": "PROHIBITION"}, bn_ctx, "যাবে না")
    assert result_of(prohibition, bn_ctx, "DUTY_WORDING") == "PASS"

    perm_ctx = make_ctx("শাখা খুলতে পারবে না।")
    permission = draft("OBLIGATION", {"obligation_type": "PERMISSION"}, perm_ctx, "পারবে না")
    assert result_of(permission, perm_ctx, "DUTY_WORDING") == "FAIL"

    en = make_ctx("Banks shall not open branches. Banks may open booths.")
    mandatory = draft("OBLIGATION", {"obligation_type": "MANDATORY"}, en, "shall not")
    assert result_of(mandatory, en, "DUTY_WORDING") == "FAIL"
    assert [c for c in mandatory.checks if c["name"] == "DUTY_WORDING"][0]["message"] == \
        "The point says this must be done, but the quote says it must not."
    allowed = draft("OBLIGATION", {"obligation_type": "PERMISSION"}, en, "may open")
    assert result_of(allowed, en, "DUTY_WORDING") == "PASS"
    not_allowed = draft("OBLIGATION", {"obligation_type": "PERMISSION"}, make_ctx("Banks may not open booths."), "may not")
    assert result_of(not_allowed, make_ctx("Banks may not open booths."), "DUTY_WORDING") == "FAIL"


def test_who():
    ctx = make_ctx("To all scheduled banks. Islamic banks shall report. Brokers shall report.")
    named = draft("OBLIGATION", {"obligation_type": "MANDATORY", "who": "ISLAMIC_BANK"}, ctx, "Islamic banks shall")
    assert result_of(named, ctx, "WHO") == "PASS"

    bn = make_ctx("সকল তফসিলি ব্যাংক\nঋণ প্রদানের নির্দেশনা প্রদান করা হলো।\n")
    covered = draft("APPLIES_TO", {"entity": "ISLAMIC_BANK"}, bn, "নির্দেশনা")
    assert result_of(covered, bn, "WHO") == "PASS"  # addressee says all scheduled banks

    stranger = draft("OBLIGATION", {"obligation_type": "MANDATORY", "who": "NBFI"}, ctx, "Brokers shall")
    assert result_of(stranger, ctx, "WHO") == "FAIL"
    unknown = draft("OBLIGATION", {"obligation_type": "MANDATORY", "who": "Space agencies"}, ctx, "Brokers shall")
    assert result_of(unknown, ctx, "WHO") == "FAIL"
    assert [c for c in unknown.checks if c["name"] == "WHO"][0]["message"] == "Who must do this is not named in the circular."
    # legacy name from the first analysis format
    legacy = draft("OBLIGATION", {"obligation_type": "MANDATORY", "who": "SCHEDULED_COMMERCIAL_BANK"}, ctx, "Islamic banks shall")
    assert result_of(legacy, ctx, "WHO") == "PASS"


def test_exemption_and_overclaim_words():
    ctx = make_ctx("Rural branches are exempt. This circular amends the earlier rule. Banks shall report.")
    ex_ok = draft("EXEMPTION", {"text": "Rural branches are exempt."}, ctx, "exempt")
    assert result_of(ex_ok, ctx, "EXEMPT_WORDS") == "PASS"
    ex_bad = draft("EXEMPTION", {"text": "Rural branches are exempt."}, ctx, "Banks shall report")
    assert result_of(ex_bad, ctx, "EXEMPT_WORDS") == "FAIL"
    over = draft("SUMMARY_POINT", {"text": "The circular repeals the old rule."}, ctx, "Banks shall report")
    assert result_of(over, ctx, "OVERCLAIM") == "FAIL"
    fine = draft("SUMMARY_POINT", {"text": "The circular amends the old rule."}, ctx, "amends")
    assert result_of(fine, ctx, "OVERCLAIM") == "PASS"


def test_evidence_and_page_checks():
    ctx = make_ctx("Banks shall report.")
    none = ClaimDraft(kind="SUMMARY_POINT", fields={"text": "x"}, evidence={"quote": []})
    assert result_of(none, ctx, "HAS_EVIDENCE") == "FAIL"
    assert by_name(none) == {"HAS_EVIDENCE": "FAIL", "MEANING": "NOT_RUN"}
    unknown = ClaimDraft(kind="SUMMARY_POINT", fields={"text": "x"}, evidence={"quote": ["p9.s9"]})
    assert result_of(unknown, ctx, "HAS_EVIDENCE") == "FAIL"
    ctx.pages[1] = C.PageInfo(1, quality_status="NEEDS_HUMAN_REVIEW")
    unread = draft("SUMMARY_POINT", {"text": "x"}, ctx, "Banks shall")
    assert result_of(unread, ctx, "PAGE_READ") == "FAIL"
    assert by_name(unread)["MEANING"] == "NOT_RUN"


def test_quote_reading_waits_until_checked():
    ctx = make_ctx("Banks shall report.")
    ctx.pages[1] = C.PageInfo(1, extraction_method="GEMINI_VISION", quality_status="SUCCESS_VISION")
    d = draft("SUMMARY_POINT", {"text": "Banks report."}, ctx, "Banks shall")
    sid = d.evidence["quote"][0]
    ctx.reading = {sid: "WAITING"}
    assert result_of(d, ctx, "QUOTE_READING") == "WAIT"
    ctx.reading = {sid: "CLEAN"}
    assert result_of(d, ctx, "QUOTE_READING") == "PASS"
    ctx.reading = {sid: "MISREAD"}
    assert result_of(d, ctx, "QUOTE_READING") == "FAIL"
    # a text-layer page needs no second reading
    ctx.pages[1] = C.PageInfo(1)
    assert result_of(d, ctx, "QUOTE_READING") is None


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------
LINK_TEXT = "This circular amends BRPD Circular No. 14 dated 23 September 2012. Banks shall report."
TARGET_ID = uuid.uuid4()


def link_ctx(text=LINK_TEXT, targets=None, issue=D(2026, 1, 1)):
    ctx = make_ctx(text, issue=issue)
    ctx.link_targets = targets if targets is not None else {"BRPD Circular No. 14": (TARGET_ID, D(2012, 9, 23))}
    return ctx


def link(ctx, claimed="AMENDS", hint="BRPD Circular No. 14", quote="amends BRPD"):
    return draft("LINK", {"claimed_type": claimed, "shown_type": "REFERENCES", "target_hint": hint, "target_document_id": None},
                 ctx, quote)


def test_link_passing_every_change_check_waits_for_a_person_and_shows_as_mention():
    ctx = link_ctx()
    d = link(ctx)
    C.apply_checks(d, ctx)
    assert {n: r for n, r in by_name(d).items() if n != "MEANING"} == {
        "HAS_EVIDENCE": "PASS", "QUOTE_FOUND": "PASS", "PAGE_READ": "PASS", "TARGET_NAMED": "PASS",
        "CHANGE_WORDS": "PASS", "TARGET_FOUND": "PASS", "TARGET_OLDER": "PASS",
    }
    assert d.fields["shown_type"] == "REFERENCES"
    assert d.fields["target_document_id"] == str(TARGET_ID)
    S.route(d, type("Doc", (), {"publication_date": D(2026, 1, 1)})(), today=D(2026, 11, 13))
    assert (d.check_status, d.review_queue) == ("WAITING_FOR_PERSON", "REQUIRED")
    assert S.is_shown(d) and S.shown_link_type(d) == "REFERENCES"


def test_link_without_change_words_is_downgraded_and_shown_as_mention():
    ctx = link_ctx("This circular mentions BRPD Circular No. 14 dated 23 September 2012.")
    d = link(ctx, quote="mentions BRPD")
    C.apply_checks(d, ctx)
    assert by_name(d)["CHANGE_WORDS"] == "FAIL"
    S.route(d, type("Doc", (), {"publication_date": D(2026, 1, 1)})(), today=D(2026, 11, 13))
    assert d.check_status == "PASSED" and d.fields["shown_type"] == "REFERENCES"


def test_link_target_not_named_is_not_shown():
    ctx = link_ctx("This circular amends the earlier rule. Banks shall report.")
    d = link(ctx, quote="amends the earlier")
    C.apply_checks(d, ctx)
    assert by_name(d)["TARGET_NAMED"] == "FAIL"
    # old circular and a failing check on a high-stakes claim: nobody has to decide it
    S.route(d, type("Doc", (), {"publication_date": D(2020, 1, 1)})(), today=D(2026, 11, 13))
    assert (d.check_status, d.review_queue) == ("NOT_SHOWN", "OPTIONAL")
    assert not S.is_shown(d)


def test_link_with_two_library_matches_is_downgraded():
    ctx = link_ctx(targets={"BRPD Circular No. 14": (None, None)})
    d = link(ctx)
    C.apply_checks(d, ctx)
    assert by_name(d)["TARGET_FOUND"] == "FAIL"
    S.route(d, type("Doc", (), {"publication_date": D(2026, 1, 1)})(), today=D(2026, 11, 13))
    assert d.check_status == "PASSED" and d.fields["shown_type"] == "REFERENCES"


def test_link_to_newer_target_is_downgraded():
    ctx = link_ctx(targets={"BRPD Circular No. 14": (TARGET_ID, D(2027, 1, 1))})
    d = link(ctx)
    C.apply_checks(d, ctx)
    assert by_name(d)["TARGET_OLDER"] == "FAIL"
    S.route(d, type("Doc", (), {"publication_date": D(2026, 1, 1)})(), today=D(2026, 11, 13))
    assert d.check_status == "PASSED" and d.fields["shown_type"] == "REFERENCES"


def test_clarifies_and_related_links():
    ctx = link_ctx("This circular clarifies BRPD Circular No. 14. Banks shall report.")
    d = link(ctx, claimed="CLARIFIES", quote="clarifies BRPD")
    C.apply_checks(d, ctx)
    assert d.fields["shown_type"] == "CLARIFIES"
    ctx2 = link_ctx("See also BRPD Circular No. 14. Banks shall report.")
    weak = link(ctx2, claimed="CLARIFIES", quote="See also")
    C.apply_checks(weak, ctx2)
    assert weak.fields["shown_type"] == "REFERENCES"
    rel = link(ctx2, claimed="RELATED_TO", quote="See also")
    C.apply_checks(rel, ctx2)
    assert rel.fields["shown_type"] == "REFERENCES"


# ---------------------------------------------------------------------------
# Routing table 4.2, row by row (date frozen)
# ---------------------------------------------------------------------------
TODAY = D(2026, 11, 13)
NEW_DOC = type("Doc", (), {"publication_date": D(2026, 5, 1)})()
OLD_DOC = type("Doc", (), {"publication_date": D(2020, 5, 1)})()


def routed(kind, fields, results, doc, monkeypatch, extra_checks=()):
    monkeypatch.setattr(rules, "today_dhaka", lambda: TODAY)
    d = ClaimDraft(kind=kind, fields=fields, evidence={"quote": ["p1.s1"]})
    d.checks = [{"name": f"C{i}", "result": r, "message": ""} for i, r in enumerate(results)] + list(extra_checks)
    S.route(d, doc, force_review=False)
    return d


def test_routing_table(monkeypatch):
    obl = {"obligation_type": "MANDATORY"}
    soft = {"obligation_type": "RECOMMENDATION"}
    d = routed("OBLIGATION", obl, ["PASS", "WAIT"], NEW_DOC, monkeypatch)
    assert (d.check_status, d.review_queue) == ("CHECKING", None)
    d = routed("OBLIGATION", obl, ["PASS", "PASS"], NEW_DOC, monkeypatch)
    assert (d.check_status, d.review_queue) == ("PASSED", None)
    d = routed("OBLIGATION", obl, ["PASS", "FAIL"], NEW_DOC, monkeypatch)  # high-stakes, new
    assert (d.check_status, d.review_queue) == ("WAITING_FOR_PERSON", "REQUIRED")
    d = routed("OBLIGATION", {**obl, "deadline": "2027-03-01"}, ["FAIL"], OLD_DOC, monkeypatch)  # own date in the future
    assert (d.check_status, d.review_queue) == ("WAITING_FOR_PERSON", "REQUIRED")
    d = routed("OBLIGATION", obl, ["FAIL"], OLD_DOC, monkeypatch)  # high-stakes, old, no future date
    assert (d.check_status, d.review_queue) == ("NOT_SHOWN", "OPTIONAL")
    d = routed("OBLIGATION", soft, ["FAIL"], NEW_DOC, monkeypatch)  # not high-stakes
    assert (d.check_status, d.review_queue) == ("NOT_SHOWN", "OPTIONAL")
    assert d.is_high_stakes is False
    # FAIL beats WAIT
    d = routed("OBLIGATION", soft, ["WAIT", "FAIL"], NEW_DOC, monkeypatch)
    assert d.check_status == "NOT_SHOWN"
    # change-the-law link that passed everything
    extras = [{"name": n, "result": "PASS", "message": ""} for n in ("CHANGE_WORDS", "TARGET_FOUND", "TARGET_OLDER")]
    link_fields = {"claimed_type": "AMENDS", "shown_type": "REFERENCES"}
    d = routed("LINK", link_fields, ["PASS"], NEW_DOC, monkeypatch, extras)
    assert (d.check_status, d.review_queue) == ("WAITING_FOR_PERSON", "REQUIRED")
    d = routed("LINK", link_fields, ["PASS"], OLD_DOC, monkeypatch, extras)
    assert (d.check_status, d.review_queue) == ("WAITING_FOR_PERSON", "OPTIONAL")
    assert S.is_shown(d)  # shown as a mention while it waits
    # asking for review hides a shown point at once
    shown = routed("SUMMARY_POINT", {"text": "t"}, ["PASS"], NEW_DOC, monkeypatch)
    assert S.is_shown(shown)
    S.ask_for_review(shown)
    assert (shown.check_status, shown.review_queue) == ("WAITING_FOR_PERSON", "REQUIRED") and not S.is_shown(shown)


def test_high_stakes_rules():
    t = TODAY
    assert S.compute_high_stakes(ClaimDraft("OBLIGATION", {"obligation_type": "MANDATORY"}, {}), t)
    assert S.compute_high_stakes(ClaimDraft("OBLIGATION", {"obligation_type": "PERMISSION", "penalty": "fine"}, {}), t)
    assert S.compute_high_stakes(ClaimDraft("OBLIGATION", {"obligation_type": "PERMISSION", "deadline": "2027-01-01"}, {}), t)
    assert not S.compute_high_stakes(ClaimDraft("OBLIGATION", {"obligation_type": "PERMISSION", "deadline": "2025-01-01"}, {}), t)
    assert S.compute_high_stakes(ClaimDraft("DATE", {"date_kind": "COMPLIANCE", "date": "2027-01-01"}, {}), t)
    assert not S.compute_high_stakes(ClaimDraft("DATE", {"date_kind": "EFFECTIVE", "date": "2027-01-01"}, {}), t)
    assert S.compute_high_stakes(ClaimDraft("LINK", {"claimed_type": "REPEALS"}, {}), t)
    assert not S.compute_high_stakes(ClaimDraft("LINK", {"claimed_type": "REFERENCES"}, {}), t)
    assert not S.compute_high_stakes(ClaimDraft("SUMMARY_POINT", {"text": "x"}, {}), t)


# ---------------------------------------------------------------------------
# Document status 4.4
# ---------------------------------------------------------------------------
def _c(status, queue=None):
    return ClaimDraft(kind="SUMMARY_POINT", fields={}, evidence={}, check_status=status, review_queue=queue)


def test_document_status_rules():
    ds = S.document_status
    assert ds("EXTRACTED", [_c("PASSED"), _c("NOT_SHOWN", "OPTIONAL"), _c("CHECKING")]) == "PUBLISHED_MACHINE_VERIFIED"
    assert ds("EXTRACTED", []) == "PUBLISHED_MACHINE_VERIFIED"
    assert ds("EXTRACTED", [_c("PASSED"), _c("WAITING_FOR_PERSON", "REQUIRED")]) == "AWAITING_REVIEW"
    assert ds("EXTRACTED", [_c("PASSED"), _c("WAITING_FOR_PERSON", "OPTIONAL")]) == "PUBLISHED_MACHINE_VERIFIED"
    assert ds("EXTRACTED", [_c("PASSED"), _c("APPROVED")]) == "PUBLISHED_HUMAN_REVIEWED"
    assert ds("EXTRACTED", [_c("REJECTED")]) == "PUBLISHED_HUMAN_REVIEWED"
    for protected in ("WITHDRAWN", "SUPERSEDED", "EXTRACTION_FAILED"):
        assert ds(protected, [_c("WAITING_FOR_PERSON", "REQUIRED")]) is None


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------
def test_input_fingerprint_changes_with_prompt_version(monkeypatch):
    pages = [{"page_number": 1, "cleaned_text": "Banks shall report."}]
    before = analysis_service.input_fingerprint("m", pages)
    assert before == analysis_service.input_fingerprint("m", pages)
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "v-next")
    assert analysis_service.input_fingerprint("m", pages) != before


def test_claim_fingerprint_ignores_computed_link_fields():
    a = claim_fingerprint("LINK", {"quote": ["p1.s1"]}, {"claimed_type": "AMENDS", "shown_type": "REFERENCES", "target_hint": "X 1"})
    b = claim_fingerprint("LINK", {"quote": ["p1.s1"]}, {"claimed_type": "AMENDS", "shown_type": "AMENDS", "target_hint": "X 1", "target_document_id": "abc"})
    assert a == b
    c = claim_fingerprint("OBLIGATION", {"quote": ["p1.s1"]}, {"deadline": "2026-12-31"})
    d = claim_fingerprint("OBLIGATION", {"quote": ["p1.s1"]}, {"deadline": "2027-12-31"})
    assert c != d


# ---------------------------------------------------------------------------
# End to end through the analysis service
# ---------------------------------------------------------------------------
PAGE_TEXT = (
    "All scheduled banks. "
    "Banks shall submit the monthly liquidity report by 31 December 2026. "
    "Banks shall not open new branches without approval. "
    "This amends BRPD Circular No. 14 dated 23 September 2012. "
    "This comes into force with immediate effect, except for state-owned banks."
)


class FixedProvider(BaseAIProvider):
    def __init__(self, payload):
        super().__init__("fixed-test-model")
        self.payload = payload

    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        data = copy.deepcopy(self.payload)
        return LLMResponse(raw_content=json.dumps(data), parsed_json=data, model_name=self.model_name)


def payload_for(ctx: C.CheckContext, deadline_c="2027-01-31"):
    s = lambda *f: sids(ctx, *f)  # noqa: E731
    return {
        "classification": {"document_type": "CIRCULAR", "subject": "Liquidity", "language": "en"},
        "executive_summary": {
            "summary_points": [
                {"text": "Banks must submit a monthly liquidity report by 31 December 2026.", "evidence_ids": s("monthly liquidity")},
                {"text": "Banks must keep 5% extra liquidity.", "evidence_ids": s("monthly liquidity")},
            ],
            "key_changes": [{"text": "BRPD Circular No. 14 is amended.", "evidence_ids": s("This amends")}],
        },
        "provisions": [{"provision_number": "1.", "heading": "Reports", "quote_span_ids": s("monthly liquidity"),
                        "provision_type": "REPORTING", "normalized_explanation": "Monthly report."}],
        "obligations": [
            {"title": "Submit monthly liquidity report", "obligation_type": "MANDATORY",
             "requirement_description": "Banks shall submit the monthly liquidity report.",
             "quote_span_ids": s("monthly liquidity"), "responsible_entity": "SCHEDULED_BANK", "who_ids": s("All scheduled"),
             "explicit_deadline": "2026-12-31", "deadline_ids": s("monthly liquidity"), "reporting_frequency": "MONTHLY"},
            {"title": "Do not open new branches", "obligation_type": "PROHIBITION",
             "requirement_description": "Banks shall not open new branches without approval.",
             "quote_span_ids": s("not open new")},
            {"title": "File annual report", "obligation_type": "MANDATORY",
             "requirement_description": "Banks shall submit the monthly liquidity report.",
             "quote_span_ids": s("monthly liquidity"), "explicit_deadline": deadline_c, "deadline_ids": s("monthly liquidity")},
        ],
        "applicability": {
            "covered": [{"entity": "SCHEDULED_BANK", "evidence_ids": s("All scheduled")}],
            "exemptions": [{"text": "State-owned banks are exempt.", "evidence_ids": s("immediate effect")}],
        },
        "deadlines": {
            "effective_date": {"date": "2026-01-01", "evidence_ids": s("immediate effect")},
            "compliance_deadline": {"date": "2026-12-31", "evidence_ids": s("monthly liquidity")},
            "reporting_deadline": None,
        },
        "relationships": [{"relationship_type": "AMENDS", "target_reference_hint": "BRPD Circular No. 14 dated 23 September 2012",
                           "quote_span_ids": s("This amends")}],
    }


async def doc_with_text(status, text=PAGE_TEXT):
    doc, version, pages = await make_document(pages=1, status=status)
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, pages[0].id)
        page.raw_text = text
        page.cleaned_text = text
        await db.commit()
    return doc, version, pages


async def run_analysis(doc_id, payload, monkeypatch, force_human_review=False):
    monkeypatch.setattr(rules, "today_dhaka", lambda: TODAY)
    monkeypatch.setattr(analysis_service, "get_ai_provider", lambda name=None: FixedProvider(payload))
    async with AsyncSessionLocal() as db:
        return await analysis_service.AnalysisService.analyze_document_version(
            db=db, document_id=doc_id, provider_name="mock", force_human_review=force_human_review)


async def load_claims(analysis_id):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis_id)
                                 .order_by(AnalysisClaim.order_index))).scalars().all()
        return rows


@pytest.mark.asyncio
async def test_end_to_end_claims_per_kind_and_status(monkeypatch):
    doc, version, pages = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    ctx = make_ctx(PAGE_TEXT)
    analysis = await run_analysis(doc.id, payload_for(ctx), monkeypatch)
    claims = await load_claims(analysis.id)

    table = {}
    for c in claims:
        table.setdefault(c.kind, []).append(c.check_status)
    assert table == {
        "SUMMARY_POINT": ["PASSED", "NOT_SHOWN"],
        "KEY_CHANGE": ["PASSED"],
        "OBLIGATION": ["PASSED", "PASSED", "WAITING_FOR_PERSON"],
        "APPLIES_TO": ["PASSED"],
        "EXEMPTION": ["PASSED"],
        "DATE": ["PASSED", "PASSED"],
        "LINK": ["PASSED"],
        "PROVISION": ["PASSED"],
    }
    bad_number = [c for c in claims if c.kind == "SUMMARY_POINT"][1]
    assert any(c["name"] == "NUMBERS" and c["result"] == "FAIL" for c in bad_number.checks)
    bad_date = [c for c in claims if c.kind == "OBLIGATION"][2]
    assert (bad_date.review_queue, bad_date.is_high_stakes) == ("REQUIRED", True)
    link_claim = [c for c in claims if c.kind == "LINK"][0]
    assert link_claim.fields["claimed_type"] == "AMENDS" and link_claim.fields["shown_type"] == "REFERENCES"
    assert all(c.fingerprint for c in claims)

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc.id)
        assert refreshed.publication_status == "AWAITING_REVIEW"  # one required point is waiting
        obls = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id)
                                 .order_by(Obligation.title))).scalars().all()
        assert {o.title: o.verification_status for o in obls} == {
            "Do not open new branches": "VERIFIED", "File annual report": "PENDING_REVIEW",
            "Submit monthly liquidity report": "VERIFIED",
        }
        rels = (await db.execute(select(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id))).scalars().all()
        # an AMENDS claim is never VERIFIED without a person, even when it is only shown as a mention
        assert [(r.relationship_type, r.verification_status) for r in rels] == [("AMENDS", "PENDING_REVIEW")]
        a = await db.get(DocumentAnalysis, analysis.id)
        assert a.executive_summary == "Banks must submit a monthly liquidity report by 31 December 2026."
        # text-layer page: no second reading is needed, so the claims were not left checking
        checks = (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.page_id == pages[0].id))).scalars().all()
        assert checks and {c.status for c in checks} == {"NOT_NEEDED"}


@pytest.mark.asyncio
async def test_bad_quote_is_never_shown_at_claim_level(monkeypatch):
    doc, version, pages = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    ctx = make_ctx(PAGE_TEXT)
    payload = payload_for(ctx)
    payload["executive_summary"]["summary_points"].append({"text": "Banks must hold gold.", "evidence_ids": ["p1.s99"]})
    payload["obligations"][1]["quote_span_ids"] = ["p7.s1"]
    analysis = await run_analysis(doc.id, payload, monkeypatch)
    claims = await load_claims(analysis.id)
    gold = [c for c in claims if c.kind == "SUMMARY_POINT"][2]
    assert gold.check_status == "NOT_SHOWN" and not S.is_shown(gold)
    assert [c for c in gold.checks if c["name"] == "HAS_EVIDENCE"][0]["result"] == "FAIL"
    prohibited = [c for c in claims if c.kind == "OBLIGATION"][1]
    assert prohibited.check_status == "WAITING_FOR_PERSON" and not S.is_shown(prohibited)
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id,
                                                         Obligation.title == "Do not open new branches"))).scalars().one()
        assert obl.verification_status == "PENDING_REVIEW"
        a = await db.get(DocumentAnalysis, analysis.id)
        assert "gold" not in a.executive_summary


@pytest.mark.asyncio
async def test_asking_for_review_on_analysis_hides_every_point(monkeypatch):
    doc, _v, _p = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    analysis = await run_analysis(doc.id, payload_for(make_ctx(PAGE_TEXT)), monkeypatch, force_human_review=True)
    claims = await load_claims(analysis.id)
    assert claims and not any(S.is_shown(c) for c in claims)
    assert all(c.check_status in ("WAITING_FOR_PERSON", "NOT_SHOWN") for c in claims)


@pytest.mark.asyncio
async def test_archive_analysis_records_no_new_circular_alert_but_live_does(monkeypatch):
    clean = {
        "classification": {"document_type": "CIRCULAR", "subject": "x", "language": "en"},
        "executive_summary": {"summary_points": [], "key_changes": []},
        "provisions": [], "obligations": [], "relationships": [],
        "applicability": {"covered": [], "exemptions": []}, "deadlines": {},
    }
    archive, _v, _p = await doc_with_text("EXTRACTED")
    live, _v2, _p2 = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    await run_analysis(archive.id, clean, monkeypatch)
    await run_analysis(live.id, clean, monkeypatch)
    async with AsyncSessionLocal() as db:
        assert (await db.get(Document, archive.id)).publication_status == "PUBLISHED_MACHINE_VERIFIED"
        keys = (await db.execute(select(AlertEvent.dedupe_key).where(
            AlertEvent.dedupe_key.in_([f"CIRCULAR_PUBLISHED:{archive.id}", f"CIRCULAR_PUBLISHED:{live.id}"])))).scalars().all()
    assert keys == [f"CIRCULAR_PUBLISHED:{live.id}"]


@pytest.mark.asyncio
async def test_decisions_carry_over_claim_by_claim(monkeypatch):
    doc, version, _pages = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    ctx = make_ctx(PAGE_TEXT)
    first = await run_analysis(doc.id, payload_for(ctx), monkeypatch)
    claims = await load_claims(first.id)
    waiting = [c for c in claims if c.check_status == "WAITING_FOR_PERSON"][0]
    shown_summary = [c for c in claims if c.kind == "SUMMARY_POINT" and c.check_status == "PASSED"][0]
    async with AsyncSessionLocal() as db:
        row = await db.get(AnalysisClaim, waiting.id)
        row.check_status, row.review_queue = "APPROVED", None
        row.review_note = "checked on the page"
        other = await db.get(AnalysisClaim, [c for c in claims if c.check_status == "NOT_SHOWN"][0].id)
        other.check_status, other.review_queue = "REJECTED", None
        await db.commit()

    # same answer again: the person's decisions stay
    second = await run_analysis(doc.id, payload_for(ctx), monkeypatch)
    again = await load_claims(second.id)
    approved = [c for c in again if c.fingerprint == waiting.fingerprint][0]
    assert approved.check_status == "APPROVED" and approved.review_note == "checked on the page"
    assert str(approved.carried_from_claim_id) == str(waiting.id)
    rejected = [c for c in again if c.check_status == "REJECTED"]
    assert len(rejected) == 1 and rejected[0].kind == "SUMMARY_POINT"
    untouched = [c for c in again if c.fingerprint == shown_summary.fingerprint][0]
    assert untouched.check_status == "PASSED" and untouched.carried_from_claim_id is None
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id,
                                                         Obligation.title == "File annual report"))).scalars().one()
        assert obl.verification_status == "VERIFIED"  # follows the approved claim
        assert (await db.get(Document, doc.id)).publication_status == "PUBLISHED_HUMAN_REVIEWED"

    # the deadline changes: that point is routed fresh and waits again
    third = await run_analysis(doc.id, payload_for(ctx, deadline_c="2027-02-28"), monkeypatch)
    latest = await load_claims(third.id)
    changed = [c for c in latest if c.kind == "OBLIGATION" and (c.fields or {}).get("title") == "File annual report"][0]
    assert changed.check_status == "WAITING_FOR_PERSON" and changed.carried_from_claim_id is None
    async with AsyncSessionLocal() as db:
        assert (await db.get(Document, doc.id)).publication_status == "AWAITING_REVIEW"


@pytest.mark.asyncio
async def test_image_read_page_claims_stay_checking_until_the_second_reading(monkeypatch):
    doc, version, pages = await doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, pages[0].id)
        page.extraction_method = "GEMINI_VISION"
        page.quality_status = "SUCCESS_VISION"
        await db.commit()
    analysis = await run_analysis(doc.id, payload_for(make_ctx(PAGE_TEXT)), monkeypatch)
    claims = await load_claims(analysis.id)
    assert claims and not any(S.is_shown(c) for c in claims)
    assert {c.check_status for c in claims} <= {"CHECKING", "NOT_SHOWN", "WAITING_FOR_PERSON"}
    assert any(c.check_status == "CHECKING" for c in claims)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.page_id == pages[0].id))).scalars().all()
        assert rows and {r.status for r in rows} == {"WAITING"}
        assert (await db.get(Document, doc.id)).publication_status in ("PUBLISHED_MACHINE_VERIFIED", "AWAITING_REVIEW")
