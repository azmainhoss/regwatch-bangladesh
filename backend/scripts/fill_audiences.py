"""Works out who every circular applies to (For you, owner 2026-11-28) and stores it in document_audiences.
The checked analysis wins; otherwise the circular's addressee line; otherwise its department. No model calls.
New circulars are filled in by themselves (audience.service.fill_missing), so this is needed once, or after
the rules change.

    .venv/bin/python backend/scripts/fill_audiences.py          # every circular
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import backend.app.main  # noqa: E402,F401  (registers every model)
from sqlalchemy import select  # noqa: E402

from backend.app.database.base import Base  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.audience.service import refresh_document  # noqa: E402
from backend.app.modules.documents.models import Document  # noqa: E402


async def main() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(Document.id))).scalars().all()
        tally: Counter = Counter()
        for n, i in enumerate(ids, 1):
            for e in await refresh_document(db, i):
                tally[e] += 1
            if n % 200 == 0:
                await db.commit()
                print(f"{n}/{len(ids)}", flush=True)
        await db.commit()
    print(f"done: {len(ids)} circulars")
    for e, c in tally.most_common():
        print(f"  {e}: {c}")


if __name__ == "__main__":
    asyncio.run(main())
