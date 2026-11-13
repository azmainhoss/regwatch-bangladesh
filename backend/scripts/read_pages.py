"""Always-on page reader: reads every page waiting for image reading (Bangla, legacy-font, scanned),
newest circulars first, using all Gemini keys in .env (GEMINI_API_KEY + GEMINI_EXTRA_API_KEYS).

- Runs batch after batch while pages are waiting; checks again every 10 s when nothing is left.
- When every key has used up today's free quota, it waits for the daily reset (about 14:05 Bangladesh time).
  Busy or out-of-quota replies never count against a page.
- Only one copy runs at a time (lock file data/page_reader.lock). While it runs, the web app's own
  page-reading job stands aside, so no page is read twice.

Usage (repo root):
    .venv/Scripts/python.exe backend/scripts/read_pages.py          # run until stopped
    .venv/Scripts/python.exe backend/scripts/read_pages.py --status # counts and exit
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

import backend.app.database.models  # noqa: E402,F401
from backend.app.core.config import settings  # noqa: E402
from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.documents.models import DocumentPage  # noqa: E402
from backend.app.modules.analysis.auto import analyze_ready_live_circulars  # noqa: E402
from backend.app.modules.extraction.vision import available_gemini_keys, gemini_keys  # noqa: E402
from backend.app.modules.extraction.vision_jobs import PAGE_READER_LOCK, process_pending_vision_pages  # noqa: E402

LOG = ROOT / "data" / "page_reader.log"


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def counts() -> dict:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(DocumentPage.quality_status, func.count()).group_by(DocumentPage.quality_status))).all()
    return {status: n for status, n in rows}


def lock_is_held_by_other() -> bool:
    if not PAGE_READER_LOCK.exists():
        return False
    try:
        info = json.loads(PAGE_READER_LOCK.read_text(encoding="utf-8"))
    except ValueError:
        return False
    fresh = time.time() - PAGE_READER_LOCK.stat().st_mtime < 900
    return fresh and info.get("pid") != os.getpid()


def heartbeat(state: str) -> None:
    info = {"pid": os.getpid(), "state": state, "at": datetime.now(timezone.utc).isoformat()}
    if state == "waiting for quota":
        from backend.app.modules.extraction.vision import _next_quota_reset
        info["quota_back_at"] = _next_quota_reset().isoformat()
    PAGE_READER_LOCK.write_text(json.dumps(info), encoding="utf-8")


async def run() -> None:
    if lock_is_held_by_other():
        print("Another page reader is running; exiting.")
        return
    if not gemini_keys():
        print("No Gemini key in .env; nothing to do.")
        return
    heartbeat("starting")
    log(f"Page reader started with {len(gemini_keys())} keys.")
    read_total = 0
    try:
        while True:
            heartbeat("reading")
            try:
                async with AsyncSessionLocal() as db:
                    summary = await process_pending_vision_pages(db, limit=40)
            except Exception as e:  # e.g. the database is busy with an import: try again shortly
                log(f"Batch skipped: {type(e).__name__}: {str(e)[:120]}")
                await asyncio.sleep(15)
                continue
            read_total += summary["read"]
            if summary["read"]:
                try:
                    n = await analyze_ready_live_circulars(AsyncSessionLocal)
                    if n:
                        log(f"analysed {n} new circular(s) whose pages are now all read")
                except Exception as e:
                    log(f"New-circular analysis skipped: {type(e).__name__}")
            if summary["read"] or summary["failed"] or summary["sent_to_review"]:
                log(f"read {summary['read']}, failed {summary['failed']}, to a person {summary['sent_to_review']}, "
                    f"busy {summary['waiting_busy']} (total read this run: {read_total})")
            if summary["out_of_quota"] or not available_gemini_keys():
                log("All keys used today's free quota; waiting for the daily reset.")
                for _ in range(30):  # 30 min, keeping the lock fresh
                    heartbeat("waiting for quota")
                    await asyncio.sleep(60)
                continue
            if summary["batch_full"] and summary["read"]:
                continue
            heartbeat("idle")
            # Short sleep, so a new upload is picked up within seconds.
            await asyncio.sleep(10)
    finally:
        try:
            PAGE_READER_LOCK.unlink()
        except OSError:
            pass


async def status() -> None:
    c = await counts()
    print(json.dumps({"pages_by_status": c, "keys": len(gemini_keys()), "keys_with_quota_now": len(available_gemini_keys())}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(status() if a.status else run())
