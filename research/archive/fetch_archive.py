"""Download the Bangla-only part of the Bangladesh Bank circular archive, slowly.

Usage:
    python fetch_archive.py index      # fetch the full list once, save data/index.json
    python fetch_archive.py download   # download until done or 18:00 (resumes where it left off)
    python fetch_archive.py report     # counts, pages, and batch folders for manual reading

One request at a time, at least 15 s apart (shared lock with the detection test).
Runs only 10:00-18:00 Bangladesh time. Files land in data/pdfs/, not committed.
"""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "detect"))
from detect_test import BDT, DAY_END, DAY_START, URL, classify, fetch  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
PDFS = DATA / "pdfs"
INDEX = DATA / "index.json"
STATE = DATA / "downloads.json"
BATCH_SIZE = 20


def in_window():
    h = datetime.now(BDT).hour
    return DAY_START <= h < DAY_END


def index():
    DATA.mkdir(parents=True, exist_ok=True)
    status, raw, _, secs = fetch("GET", URL, timeout=180)
    outcome, rows = classify(status, raw.decode("utf-8", "replace"))
    if outcome != "ok":
        sys.exit(f"listing failed: {outcome}")
    groups = {}
    for r in rows:
        groups.setdefault((r["date"], r["title"]), []).append(r)
    items = []
    for (date, title), rs in groups.items():
        langs = {r["lang"] for r in rs}
        for r in rs:
            items.append({**r, "bangla_only": langs == {"bn"}})
    INDEX.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    bn_only = [i for i in items if i["bangla_only"]]
    print(f"{len(groups)} circulars, {len(items)} PDFs, {len(bn_only)} Bangla-only PDFs ({secs:.1f}s)")


def safe_name(item):
    d = datetime.strptime(item["date"], "%d/%m/%y").strftime("%Y-%m-%d")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", item["pdf"].rsplit("/", 1)[-1])
    return f"{d}_{base}"


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def download():
    items = [i for i in json.loads(INDEX.read_text(encoding="utf-8")) if i["bangla_only"]]
    state = load_state()
    PDFS.mkdir(parents=True, exist_ok=True)
    for item in items:
        if not in_window():
            print("outside 10:00-18:00, stopping")
            break
        if state.get(item["pdf"], {}).get("status") in ("ok", "rejected"):
            continue
        try:
            status, raw, headers, _ = fetch("GET", item["pdf"], timeout=120)
        except Exception as e:  # network error: try again next run
            state[item["pdf"]] = {"status": f"error:{type(e).__name__}"}
            continue
        if raw[:4] == b"%PDF":
            name = safe_name(item)
            (PDFS / name).write_bytes(raw)
            state[item["pdf"]] = {"status": "ok", "file": name, "bytes": len(raw),
                                  "sha256": hashlib.sha256(raw).hexdigest(),
                                  "etag": headers.get("ETag"), "last_modified": headers.get("Last-Modified")}
        elif b"request rejected" in raw.lower():
            state[item["pdf"]] = {"status": "rejected"}  # skip this file, not a block
        else:
            outcome, _ = classify(status, raw.decode("utf-8", "replace"))
            state[item["pdf"]] = {"status": f"failed:{outcome}"}
            if outcome == "challenge":
                STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
                sys.exit("bot check page: stopping, try later")
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def report():
    import pymupdf
    items = [i for i in json.loads(INDEX.read_text(encoding="utf-8")) if i["bangla_only"]]
    state = load_state()
    ok = [state[i["pdf"]] for i in items if state.get(i["pdf"], {}).get("status") == "ok"]
    pages = 0
    for s in ok:
        if "pages" not in s:
            with pymupdf.open(PDFS / s["file"]) as doc:
                s["pages"] = doc.page_count
        pages += s["pages"]
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    statuses = {}
    for i in items:
        k = state.get(i["pdf"], {}).get("status", "pending")
        statuses[k] = statuses.get(k, 0) + 1
    print(f"Bangla-only PDFs: {len(items)}  {statuses}")
    print(f"Downloaded: {len(ok)} files, {pages} pages"
          + (f", {pages / len(ok):.1f} pages each" if ok else ""))
    if ok and len(ok) < len(items):
        print(f"Estimated total pages: {round(pages / len(ok) * len(items))}")


if __name__ == "__main__":
    {"index": index, "download": download, "report": report}[sys.argv[1]]()
