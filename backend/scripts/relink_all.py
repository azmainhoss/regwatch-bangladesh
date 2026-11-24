"""Applies the 2026-11-24 History & links rules to every circular already in the library (no model calls).

1. Links whose cited circular was not found get another try with the better matching (a department's section
   number left out, "ACD" for "ACD-1", told apart by the cited date).
2. Every link point that no person decided is checked again: change-the-law links that pass every machine check
   (change words, target named in the quote, exactly one older library circular, matching date) are confirmed
   and their rows become VERIFIED, so the target circulars' "in force" status follows by itself.
Nothing is written without --yes; with --yes a database copy is saved first.

    .venv/bin/python backend/scripts/relink_all.py          # counts only
    .venv/bin/python backend/scripts/relink_all.py --yes    # change it
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

import backend.app.main  # noqa: E402,F401  (registers every model)
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis  # noqa: E402
from backend.app.modules.analysis.sentences import SentenceIndex  # noqa: E402
from backend.app.modules.claims import decide  # noqa: E402
from backend.app.modules.claims import reading as R  # noqa: E402
from backend.app.modules.claims import status as S  # noqa: E402
from backend.app.modules.claims.checks import run_code_checks  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentVersion  # noqa: E402
from backend.app.modules.relationships.linking import link_relationship_targets  # noqa: E402
from backend.app.modules.relationships.models import DocumentRelationship  # noqa: E402


def backup_db() -> None:
    url = settings.SYNC_DATABASE_URL or ""
    path = url.split("sqlite:///", 1)[-1] if url.startswith("sqlite") else None
    if not path or not os.path.exists(path):
        return
    out = f"{os.path.splitext(path)[0]}.before-relink-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(path), sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close(), dst.close()
    print(f"Database copy: {out}")


async def counts(db) -> Counter:
    rows = (
        await db.execute(
            select(DocumentRelationship.relationship_type, DocumentRelationship.verification_status,
                   DocumentRelationship.target_document_id.isnot(None), func.count())
            .group_by(DocumentRelationship.relationship_type, DocumentRelationship.verification_status,
                      DocumentRelationship.target_document_id.isnot(None))
        )
    ).all()
    out: Counter = Counter()
    for t, v, has, n in rows:
        out[("linked" if has else "no target", "CHANGE" if t in ("AMENDS", "REPEALS", "SUPERSEDES", "REPLACES") else t, v)] += n
    return out


async def main(write: bool) -> None:
    async with AsyncSessionLocal() as db:
        before = await counts(db)
        if not write:
            for k, n in sorted(before.items()):
                print(f"{' / '.join(k):45} {n}")
            print("Nothing changed (add --yes).")
            return
        linked = await link_relationship_targets(db)
        print(f"Links matched to a library circular now: {linked}")

        version_ids = (
            await db.execute(
                select(DocumentAnalysis.document_version_id).join(AnalysisClaim, AnalysisClaim.analysis_id == DocumentAnalysis.id)
                .where(AnalysisClaim.kind == "LINK", AnalysisClaim.check_status.notin_(S.DECIDED_STATUSES)).distinct()
            )
        ).scalars().all()
        from backend.app.modules.analysis.service import pages_payload_for

        done = 0
        for vid in version_ids:
            version = (await db.execute(select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id == vid))).scalars().first()
            doc = await db.get(Document, version.document_id) if version else None
            if version is None or doc is None:
                continue
            claims = (
                await db.execute(
                    select(AnalysisClaim).join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
                    .where(DocumentAnalysis.document_version_id == vid, AnalysisClaim.kind == "LINK",
                           AnalysisClaim.check_status.notin_(S.DECIDED_STATUSES))
                )
            ).scalars().all()
            index = SentenceIndex.build(pages_payload_for(version))
            reading = await R.ensure_reading_checks(db, claims, index, version.pages)
            await run_code_checks(db, claims, index, doc, version.pages, reading)
            for claim in claims:
                asked = any(c.get("name") == S.ASKED_FOR_REVIEW_CHECK for c in (claim.checks or []))
                S.route(claim, doc)
                if asked:
                    S.ask_for_review(claim)
                await decide.settle(db, claim, doc)
                done += 1
            await db.commit()
        print(f"Link points checked again: {done} in {len(version_ids)} circulars")
        after = await counts(db)
        keys = sorted(set(before) | set(after))
        print(f"{'':45} before  after")
        for k in keys:
            print(f"{' / '.join(k):45} {before.get(k, 0):6} {after.get(k, 0):6}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.yes:
        backup_db()
    asyncio.run(main(a.yes))
