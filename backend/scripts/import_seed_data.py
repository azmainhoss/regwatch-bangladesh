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
        print(f"  -> Importing {len(rows)} records into '{table}'...")
        for r in rows:
            # Clean JSON columns if stored as strings
            cols = list(r.keys())
            vals = list(r.values())
            # Convert python dicts/lists to JSON strings if inserting raw text
            cleaned_vals = []
            for v in vals:
                if isinstance(v, (dict, list)):
                    cleaned_vals.append(json.dumps(v))
                else:
                    cleaned_vals.append(v)

            col_names = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            stmt = text(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})")
            params = {cols[i]: cleaned_vals[i] for i in range(len(cols))}
            try:
                await db.execute(stmt, params)
            except Exception as e:
                # Ignore duplicates if any
                pass

    await db.commit()
    print("[SEED] Hydration completed successfully!")

async def main():
    async with AsyncSessionLocal() as session:
        await import_seed(session)

if __name__ == "__main__":
    asyncio.run(main())
