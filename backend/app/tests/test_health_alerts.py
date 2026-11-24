"""Admin health alerts: no successful bb.org.bd check for 3 hours, no laptop analysis upload for a day."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.alerts import sweeps
from backend.app.modules.alerts.models import AlertEvent
from backend.app.modules.alerts.templates import render
from backend.app.modules.documents.models import Document
from backend.app.modules.sources.models import Source, SourceRun
from backend.app.tests.factories import make_document

# 13:00 in Dhaka on a weekday: inside the checking window, more than 3 hours after it opens.
NOON_DHAKA = datetime(2026, 11, 24, 7, 0, tzinfo=timezone.utc)


async def _events(queue: str):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AlertEvent).where(AlertEvent.dedupe_key.like(f"ADMIN_QUEUE:{queue}:%")))).scalars().all()
        return list(rows)


async def _clear():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AlertEvent).where(AlertEvent.dedupe_key.like("ADMIN_QUEUE:checker:%")))
        await db.execute(delete(AlertEvent).where(AlertEvent.dedupe_key.like("ADMIN_QUEUE:uploads:%")))
        await db.execute(delete(SourceRun))
        await db.commit()


async def _run(now):
    async with AsyncSessionLocal() as db:
        n = await sweeps.ensure_health_events(db, now=now)
        await db.commit()
        return n


async def _add_run(completed_at):
    async with AsyncSessionLocal() as db:
        source = (await db.execute(select(Source))).scalars().first()
        db.add(SourceRun(source_id=source.id, status="COMPLETED", started_at=completed_at, completed_at=completed_at))
        await db.commit()


@pytest.mark.asyncio
async def test_checker_alert_after_three_hours_without_a_successful_check(monkeypatch):
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "MONITOR_WINDOW_START", 9)
    monkeypatch.setattr(settings, "MONITOR_WINDOW_END", 19)
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", None)
    await _clear()

    await _add_run(NOON_DHAKA - timedelta(hours=1))
    await _run(NOON_DHAKA)
    assert await _events("checker") == []

    await _clear()
    await _add_run(NOON_DHAKA - timedelta(hours=5))
    await _run(NOON_DHAKA)
    await _run(NOON_DHAKA + timedelta(minutes=15))  # once a day only
    events = await _events("checker")
    assert len(events) == 1
    assert "No successful check of bb.org.bd for 5 hours" in render("ADMIN_QUEUE", events[0].payload).title


@pytest.mark.asyncio
async def test_no_checker_alert_outside_the_window_or_where_the_checker_does_not_run(monkeypatch):
    monkeypatch.setattr(settings, "MONITOR_WINDOW_START", 9)
    monkeypatch.setattr(settings, "MONITOR_WINDOW_END", 19)
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", None)
    await _clear()
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    early = datetime(2026, 11, 24, 4, 0, tzinfo=timezone.utc)  # 10:00 in Dhaka: the window opened only an hour ago
    await _run(early)
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    await _run(NOON_DHAKA)
    assert await _events("checker") == []


@pytest.mark.asyncio
async def test_upload_alert_only_when_recent_circulars_wait(monkeypatch):
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", SecretStr("u" * 40))
    await _clear()
    # Two days on, so any analysis uploaded by other tests today is already a day old.
    now = datetime.now(timezone.utc) + timedelta(days=2)
    doc, _v, _p = await make_document()
    async with AsyncSessionLocal() as db:
        row = await db.get(Document, doc.id)
        row.is_synthetic_fixture = False
        row.publication_date = now.date()
        row.publication_status = "EXTRACTED"
        await db.commit()
    await _run(now)
    events = await _events("uploads")
    assert len(events) == 1
    assert "No analysis uploaded from the laptop" in render("ADMIN_QUEUE", events[0].payload).title

    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", None)  # Phase 1 not in use: never alerts
    await _clear()
    await _run(now)
    assert await _events("uploads") == []
