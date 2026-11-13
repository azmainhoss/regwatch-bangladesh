"""The alerts job: hands out events, runs the deadline and queue checks, builds summaries, sends email.

Off unless SCHEDULER_ENABLED or ALERTS_WORKER_ENABLED is on. Run it in one process only.
The inbox works without it (the unread-count poll hands out events and runs the checks); only email needs it.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.alerts import mailer
from backend.app.modules.alerts.dispatch import dispatch_pending
from backend.app.modules.alerts.models import (
    AlertNotification, EmailDeliveryAttempt, EmailOutbox,
)

BACKOFF = [60, 300, 900, 3600, 10800, 21600]  # 1 min, 5 min, 15 min, 1 h, 3 h, 6 h
LEASE_SECONDS = 300
BATCH = 20

_dispatch_lock: Optional[asyncio.Lock] = None


def _lock() -> asyncio.Lock:
    global _dispatch_lock
    if _dispatch_lock is None:
        _dispatch_lock = asyncio.Lock()
    return _dispatch_lock


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def dispatch_in_new_session() -> None:
    """Hands out pending events in their own session. Two of these never overlap in one process."""
    from backend.app.database.session import AsyncSessionLocal
    async with _lock():
        try:
            async with AsyncSessionLocal() as session:
                await dispatch_pending(session)
                await session.commit()
        except Exception as exc:
            logger.warning("Alert hand-out failed: %s", type(exc).__name__)


def kick_dispatch() -> None:
    """Called after a commit. Does nothing when switched off (tests) or when no event loop is running."""
    if not settings.ALERTS_KICK_AFTER_COMMIT:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        task = loop.create_task(dispatch_in_new_session())
        _background.add(task)
        task.add_done_callback(_background.discard)
    except Exception as exc:
        logger.warning("Alert hand-off not started: %s", type(exc).__name__)


_background: set = set()


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
async def send_due_emails(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Sends due outbox rows with retry and backoff. Returns how many were handled. Commits as it goes."""
    if not mailer.email_configured():
        return 0
    now = now or _now()
    # A crash in the middle of a send leaves the row SENDING. It goes back to PENDING (it may be sent twice; accepted).
    await db.execute(update(EmailOutbox).where(
        EmailOutbox.status == "SENDING", EmailOutbox.locked_until < now,
    ).values(status="PENDING", locked_until=None))
    cutoff = now - timedelta(hours=settings.ALERTS_EMAIL_MAX_AGE_HOURS)
    await db.execute(update(EmailOutbox).where(
        EmailOutbox.status == "PENDING", EmailOutbox.created_at < cutoff,
    ).values(status="EXPIRED"))
    await db.commit()

    ids = [r[0] for r in (await db.execute(
        select(EmailOutbox.id).where(EmailOutbox.status == "PENDING", EmailOutbox.next_attempt_at <= now)
        .order_by(EmailOutbox.next_attempt_at, EmailOutbox.id).limit(BATCH)
    )).all()]
    handled = 0
    for oid in ids:
        row = await db.get(EmailOutbox, oid)
        if row is None or row.status != "PENDING":
            continue
        started = _now()
        row.status = "SENDING"
        row.locked_until = now + timedelta(seconds=LEASE_SECONDS)
        await db.commit()
        msg = mailer.build_message(row.to_address, row.subject, row.text_body, row.html_body)
        result = await asyncio.to_thread(mailer.send_now, msg)
        await record_attempt(db, row, result, started, now)
        handled += 1
    return handled


async def record_attempt(db: AsyncSession, row: EmailOutbox, result, started: datetime, now: Optional[datetime] = None) -> None:
    """Stores the outcome of one send on the row, adds the log line and commits."""
    now = now or _now()
    row.attempts = (row.attempts or 0) + 1
    row.locked_until = None
    outcome = result.outcome
    if result.ok:
        row.status = "SENT"
        row.sent_at = _now()
        row.smtp_message_id = (result.message_id or "")[:255] or None
        row.last_error = None
        ids = [i for i in (row.notification_ids or [])]
        if ids:
            await db.execute(update(AlertNotification).where(
                AlertNotification.id.in_(ids), AlertNotification.emailed_at.is_(None),
            ).values(emailed_at=_now()))
    elif outcome == "FAILED":
        row.status = "FAILED"
        row.last_error = mailer.redact(result.error)
    else:
        row.last_error = mailer.redact(result.error)
        if row.attempts >= settings.ALERTS_EMAIL_MAX_ATTEMPTS:
            row.status = "FAILED"
            outcome = "FAILED"
        else:
            row.status = "PENDING"
            row.next_attempt_at = now + timedelta(seconds=BACKOFF[min(row.attempts, len(BACKOFF)) - 1])
    db.add(EmailDeliveryAttempt(
        outbox_id=row.id, attempt_no=row.attempts, started_at=started, finished_at=_now(),
        outcome=outcome, smtp_code=result.smtp_code, error=mailer.redact(result.error) if result.error else None,
    ))
    logger.info("Email %s kind=%s attempt=%s outcome=%s code=%s", row.id, row.kind, row.attempts, outcome, result.smtp_code)
    await db.commit()


# ---------------------------------------------------------------------------
# Sweeps and clean-up
# ---------------------------------------------------------------------------
async def run_sweeps(db: AsyncSession) -> None:
    from backend.app.modules.alerts import sweeps
    from backend.app.modules.organizations.models import Organization
    org_ids = [r[0] for r in (await db.execute(select(Organization.id).where(Organization.is_active.is_(True)))).all()]
    for org_id in org_ids:
        for step in (sweeps.ensure_deadline_events, sweeps.ensure_source_change_events):
            try:
                await step(db, org_id)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("Alert check failed: %s", type(exc).__name__)
    for step in (sweeps.ensure_admin_queue_events, sweeps.sweep_published):
        try:
            await step(db)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("Alert check failed: %s", type(exc).__name__)


async def clean_up(db: AsyncSession) -> None:
    now = _now()
    await db.execute(delete(AlertNotification).where(
        AlertNotification.created_at < now - timedelta(days=settings.ALERTS_RETENTION_DAYS)
    ))
    await db.execute(update(EmailOutbox).where(
        EmailOutbox.status.in_(["SENT", "EXPIRED", "FAILED"]),
        EmailOutbox.created_at < now - timedelta(days=30),
        EmailOutbox.text_body != "",
    ).values(text_body="", html_body=""))
    await db.commit()


class AlertsWorker:
    """Runs every ALERTS_WORKER_POLL_SECONDS, or sooner when kicked."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory
        self._task: Optional[asyncio.Task] = None
        self._wake: Optional[asyncio.Event] = None
        self._running = False
        self._last_sweep: Optional[datetime] = None

    @property
    def running(self) -> bool:
        return self._running

    def kick(self) -> None:
        if self._wake is not None:
            self._wake.set()

    async def start(self) -> None:
        if self._running:
            return
        if self._session_factory is None:
            from backend.app.database.session import AsyncSessionLocal
            self._session_factory = AsyncSessionLocal
        self._running = True
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        logger.info("Alerts job started.")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _step(self, name: str, fn) -> None:
        try:
            async with self._session_factory() as session:
                await fn(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Alerts job step %s failed: %s", name, type(exc).__name__)

    async def _dispatch(self, session: AsyncSession) -> None:
        async with _lock():
            await dispatch_pending(session)
            await session.commit()

    async def _sweep(self, session: AsyncSession) -> None:
        await run_sweeps(session)
        await self._dispatch(session)
        await clean_up(session)

    async def _digest(self, session: AsyncSession) -> None:
        from backend.app.modules.alerts.digest import build_digests
        await build_digests(session, _now())
        await session.commit()

    async def run_once(self) -> None:
        await self._step("dispatch", self._dispatch)
        now = _now()
        if self._last_sweep is None or now - self._last_sweep >= timedelta(minutes=settings.ALERTS_SWEEP_MINUTES):
            self._last_sweep = now
            await self._step("sweep", self._sweep)
        await self._step("digest", self._digest)
        await self._step("send", send_due_emails)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=settings.ALERTS_WORKER_POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            self._wake.clear()


alerts_worker = AlertsWorker()
