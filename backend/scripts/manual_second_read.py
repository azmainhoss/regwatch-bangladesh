"""Second reading of quoted sentences from a reading typed by hand instead of Gemini (for when the quota is out).

Same check as the background job (claims.reading_jobs.process_pending_quote_checks -> reading.check_page):
the typed reading of the whole page stands in for the model's strip readings, and the usual comparison
(same numbers, dates, "no" words and codes, at most 3% other edits) decides. It can only confirm a sentence
(CLEAN) or, for a sentence it cannot find on the page, leave it unclear. It never corrects a figure or marks a
misread: the sharper tie-break reading is answered "busy", so a disagreement keeps waiting for Gemini.

Usage on the server (cd /opt/regwatch/app, as the regwatch user, with .venv/bin/python):
  backend/scripts/manual_second_read.py pages <out_dir> <version_id>...   page images that have waiting sentences
  backend/scripts/manual_second_read.py apply <readings_dir> <version_id>...   reads <ver8>_p<NN>.txt for each page
"""
import asyncio
import os
import sys

sys.path.insert(0, "/opt/regwatch/app")
from sqlalchemy import select  # noqa: E402

import backend.app.database.models  # noqa: E402,F401
from backend.app.core.config import settings  # noqa: E402
from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.claims import reading as R  # noqa: E402
from backend.app.modules.claims import reading_jobs  # noqa: E402
from backend.app.modules.claims.models import QuoteReadingCheck  # noqa: E402
from backend.app.modules.documents.models import DocumentPage, DocumentVersion  # noqa: E402
from backend.app.modules.extraction import vision  # noqa: E402
from backend.app.modules.extraction.vision import VisionResult  # noqa: E402
from backend.app.core.storage import storage_service  # noqa: E402

READER = "typed-reading"


async def waiting_pages(db, versions):
    rows = (await db.execute(
        select(DocumentPage.id, DocumentPage.document_version_id, DocumentPage.page_number)
        .join(QuoteReadingCheck, QuoteReadingCheck.page_id == DocumentPage.id)
        .where(QuoteReadingCheck.status == "WAITING", DocumentPage.document_version_id.in_(versions))
        .group_by(DocumentPage.id, DocumentPage.document_version_id, DocumentPage.page_number)
        .order_by(DocumentPage.document_version_id, DocumentPage.page_number)
    )).all()
    return [(r[0], str(r[1]), r[2]) for r in rows]


def name(version_id, page_number):
    return f"{str(version_id)[:8]}_p{page_number:02d}"


async def dump(out_dir, versions):
    os.makedirs(out_dir, exist_ok=True)
    async with AsyncSessionLocal() as db:
        for _pid, vid, n in await waiting_pages(db, versions):
            version = await db.get(DocumentVersion, vid)
            png = vision.render_page_png(storage_service.get_file_bytes(version.storage_path), n, dpi=settings.QUOTE_CHECK_DPI)
            with open(os.path.join(out_dir, name(vid, n) + ".png"), "wb") as f:
                f.write(png)
            print(name(vid, n))


async def apply(readings_dir, versions):
    total = {}
    async with AsyncSessionLocal() as db:
        pages = await waiting_pages(db, versions)
    for pid, vid, n in pages:
        path = os.path.join(readings_dir, name(vid, n) + ".txt")
        if not os.path.exists(path):
            print(name(vid, n), "no typed reading, skipped")
            continue
        lines = [ln.rstrip() for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]

        async def send(images, model, prompt=None, lines=lines):
            if model != settings.QUOTE_CHECK_MODEL:  # the tie-break: leave it to Gemini
                return VisionResult(success=False, transient=True, not_sent=True, error="left for the model")
            crops = [{"index": i + 1, "lines": lines} for i in range(len(images))]
            return VisionResult(success=True, data={"crops": crops}, model=READER)

        async def only_this(db, limit, pid=pid):
            return [pid]

        reading_jobs.pending_page_ids = only_this
        async with AsyncSessionLocal() as db:
            s = await reading_jobs.process_pending_quote_checks(db, limit=1, send=send)
        print(name(vid, n), {k: s[k] for k in ("clean", "unclear", "misread", "corrected", "claims_rerouted") if s.get(k)})
        for k, v in s.items():
            if isinstance(v, int) and not isinstance(v, bool):
                total[k] = total.get(k, 0) + v
    print("total", total)


if __name__ == "__main__":
    mode, target, *vers = sys.argv[1:]
    asyncio.run(dump(target, vers) if mode == "pages" else apply(target, vers))
