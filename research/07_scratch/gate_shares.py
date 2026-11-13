"""Estimates what share of circulars each review rule would catch.

Read-only. Uses:
- the full listing titles (4,818 rows) for a title-based count;
- the 130-row research sample (random 100 + recent 30) page texts for a body-text count.
Text per page: PyMuPDF for English pages, the Gemini Flash-Lite reading where one exists, else the
Bijoy converter / Tesseract text (noisy, so Bangla counts are a rough lower bound).
"""
import json
import os
import re
from collections import Counter

R = "E:/regwatch-research"
listing = json.load(open(f"{R}/listing.json", encoding="utf-8"))
picks = {p["row_index"]: p["pick_group"] for p in json.load(open(f"{R}/picks.json", encoding="utf-8"))["picks"]}
docs = json.load(open(f"{R}/gold/doc_index.json", encoding="utf-8"))

EN_CHANGE = re.compile(
    r"\b(amend\w*|repeal\w*|supersed\w*|rescind\w*|in place of|substitut\w*|replac\w*|stands? (?:withdrawn|cancelled|revoked)|"
    r"(?:is|are|been|hereby) (?:withdrawn|cancelled|revoked)|shall be read as|modif\w*|revis\w*|partial(?:ly)? change|inserted|deleted|omitted)\b",
    re.I,
)
EN_STRONG = re.compile(r"\b(amend\w*|repeal\w*|supersed\w*|rescind\w*|in place of|substitut\w*|stands? (?:withdrawn|cancelled|revoked)|(?:hereby|is|are|been) (?:withdrawn|cancelled|revoked)|shall be read as|inserted|deleted|omitted)\b", re.I)
BN_CHANGE = re.compile(r"(সংশোধ|রহিত|বাতিল|প্রতিস্থাপ|পরিবর্তে|স্থলে|প্রত্যাহার|পরিমার্জ|সংযোজ|বিলুপ্ত|নিম্নরূপে প্রতিস্থাপিত|পঠিত হবে)")
EN_REF = re.compile(r"\b(?:circular|circular letter|master circular|letter|guideline|notification)\s*(?:letter\s*)?no\.?\s*[\w\-/\.]*\d", re.I)
BN_REF = re.compile(r"(সার্কুলার|প্রজ্ঞাপন|পত্র)\s*(?:লেটার\s*)?নং")
DATE = re.compile(r"\b\d{1,2}[\./-]\d{1,2}[\./-](?:19|20)\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+(?:19|20)\d{2}\b|[০-৯]{1,2}[/\.-][০-৯]{1,2}[/\.-][০-৯]{2,4}", re.I)
DEADLINE = re.compile(r"\b(within|by|not later than|on or before|deadline|no later than|latest by)\b|(মধ্যে|এর পূর্বে|তারিখের মধ্যে|সময়সীমা)", re.I)
PENALTY = re.compile(r"\b(penal\w*|fine|punitive|section 109|section 111|action will be taken|legal action)\b|(জরিমানা|দণ্ড|শাস্তি|ব্যবস্থা গ্রহণ)", re.I)
TITLE_CHANGE = re.compile(r"\b(amend\w*|repeal\w*|supersed\w*|revis\w*|modif\w*|substitut\w*|replac\w*|change[sd]? in|withdraw\w*|cancel\w*|relax\w*|extension|extend\w*|re-?fix\w*|re-?schedul\w*|update[sd]?)\b", re.I)


def page_text(pid, cls):
    for sub in ("gemini-3.5-flash-lite", "pymupdf_raw" if cls == "english_clean" else None,
                "bijoy_unicodeconverter", "tesseract_best", "pymupdf_raw"):
        if not sub:
            continue
        p = f"{R}/reading/{sub}/{pid}.txt"
        if os.path.exists(p):
            t = open(p, encoding="utf-8", errors="replace").read()
            if t.strip():
                return t, sub
    return "", None


# 1) Titles across the whole listing.
tc = sum(1 for r in listing if TITLE_CHANGE.search(r.get("title") or ""))
print(f"Listing rows: {len(listing)}; titles with change words: {tc} ({tc/len(listing):.1%})")
for yr in ("2000", "2010", "2020"):
    rows = [r for r in listing if (r.get("date") or "")[:3] == yr[:3]]
    n = sum(1 for r in rows if TITLE_CHANGE.search(r.get("title") or ""))
    print(f"  {yr}s: {n}/{len(rows)} ({n/max(len(rows),1):.1%})")

# 2) Body text of the sample.
stats = {"random": Counter(), "recent": Counter()}
for d in docs:
    g = picks.get(d["row"], "random")
    st = stats[g]
    st["docs"] += 1
    texts, vision_pages, src = [], 0, Counter()
    for p in d["pages"]:
        t, s = page_text(p["page_id"], p["cls"])
        src[s] += 1
        texts.append(t)
        if p["cls"] != "english_clean":
            vision_pages += 1
    full = "\n".join(texts)
    st["pages"] += len(d["pages"])
    st["vision_pages"] += vision_pages
    if vision_pages:
        st["docs_with_vision_page"] += 1
    if vision_pages == len(d["pages"]):
        st["docs_all_vision"] += 1
    change_en = bool(EN_CHANGE.search(full))
    strong_en = bool(EN_STRONG.search(full))
    change_bn = bool(BN_CHANGE.search(full))
    title_change = bool(TITLE_CHANGE.search(d.get("title") or ""))
    if strong_en or change_bn:
        st["change_trigger_strong"] += 1
    if change_en or change_bn:
        st["change_trigger_any"] += 1
    if title_change:
        st["title_change"] += 1
    if EN_REF.search(full) or BN_REF.search(full):
        st["cites_other_instrument"] += 1
    if DATE.search(full) and DEADLINE.search(full):
        st["has_deadline_wording"] += 1
    if PENALTY.search(full):
        st["has_penalty_wording"] += 1
    if d["total_pages"] > 12:
        st["long_doc_gt12"] += 1
    if d["total_pages"] <= 3:
        st["short_le3"] += 1

for g, st in stats.items():
    n = st["docs"]
    print(f"\n== {g}: {n} circulars, {st['pages']} pages, {st['vision_pages']} pages need image reading ({st['vision_pages']/st['pages']:.0%})")
    for k in ("docs_with_vision_page", "docs_all_vision", "title_change", "change_trigger_strong", "change_trigger_any",
              "cites_other_instrument", "has_deadline_wording", "has_penalty_wording", "long_doc_gt12", "short_le3"):
        print(f"  {k}: {st[k]} ({st[k]/n:.0%})")
