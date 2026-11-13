"""Fetch the full circular list once and save data/index.json (one entry per PDF URL)."""
import json
import sys
from collections import Counter

from archive_lib import DATA, INDEX, URL, classify_listing, department_of, fetch, iso, reference_of


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    status, raw, _, secs = fetch("GET", URL, gap=5, timeout=300)
    outcome, rows = classify_listing(status, raw)
    if outcome != "ok":
        sys.exit(f"listing failed: {outcome} (http {status}, {len(raw)} bytes)")
    items, circulars = [], {}
    for r in rows:
        key = (r["date"], r["title"])
        circulars.setdefault(key, len(circulars) + 1)
        items.append({
            "url": r["url"], "lang": r["lang"], "date": r["date"], "title": r["title"],
            "department": department_of(r["title"]), "reference": reference_of(r["title"]),
            "circular_id": circulars[key]})
    seen, unique = set(), []
    for it in items:  # the same PDF can sit in two rows; keep the first
        if it["url"] not in seen:
            seen.add(it["url"])
            unique.append(it)
    INDEX.write_text(json.dumps({"built_at": iso(), "pdfs": unique}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    langs = Counter(i["lang"] for i in unique)
    print(f"{len(circulars)} circulars, {len(unique)} PDFs {dict(langs)}, "
          f"listing {len(raw)/1e6:.1f} MB in {secs:.1f}s")


if __name__ == "__main__":
    main()
