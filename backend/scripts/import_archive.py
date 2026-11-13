"""Load the downloaded Bangladesh Bank archive (research/archive/data) into the shared library.

Reads data/index.json and data/state.jsonl written by research/archive/fetch_all.py and sends each
saved PDF through the same ingest code as uploads (SHA-256 archive, versions, duplicate checks,
page reading). English pages are read from the text layer; Bangla, legacy-font and scanned pages are
queued as PENDING_VISION. No analysis is run and no alerts are written.

By default it works on a SEPARATE database and storage folder (research/archive/data/import_test),
never the developer database. To load the real app database, pass --app-db (uses .env as the app does).

Usage (from the repo root, with the repo .venv):
    .venv/Scripts/python.exe backend/scripts/import_archive.py --limit 50
    .venv/Scripts/python.exe backend/scripts/import_archive.py --spot-check 10
    .venv/Scripts/python.exe backend/scripts/import_archive.py --app-db        # the real import
Safe to stop and re-run: finished files are skipped.
"""
import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "research" / "archive" / "data"
TEST_DIR = ARCHIVE / "import_test"

parser = argparse.ArgumentParser()
parser.add_argument("--app-db", action="store_true", help="use the database and storage from .env (the real app)")
parser.add_argument("--limit", type=int, default=0, help="import at most this many files this run")
parser.add_argument("--spot-check", type=int, default=0, help="print N random imported circulars and exit")
parser.add_argument("--summary", action="store_true", help="print counts and exit")
args = parser.parse_args()

# The settings are read when the backend is first imported, so choose the database before that.
if not args.app_db:
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DIR / 'regwatch_import.db').as_posix()}"
    os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'regwatch_import.db').as_posix()}"
    os.environ["STORAGE_LOCAL_ROOT"] = str(TEST_DIR / "storage")
os.environ["GEMINI_API_KEY"] = ""  # never call a model from this script
os.environ["VISION_WORKER_ENABLED"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

import backend.app.database.models  # noqa: E402,F401  (registers every table)
from backend.app.database.base import Base  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, sync_engine  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion  # noqa: E402
from backend.app.modules.documents.service import document_ingestion_service  # noqa: E402
from backend.app.modules.extraction.service import STATUS_PENDING_VISION  # noqa: E402
from backend.app.modules.institutions.models import Institution, InstitutionDepartment  # noqa: E402
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector  # noqa: E402

IMPORT_LOG = ARCHIVE / "import_state.jsonl" if args.app_db else TEST_DIR / "import_state.jsonl"
PDFS = ARCHIVE / "pdfs"


def load_jsonl_latest(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out[r["url"]] = r
    return out


def log_import(rec):
    with IMPORT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def department_code(item):
    code = re.sub(r"-\d+$", "", (item.get("department") or "").strip().upper())
    if not code or code == "CIRCULAR":
        code = BangladeshBankConnector.infer_department_code(item["title"], None, item["url"]) or ""
    return code or None


def reference_number(item):
    """Official reference plus the year. Many departments restart numbering every year
    ('BRPD Circular No. 05' exists in every year), and the ingest code treats one reference
    number as one document, so the plain reference would merge different circulars."""
    ref = item["title"].split(":")[0].strip()
    year = (item["date"] or "")[:4]
    return f"{ref}/{year}" if year else ref


async def ensure_institution(db):
    bb = (await db.execute(select(Institution).where(Institution.code == "BB"))).scalar_one_or_none()
    if bb is None:
        bb = Institution(code="BB", name="Bangladesh Bank", name_bn="বাংলাদেশ ব্যাংক",
                         website_url="https://www.bb.org.bd", is_active=True)
        db.add(bb)
        await db.flush()
    return bb


async def ensure_departments(db, bb, codes):
    have = {d.code: d.id for d in (await db.execute(
        select(InstitutionDepartment).where(InstitutionDepartment.institution_id == bb.id))).scalars()}
    for code in sorted(c for c in codes if c and c not in have):
        d = InstitutionDepartment(institution_id=bb.id, code=code, name=code)
        db.add(d)
        await db.flush()
        have[code] = d.id
    await db.commit()
    return have


def downloaded_items():
    index = json.loads((ARCHIVE / "index.json").read_text(encoding="utf-8"))["pdfs"]
    state = load_jsonl_latest(ARCHIVE / "state.jsonl")
    items = []
    for it in index:
        rec = state.get(it["url"])
        if rec and rec["status"] == "ok" and (PDFS / rec["file"]).exists():
            items.append({**it, **{k: rec[k] for k in ("file", "sha256", "etag", "last_modified", "at")}})
    # one circular at a time, English first so it stays the main version
    items.sort(key=lambda i: (i["circular_id"], i["lang"] != "en"))
    return items, len(index)


async def run_import():
    items, total = downloaded_items()
    done = load_jsonl_latest(IMPORT_LOG)
    todo = [i for i in items if done.get(i["url"], {}).get("status") not in ("imported", "duplicate")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(items)} files downloaded of {total} in the index; {len(todo)} to import now", flush=True)
    counts = {"imported": 0, "duplicate": 0, "failed": 0}
    async with AsyncSessionLocal() as db:
        bb = await ensure_institution(db)
        await db.commit()
        depts = await ensure_departments(db, bb, {department_code(i) for i in items})
        group_doc = {}   # circular_id -> document id, so the Bangla file joins the English one
        used_refs = {}   # reference number -> circular_id, to keep different circulars apart
        for prev in done.values():
            if prev.get("document_id"):
                group_doc[prev["circular_id"]] = prev["document_id"]
        for n, item in enumerate(todo, 1):
            try:
                pdf = (PDFS / item["file"]).read_bytes()
                existing = (await db.execute(
                    select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id)
                    .where(DocumentVersion.file_sha256 == item["sha256"], Document.owner_user_id.is_(None)).limit(1)
                )).scalars().first()
                if existing is not None:
                    log_import({"url": item["url"], "circular_id": item["circular_id"], "status": "duplicate",
                                "document_id": str(existing.document_id)})
                    group_doc.setdefault(item["circular_id"], str(existing.document_id))
                    counts["duplicate"] += 1
                    continue
                ref = reference_number(item)
                target = group_doc.get(item["circular_id"])
                if target is None:
                    owner = used_refs.setdefault(ref, item["circular_id"])
                    if owner != item["circular_id"]:
                        ref = f"{ref} dated {item['date']}"
                    used_refs[ref] = item["circular_id"]
                title = item["title"]
                doc, version, pages = await document_ingestion_service.ingest_document(
                    db=db, pdf_bytes=pdf, institution_id=bb.id,
                    department_id=depts.get(department_code(item)),
                    reference_number=ref, title=title,
                    publication_date=date.fromisoformat(item["date"]),
                    source_url=item["url"],
                    document_type=BangladeshBankConnector.infer_publication_type(title, None),
                    language="English" if item["lang"] == "en" else "Bangla",
                    etag=item.get("etag"), last_modified=item.get("last_modified"),
                    target_document_id=None if target is None else __import__("uuid").UUID(target),
                )
                group_doc[item["circular_id"]] = str(doc.id)
                log_import({"url": item["url"], "circular_id": item["circular_id"], "status": "imported",
                            "document_id": str(doc.id), "pages": pages})
                counts["imported"] += 1
            except Exception as e:  # keep going; the file stays listed as failed
                await db.rollback()
                log_import({"url": item["url"], "circular_id": item["circular_id"], "status": "failed",
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})
                counts["failed"] += 1
            if n % 25 == 0:
                print(f"  {n}/{len(todo)} {counts}", flush=True)
    print(f"import finished: {counts}")


async def summary():
    async with AsyncSessionLocal() as db:
        docs = (await db.execute(select(func.count()).select_from(Document).where(Document.owner_user_id.is_(None)))).scalar()
        vers = (await db.execute(select(func.count()).select_from(DocumentVersion))).scalar()
        pages = (await db.execute(select(func.count()).select_from(DocumentPage))).scalar()
        wait = (await db.execute(select(func.count()).select_from(DocumentPage)
                                 .where(DocumentPage.quality_status == STATUS_PENDING_VISION))).scalar()
        langs = (await db.execute(select(DocumentVersion.language, func.count()).group_by(DocumentVersion.language))).all()
    items, total = downloaded_items()
    log = load_jsonl_latest(IMPORT_LOG)
    by = {}
    for r in log.values():
        by[r["status"]] = by.get(r["status"], 0) + 1
    print(f"downloaded files: {len(items)} of {total} in index; import log: {by}")
    print(f"database: {docs} circulars (documents), {vers} files (versions) {dict(langs)}, "
          f"{pages} pages, {wait} pages waiting for vision reading")
    return docs, vers


async def spot_check(n):
    index = {i["url"]: i for i in json.loads((ARCHIVE / "index.json").read_text(encoding="utf-8"))["pdfs"]}
    async with AsyncSessionLocal() as db:
        versions = (await db.execute(select(DocumentVersion).where(DocumentVersion.source_url.is_not(None)))).scalars().all()
        random.Random(20261113).shuffle(versions)
        for v in versions[:n]:
            doc = await db.get(Document, v.document_id)
            page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == v.id)
                                     .order_by(DocumentPage.page_number).limit(1))).scalars().first()
            idx = index.get(v.source_url)
            ok_title = idx is not None and idx["title"] == doc.title
            ok_date = idx is not None and idx["date"] == str(doc.publication_date)
            text = re.sub(r"\s+", " ", (page.cleaned_text or page.raw_text or "") if page else "")[:140]
            print(f"- {doc.reference_number} | {doc.publication_date} | {v.language} | {v.page_count} pages | "
                  f"title match {ok_title}, date match {ok_date}\n  {doc.title[:110]}\n  page 1 ({page.quality_status if page else '-'}): {text!r}")


async def main():
    if not args.app_db:
        Base.metadata.create_all(bind=sync_engine)
    if args.spot_check:
        await spot_check(args.spot_check)
    elif args.summary:
        await summary()
    else:
        await run_import()
        await summary()


asyncio.run(main())
