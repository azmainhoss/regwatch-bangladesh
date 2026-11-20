"""Checker gaps found in the first manual archive analysis (14 Nov 2026)."""
import re

from backend.app.modules.claims import wording as W
from backend.app.modules.claims.checks import _search_form
from backend.app.modules.relationships import linking as L


def _named(quote: str, hint: str) -> bool:
    form = _search_form(quote)
    return any(re.search(r"(?<![\w/])" + re.escape(k) + r"(?![\w/])", form) for k in L.reference_keys(hint))


def test_bangla_circular_names_match_english_hints():
    assert _named("বিআরপিডি সার্কুলার নং-১১/২০২২-এর আলোকে", "BRPD Circular No. 11/2022")
    assert _named("বিআরপিডি-১ সার্কুলার নং-১১/২০২৬ এর মাধ্যমে", "BRPD-1 Circular No. 11/2026")
    assert _named("এফআইডি সার্কুলার লেটার নং-০১/২০২৩ এতদ্বারা রহিত করা হলো।", "FID Circular Letter No. 01/2023")
    assert _named("ডিওএস সার্কুলার নং ৫", "DOS Circular No. 5")
    assert _named("বিআরিপিডি সার্কুলার নং ৭", "BRPD Circular No. 7")  # a common misreading


def test_circular_letter_never_matches_plain_circular():
    assert not _named("এফআইডি সার্কুলার লেটার নং-০২/২০২২", "FID Circular No. 02/2022")


def test_bangla_department_inside_a_word_is_left_alone():
    assert L.normalize_reference("ক্যাফেএফই সার্কুলার নং ১") != "fe circular no 1"


def test_stored_references_normalise_the_same_both_ways():
    assert L.normalize_reference("বিআরপিডি সার্কুলার নং-১১/২০২২") == L.normalize_reference("BRPD Circular No. 11/2022")


def test_new_duty_words():
    assert W.has_any("অনুসরণের জন্য আপনাদেরকে নির্দেশনা প্রদান করা হলো।", W.DUTY_WORDS["MANDATORY"])
    assert W.has_any("পিপিজি লাভকরণ সাপেক্ষে আবেদন করবে।", W.DUTY_WORDS["CONDITIONAL"])
    assert W.has_any("eRefinance System পোর্টালে অনলাইন আবেদন করবে।", W.DUTY_WORDS["REPORTING"])
    assert W.has_any("ঋণগ্রহীতাকে স্পষ্ট তথ্য প্রদান করা হয়েছে", W.DUTY_WORDS["DISCLOSURE"])
    assert W.has_any("shall be eligible for credit to RFCD accounts only provided that it is declared", W.ONLY_WORDS)
