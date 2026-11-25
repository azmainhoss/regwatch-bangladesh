"""Applies the owner's "no human review" rule (2026-11-25) to everything already in the library (no model calls).

1. Points parked "waiting for a person" leave that queue: the "asked for review" mark is dropped and the point is
   routed by its machine checks alone (passed: shown; failed: hidden from the summary but listed as
   "Page N · AI draft"; still checking: stays checking).
2. Every link row is settled by the machine (claims/status.link_row_status): confirmed change links and plain
   mentions VERIFIED, unconfirmed change links VERIFIED as mentions (REFERENCES), failed links REJECTED; only links
   whose checks are still running stay PENDING_REVIEW.
3. Each analysed circular's status is recomputed: "AI verified" only once at least one point has passed.
Nothing is written without --yes; with --yes a database copy is saved first.

    .venv/bin/python backend/scripts/machine_settle.py          # counts only
    .venv/bin/python backend/scripts/machine_settle.py --yes    # change it
"""
import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import backend.app.main  # noqa: E402,F401  (registers every model)
from sqlalchemy import func, select  # noqa: E402

from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis  # noqa: E402
from backend.app.modules.claims import status as S  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentVersion  # noqa: E402
from backend.app.modules.relationships.models import DocumentRelationship  # noqa: E402
from backend.scripts.relink_all import backup_db  # noqa: E402


async def counts(db) -> Counter:
    out: Counter = Counter()
    for st, n in (await db.execute(select(AnalysisClaim.check_status, func.count()).group_by(AnalysisClaim.check_status))).all():
        out[f"point {st}"] = n
    for st, n in (await db.execute(select(Document.publication_status, func.count()).group_by(Document.publication_status))).all():
        out[f"circular {st}"] = n
    for st, n in (await db.execute(select(DocumentRelationship.verification_status, func.count()).group_by(DocumentRelationship.verification_status))).all():
        out[f"link {st}"] = n
    return out


async def main(write: bool) -> None:
    async with AsyncSessionLocal() as db:
        before = await counts(db)
        if not write:
            for k, n in sorted(before.items()):
                print(f"{k:32} {n}")
            print("Counts only. Run with --yes to apply.")
            return
        backup_db()
        rows = (
            await db.execute(
                select(AnalysisClaim, DocumentAnalysis.document_version_id)
                .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
                .where((AnalysisClaim.check_status == S.WAITING_FOR_PERSON) | (AnalysisClaim.kind == "LINK"))
            )
        ).all()
        docs = {}
        changed = []
        for claim, vid in rows:
            if vid not in docs:
                version = await db.get(DocumentVersion, vid)
                docs[vid] = await db.get(Document, version.document_id) if version else None
            doc = docs[vid]
            if doc is None:
                continue
            if claim.check_status == S.WAITING_FOR_PERSON:
                claim.checks = [c for c in (claim.checks or []) if c.get("name") != S.ASKED_FOR_REVIEW_CHECK]
                claim.check_status, claim.review_queue = S.CHECKING, None  # not a decided status, so route() runs
                S.route(claim, doc)
            changed.append(claim)
        await S.sync_rows(db, changed)
        await db.commit()
        # 3. Every analysed circular's status follows its points: "AI verified" only once a point has passed.
        from backend.app.modules.claims.decide import claims_of, latest_analysis_id

        for doc in (await db.execute(select(Document).where(Document.publication_status.like("PUBLISHED%") | (Document.publication_status == "AWAITING_REVIEW")))).scalars().all():
            aid = await latest_analysis_id(db, doc)
            if aid is not None:
                S.apply_document_status(doc, await claims_of(db, aid))
        await db.commit()
        after = await counts(db)
        print(f"{'':32} before  after")
        for k in sorted(set(before) | set(after)):
            print(f"{k:32} {before.get(k, 0):6} {after.get(k, 0):6}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="write the changes (a database copy is made first)")
    asyncio.run(main(ap.parse_args().yes))
