"""A new circular never goes to analysis with a page that is not cleanly read.

Order per page: text layer -> Gemini (main, then stronger) -> the last reading route -> held + alert.
"Ready for analysis" means every page has status SUCCESS_* with text that does not look damaged.
"""
import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.analysis import auto
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.extraction import strong_reader
from backend.app.modules.extraction.quality import ExtractionQualityAssessor, text_layer_looks_damaged
from backend.app.modules.extraction.vision import VisionResult

GARBLED = "~8. \\5W'R~~~~;qJf\\bc~C<f'~~~'ft9J,Cm\\5W'R~c<Wr9i~~ ~Q. \\5W'R~~~~~\\5W'R~~q~~"
BANGLA = "ব্যাংকসমূহকে প্রতি মাসে প্রতিবেদন দাখিল করতে হবে।"


def _damaged(text):
    return text_layer_looks_damaged(ExtractionQualityAssessor.assess_page(1, text, "TEXT_LAYER"))


def test_fill_in_lines_bangla_and_word_bullets_are_not_damage():
    assert not _damaged("Name of tour operator: ……………………………. Date: ………………\nSignature: ..........................")
    assert not _damaged("শাখার নাম: ……………… তারিখ: ……………\n" + BANGLA * 3)
    assert not _damaged("Banks must report monthly.\nKeep records. for five years.")
    assert _damaged(GARBLED)  # legacy-font text is still caught
    assert _damaged("ms‡hvRbx-M ‡`‡ ¯¯© †¶‡ ‡`‡ ©¯¯")


async def _live_circular(statuses_and_texts, title="Live circular for the last reading route"):
    from backend.app.tests.test_page_reading import _ingest, bangla_pdf

    doc_id, version_id = await _ingest(bangla_pdf(pages=len(statuses_and_texts)), title=title)
    async with AsyncSessionLocal() as db:
        (await db.get(Document, doc_id)).publication_status = "PUBLISHED_MACHINE_PROCESSED"
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version_id)
                                  .order_by(DocumentPage.page_number))).scalars().all()
        for page, (status, text) in zip(pages, statuses_and_texts):
            page.quality_status, page.raw_text, page.cleaned_text = status, text, text
        await db.commit()
    return doc_id, version_id


async def _page(version_id, number):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version_id,
                                                            DocumentPage.page_number == number))).scalar_one()


async def _ready(doc_id):
    auto._last_try.clear()
    async with AsyncSessionLocal() as db:
        return doc_id in await auto.ready_live_circulars(db, limit=500)


@pytest.mark.asyncio
async def test_none_waiting_is_not_enough_every_page_must_be_read_cleanly():
    failed, _ = await _live_circular([("SUCCESS_VISION", BANGLA), ("READ_FAILED", "")])
    damaged, _ = await _live_circular([("SUCCESS_NATIVE", GARBLED)])
    clean, _ = await _live_circular([("SUCCESS_VISION", BANGLA), ("SUCCESS_NATIVE", "Banks must report. Name: ………")])
    assert not await _ready(failed)
    assert not await _ready(damaged)
    assert await _ready(clean)


@pytest.mark.asyncio
async def test_last_route_reads_an_unread_page_and_the_circular_becomes_ready(monkeypatch):
    doc_id, version_id = await _live_circular([("SUCCESS_VISION", BANGLA), ("READ_FAILED", "")])
    monkeypatch.setattr(strong_reader.storage_service, "get_file_bytes", _pdf_bytes_for(version_id))
    seen = []

    async def reader(png):
        seen.append(png)
        return VisionResult(success=True, text=BANGLA, model="test-reader")

    async with AsyncSessionLocal() as db:
        out = await strong_reader.rescue_unread_live_pages(db, reader=reader)
    assert out["read"] >= 1 and seen
    page = await _page(version_id, 2)
    assert page.quality_status == "SUCCESS_VISION" and page.extraction_method == "STRONG_VISION"
    assert page.raw_text == BANGLA and page.vision_error.startswith(strong_reader.TRIED_MARK)
    assert await _ready(doc_id)


@pytest.mark.asyncio
async def test_a_page_the_last_route_cannot_read_holds_the_circular_and_alerts_once(monkeypatch):
    from backend.app.modules.alerts.models import AlertEvent

    doc_id, version_id = await _live_circular([("SUCCESS_NATIVE", GARBLED)], title="Held live circular")
    monkeypatch.setattr(strong_reader.storage_service, "get_file_bytes", _pdf_bytes_for(version_id))
    calls = []

    async def reader(png):
        calls.append(1)
        return VisionResult(success=True, text=GARBLED, model="test-reader")  # still damaged

    async with AsyncSessionLocal() as db:
        await strong_reader.rescue_unread_live_pages(db, reader=reader)
    page = await _page(version_id, 1)
    assert page.quality_status == "READ_FAILED" and "failed" in page.vision_error
    assert not await _ready(doc_id)
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AlertEvent).where(
            AlertEvent.dedupe_key == f"ADMIN_QUEUE:pages:held:{doc_id}"))).scalars().all()
    assert len(events) == 1

    n = len(calls)
    async with AsyncSessionLocal() as db:
        await strong_reader.rescue_unread_live_pages(db, reader=reader)
    assert len(calls) == n  # one try per page, never a loop


@pytest.mark.asyncio
async def test_without_a_key_the_circular_is_held_and_alerted(monkeypatch):
    from backend.app.modules.alerts.models import AlertEvent

    monkeypatch.setattr(settings, "STRONG_READER_API_KEY", None)
    doc_id, version_id = await _live_circular([("READ_FAILED", "")], title="Held live circular, no key")
    async with AsyncSessionLocal() as db:
        await strong_reader.rescue_unread_live_pages(db)
    page = await _page(version_id, 1)
    assert page.quality_status == "READ_FAILED"
    assert not page.vision_error.startswith(strong_reader.TRIED_MARK)  # not a try: read once a key is added
    assert not await _ready(doc_id)
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(AlertEvent).where(
            AlertEvent.dedupe_key == f"ADMIN_QUEUE:pages:held:{doc_id}"))).scalars().first() is not None


@pytest.mark.asyncio
async def test_analysis_holds_every_point_when_a_page_ended_unread(monkeypatch):
    from backend.app.modules.analysis.service import AnalysisService

    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "mock")
    seen = {}
    real = AnalysisService._replace_analysis_results

    async def spy(*args, **kwargs):
        seen["force"] = kwargs.get("force_human_review")
        return await real(*args, **kwargs)

    monkeypatch.setattr(AnalysisService, "_replace_analysis_results", staticmethod(spy))
    doc_id, _ = await _live_circular([("SUCCESS_VISION", BANGLA), ("READ_FAILED", "")], title="Analysed on request")
    async with AsyncSessionLocal() as db:
        try:
            await AnalysisService.analyze_document_version(db=db, document_id=doc_id, provider_name="mock")
        except RuntimeError:
            pass  # the mock may find nothing to say; only the hold decision matters here
    assert seen.get("force") is True


def _pdf_bytes_for(version_id):
    from backend.app.tests.test_page_reading import bangla_pdf

    data = bangla_pdf(pages=2)
    return lambda path: data
