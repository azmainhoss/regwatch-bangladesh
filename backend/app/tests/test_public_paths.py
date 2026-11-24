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
