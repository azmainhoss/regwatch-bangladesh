"""Sorts every circular that has no subject category yet (topics/classify.py), newest first.

Safe to stop and start again: sorted circulars are skipped. Uses the free Gemini keys gently
(one call of 25 circulars every few seconds, rotating keys). New circulars are also sorted by the
live checker on its own, so this is only needed for the backlog.

Usage (repo root):
    .venv/Scripts/python.exe backend/scripts/classify_topics.py [--limit 5000] [--status]
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import backend.app.database.models  # noqa: E402,F401
from sqlalchemy import func, select  # noqa: E402

from backend.app.database.base import Base  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.documents.models import Document  # noqa: E402
from backend.app.modules.topics.classify import classify_pending  # noqa: E402
from backend.app.modules.topics.models import DocumentTopic  # noqa: E402


async def main(limit: int, status_only: bool) -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[DocumentTopic.__table__]))
    async with AsyncSessionLocal() as db:
        total = (await db.execute(select(func.count()).select_from(Document).where(Document.owner_user_id.is_(None)))).scalar_one()
        done = (await db.execute(select(func.count(func.distinct(DocumentTopic.document_id))))).scalar_one()
        print(f"Sorted: {done} of {total} circulars.")
        if status_only:
            return
        left = limit
        while left > 0:
            n = await classify_pending(db, limit=min(100, left))
            if not n:
                break
            left -= n
            done += n
            print(f"Sorted: {done} of {total}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6000)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.status))
