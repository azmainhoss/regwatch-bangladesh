"""Before go-live: hide test circulars from the library and fix reference numbers that carry the year twice.

1. Test circulars: shared circulars with no bb.org.bd address (speed tests, early demo copies) and private copies
   owned by demo/test logins. They are flagged as test data (is_synthetic_fixture), which hides them from the
   dashboard, search and counts. Nothing is deleted, so it can be undone.
2. "DID Circular No. 01/2026/2026" -> "DID Circular No. 01/2026" (same year twice at the end).

Dry run by default; --yes writes, and first saves the exact undo statements to data/prelaunch_cleanup_undo.sql.
Usage (repo root):  .venv/bin/python backend/scripts/prelaunch_cleanup.py [--yes]
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.scripts.manage_accounts import is_demo  # noqa: E402

DOUBLE_YEAR = re.compile(r"/((?:19|20)\d{2})/\1$")


def db_path() -> Path:
    from backend.app.core.config import settings
    url = settings.SYNC_DATABASE_URL or ""
    if not url.startswith("sqlite"):
        sys.exit("SQLite only.")
    p = Path(url.split("///", 1)[1])
    return p if p.is_absolute() else ROOT / p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    path = db_path()
    con = sqlite3.connect(path)
    emails = {uid: email for uid, email in con.execute("select id, email from users")}
    rows = con.execute("""select id, reference_number, title, owner_user_id from documents
                          where coalesce(is_synthetic_fixture, 0) = 0""").fetchall()
    hide = []
    for doc_id, ref, title, owner in rows:
        url = con.execute("select source_url from documents where id = ?", (doc_id,)).fetchone()[0] or ""
        if owner is None and "bb.org.bd/" not in url:
            hide.append((doc_id, ref, title, "no bb.org.bd address"))
        elif owner is not None and is_demo(emails.get(owner, "")):
            hide.append((doc_id, ref, title, f"private copy of {emails.get(owner)}"))
    refs = [(doc_id, ref, DOUBLE_YEAR.sub(r"/\1", ref)) for doc_id, ref, _t, _o in rows if ref and DOUBLE_YEAR.search(ref)]

    for doc_id, ref, title, why in hide:
        print(f"hide: {ref or '-'} | {title} ({why})")
    for _id, old, new in refs:
        print(f"fix number: {old} -> {new}")
    if not args.yes:
        print(f"Dry run: {len(hide)} to hide, {len(refs)} numbers to fix. Run again with --yes.")
        return
    undo = path.with_name("prelaunch_cleanup_undo.sql")
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"  # noqa: E731
    with undo.open("a", encoding="utf-8") as f:
        for h in hide:
            f.write(f"update documents set is_synthetic_fixture = 0 where id = {q(h[0])};\n")
        for i, old, _new in refs:
            f.write(f"update documents set reference_number = {q(old)} where id = {q(i)};\n")
    con.executemany("update documents set is_synthetic_fixture = 1 where id = ?", [(h[0],) for h in hide])
    con.executemany("update documents set reference_number = ? where id = ?", [(new, i) for i, _old, new in refs])
    con.commit()
    print(f"Done: {len(hide)} hidden, {len(refs)} numbers fixed. Undo: sqlite3 {path} < {undo}")


if __name__ == "__main__":
    main()
