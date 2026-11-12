"""Page reading by fonts, the page-image (vision) job, the manual archive import, and
English/Bangla language variants.

Every PDF is built here with PyMuPDF. Gemini is never called: replies are faked.
"""
import json
import uuid
from datetime import date
from pathlib import Path

import httpx
import pymupdf
import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.extraction.page_router import (
    REASON_BANGLA_UNICODE,
    REASON_BROKEN_BANGLA,
    REASON_CLEAN_TEXT,
    REASON_LEGACY_FONT,
    REASON_NEAR_EMPTY,
    TEXT_LAYER,
    VISION,
    broken_bangla_count,
    is_legacy_font,
    route_page,
)
from backend.app.modules.extraction.service import extraction_service
from backend.app.modules.extraction.vision import VisionResult, parse_vision_reply, read_page_image, render_page_png
from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages
from backend.app.modules.sources.connector.base import AntiBotChallenge, FetchedFile
from backend.app.modules.sources.service import source_monitoring_service
from backend.app.tests.factories import make_institution

BANGLA = "বাংলাদেশ ব্যাংক প্রধান কার্যালয় মতিঝিল ঢাকা সকল তফসিলি ব্যাংকের প্রধান নির্বাহী"
BIJOY = "evsjv‡`k e¨vsK cÖavb Kvh©vjq gwZwSj XvKv mKj Zdwmwj e¨vs‡Ki cÖavb wbe©vnx"


# --------------------------------------------------------------------------- tiny PDFs
def english_pdf(*lines: str) -> bytes:
    lines = lines or (
        f"BRPD Circular No. {uuid.uuid4().hex[:4]}: Loan classification and provisioning.",
        "All scheduled banks are advised to maintain the required provision of 2.5% from 1 January 2027.",
    )
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 18 * i), line, fontname="helv", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def bijoy_pdf(font_name: str = "SutonnyMJ") -> bytes:
    """Bijoy ANSI text in a font whose name says SutonnyMJ (the glyph shapes do not matter)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), BIJOY, fontname="helv", fontsize=11)
    page.insert_text((72, 90), f"{BIJOY} {uuid.uuid4().hex[:6]}", fontname="helv", fontsize=11)
    for font in page.get_fonts():
        doc.xref_set_key(font[0], "BaseFont", f"/{font_name}")
    data = doc.tobytes()
    doc.close()
    return data


def bangla_pdf(pages: int = 1) -> bytes:
    """Clean Bangla Unicode text layer (glyphs placed one by one, so the text comes back exact)."""
    font = pymupdf.Font(script=pymupdf.UCDN_SCRIPT_BENGALI)
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page()
        page.insert_font(fontname="bn", fontbuffer=font.buffer)
        page.insert_text((50, 80), f"{BANGLA} {n + 1}", fontname="bn", fontsize=12)
        page.insert_text((50, 100), uuid.uuid4().hex, fontname="helv", fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def scanned_pdf() -> bytes:
    """A page that is only a picture of text: no text layer at all."""
    src = pymupdf.open(stream=english_pdf(), filetype="pdf")
    png = src[0].get_pixmap(dpi=72).tobytes("png")
    src.close()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)
    data = doc.tobytes()
    doc.close()
    return data


def _route(pdf: bytes):
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return route_page(doc[0])


# --------------------------------------------------------------------------- routing
def test_english_text_layer_page_is_read_locally_with_line_boxes():
    route = _route(english_pdf("Bangladesh Bank Head Office, Motijheel, Dhaka.", "BRPD Circular No. 15 dated 27 November 2024."))
    assert route.route == TEXT_LAYER and route.reason == REASON_CLEAN_TEXT
    assert [line["text"] for line in route.line_boxes] == [
        "Bangladesh Bank Head Office, Motijheel, Dhaka.", "BRPD Circular No. 15 dated 27 November 2024."]
    for line in route.line_boxes:
        ymin, xmin, ymax, xmax = line["box_2d"]
        assert 0 <= ymin < ymax <= 1000 and 0 <= xmin < xmax <= 1000
    # The second line sits below the first.
    assert route.line_boxes[1]["box_2d"][0] > route.line_boxes[0]["box_2d"][0]


@pytest.mark.parametrize("font", ["SutonnyMJ", "ABCDEF+SutonnyMJ", "NikoshBAN", "NokshiStandard", "SolaimanLipiMJ"])
def test_bijoy_font_page_goes_to_vision(font):
    route = _route(bijoy_pdf(font))
    assert route.route == VISION and route.reason == REASON_LEGACY_FONT and route.language == "bn"


def test_legacy_font_names():
    assert is_legacy_font("SutonnyMJ-Bold") and is_legacy_font("ABCDEF+NokshiStandard")
    assert not is_legacy_font("Helvetica") and not is_legacy_font("NotoSerifBengali-Regular")
    assert not is_legacy_font("TimesNewRomanPSMT")


def test_scanned_page_goes_to_vision():
    route = _route(scanned_pdf())
    assert route.route == VISION and route.reason == REASON_NEAR_EMPTY


def test_bangla_unicode_page_goes_to_vision():
    route = _route(bangla_pdf())
    assert route.route == VISION and route.reason == REASON_BANGLA_UNICODE and route.language == "bn"


def test_broken_bangla_page_goes_to_vision():
    doc = pymupdf.open()
    page = doc.new_page()
    # Shaped Bangla comes back from the text layer with vowel signs out of place.
    page.insert_htmlbox(pymupdf.Rect(50, 50, 550, 400), f"<p>{BANGLA}। {BANGLA}।</p>")
    pdf = doc.tobytes()
    route = _route(pdf)
    assert route.route == VISION and route.reason in (REASON_BROKEN_BANGLA, REASON_BANGLA_UNICODE)
    assert broken_bangla_count(BANGLA) == 0
    assert broken_bangla_count("ি" + "ব" + "��") == 3


def test_short_bangla_letterhead_on_an_english_page_stays_text_layer():
    font = pymupdf.Font(script=pymupdf.UCDN_SCRIPT_BENGALI)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="bn", fontbuffer=font.buffer)
    page.insert_text((50, 50), "বাংলাদেশ ব্যাংক", fontname="bn", fontsize=12)
    for i in range(6):
        page.insert_text((50, 90 + 16 * i), "All scheduled banks shall maintain the cash reserve ratio as set out below.",
                         fontname="helv", fontsize=10)
    assert _route(doc.tobytes()).route == TEXT_LAYER


def test_extraction_never_fills_placeholder_text():
    pages = extraction_service.extract_document_pages(scanned_pdf())
    assert pages[0]["quality_status"] == "PENDING_VISION"
    assert pages[0]["raw_text"] == "" and pages[0]["cleaned_text"] == ""
    assert pages[0]["line_boxes"] is None


# --------------------------------------------------------------------------- vision call (faked)
def _gemini_reply(lines):
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"lines": lines}, ensure_ascii=False)}]},
                            "finishReason": "STOP"}]}
    return httpx.Response(200, json=body)


def _client(replies, seen):
    replies = list(replies)

    def handler(request: httpx.Request):
        seen.append(json.loads(request.content))
        return replies.pop(0)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_vision_call_returns_text_and_boxes():
    seen = []
    lines = [{"text": "বাংলাদেশ ব্যাংক", "box_2d": [40, 300, 70, 700]},
             {"text": "বিআরপিডি সার্কুলার নং-১৫", "box_2d": [90, 100, 120, 600]}]
    async with _client([_gemini_reply(lines)], seen) as client:
        result = await read_page_image(b"png-bytes", api_key="test-key", client=client)
    assert result.success
    assert result.text == "বাংলাদেশ ব্যাংক\nবিআরপিডি সার্কুলার নং-১৫"
    assert result.line_boxes == lines
    request = seen[0]
    assert request["generationConfig"]["responseSchema"]["properties"]["lines"]
    assert request["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert result.model == settings.VISION_MODEL == "gemini-3.5-flash-lite"


async def test_vision_call_retries_429_then_succeeds():
    seen, delays = [], []

    async def fake_sleep(seconds):
        delays.append(seconds)

    replies = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(503),
               _gemini_reply([{"text": "line", "box_2d": [1, 2, 3, 4]}])]
    async with _client(replies, seen) as client:
        result = await read_page_image(b"png", api_key="k", client=client, sleep=fake_sleep)
    assert result.success and result.text == "line"
    assert len(seen) == 3
    assert delays[0] == 7.0 and delays[1] == settings.VISION_RETRY_BASE_SECONDS * 2


async def test_vision_call_failure_and_missing_key():
    seen = []

    async def no_sleep(_):
        pass

    async with _client([httpx.Response(400, text="bad request")], seen) as client:
        result = await read_page_image(b"png", api_key="k", client=client, sleep=no_sleep)
    assert not result.success and "400" in result.error and result.text == ""

    no_key = await read_page_image(b"png", api_key="")
    assert not no_key.success and no_key.no_key


def test_parse_vision_reply_rejects_empty_answers():
    with pytest.raises(ValueError):
        parse_vision_reply({"candidates": [{"content": {"parts": [{"text": '{"lines": []}'}]}}]})
    lines = parse_vision_reply({"candidates": [{"content": {"parts": [
        {"text": '```json\n{"lines": [{"text": "a", "box_2d": [0, 0, 2000, 10]}]}\n```'}]}}]})
    assert lines == [{"text": "a", "box_2d": [0, 0, 1000, 10]}]


def test_render_page_png_is_200_dpi():
    png = render_page_png(english_pdf(), 1)
    pix = pymupdf.Pixmap(png)
    assert pix.width == round(595 * 200 / 72) or abs(pix.width - 1653) <= 2


# --------------------------------------------------------------------------- vision job + storage
async def _ingest(pdf: bytes, **kw):
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc, version, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=pdf, institution_id=inst.id, title=kw.pop("title", f"Reading test {uuid.uuid4().hex[:6]}"),
            publication_date=date(2026, 11, 1), **kw)
        return doc.id, version.id


async def _pages(version_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version_id)
                                 .order_by(DocumentPage.page_number))).scalars().all()


async def test_text_layer_pages_store_line_boxes():
    _doc_id, version_id = await _ingest(english_pdf())
    page = (await _pages(version_id))[0]
    assert page.extraction_method == "TEXT_LAYER" and page.quality_status == "SUCCESS_NATIVE"
    assert page.line_boxes and all(len(line["box_2d"]) == 4 for line in page.line_boxes)


async def test_vision_job_reads_pending_pages_and_stores_boxes():
    _doc_id, version_id = await _ingest(bangla_pdf(pages=2))
    pages = await _pages(version_id)
    assert [p.quality_status for p in pages] == ["PENDING_VISION", "PENDING_VISION"]
    assert all(p.raw_text == "" for p in pages)

    calls = []

    async def reader(png):
        calls.append(png[:8])
        n = len(calls)
        return VisionResult(success=True, text=f"পৃষ্ঠা {n}", line_boxes=[{"text": f"পৃষ্ঠা {n}", "box_2d": [10, 10, 40, 300]}])

    async with AsyncSessionLocal() as db:
        summary = await process_pending_vision_pages(db, reader=reader, version_id=version_id)
    assert summary["read"] == 2 and all(c == b"\x89PNG\r\n\x1a\n" for c in calls)
    pages = await _pages(version_id)
    assert [p.quality_status for p in pages] == ["SUCCESS_VISION", "SUCCESS_VISION"]
    assert [p.extraction_method for p in pages] == ["GEMINI_VISION", "GEMINI_VISION"]
    assert pages[0].raw_text == "পৃষ্ঠা 1" and pages[0].line_boxes == [{"text": "পৃষ্ঠা 1", "box_2d": [10, 10, 40, 300]}]


async def test_vision_job_failure_keeps_page_pending_then_sends_it_to_a_person():
    _doc_id, version_id = await _ingest(bijoy_pdf())

    async def failing(png):
        return VisionResult(success=False, error="HTTP 503")

    for attempt in range(1, settings.VISION_MAX_ATTEMPTS + 1):
        async with AsyncSessionLocal() as db:
            await process_pending_vision_pages(db, reader=failing, version_id=version_id)
        page = (await _pages(version_id))[0]
        assert page.raw_text == "" and page.vision_attempts == attempt and page.vision_error == "HTTP 503"
        expected = "NEEDS_HUMAN_REVIEW" if attempt == settings.VISION_MAX_ATTEMPTS else "PENDING_VISION"
        assert page.quality_status == expected


async def test_vision_job_without_key_leaves_pages_waiting(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    _doc_id, version_id = await _ingest(scanned_pdf())
    async with AsyncSessionLocal() as db:
        summary = await process_pending_vision_pages(db)
    assert summary["waiting_no_key"] >= 1
    page = (await _pages(version_id))[0]
    assert page.quality_status == "PENDING_VISION" and page.vision_attempts == 0 and page.raw_text == ""


async def test_vision_job_never_touches_human_corrected_pages():
    _doc_id, version_id = await _ingest(scanned_pdf())
    async with AsyncSessionLocal() as db:
        page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version_id))).scalars().one()
        page.is_human_corrected = True
        page.human_corrected_text = page.raw_text = "Corrected by hand"
        await db.commit()

    async def reader(png):
        raise AssertionError("must not be called")

    async with AsyncSessionLocal() as db:
        await process_pending_vision_pages(db, reader=reader, version_id=version_id)
    assert (await _pages(version_id))[0].raw_text == "Corrected by hand"


# --------------------------------------------------------------------------- English / Bangla variants
async def test_english_and_bangla_files_with_the_same_reference_are_both_current():
    ref = f"BRPD Circular No. {uuid.uuid4().hex[:5]}"
    base = f"https://www.bb.org.bd/mediaroom/circulars/brpd/var{uuid.uuid4().hex[:6]}"
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc, en, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=english_pdf(), institution_id=inst.id, title="Variant test", publication_date=date(2026, 11, 1),
            reference_number=ref, source_url=f"{base}e.pdf", language="English")
        doc_id, en_id = doc.id, en.id
    async with AsyncSessionLocal() as db:
        doc, bn, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=bangla_pdf(), institution_id=inst.id, title="Variant test", publication_date=date(2026, 11, 1),
            reference_number=ref, source_url=f"{base}b.pdf", language="Bangla")
        assert doc.id == doc_id
        bn_id = bn.id

    async with AsyncSessionLocal() as db:
        versions = {v.id: v for v in (await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc_id))).scalars().all()}
        doc = await db.get(Document, doc_id)
    assert versions[en_id].language == "en" and versions[en_id].status == "CURRENT"
    assert versions[bn_id].language == "bn" and versions[bn_id].status == "CURRENT"
    assert doc.current_version_id == en_id  # the English text layer stays the main version

    # A replaced English file supersedes only the old English file.
    async with AsyncSessionLocal() as db:
        _doc, en2, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=english_pdf(), institution_id=inst.id, title="Variant test", publication_date=date(2026, 11, 1),
            reference_number=ref, source_url=f"{base}e.pdf", language="English")
        en2_id = en2.id
    async with AsyncSessionLocal() as db:
        status = {v.id: v.status for v in (await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc_id))).scalars().all()}
        doc = await db.get(Document, doc_id)
    assert status == {en_id: "SUPERSEDED", bn_id: "CURRENT", en2_id: "CURRENT"}
    assert doc.current_version_id == en2_id


async def test_language_is_worked_out_from_the_pages_without_a_hint():
    _doc_id, version_id = await _ingest(bangla_pdf(), reference_number=f"X-{uuid.uuid4().hex[:5]}")
    async with AsyncSessionLocal() as db:
        assert (await db.get(DocumentVersion, version_id)).language == "bn"


async def test_recheck_checks_both_language_variants_and_supersedes_within_one():
    ref = f"FEPD Circular No. {uuid.uuid4().hex[:5]}"
    base = f"https://www.bb.org.bd/mediaroom/circulars/fepd/rv{uuid.uuid4().hex[:6]}"
    en_url, bn_url = f"{base}e.pdf", f"{base}b.pdf"
    inst = await make_institution()
    ids = {}
    for url, pdf, lang in ((en_url, english_pdf(), "English"), (bn_url, bangla_pdf(), "Bangla")):
        async with AsyncSessionLocal() as db:
            doc, v, _ = await document_ingestion_service.ingest_document(
                db=db, pdf_bytes=pdf, institution_id=inst.id, title="Recheck variants", publication_date=date(2026, 11, 2),
                reference_number=ref, source_url=url, etag='"v1"', last_modified="Mon, 02 Nov 2026 10:00:00 GMT",
                language=lang)
            ids[lang], doc_id = v.id, doc.id

    new_bn = bangla_pdf()

    class Site:
        heads = []

        async def head_document(self, url):
            self.heads.append(url)
            if url == bn_url:
                return FetchedFile(url=url, etag='"v2"', last_modified="Tue, 10 Nov 2026 10:00:00 GMT")
            if url == en_url:
                return FetchedFile(url=url, etag='"v1"', last_modified="Mon, 02 Nov 2026 10:00:00 GMT")
            return FetchedFile(url=url, challenge=AntiBotChallenge(
                is_blocked=False, challenge_type="HTTP_ERROR", status_code=404, details="not found"))

        async def fetch_document(self, url):
            assert url == bn_url
            return FetchedFile(url=url, content=new_bn, etag='"v2"', last_modified="Tue, 10 Nov 2026 10:00:00 GMT")

    site = Site()
    async with AsyncSessionLocal() as db:
        await source_monitoring_service.recheck_archive(db, connector=site)
    assert en_url in site.heads and bn_url in site.heads

    async with AsyncSessionLocal() as db:
        versions = (await db.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
                                     .order_by(DocumentVersion.version_number))).scalars().all()
    by_id = {v.id: v for v in versions}
    assert by_id[ids["English"]].status == "CURRENT"
    assert by_id[ids["Bangla"]].status == "SUPERSEDED"
    newest = versions[-1]
    assert newest.language == "bn" and newest.status == "CURRENT" and newest.etag == '"v2"'
