"""Loads hand-made page readings of the Bangla archive into the matching documents.

The Bangla-only archive PDFs (research/archive/data/pdfs/) are read by a person through the
Gemini app with the prompt in research/archive/READING_PROMPT.md. Each answer is saved as a
.txt file with the same name as its PDF, with a `=== PAGE n ===` line before every page.

    python -m backend.scripts.import_manual_reading <txt folder> [--dry-run]
    python -m backend.scripts.import_manual_reading --sample 10

For every .txt file:
- the PDF with the same name is found in --pdf-dir and its pages counted; a different page
  count is reported and the file is not imported;
- the document is found by the PDF's SHA-256, or by its source URL from downloads.json;
  if there is none yet, the PDF is ingested first (shared library);
- each page gets the text, method MANUAL_SUBSCRIPTION_READING, status SUCCESS_VISION_MANUAL.
  Pages a person corrected in the app are never overwritten. Running it again changes nothing.
"""
import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf as fitz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.extraction.service import METHOD_MANUAL, STATUS_VISION_MANUAL
from backend.app.modules.institutions.models import Institution, InstitutionDepartment
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector

REPO = Path(__file__).resolve().parents[2]
ARCHIVE_DATA = REPO / "research" / "archive" / "data"
DEFAULT_PDF_DIR = ARCHIVE_DATA / "pdfs"
DEFAULT_DOWNLOADS = ARCHIVE_DATA / "downloads.json"
DEFAULT_INDEX = ARCHIVE_DATA / "index.json"

PAGE_MARKER = re.compile(r"^[ \t]*=+[ \t]*PAGE[ \t]+([0-9০-৯]+)[ \t]*=+[ \t]*$", re.IGNORECASE | re.MULTILINE)
CODE_FENCE = re.compile(r"^[ \t]*```[a-zA-Z]*[ \t]*$", re.MULTILINE)
BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


class ReadingFormatError(ValueError):
    pass


def parse_reading(text: str) -> List[str]:
    """Splits a reading into pages. Returns the page texts in order (page 1 first)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    text = CODE_FENCE.sub("", text)
    markers = list(PAGE_MARKER.finditer(text))
    if not markers:
        raise ReadingFormatError("no '=== PAGE n ===' lines found")
    if text[:markers[0].start()].strip():
        raise ReadingFormatError("text before the first '=== PAGE 1 ===' line")
    numbers = [int(m.group(1).translate(BANGLA_DIGITS)) for m in markers]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ReadingFormatError(f"page markers are not 1, 2, 3 ... in order: {numbers}")
    pages = []
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        pages.append(text[m.end():end].strip("\n").rstrip())
    return pages


@dataclass
class ImportReport:
    imported_files: List[str] = field(default_factory=list)
    unchanged_files: List[str] = field(default_factory=list)
    ingested_files: List[str] = field(default_factory=list)
    page_mismatches: List[Tuple[str, int, int]] = field(default_factory=list)  # (file, txt pages, pdf pages)
    format_errors: List[Tuple[str, str]] = field(default_factory=list)
    missing_pdfs: List[str] = field(default_factory=list)
    unmatched: List[Tuple[str, str]] = field(default_factory=list)
    pages_written: int = 0
    pages_unchanged: int = 0
    pages_kept_human: int = 0

    def lines(self, dry_run: bool) -> List[str]:
        verb = "would import" if dry_run else "imported"
        out = [
            f"{verb}: {len(self.imported_files)} files, {self.pages_written} pages"
            + (f" ({len(self.ingested_files)} PDFs {'would be' if dry_run else 'were'} ingested first)" if self.ingested_files else ""),
            f"already up to date: {len(self.unchanged_files)} files, {self.pages_unchanged} pages",
            f"pages kept because a person corrected them: {self.pages_kept_human}",
        ]
        for name, txt_pages, pdf_pages in self.page_mismatches:
            out.append(f"PAGE COUNT MISMATCH, not imported: {name} has {txt_pages} pages, the PDF has {pdf_pages}")
        for name, why in self.format_errors:
            out.append(f"FORMAT PROBLEM, not imported: {name}: {why}")
        for name in self.missing_pdfs:
            out.append(f"NO PDF with this name, not imported: {name}")
        for name, why in self.unmatched:
            out.append(f"NOT MATCHED, not imported: {name}: {why}")
        return out


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else default


def _parse_listing_date(raw: Optional[str]) -> Optional[date]:
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def _date_from_filename(name: str) -> Optional[date]:
    m = re.match(r"(\d{4}-\d{2}-\d{2})_", name)
    return _parse_listing_date(m.group(1)) if m else None


async def _find_version(db: AsyncSession, sha: str, url: Optional[str]) -> Tuple[Optional[DocumentVersion], str]:
    version = (await db.execute(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentVersion.file_sha256 == sha, Document.owner_user_id.is_(None))
        .order_by(DocumentVersion.created_at)
        .limit(1)
    )).scalars().first()
    if version is not None:
        return version, "sha256"
    if url:
        version = (await db.execute(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.owner_user_id.is_(None),
                or_(DocumentVersion.source_url == url,
                    (DocumentVersion.source_url.is_(None)) & (Document.source_url == url)),
            )
            .order_by((DocumentVersion.status == "CURRENT").desc(), DocumentVersion.version_number.desc())
            .limit(1)
        )).scalars().first()
        if version is not None:
            return version, "source_url"
    return None, ""


async def _ingest_archive_pdf(db: AsyncSession, pdf_bytes: bytes, pdf_name: str, url: Optional[str],
                              listing: Dict, download: Dict) -> DocumentVersion:
    bb = (await db.execute(select(Institution).where(Institution.code == "BB"))).scalars().first()
    if bb is None:
        raise LookupError("Institution 'BB' (Bangladesh Bank) is not in the database; run the seed first.")
    title = listing.get("title") or Path(pdf_name).stem
    ref_match = BangladeshBankConnector._REF.search(title)
    ref_no = ref_match.group(1).strip() if ref_match else None
    dept_code = BangladeshBankConnector.infer_department_code(title, ref_no, url or "")
    dept_id = None
    if dept_code:
        dept_id = (await db.execute(select(InstitutionDepartment.id).where(
            InstitutionDepartment.institution_id == bb.id, InstitutionDepartment.code == dept_code
        ))).scalars().first()
    pub_date = _parse_listing_date(listing.get("date")) or _date_from_filename(pdf_name) or date.today()
    _doc, version, _pages = await document_ingestion_service.ingest_document(
        db=db,
        pdf_bytes=pdf_bytes,
        institution_id=bb.id,
        department_id=dept_id,
        reference_number=ref_no,
        title=title,
        publication_date=pub_date,
        document_type=BangladeshBankConnector.infer_publication_type(title, ref_no),
        source_url=url,
        etag=download.get("etag"),
        last_modified=download.get("last_modified"),
        owner_user_id=None,
        language="bn",
    )
    return version


async def import_folder(
    db: AsyncSession,
    txt_dir: Path,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    downloads_path: Path = DEFAULT_DOWNLOADS,
    index_path: Path = DEFAULT_INDEX,
    dry_run: bool = False,
) -> ImportReport:
    report = ImportReport()
    downloads = load_json(downloads_path, {})
    url_by_file = {v.get("file"): url for url, v in downloads.items() if isinstance(v, dict) and v.get("file")}
    download_by_url = {url: v for url, v in downloads.items() if isinstance(v, dict)}
    listing_by_url = {item.get("pdf"): item for item in load_json(index_path, []) if isinstance(item, dict)}

    for txt_path in sorted(Path(txt_dir).glob("*.txt")):
        pdf_name = f"{txt_path.stem}.pdf"
        pdf_path = Path(pdf_dir) / pdf_name
        if not pdf_path.exists():
            report.missing_pdfs.append(txt_path.name)
            continue
        try:
            pages = parse_reading(txt_path.read_text(encoding="utf-8-sig"))
        except (ReadingFormatError, UnicodeDecodeError) as e:
            report.format_errors.append((txt_path.name, str(e)))
            continue

        pdf_bytes = pdf_path.read_bytes()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            pdf_pages = doc.page_count
        if len(pages) != pdf_pages:
            report.page_mismatches.append((txt_path.name, len(pages), pdf_pages))
            continue

        sha = hashlib.sha256(pdf_bytes).hexdigest()
        url = url_by_file.get(pdf_name)
        version, matched_by = await _find_version(db, sha, url)
        if version is not None and matched_by == "source_url" and version.page_count != pdf_pages:
            report.unmatched.append((txt_path.name, f"stored file for {url} has {version.page_count} pages, not {pdf_pages}"))
            continue

        if version is None:
            report.ingested_files.append(pdf_name)
            if dry_run:
                report.imported_files.append(txt_path.name)
                report.pages_written += len(pages)
                continue
            version = await _ingest_archive_pdf(db, pdf_bytes, pdf_name, url, listing_by_url.get(url, {}),
                                                download_by_url.get(url, {}))

        existing = {
            p.page_number: p for p in (await db.execute(
                select(DocumentPage).where(DocumentPage.document_version_id == version.id)
            )).scalars().all()
        }
        written = 0
        for number, text in enumerate(pages, start=1):
            page = existing.get(number)
            if page is not None and page.is_human_corrected:
                report.pages_kept_human += 1
                continue
            if (page is not None and page.extraction_method == METHOD_MANUAL
                    and page.quality_status == STATUS_VISION_MANUAL and page.raw_text == text):
                report.pages_unchanged += 1
                continue
            written += 1
            if dry_run:
                continue
            if page is None:
                page = DocumentPage(document_version_id=version.id, page_number=number,
                                    has_tables=False, extracted_tables=[], layout_hierarchy={},
                                    is_human_corrected=False)
                db.add(page)
            page.raw_text = text
            page.cleaned_text = text
            page.extraction_method = METHOD_MANUAL
            page.quality_status = STATUS_VISION_MANUAL
            page.quality_score = 1.0
            page.line_boxes = None  # the app reading gives no line positions
            page.has_tables = " | " in text
            page.vision_error = None

        if not dry_run:
            version.language = "bn"
            version.page_count = max(version.page_count or 0, pdf_pages)
            await db.commit()
        report.pages_written += written
        (report.imported_files if written else report.unchanged_files).append(txt_path.name)
    return report


async def sample_pages(db: AsyncSession, n: int, downloads_path: Path = DEFAULT_DOWNLOADS,
                       seed: Optional[int] = None) -> List[Dict]:
    """N random hand-read pages with the PDF file and page number to check them against."""
    file_by_sha = {v.get("sha256"): v.get("file") for v in load_json(downloads_path, {}).values()
                   if isinstance(v, dict) and v.get("sha256")}
    rows = (await db.execute(
        select(DocumentPage.page_number, DocumentPage.raw_text, DocumentVersion.file_sha256,
               DocumentVersion.storage_path, Document.title)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentPage.extraction_method == METHOD_MANUAL, DocumentPage.is_human_corrected.is_(False))
    )).all()
    picked = random.Random(seed).sample(list(rows), min(n, len(rows)))
    return [{
        "pdf": file_by_sha.get(sha) or storage_path,
        "page": page_number,
        "title": title,
        "text": text,
    } for page_number, text, sha, storage_path, title in picked]


async def _main(args) -> int:
    from backend.app.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if args.folder:
            report = await import_folder(db, Path(args.folder), Path(args.pdf_dir), Path(args.downloads),
                                         Path(args.index), dry_run=args.dry_run)
            for line in report.lines(args.dry_run):
                print(line)
        if args.sample:
            samples = await sample_pages(db, args.sample, Path(args.downloads), seed=args.seed)
            if not samples:
                print("No hand-read pages imported yet.")
            for s in samples:
                print(f"\n----- {s['pdf']}  page {s['page']}  ({s['title'][:80]})")
                print(s["text"])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", help="folder of .txt readings named like the PDFs")
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--downloads", default=str(DEFAULT_DOWNLOADS), help="downloads.json from fetch_archive.py")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="index.json from fetch_archive.py (titles, dates)")
    parser.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    parser.add_argument("--sample", type=int, default=0, help="print N random imported pages to check by eye")
    parser.add_argument("--seed", type=int, default=None, help="random seed for --sample")
    args = parser.parse_args(argv)
    if not args.folder and not args.sample:
        parser.error("give a folder of .txt files, --sample N, or both")
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
