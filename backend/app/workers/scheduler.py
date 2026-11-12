"""Background schedule for the bb.org.bd checks (DECISIONS.md 1).

All times are local time in MONITOR_TIMEZONE (Asia/Dhaka). The host PC is only on inside
MONITOR_WINDOW_START..MONITOR_WINDOW_END, so nothing is scheduled outside that window:
- new-circular check every POLL_INTERVAL_WORKDAY_MINUTES Sun-Thu, every
  POLL_INTERVAL_WEEKEND_MINUTES Fri-Sat;
- full-list reconcile once a day at RECONCILE_TIME;
- archive re-check once a week on RECHECK_WEEKDAY at RECHECK_TIME.

`next_run(now)` is a pure function so the schedule can be tested without waiting.
Run the scheduler in one process only (SCHEDULER_ENABLED): the request pace and lock live in memory.
"""
import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.sources.models import Source
from backend.app.modules.sources.service import source_in_backoff, source_monitoring_service

POLL = "poll"
RECONCILE = "reconcile"
RECHECK = "recheck"

# Python weekday numbers: Mon=0 ... Thu=3, Fri=4, Sat=5, Sun=6. Bangladesh works Sun-Thu.
WORKDAYS = (6, 0, 1, 2, 3)

# A job whose time passed long ago (the PC was asleep) is skipped, not run late.
MAX_LATENESS_SECONDS = 300


def _hhmm(value: str) -> time:
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


def _in_window(local: datetime, cfg) -> bool:
    start = time(cfg.MONITOR_WINDOW_START, 0)
    end = time(cfg.MONITOR_WINDOW_END, 0)
    return start <= local.timetz().replace(tzinfo=None) < end


def _next_window_start(local: datetime, cfg) -> datetime:
    start_today = local.replace(hour=cfg.MONITOR_WINDOW_START, minute=0, second=0, microsecond=0)
    if local < start_today:
        return start_today
    return start_today + timedelta(days=1)


def _next_daily(local: datetime, at: time) -> datetime:
    candidate = local.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return candidate if candidate > local else candidate + timedelta(days=1)


def next_run(now: datetime, cfg=settings) -> Tuple[datetime, str]:
    """Returns (when, kind) for the next job after `now`. kind is "poll", "reconcile" or "recheck"."""
    tz = ZoneInfo(cfg.MONITOR_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(tz)

    # New-circular check: interval after now while inside the window, else the next window start.
    if _in_window(local, cfg):
        minutes = cfg.POLL_INTERVAL_WORKDAY_MINUTES if local.weekday() in WORKDAYS else cfg.POLL_INTERVAL_WEEKEND_MINUTES
        poll_at = local + timedelta(minutes=minutes)
        if not (_in_window(poll_at, cfg) and poll_at.date() == local.date()):
            poll_at = _next_window_start(local, cfg)
    else:
        poll_at = _next_window_start(local, cfg)

    candidates = []
    reconcile_time = _hhmm(cfg.RECONCILE_TIME)
    reconcile_at = _next_daily(local, reconcile_time)
    if _in_window(reconcile_at, cfg):
        candidates.append((reconcile_at, 0, RECONCILE))

    recheck_at = _next_daily(local, _hhmm(cfg.RECHECK_TIME))
    while recheck_at.weekday() != cfg.RECHECK_WEEKDAY:
        recheck_at += timedelta(days=1)
    if _in_window(recheck_at, cfg):
        candidates.append((recheck_at, 1, RECHECK))

    candidates.append((poll_at, 2, POLL))
    when, _priority, kind = min(candidates)
    return when, kind


class ScheduledMonitoringService:
    def __init__(self, clock: Optional[Callable[[], datetime]] = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._is_running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Source monitoring scheduler started (window {settings.MONITOR_WINDOW_START}:00-"
            f"{settings.MONITOR_WINDOW_END}:00 {settings.MONITOR_TIMEZONE})."
        )

    async def stop(self):
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Source monitoring scheduler stopped.")

    async def _run_loop(self):
        last_target: Optional[datetime] = None
        while self._is_running:
            now = self._clock()
            if last_target is not None and now <= last_target:
                now = last_target + timedelta(seconds=1)
            target, kind = next_run(now)
            delay = (target - self._clock()).total_seconds()
            logger.info(f"Next scheduled {kind} at {target.isoformat()}.")
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            last_target = target
            lateness = (self._clock() - target).total_seconds()
            if lateness > MAX_LATENESS_SECONDS:
                logger.info(f"Skipping {kind} planned for {target.isoformat()} ({int(lateness)} s late).")
                continue
            try:
                await self.run_job(kind)
            except Exception as e:
                logger.error(f"Error in scheduled {kind}: {e}")

    async def run_job(self, kind: str):
        if kind == RECHECK:
            await self.recheck_archive()
        else:
            await self.poll_active_sources(mode=kind)

    async def _active_sources(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Source).where(
                    Source.is_active == True,
                    Source.monitoring_method != "MANUAL_ONLY"
                )
            )
            return result.scalars().all()

    async def poll_active_sources(self, mode: str = POLL):
        # Read the list of sources with a short-lived session, then give every source
        # its own session so one failure (or a broken transaction) cannot affect the rest.
        sources = await self._active_sources()
        if not sources:
            logger.info("No active regulatory sources configured for monitoring.")
            return

        run_type = "SCHEDULED_RECONCILE" if mode == RECONCILE else "SCHEDULED_POLL"
        for source in sources:
            if source_in_backoff(source, self._clock()):
                logger.info(f"Source '{source.name}' is backing off after failed checks; skipping this {mode}.")
                continue
            try:
                async with AsyncSessionLocal() as session:
                    run = await source_monitoring_service.execute_source_monitoring(
                        db=session,
                        source_id=source.id,
                        run_type=run_type,
                        mode=mode,
                    )
                    logger.info(
                        f"Source '{source.name}' {mode} finished: {run.status} "
                        f"({run.outcome}, {run.valid_documents_discovered} new)."
                    )
            except Exception as ex:
                logger.error(f"Failed scheduled {mode} for source '{source.name}': {ex}")

    async def recheck_archive(self):
        sources = await self._active_sources()
        if any(source_in_backoff(s, self._clock()) for s in sources):
            logger.info("Skipping the weekly archive re-check: the site check is backing off.")
            return
        async with AsyncSessionLocal() as session:
            await source_monitoring_service.recheck_archive(session)


monitoring_scheduler = ScheduledMonitoringService()
