"""Step 1 of the scorer: save the fixed inputs, once.

For every page of every circular in a split:
- English pages with a clean text layer get their text and word boxes exactly as the app's ingest makes them.
- Bangla, legacy-font and scanned pages are read once from the page image with the app's own page reader
  (free Gemini keys, key rotation), giving text and line boxes exactly as the app stores them.
Each page is saved as inputs/<page_id>.json. Pages already saved are skipped, so it is safe to run again.

The answer kit's and the gold transcriptions are never used as input: that would hide reading errors.

A page is saved only when its reading really worked. When the free quota stops the reading, the page
stays unsaved and is counted as waiting. Nothing is ever filled in for it.

Usage (repo root):
    .venv\\Scripts\\python.exe research\\scoring\\prepare_inputs.py --split dev
    .venv\\Scripts\\python.exe research\\scoring\\prepare_inputs.py --split dev --status
    .venv\\Scripts\\python.exe research\\scoring\\prepare_inputs.py --split dev --wait     # sleeps until the quota is back, then continues
    .venv\\Scripts\\python.exe research\\scoring\\prepare_inputs.py --split test --final   # only for the final run
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import common
import quota
from common import ScorerError

common.point_app_at_scratch()

from backend.app.core.config import settings  # noqa: E402
from backend.app.modules.extraction import vision  # noqa: E402
from backend.app.modules.extraction.quality import ExtractionQualityAssessor  # noqa: E402
from backend.app.modules.extraction.service import (  # noqa: E402
    METHOD_VISION,
    STATUS_VISION,
    ExtractionService,
)

common.assert_scratch_database()
common.quiet_app_logs()

BUSY_WAIT_SECONDS = 60
MAX_BUSY_ROUNDS = 6  # one page: after this many busy waits in a row the run moves on
MAX_REAL_FAILURES = 3  # one page: real (not quota, not busy) failures in one run before it is skipped


def say(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def page_file(page_id: str) -> Path:
    return common.inputs_dir() / f"{page_id}.json"


def is_ready(page_id: str) -> bool:
    return page_file(page_id).exists()


# ---------------------------------------------------------------------------
# Saving pages
# ---------------------------------------------------------------------------
def _base_record(ref: common.PageRef, row: int) -> Dict[str, Any]:
    return {
        "page_id": ref.page_id,
        "row": row,
        "stem": ref.stem,
        "page": ref.page,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def save_text_layer_page(ref: common.PageRef, row: int, p: Dict[str, Any]) -> None:
    rec = _base_record(ref, row)
    rec.update({
        "method": p["extraction_method"],
        "route_reason": p.get("route_reason"),
        "language": p.get("language"),
        "text": p["raw_text"],
        "cleaned_text": p["cleaned_text"],
        "line_boxes": p.get("line_boxes"),
        "has_tables": bool(p.get("has_tables")),
        "quality_status": p["quality_status"],
        "quality_score": p.get("quality_score", 1.0),
        "model": None,
    })
    common.write_json(page_file(ref.page_id), rec)


def save_vision_page(ref: common.PageRef, row: int, result: "vision.VisionResult", route: Dict[str, Any]) -> None:
    text = result.text.strip()
    rec = _base_record(ref, row)
    score = ExtractionQualityAssessor.assess_page(page_number=ref.page, raw_text=text, extraction_method=METHOD_VISION).quality_score
    rec.update({
        "method": METHOD_VISION,
        "route_reason": route.get("route_reason"),
        "language": route.get("language"),
        "text": text,
        "cleaned_text": re.sub(r"\n{3,}", "\n\n", text),
        "line_boxes": result.line_boxes,
        "has_tables": False,
        "quality_status": STATUS_VISION,
        "quality_score": score,
        "model": result.model,
    })
    common.write_json(page_file(ref.page_id), rec)


# ---------------------------------------------------------------------------
# The work
# ---------------------------------------------------------------------------
def extract_row_pages(rows: List[common.RowInfo]) -> Tuple[int, List[Dict[str, Any]], List[str]]:
    """Saves every text-layer page that is not saved yet. Returns (saved now, image-read pages still to read, problems)."""
    svc = ExtractionService()
    saved = 0
    todo: List[Dict[str, Any]] = []
    problems: List[str] = []
    for row in rows:
        for stem in row.stems:
            refs = row.pages_of(stem)
            missing = [r for r in refs if not is_ready(r.page_id)]
            if not missing:
                continue
            pdf = common.pdf_path(stem)
            if not pdf.exists():
                problems.append(f"{stem}: PDF not found at {pdf}")
                continue
            try:
                pages = svc.extract_document_pages(pdf.read_bytes())
            except Exception as e:  # a broken PDF is reported, not hidden
                problems.append(f"{stem}: could not read the PDF ({type(e).__name__}: {e})")
                continue
            by_number = {p["page_number"]: p for p in pages}
            if len(pages) != len(refs):
                problems.append(f"{stem}: the PDF has {len(pages)} pages but the circular list has {len(refs)}")
            for ref in missing:
                p = by_number.get(ref.page)
                if p is None:
                    problems.append(f"{ref.page_id}: page not in the PDF")
                    continue
                if p["quality_status"] == "PENDING_VISION":
                    todo.append({"ref": ref, "row": row.row, "main": stem == row.main_stem,
                                 "route_reason": p.get("route_reason"), "language": p.get("language")})
                else:
                    save_text_layer_page(ref, row.row, p)
                    saved += 1
    # Pages of the file the app analyses come first; their Bangla twin files last.
    todo.sort(key=lambda t: (not t["main"], t["row"], t["ref"].page_id))
    return saved, todo, problems


async def read_image_pages(todo: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reads the pages waiting for image reading, as far as the free quota allows."""
    summary = {"read": 0, "failed": [], "busy": [], "quota_stopped": False, "no_key": False}
    keys_all = vision.gemini_keys()
    if not keys_all:
        summary["no_key"] = True
        return summary
    turn = 0
    for item in todo:
        ref: common.PageRef = item["ref"]
        if is_ready(ref.page_id):
            continue
        keys = vision.available_gemini_keys()
        if not keys:
            summary["quota_stopped"] = True
            break
        try:
            png = vision.render_page_png(common.pdf_path(ref.stem).read_bytes(), ref.page)
        except Exception as e:
            summary["failed"].append(f"{ref.page_id}: could not draw the page ({type(e).__name__})")
            continue
        busy_rounds = 0
        real_failures = 0
        while True:
            keys = vision.available_gemini_keys()
            if not keys:
                summary["quota_stopped"] = True
                break
            key = keys[turn % len(keys)]
            turn += 1
            result = await vision.read_page_image(png, api_key=key)
            if result.success and result.text.strip():
                save_vision_page(ref, item["row"], result, item)
                summary["read"] += 1
                say(f"read {ref.page_id} ({summary['read']} so far)")
                break
            if result.no_key:
                summary["no_key"] = True
                break
            if result.quota_exhausted:
                continue  # this key is used up for today: try the next one (the loop checks for none left)
            if result.transient:
                busy_rounds += 1
                if busy_rounds >= MAX_BUSY_ROUNDS:
                    summary["busy"].append(ref.page_id)
                    break
                say(f"service busy on {ref.page_id}; waiting {BUSY_WAIT_SECONDS} s")
                await asyncio.sleep(BUSY_WAIT_SECONDS)
                continue
            real_failures += 1
            if real_failures >= MAX_REAL_FAILURES:
                summary["failed"].append(f"{ref.page_id}: {result.error}")
                break
        if summary["quota_stopped"] or summary["no_key"]:
            break
    quota.save()
    return summary


def counts(rows: List[common.RowInfo]) -> Dict[str, Any]:
    total = ready = 0
    waiting_en = waiting_img = 0
    img_total = 0
    waiting_main_img = 0
    for row in rows:
        for ref in row.pages:
            total += 1
            is_img = not (ref.kind or "").startswith("english")
            img_total += is_img
            if is_ready(ref.page_id):
                ready += 1
            elif is_img:
                waiting_img += 1
                waiting_main_img += ref.stem == row.main_stem
            else:
                waiting_en += 1
    return {"pages": total, "ready": ready, "waiting": total - ready, "waiting_english": waiting_en,
            "waiting_image_read": waiting_img, "waiting_image_read_main_file": waiting_main_img,
            "image_read_pages_in_split": img_total}


def print_counts(rows: List[common.RowInfo], split: str) -> Dict[str, Any]:
    c = counts(rows)
    ready_rows = sum(1 for r in rows if all(is_ready(p.page_id) for p in r.pages_of(r.main_stem)))
    print(f"\nSplit {split}: {len(rows)} circulars, {c['pages']} pages.")
    print(f"  Ready:   {c['ready']} pages")
    print(f"  Waiting: {c['waiting']} pages ({c['waiting_english']} English, {c['waiting_image_read']} Bangla or scanned"
          f", of which {c['waiting_image_read_main_file']} in the file the app analyses)")
    print(f"  Circulars with every page of the analysed file ready: {ready_rows} of {len(rows)}")
    if c["waiting_image_read"]:
        print(f"  Free quota for page reading comes back about {quota.reset_time_text()}.")
    return {**c, "rows_ready": ready_rows, "rows": len(rows)}


async def main_async(args: argparse.Namespace) -> int:
    common.require_split(args.split, args.final)
    rows = common.load_rows(args.split, common.parse_rows_arg(args.rows))
    if args.status:
        print_counts(rows, args.split)
        return 0
    if args.final:
        common.log_final("-", f"prepare_inputs {args.split}")
    quota.load([settings.VISION_MODEL])
    while True:
        saved, todo, problems = extract_row_pages(rows)
        say(f"text-layer pages saved this run: {saved}; pages waiting for image reading: {len(todo)}")
        for pr in problems:
            say(f"PROBLEM {pr}")
        summary = await read_image_pages(todo) if todo else {"read": 0, "failed": [], "busy": [], "quota_stopped": False, "no_key": False}
        if summary["no_key"]:
            say("No Gemini key found in .env; image pages cannot be read.")
        for f in summary["failed"]:
            say(f"FAILED {f}")
        for b in summary["busy"]:
            say(f"BUSY (will be tried again on the next run) {b}")
        c = print_counts(rows, args.split)
        if not args.wait or not c["waiting_image_read"] or summary["no_key"]:
            break
        if summary["quota_stopped"]:
            reset = vision._next_quota_reset()
            wait_s = max(60, (reset - datetime.now(timezone.utc)).total_seconds() + 120)
            say(f"Waiting for the free quota until about {quota.reset_time_text()}.")
            slept = 0.0
            while slept < wait_s:
                await asyncio.sleep(min(600, wait_s - slept))
                slept += 600
            vision._exhausted_until.clear()
        else:
            await asyncio.sleep(300)  # busy or failed pages: try again in a while
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Save the fixed inputs (page text and boxes) for a split.")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--rows", help="only these rows, e.g. 2450,1426")
    ap.add_argument("--status", action="store_true", help="print the counts and stop")
    ap.add_argument("--wait", action="store_true", help="when the free quota stops, sleep until it is back and continue")
    ap.add_argument("--final", action="store_true", help="needed for --split test (final run only)")
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args))
    except ScorerError as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
