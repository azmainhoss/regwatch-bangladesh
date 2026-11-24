"""Judges the stored second readings again with the current rules (2026-11-24 review), with no new model calls.

For every quote reading that ended MISREAD or UNCLEAR:
- a stored reading of our lines that the current comparison accepts (Bangla spelling variants, wider
  focus) -> CLEAN;
- every stored reading missed our lines (the strip held other lines because the line box was off) ->
  WAITING with its readings cleared, so the page reader reads it again with the wider strip and the
  whole-page fallback (automatic, within the daily Gemini quota);
- anything else keeps its result.
Then every undecided claim on a changed page is checked again, so points that now pass are shown.
Nothing is written without --yes; with --yes a database copy is saved first.

    .venv/bin/python backend/scripts/rejudge_readings.py          # counts only
    .venv/bin/python backend/scripts/rejudge_readings.py --yes    # change it
"""
import argparse
import asyncio
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

import backend.app.main  # noqa: E402,F401  (registers every model)
from backend.app.core.config import settings  # noqa: E402
from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.claims import reading as R  # noqa: E402
from backend.app.modules.claims.models import QuoteReadingCheck  # noqa: E402
from backend.app.modules.claims.reading_jobs import _department_codes, reroute_claims_for_page  # noqa: E402
from backend.app.modules.documents.models import DocumentPage  # noqa: E402

USABLE = ("CROP", "SHARP_CROP", "PAGE")


def verdict(row) -> str:
    reads = [x for x in (row.reads or []) if isinstance(x, dict)]
    ours = row.our_text or ""
    texts = []
    for x in reads:
        full = x.get("full") or x.get("text") or ""
        if x.get("kind") in USABLE and full:
            found = R.locate_in_page_reading(ours, full)
            if found is not None:
                texts.append(found)
    if not texts:
        return "REREAD" if reads else "KEEP"
    return "CLEAN" if any(R.same_reading(ours, t, row.numbers_confirmed or [], CODES) for t in texts) else "KEEP"


CODES: list = []


def backup_db() -> None:
    url = settings.SYNC_DATABASE_URL or ""
    path = url.split("sqlite:///", 1)[-1] if url.startswith("sqlite") else None
    if not path or not os.path.exists(path):
        return
    out = f"{os.path.splitext(path)[0]}.before-rejudge-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(path), sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close(), dst.close()
    print(f"Database copy: {out}")


async def main(write: bool) -> None:
    global CODES
    async with AsyncSessionLocal() as db:
        CODES = list(await _department_codes(db))
        rows = (await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.status.in_(("MISREAD", "UNCLEAR"))))).scalars().all()
        counts: Counter = Counter()
        pages = set()
        for row in rows:
            v = verdict(row)
            counts[(row.status, v)] += 1
            if not write or v == "KEEP":
                continue
            if v == "CLEAN":
                row.status, row.last_error = "CLEAN", None
                row.checked_at = datetime.utcnow()
            else:
                row.status, row.reads, row.last_error, row.attempts, row.checked_at = "WAITING", [], None, 0, None
            pages.add(row.page_id)
        for (before, v), n in sorted(counts.items()):
            print(f"{before:8} -> {v:6} {n}")
        if not write:
            print("Nothing changed (add --yes).")
            return
        await db.commit()
        rerouted = 0
        for page_id in pages:
            page = await db.get(DocumentPage, page_id)
            if page is not None:
                rerouted += await reroute_claims_for_page(db, page.document_version_id, page.page_number)
                await db.commit()
        print(f"Pages changed: {len(pages)}; claims checked again: {rerouted}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.yes:
        backup_db()
    asyncio.run(main(a.yes))
