import asyncio
import json
import os
import sys
from pathlib import Path
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure root is in sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.database.session import AsyncSessionLocal
import backend.app.database.models
from backend.app.modules.documents.models import Document

SEED_FILE = Path(__file__).resolve().parent.parent / "app" / "fixtures" / "production_seed.json"

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from sqlalchemy import select, Boolean, Date, DateTime
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure root is in sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.database.session import AsyncSessionLocal
from backend.app.database.models import Base
from backend.app.database.base import GUID
import backend.app.database.models
from backend.app.modules.documents.models import Document

SEED_FILE = Path(__file__).resolve().parent.parent / "app" / "fixtures" / "production_seed.json"

async def import_seed(db: AsyncSession):
    if not SEED_FILE.exists():
        print(f"[SEED] Seed file not found at {SEED_FILE}")
        return

    # Check if documents already exist
    existing_count = (await db.execute(select(Document))).scalars().all()
    if len(existing_count) > 0:
        print(f"[SEED] Database already contains {len(existing_count)} documents. Skipping import.")
        return

    print(f"[SEED] Hydrating database from {SEED_FILE.name}...")
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Tables to import in topological order
    tables = [
        "institutions",
        "institution_departments",
        "users",
        "user_profiles",
        "organizations",
        "departments",
        "organization_members",
        "sources",
        "documents",
        "document_versions",
        "document_pages",
        "document_analyses",
        "provisions",
        "obligations",
        "analysis_claims",
        "claim_citations"
    ]

    for table in tables:
        rows = data.get(table, [])
        if not rows:
            continue
        table_obj = Base.metadata.tables.get(table)
        if table_obj is None:
            continue

        print(f"  -> Importing {len(rows)} records into '{table}'...")
        cleaned_rows = []
        for r in rows:
            row_dict = {}
            for col in table_obj.columns:
                if col.name not in r:
                    continue
                val = r[col.name]
                if val is None:
                    row_dict[col.name] = None
                elif isinstance(col.type, GUID):
                    row_dict[col.name] = uuid.UUID(str(val))
                elif isinstance(col.type, DateTime):
                    row_dict[col.name] = datetime.fromisoformat(str(val)) if isinstance(val, str) else val
                elif isinstance(col.type, Date):
                    row_dict[col.name] = date.fromisoformat(str(val)) if isinstance(val, str) else val
                elif isinstance(col.type, Boolean):
                    row_dict[col.name] = bool(int(val) if str(val).isdigit() else val)
                elif isinstance(val, (dict, list)):
                    row_dict[col.name] = val
                else:
                    row_dict[col.name] = val
            cleaned_rows.append(row_dict)

        if cleaned_rows:
            # Insert in chunks of 100
            for i in range(0, len(cleaned_rows), 100):
                chunk = cleaned_rows[i:i+100]
                try:
                    await db.execute(table_obj.insert(), chunk)
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    print(f"Error importing batch for table '{table}': {e}")

    await db.commit()
    print("[SEED] Hydration completed successfully!")

async def main():
    async with AsyncSessionLocal() as session:
        await import_seed(session)

if __name__ == "__main__":
    asyncio.run(main())

