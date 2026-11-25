"""Readable circular addresses (modules/library/public.py)."""
from datetime import date
from types import SimpleNamespace as N

from backend.app.modules.library.public import dept_code, number_part, path_of, title_part


def doc(ref, title, d):
    return N(reference_number=ref, title=title, publication_date=d)


def test_number_and_year_from_reference():
    assert number_part(doc("BRPD Circular Letter No. 49/2024", "x", date(2024, 11, 14))) == "49-2024"


def test_year_from_publication_date_when_reference_has_none():
    assert number_part(doc("BRPD-1 Circular Letter No. 39", "x", date(2026, 11, 19))) == "39-2026"


def test_leading_zeros_dropped():
    assert number_part(doc("PSD Circular No. 01/2025", "x", date(2025, 1, 19))) == "1-2025"


def test_title_words_skip_reference_and_filler():
    d = doc("BRPD Circular Letter No. 49/2024", "BRPD Circular Letter No. 49: Regarding Transfer of Jute Sector Outstanding Loans to Block Account.", date(2024, 11, 14))
    assert title_part(d) == "transfer-of-jute-sector-outstanding-loans-to-block"


def test_department_from_table_or_reference():
    d = doc("BRPD-1 Circular Letter No. 39", "x", date(2026, 11, 19))
    assert dept_code(d, "BRPD") == "brpd"
    assert dept_code(d, None) == "brpd"
    assert path_of(d, "BRPD").startswith("/circular/brpd/39-2026")


# ---- list pages (SEO hubs)
from backend.app.modules.library.public import HUB_MIN_INDEXABLE, _hubs_from, _reference_from_title


def item(dept, ok, topics=(), year=2026):
    return {"dept": dept, "indexable": ok, "topics": list(topics), "publication_date": date(year, 1, 1)}


def test_hub_needs_enough_analysed_circulars():
    items = [item("brpd", True, ["CREDIT"])] * HUB_MIN_INDEXABLE + [item("psd", True)] * (HUB_MIN_INDEXABLE - 1) + [item("psd", False)] * 50
    h = _hubs_from(items)
    assert [d.code for d in h.departments] == ["brpd"]
    assert [t.code for t in h.topics] == ["credit"]
    assert h.departments[0].name == "Banking Regulation and Policy Department"


def test_unknown_department_and_other_topic_get_no_page():
    items = [item("bb", True, ["OTHER"])] * 10
    h = _hubs_from(items)
    assert h.departments == [] and h.topics == []
    assert [y.code for y in h.years] == ["2026"]


def test_reference_read_from_title_when_missing():
    assert _reference_from_title("BRD Circular No. 04: Regarding Placement of Padma Bank PLC") == "BRD Circular No. 04"
    assert _reference_from_title("Some notice without a number") is None
