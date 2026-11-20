"""Clears out the old "needs a person" page status (NEEDS_HUMAN_REVIEW): no page is left for a person.

Pages are sent back for page-image reading (NEEDS_HUMAN_REVIEW -> PENDING_VISION):

1. "key" pages: image reading failed only because the reading key no longer worked (its project was
   deleted or suspended, or the key was invalid). That is not the page's fault. Their text is empty, so
   filling them in never changes the sentence IDs of any other page (IDs are per page: p5.s3), and they
   are sent back even when the circular was already analysed or handed out for analysis.
2. "damaged" pages: the PDF's own text layer holds broken characters or runs of odd symbols (legacy
   font, broken encoding) and the page went straight to a person without its image ever being read. New uploads now read
   such pages from the image (extraction/service.py). Their text gets replaced, which changes that
   page's sentence IDs, so they are sent back only when the circular has no analysis yet and was not
   handed out for analysis (the local manual-analysis folders and, with --repo, the shared work repo),
   or when it was handed out but not analysed yet and is listed in REDO.txt (manual_analysis.py mark-redo).
3. "failed" pages: image reading really failed on them. Their text is empty, so they go straight to the
   reader's stronger route (bigger model, sharper image); if that fails too they end as READ_FAILED.

Pages that are only short keep their text and count as read (SUCCESS_NATIVE). Damaged pages of a
circular already analysed in the app keep the old status until the user decides to redo it
(manual_analysis.py mark-redo --approved), and pages
a person corrected are never touched.
Nothing is changed without --yes; with --yes a copy of the database is saved first (data/regwatch.before-requeue-<time>.db).

    .venv\\Scripts\\python.exe backend\\scripts\\requeue_pages.py                 # what would change
    .venv\\Scripts\\python.exe backend\\scripts\\requeue_pages.py --repo F:\\side-income\\regwatch-analysis-work
    .venv\\Scripts\\python.exe backend\\scripts\\requeue_pages.py --repo ... --yes   # change it
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.modules.extraction.quality import ExtractionQualityAssessor, text_layer_looks_damaged  # noqa: E402
from backend.app.modules.extraction.vision import is_dead_key_reply  # noqa: E402
from backend.app.core.config import settings  # noqa: E402

WORK = ROOT / "research" / "archive" / "data" / "manual_analysis"
LOCAL_FOLDERS = (WORK / "inbox", WORK / "answers", WORK / "done")
REDO = WORK / "REDO.txt"
REPO_FOLDERS = ("inbox", "inbox_long", "answers")

PENDING, REVIEW, NATIVE = "PENDING_VISION", "NEEDS_HUMAN_REVIEW", "SUCCESS_NATIVE"
TEXT_LAYER, VISION = "TEXT_LAYER", "GEMINI_VISION"


def default_db() -> Path:
    from backend.app.core.config import settings

    path = settings.SYNC_DATABASE_URL.split("///", 1)[1]
    return Path(path) if os.path.isabs(path) else (ROOT / path).resolve()


def _key(doc_id) -> str:
    """The file name the manual analysis uses for a circular (its id as a dashed UUID)."""
    try:
        return str(UUID(str(doc_id).replace("-", "")))
    except ValueError:
        return str(doc_id)


def redo_keys(path: Path = REDO, approved_only: bool = False) -> Set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, reason = line.partition("|")
        if key.strip() and (not approved_only or reason.strip().lower().startswith("approved")):
            out.add(key.strip())
    return out


def handed_out(folders: Iterable[Path]) -> Set[str]:
    """Circulars already written out for analysis (inbox) or answered."""
    keys: Set[str] = set()
    for folder in folders:
        if folder.is_dir():
            keys |= {p.stem for p in folder.iterdir() if p.suffix in (".txt", ".json")}
    return keys


def error_is_dead_key(error: Optional[str]) -> bool:
    """A stored error like 'HTTP 403: {...}' that blames the key, or the new plain wording."""
    error = error or ""
    if "reading key no longer works" in error:
        return True
    if not error.startswith("HTTP "):
        return False
    try:
        code = int(error[5:8])
    except ValueError:
        return False
    return is_dead_key_reply(code, error)


def plan(conn: sqlite3.Connection, done_keys: Set[str], redo: Optional[Set[str]] = None,
         approved: Optional[Set[str]] = None) -> Dict[str, List[tuple]]:
    redo = redo or set()
    approved = approved or set()
    rows = conn.execute(
        """
        select p.id, p.extraction_method, coalesce(p.vision_attempts, 0), p.vision_error, d.id, d.title, p.raw_text,
               (select count(*) from document_analyses a where a.document_version_id = v.id) as analyses
        from document_pages p
        join document_versions v on v.id = p.document_version_id
        join documents d on d.id = v.document_id
        where p.quality_status = ? and coalesce(p.is_human_corrected, 0) = 0
        """,
        (REVIEW,),
    ).fetchall()
    out: Dict[str, List[tuple]] = {"key": [], "damaged": [], "damaged_kept": [], "short": [], "failed": [], "other": []}
    for page_id, method, attempts, error, doc_id, title, text, analyses in rows:
        if error_is_dead_key(error):
            out["key"].append((page_id, doc_id, title))
        elif method == TEXT_LAYER and attempts == 0:
            metric = ExtractionQualityAssessor.assess_page(1, text or "", TEXT_LAYER)
            if not text_layer_looks_damaged(metric):
                out["short"].append((page_id, doc_id, title))  # clean but short: its text stays, counts as read
                continue
            # A circular marked to be redone is read again unless it is already analysed in the app:
            # replacing text that published points quote is a person's call.
            # A person approved analysing it again (REDO.txt "approved"): read it again even if analysed.
            if _key(doc_id) not in approved and (analyses or (_key(doc_id) in done_keys and _key(doc_id) not in redo)):
                out["damaged_kept"].append((page_id, doc_id, title))
            else:
                out["damaged"].append((page_id, doc_id, title))
        elif not (text or "").strip():
            out["failed"].append((page_id, doc_id, title))
        else:
            out["other"].append((page_id, doc_id, title))  # not expected: has text but not from its text layer
    return out


def apply(conn: sqlite3.Connection, groups: Dict[str, List[tuple]]) -> int:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    changed = 0
    for page_id, _doc, _title in groups["key"]:
        changed += conn.execute(
            "update document_pages set quality_status = ?, vision_attempts = 0, vision_error = null, updated_at = ? "
            "where id = ? and quality_status = ? and coalesce(is_human_corrected, 0) = 0",
            (PENDING, now, page_id, REVIEW),
        ).rowcount
    for page_id, _doc, _title in groups["damaged"]:
        # Same shape as a page the ingest queues for image reading: empty text, the text layer kept aside.
        changed += conn.execute(
            "update document_pages set quality_status = ?, extraction_method = ?, native_text = coalesce(native_text, raw_text), "
            "raw_text = '', cleaned_text = '', line_boxes = null, quality_score = 0.0, vision_attempts = 0, "
            "vision_error = null, updated_at = ? "
            "where id = ? and quality_status = ? and coalesce(is_human_corrected, 0) = 0 and extraction_method = ?",
            (PENDING, VISION, now, page_id, REVIEW, TEXT_LAYER),
        ).rowcount
    for page_id, _doc, _title in groups["short"]:
        changed += conn.execute(
            "update document_pages set quality_status = ?, updated_at = ? "
            "where id = ? and quality_status = ? and coalesce(is_human_corrected, 0) = 0",
            (NATIVE, now, page_id, REVIEW),
        ).rowcount
    for page_id, _doc, _title in groups["failed"]:
        # Straight to the stronger route: the main model already failed on it.
        changed += conn.execute(
            "update document_pages set quality_status = ?, vision_attempts = ?, updated_at = ? "
            "where id = ? and quality_status = ? and coalesce(is_human_corrected, 0) = 0 "
            "and coalesce(raw_text, '') = ''",
            (PENDING, settings.VISION_MAX_ATTEMPTS, now, page_id, REVIEW),
        ).rowcount
    conn.commit()
    return changed


def _summary(groups: Dict[str, List[tuple]]) -> str:
    def n_docs(items):
        return len({d for _p, d, _t in items})

    return "\n".join([
        f"Pages that failed only because the reading key stopped working: {len(groups['key'])} "
        f"in {n_docs(groups['key'])} circulars -> sent back for reading",
        f"Damaged text pages never read from the image: {len(groups['damaged'])} "
        f"in {n_docs(groups['damaged'])} circulars -> sent back for reading",
        f"Damaged text pages left as they are (circular already analysed or handed out): {len(groups['damaged_kept'])} "
        f"in {n_docs(groups['damaged_kept'])} circulars",
        f"Short but clean text pages, text kept, marked as read: {len(groups['short'])} "
        f"in {n_docs(groups['short'])} circulars",
        f"Pages image reading really failed on -> the stronger route: {len(groups['failed'])} "
        f"in {n_docs(groups['failed'])} circulars",
        f"Other pages left as they are: {len(groups['other'])} "
        f"in {n_docs(groups['other'])} circulars",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, help="database file (default: the app's own)")
    ap.add_argument("--repo", type=Path, help="the shared analysis work repo, so circulars handed out there are left alone")
    ap.add_argument("--yes", action="store_true", help="make the change (a copy of the database is saved first)")
    args = ap.parse_args(argv)

    db = args.db or default_db()
    folders = list(LOCAL_FOLDERS) + ([args.repo / f for f in REPO_FOLDERS] if args.repo else [])
    done_keys = handed_out(folders)
    with sqlite3.connect(db, timeout=60) as conn:
        groups = plan(conn, done_keys, redo_keys(), redo_keys(approved_only=True))
        print(_summary(groups))
        if not args.repo:
            print("(No --repo given: circulars handed out only in the shared work repo are not known here.)")
        if not args.yes:
            print("Nothing changed. Run again with --yes to make the change.")
            return 0
        backup = db.with_name(f"{db.stem}.before-requeue-{datetime.now():%Y%m%d-%H%M}{db.suffix}")
        conn.execute("pragma wal_checkpoint(full)")
        shutil.copy2(db, backup)
        changed = apply(conn, groups)
    print(f"Sent {changed} pages back for page-image reading. Copy of the database before: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
