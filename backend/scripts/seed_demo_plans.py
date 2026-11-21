"""Puts the demo banks (ABC Bank PLC, XYZ Bank PLC) on the Enterprise plan, so the demo keeps every feature.

Safe to run again: a bank that already has an active plan is left alone.
Usage (repo root): .venv/Scripts/python.exe backend/scripts/seed_demo_plans.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import backend.app.database.models  # noqa: E402,F401
from sqlalchemy import select  # noqa: E402

from backend.app.database.base import Base  # noqa: E402
from backend.app.database.session import AsyncSessionLocal, async_engine  # noqa: E402
from backend.app.modules.organizations.models import Organization  # noqa: E402
from backend.app.modules.plans.models import DailyUsage, Subscription  # noqa: E402

DEMO = ("ABC Bank PLC", "XYZ Bank PLC")


async def main() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Subscription.__table__, DailyUsage.__table__]))
    async with AsyncSessionLocal() as db:
        for org in (await db.execute(select(Organization).where(Organization.name.in_(DEMO)))).scalars().all():
            have = (await db.execute(select(Subscription.id).where(Subscription.organization_id == org.id, Subscription.status == "ACTIVE"))).first()
            if have:
                print(f"{org.name}: already has a plan")
                continue
            db.add(Subscription(organization_id=org.id, plan="ENTERPRISE", seats=20, status="ACTIVE", organization_name=org.name,
                                note="Demo bank"))
            print(f"{org.name}: Enterprise, 20 seats")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
