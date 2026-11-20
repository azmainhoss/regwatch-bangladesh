r"""One-off (20 Nov 2026): no point waits for a person any more. Points still WAITING_FOR_PERSON are routed
again with today's rules (failed a check -> hidden; passed every check -> shown, a change-the-law link as
"Mentions"), their rows synced, and each circular's status set again. A copy of the database is saved first.

    .venv\Scripts\python.exe backend\scripts\reroute_waiting_points.py
"""
import asyncio
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import backend.app.database.models  # noqa: E402,F401
from sqlalchemy import select  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis  # noqa: E402
from backend.app.modules.claims import status as S  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentVersion  # noqa: E402


async def main() -> None:
    db_path = settings.SYNC_DATABASE_URL.split("///", 1)[1]
    with sqlite3.connect(db_path) as c:
        c.execute("pragma wal_checkpoint(full)")
    backup = Path(db_path).with_name(f"regwatch.before-reroute-{datetime.now():%Y%m%d-%H%M}.db")
    shutil.copy2(db_path, backup)
    async with AsyncSessionLocal() as db:
        waiting = (await db.execute(select(AnalysisClaim, Document)
                                    .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
                                    .join(DocumentVersion, DocumentVersion.id == DocumentAnalysis.document_version_id)
                                    .join(Document, Document.id == DocumentVersion.document_id)
                                    .where(AnalysisClaim.check_status == S.WAITING_FOR_PERSON))).all()
        docs = {}
        for claim, doc in waiting:
            asked = any(c.get("name") == S.ASKED_FOR_REVIEW_CHECK for c in (claim.checks or []))
            S.route(claim, doc, force_review=asked)
            docs[doc.id] = doc
        await S.sync_rows(db, [c for c, _d in waiting])
        for doc in docs.values():
            analysis = (await db.execute(select(DocumentAnalysis).where(
                DocumentAnalysis.document_version_id == doc.current_version_id))).scalars().first()
            if analysis is None:
                continue
            claims = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all()
            S.apply_document_status(doc, claims)
        await db.commit()
    await async_engine.dispose()
    print(f"Routed {len(waiting)} waiting point(s) again in {len(docs)} circular(s). Copy before: {backup}")


if __name__ == "__main__":
    asyncio.run(main())
