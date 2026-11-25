"""Runs the server's own second-reading job, but only on the pages of the given circular versions.

Same code path as the background job (claims.reading_jobs.process_pending_quote_checks); only the page
selection is narrowed. Usage on the server: cd /opt/regwatch/app && sudo -u regwatch .venv/bin/python backend/scripts/second_read.py <version_id>...
Use it to get a much-searched circular to Ready first (the background job goes newest first). Run it early in the day,
before the background job uses up the Gemini quota (resets about 14:00 Dhaka).
"""
import asyncio
import sys

sys.path.insert(0, "/opt/regwatch/app")
from sqlalchemy import select  # noqa: E402

import backend.app.database.models  # noqa: E402,F401
from backend.app.database.session import AsyncSessionLocal  # noqa: E402
from backend.app.modules.claims import reading_jobs  # noqa: E402
from backend.app.modules.claims.models import QuoteReadingCheck  # noqa: E402
from backend.app.modules.documents.models import DocumentPage  # noqa: E402

VERSIONS = sys.argv[1:]


async def only_these_pages(db, limit):
    rows = (await db.execute(
        select(QuoteReadingCheck.page_id, DocumentPage.document_version_id, DocumentPage.page_number)
        .join(DocumentPage, DocumentPage.id == QuoteReadingCheck.page_id)
        .where(QuoteReadingCheck.status == "WAITING", DocumentPage.document_version_id.in_(VERSIONS))
        .group_by(QuoteReadingCheck.page_id, DocumentPage.document_version_id, DocumentPage.page_number)
        .order_by(DocumentPage.document_version_id, DocumentPage.page_number)
    )).all()
    return [r[0] for r in rows][:limit]


async def main():
    reading_jobs.pending_page_ids = only_these_pages
    async with AsyncSessionLocal() as db:
        summary = await reading_jobs.process_pending_quote_checks(db, limit=20)
    print(summary)


asyncio.run(main())
