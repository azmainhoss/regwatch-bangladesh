"""Pages of new circulars held from analysis because no reader could read them: read them by hand.

A new circular (found by the live checker) is analysed only when every page has clean text. A page that
both Gemini routes and the last reading route could not read (or that waits because the last route has no
key yet) holds its circular, and the platform team gets an alert. Until the last route has a key, a person
or a coding session on this PC reads those pages from their images with this script:

    .venv\\Scripts\\python.exe backend\\scripts\\held_pages.py list
        writes each held page as a 200 dpi image to research/archive/data/held_pages/ and prints
        <page_id>  <reference>  page <n>  <image path>
    .venv\\Scripts\\python.exe backend\\scripts\\held_pages.py save <page_id> <text file>
        saves the transcription (exact text in the page's own language, numbers and dates as printed,
        tables as rows with " | " between cells, [illegible] for anything unreadable). The page becomes
        read (method MANUAL_SUBSCRIPTION_READING), and the circular is analysed once all pages are clean.

The text must not look damaged; otherwise nothing is saved. Pages a person corrected are never touched.
"""
import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import os  # noqa: E402

os.chdir(ROOT)  # the database path in .env is relative to the repo root

import backend.app.database.models  # noqa: E402,F401
from sqlalchemy import select  # noqa: E402

from backend.app.core.storage import storage_service  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion  # noqa: E402
from backend.app.modules.extraction.quality import ExtractionQualityAssessor  # noqa: E402
from backend.app.modules.extraction.service import METHOD_MANUAL, STATUS_VISION_MANUAL  # noqa: E402
from backend.app.modules.extraction.strong_reader import LIVE_STATUS, page_is_read, page_text_ok  # noqa: E402
from backend.app.modules.extraction.vision import render_page_png  # noqa: E402

OUT = ROOT / "research" / "archive" / "data" / "held_pages"


async def held_pages(db):
    """(page, storage_path, document) for unread pages of new circulars that no reader is still working on."""
    rows = (await db.execute(
        select(DocumentPage, DocumentVersion.storage_path, Document)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(Document.publication_status == LIVE_STATUS, Document.owner_user_id.is_(None),
               DocumentPage.is_human_corrected.is_(False),
               DocumentPage.quality_status.in_(("READ_FAILED", "NEEDS_HUMAN_REVIEW")))
        .order_by(Document.publication_date.desc(), DocumentPage.page_number)
    )).all()
    return [(p, path, d) for p, path, d in rows if not page_is_read(p)]


async def cmd_list() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as db:
        rows = await held_pages(db)
    pdfs = {}
    for page, path, doc in rows:
        if path not in pdfs:
            pdfs[path] = storage_service.get_file_bytes(path)
        image = OUT / f"{page.id}.png"
        image.write_bytes(render_page_png(pdfs[path], page.page_number, 200))
        print(f"{page.id}  {doc.reference_number or doc.title}  page {page.page_number}  {image}")
    print(f"{len(rows)} held page(s).")
    return 0


async def cmd_save(page_id: str, text_file: str) -> int:
    text = Path(text_file).read_text(encoding="utf-8").strip()
    if not page_text_ok(text):
        print("Not saved: the text is empty or looks damaged.")
        return 1
    async with AsyncSessionLocal() as db:
        page = await db.get(DocumentPage, UUID(page_id))
        if page is None or page.is_human_corrected:
            print("Not saved: no such page, or a person corrected it.")
            return 1
        if page.extraction_method == "TEXT_LAYER" and page.raw_text and not page.native_text:
            page.native_text = page.raw_text
        page.raw_text = text
        page.ocr_text = text
        page.cleaned_text = re.sub(r"\n{3,}", "\n\n", text)
        page.line_boxes = None
        page.extraction_method = METHOD_MANUAL
        page.quality_status = STATUS_VISION_MANUAL
        page.quality_score = ExtractionQualityAssessor.assess_page(
            page_number=page.page_number, raw_text=text, extraction_method=METHOD_MANUAL).quality_score
        page.vision_error = None
        page.updated_at = datetime.now(timezone.utc)
        await db.commit()
    print(f"Saved page {page_id}.")
    from backend.app.modules.analysis.auto import analyze_ready_live_circulars

    n = await analyze_ready_live_circulars(AsyncSessionLocal)
    if n:
        print(f"Analysed {n} circular(s) whose pages are now all read.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("save")
    p.add_argument("page_id")
    p.add_argument("text_file")
    args = ap.parse_args()

    async def run() -> int:
        try:
            return await (cmd_list() if args.cmd == "list" else cmd_save(args.page_id, args.text_file))
        finally:
            await async_engine.dispose()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
