"""Manual archive import: .txt readings made in the Gemini app, loaded into the documents' pages."""
import hashlib
import json
import uuid
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.scripts.import_manual_reading import ReadingFormatError, import_folder, parse_reading, sample_pages


def _pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for n in range(pages):
        doc.new_page().insert_text((72, 72), f"Archive page {n + 1} {uuid.uuid4().hex}")
    data = doc.tobytes()
    doc.close()
    return data


def _reading(*pages: str) -> str:
    return "".join(f"=== PAGE {n} ===\n{text}\n" for n, text in enumerate(pages, start=1))


@pytest.fixture
def archive(tmp_path):
    """A small archive folder: pdfs/, readings/, downloads.json and index.json like fetch_archive.py writes."""
    pdf_dir, txt_dir = tmp_path / "pdfs", tmp_path / "readings"
    pdf_dir.mkdir()
    txt_dir.mkdir()
    downloads, index = {}, []

    def add(stem: str, pages: int, reading: str = None):
        pdf = _pdf(pages)
        (pdf_dir / f"{stem}.pdf").write_bytes(pdf)
        url = f"https://www.bb.org.bd/mediaroom/circulars/brpd/{stem}.pdf"
        downloads[url] = {"status": "ok", "file": f"{stem}.pdf", "bytes": len(pdf),
                          "sha256": hashlib.sha256(pdf).hexdigest(), "etag": '"e1"',
                          "last_modified": "Sun, 04 Jan 2026 09:00:00 GMT"}
        index.append({"date": "04/01/26", "title": f"BRPD Circular No. {stem[-4:]}: আমানত", "lang": "bn",
                      "pdf": url, "bangla_only": True})
        (tmp_path / "downloads.json").write_text(json.dumps(downloads), encoding="utf-8")
        (tmp_path / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        if reading is not None:
            (txt_dir / f"{stem}.txt").write_text(reading, encoding="utf-8")
        return pdf, url

    def run(dry_run=False):
        async def go():
            async with AsyncSessionLocal() as db:
                return await import_folder(db, txt_dir, pdf_dir, tmp_path / "downloads.json",
                                           tmp_path / "index.json", dry_run=dry_run)
        return go()

    return type("Archive", (), {"add": staticmethod(add), "run": staticmethod(run), "txt_dir": txt_dir,
                                "downloads": tmp_path / "downloads.json"})


async def _pages_for(pdf: bytes):
    sha = hashlib.sha256(pdf).hexdigest()
    async with AsyncSessionLocal() as db:
        version = (await db.execute(select(DocumentVersion).where(DocumentVersion.file_sha256 == sha))).scalars().first()
        if version is None:
            return None, []
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version.id)
                                  .order_by(DocumentPage.page_number))).scalars().all()
        return version, pages


def test_parse_reading():
    assert parse_reading("=== PAGE 1 ===\nক\nখ\n=== PAGE 2 ===\n\nগ | ঘ\n") == ["ক\nখ", "গ | ঘ"]
    assert parse_reading("```\n=== PAGE ১ ===\nক\n```") == ["ক"]
    with pytest.raises(ReadingFormatError):
        parse_reading("no markers here")
    with pytest.raises(ReadingFormatError):
        parse_reading("=== PAGE 1 ===\na\n=== PAGE 3 ===\nb")
    with pytest.raises(ReadingFormatError):
        parse_reading("Here is the transcription:\n=== PAGE 1 ===\na")


async def test_good_file_is_imported_into_a_new_shared_document(archive):
    stem = f"2026-01-04_jan042026brpd{uuid.uuid4().hex[:4]}"
    pdf, url = archive.add(stem, 2, _reading("বাংলাদেশ ব্যাংক\nসার্কুলার নং ০৭", "ক্রমিক | হার\n১ | ২.৫%"))
    report = await archive.run()
    assert report.imported_files == [f"{stem}.txt"] and report.ingested_files == [f"{stem}.pdf"]
    assert report.pages_written == 2

    version, pages = await _pages_for(pdf)
    assert version.language == "bn" and version.source_url == url and version.etag == '"e1"'
    assert [p.raw_text for p in pages] == ["বাংলাদেশ ব্যাংক\nসার্কুলার নং ০৭", "ক্রমিক | হার\n১ | ২.৫%"]
    assert {p.extraction_method for p in pages} == {"MANUAL_SUBSCRIPTION_READING"}
    assert {p.quality_status for p in pages} == {"SUCCESS_VISION_MANUAL"}
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, version.document_id)
    assert doc.owner_user_id is None and doc.publication_date.isoformat() == "2026-01-04"


async def test_page_count_mismatch_is_reported_not_imported(archive):
    stem = f"2026-01-05_mismatch{uuid.uuid4().hex[:4]}"
    pdf, _ = archive.add(stem, 2, _reading("only one page"))
    report = await archive.run()
    assert report.page_mismatches == [(f"{stem}.txt", 1, 2)]
    assert report.imported_files == []
    version, _ = await _pages_for(pdf)
    assert version is None  # nothing was ingested


async def test_dry_run_changes_nothing(archive):
    stem = f"2026-01-06_dry{uuid.uuid4().hex[:4]}"
    pdf, _ = archive.add(stem, 1, _reading("শুধু দেখা"))
    async with AsyncSessionLocal() as db:
        before = (await db.execute(select(func.count()).select_from(DocumentVersion))).scalar()
    report = await archive.run(dry_run=True)
    assert report.imported_files == [f"{stem}.txt"] and report.pages_written == 1
    assert "would import" in report.lines(dry_run=True)[0]
    async with AsyncSessionLocal() as db:
        after = (await db.execute(select(func.count()).select_from(DocumentVersion))).scalar()
    assert before == after
    assert (await _pages_for(pdf))[0] is None


async def test_import_is_idempotent_and_keeps_human_corrections(archive):
    stem = f"2026-01-07_idem{uuid.uuid4().hex[:4]}"
    pdf, _ = archive.add(stem, 2, _reading("প্রথম পৃষ্ঠা", "দ্বিতীয় পৃষ্ঠা"))
    await archive.run()

    again = await archive.run()
    assert again.imported_files == [] and again.unchanged_files == [f"{stem}.txt"]
    assert again.pages_written == 0 and again.pages_unchanged == 2

    # A person corrects page 1 in the app; a new reading of both pages comes in.
    version, pages = await _pages_for(pdf)
    async with AsyncSessionLocal() as db:
        page1 = await db.get(DocumentPage, pages[0].id)
        page1.is_human_corrected = True
        page1.human_corrected_text = page1.raw_text = "হাতে ঠিক করা"
        await db.commit()
    (archive.txt_dir / f"{stem}.txt").write_text(_reading("নতুন প্রথম", "নতুন দ্বিতীয়"), encoding="utf-8")

    report = await archive.run()
    assert report.pages_kept_human == 1 and report.pages_written == 1
    _, pages = await _pages_for(pdf)
    assert pages[0].raw_text == "হাতে ঠিক করা" and pages[0].is_human_corrected
    assert pages[1].raw_text == "নতুন দ্বিতীয়"


async def test_existing_document_is_matched_by_sha256_not_duplicated(archive):
    from datetime import date
    from backend.app.modules.documents.service import document_ingestion_service
    from backend.app.tests.factories import make_institution

    stem = f"2026-01-08_known{uuid.uuid4().hex[:4]}"
    pdf, url = archive.add(stem, 1, _reading("আগে থেকে আছে"))
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        _doc, version, _ = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=pdf, institution_id=inst.id, title="Known", publication_date=date(2026, 1, 8), source_url=url)
        version_id = version.id

    report = await archive.run()
    assert report.ingested_files == [] and report.pages_written == 1
    async with AsyncSessionLocal() as db:
        page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version_id))).scalars().one()
    assert page.raw_text == "আগে থেকে আছে" and page.quality_status == "SUCCESS_VISION_MANUAL"


async def test_sample_prints_pdf_file_and_page_number(archive):
    stem = f"2026-01-09_sample{uuid.uuid4().hex[:4]}"
    archive.add(stem, 2, _reading("নমুনা ১", "নমুনা ২"))
    await archive.run()
    async with AsyncSessionLocal() as db:
        samples = await sample_pages(db, 1000, archive.downloads, seed=1)
    mine = [s for s in samples if s["pdf"] == f"{stem}.pdf"]
    assert sorted((s["page"], s["text"]) for s in mine) == [(1, "নমুনা ১"), (2, "নমুনা ২")]
