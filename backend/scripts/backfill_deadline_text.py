"""Copies each requirement's deadline in words ("within 14 days of issuance") onto the obligation and onto
register items made from it, where they hold no words yet. Before this fix only a calendar date was copied,
so register items showed "Not set" for deadlines the circular gives in words.

Dry run by default; --yes writes. Safe to run again (only fills empty or date-only descriptions).

Usage (repo root):  .venv/bin/python backend/scripts/backfill_deadline_text.py [--yes]
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.app.core.config import settings  # noqa: E402

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def db_path() -> str:
    url = settings.SYNC_DATABASE_URL or ""
    if not url.startswith("sqlite"):
        sys.exit("This script handles the SQLite database only; run the same UPDATEs by hand on PostgreSQL.")
    return url.split("///", 1)[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="write the changes (default: only count them)")
    args = ap.parse_args()
    con = sqlite3.connect(db_path())
    words = {}
    for oid, fields in con.execute(
        "SELECT obligation_id, fields FROM analysis_claims WHERE obligation_id IS NOT NULL AND fields IS NOT NULL"
    ):
        try:
            text = (json.loads(fields) if isinstance(fields, str) else fields or {}).get("deadline_text")
        except ValueError:
            continue
        if isinstance(text, str) and text.strip():
            words[oid] = text.strip()

    def empty(v) -> bool:
        return not v or not str(v).strip() or bool(ISO.match(str(v).strip()))

    obl = [(oid, w) for oid, w in words.items()
           if empty((con.execute("SELECT deadline_description FROM obligations WHERE id = ?", (oid,)).fetchone() or ["x"])[0])]
    items = [(w, iid) for iid, oid, cur in con.execute("SELECT id, obligation_id, deadline_description FROM compliance_items")
             if oid in words and empty(cur) for w in [words[oid]]]
    print(f"Requirements with a deadline in words: {len(words)}")
    print(f"  obligations to fill: {len(obl)}")
    print(f"  register items to fill: {len(items)}")
    if not args.yes:
        print("Dry run. Run again with --yes to write.")
        return
    con.executemany("UPDATE obligations SET deadline_description = ? WHERE id = ?", [(w, oid) for oid, w in obl])
    con.executemany("UPDATE compliance_items SET deadline_description = ? WHERE id = ?", items)
    con.commit()
    print("Written.")


if __name__ == "__main__":
    main()
