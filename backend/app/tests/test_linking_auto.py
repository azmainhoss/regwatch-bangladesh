"""History & links without a person (2026-11-24): better matching of cited circulars, and machine-confirmed
change-the-law links."""
import uuid
from datetime import date
from types import SimpleNamespace

from backend.app.modules.claims import checks as C
from backend.app.modules.relationships import linking as L

A1_C03 = uuid.uuid4()   # ACD-1 Circular No. 03/2026, 16 Aug 2026
A1_L03 = uuid.uuid4()   # ACD-1 Circular Letter No. 03/2026, 30 Aug 2026
B1_C05 = uuid.uuid4()   # BRPD-1 Circular No. 05/2026, 10 Feb 2026
B2_C05 = uuid.uuid4()   # BRPD-2 Circular No. 05/2026, 12 Mar 2026
SRC = uuid.uuid4()


def index():
    docs = {
        A1_C03: ("ACD-1 Circular No. 03/2026", date(2026, 8, 16)),
        A1_L03: ("ACD-1 Circular Letter No. 03/2026", date(2026, 8, 30)),
        B1_C05: ("BRPD-1 Circular No. 05/2026", date(2026, 2, 10)),
        B2_C05: ("BRPD-2 Circular No. 05/2026", date(2026, 3, 12)),
    }
    idx = L.ReferenceIndex({}, {}, {})
    for d, (ref, published) in docs.items():
        key = L.normalize_reference(ref)
        idx.exact.setdefault(key, set()).add(d)
        idx.base.setdefault(L.base_key(key), set()).add(d)
        idx.dates[d] = published
    return idx


def test_department_section_number_left_out_is_matched_with_its_date():
    # the live case: "ACD Circular No. 03 dated 16 August 2026" is filed as "ACD-1 Circular No. 03/2026"
    assert L.match_target("ACD Circular No. 03 dated 16 August 2026", index(), SRC) == A1_C03
    # circular and circular letter stay different
    assert L.match_target("ACD Circular Letter No. 03 dated 30 August 2026", index(), SRC) == A1_L03


def test_fuzzy_match_needs_the_date_to_agree():
    # without the section number, a wrong or missing date never links
    assert L.match_target("ACD Circular No. 03 dated 20 August 2026", index(), SRC) is None
    assert L.match_target("ACD Circular No. 03/2026", index(), SRC) == A1_C03  # the only candidate, no date given


def test_two_candidates_are_told_apart_only_by_the_date():
    assert L.match_target("BRPD Circular No. 05/2026", index(), SRC) is None  # BRPD-1 or BRPD-2: never a guess
    assert L.match_target("BRPD Circular No. 05 dated 12 March 2026", index(), SRC) == B2_C05


def test_exact_number_still_wins():
    assert L.match_target("BRPD-1 Circular No. 05/2026", index(), SRC) == B1_C05
    assert L.match_target("BRPD-1 Circular No. 05/2026", index(), B1_C05) is None  # never itself


def _link(claimed="AMENDS", hint="ACD Circular No. 03 dated 16 August 2026"):
    return SimpleNamespace(kind="LINK", fields={"claimed_type": claimed, "target_hint": hint})


def _ctx(target_date):
    return SimpleNamespace(link_targets={"ACD Circular No. 03 dated 16 August 2026": (A1_C03, target_date),
                                         "ACD Circular No. 03/2026": (A1_C03, target_date)})


PASSING = [{"name": n, "result": C.PASS} for n in C.AUTO_CONFIRM_CHECKS]


def test_change_link_is_confirmed_by_the_machine_when_every_check_passes():
    assert C.link_shown_type(_link(), PASSING, _ctx(date(2026, 8, 16))) == "AMENDS"
    assert C.link_shown_type(_link("REPEALS"), PASSING, _ctx(date(2026, 8, 16))) == "REPEALS"


def test_change_link_stays_a_mention_when_anything_is_unsure():
    # the date the quote gives is not the target's date
    assert C.link_shown_type(_link(), PASSING, _ctx(date(2026, 8, 30))) == "REFERENCES"
    # any one machine check not passed
    for name in C.AUTO_CONFIRM_CHECKS:
        checks = [{"name": c["name"], "result": C.FAIL if c["name"] == name else C.PASS} for c in PASSING]
        assert C.link_shown_type(_link(), checks, _ctx(date(2026, 8, 16))) == "REFERENCES", name
    # without context (old callers) nothing is confirmed
    assert C.link_shown_type(_link(), PASSING, None) == "REFERENCES"


def test_fe_and_fepd_are_one_department_when_the_date_agrees():
    idx = index()
    fe31 = uuid.uuid4()
    key = L.normalize_reference("FEPD Circular No. 31/2025")
    idx.exact.setdefault(key, set()).add(fe31)
    idx.base.setdefault(L.base_key(key), set()).add(fe31)
    idx.dates[fe31] = date(2025, 7, 31)
    assert L.match_target("FE Circular No. 31 dated July 31, 2025", idx, SRC) == fe31
    assert L.match_target("FE Circular No. 31 dated August 31, 2025", idx, SRC) is None


def test_change_words_cover_replaced_extended_and_bangla_past_forms():
    from backend.app.modules.claims import wording as W
    assert W.has_any("এ সার্কুলারের নির্দেশনার মাধ্যমে প্রতিস্থাপিত মর্মে বিবেচিত হবে।", W.CHANGE_WORDS["REPLACES"], mode="stem")
    assert W.has_any("Accordingly, the said provision shall be replaced by the following:", W.CHANGE_WORDS["AMENDS"], mode="stem")
    assert W.has_any("নির্ধারিত সময়সীমা আগামী ৩১/১২/২০২৬ পর্যন্ত বর্ধিত করা হলো।", W.CHANGE_WORDS["AMENDS"], mode="stem")
