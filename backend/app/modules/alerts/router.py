"""Alerts: the inbox, the unread-count poll, settings, and the email box for platform staff."""
import asyncio
import html
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.database.session import get_async_db
from backend.app.modules.alerts import inbox, mailer, prefs, sweeps
from backend.app.modules.alerts.dispatch import dispatch_pending
from backend.app.modules.alerts.kinds import EMAIL_MODES, GROUPS
from backend.app.modules.alerts.models import AlertNotification, AlertPreference, EmailOutbox
from backend.app.modules.alerts.schemas import (
    AlertChangeRead, AlertListRead, DepartmentOption, EmailStatusRead, GroupOption, OutboxCounts, OutboxListRead,
    OutboxRowRead, PreferenceOptions, PreferencesRead, PreferencesWrite, ReadAllBody, ReadAllRead, SummaryRead,
    TestEmailRead, ChannelSetting,
)
from backend.app.modules.alerts import worker as alerts_worker_module
from backend.app.modules.compliance.service import ConflictError
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.deps import get_current_superuser, get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import InstitutionDepartment
from backend.app.modules.organizations.models import Organization, OrganizationMember

router = APIRouter(prefix="/alerts", tags=["Alerts"])
AN = AlertNotification

# Last time a poll ran the checks for one bank (or "admin") in this process.
_last_poll_sweep: Dict[str, datetime] = {}
_last_test_email: Dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _dispatch(db: AsyncSession) -> int:
    """Hands out pending events, then saves. Never raises: the count must always come back."""
    try:
        async with alerts_worker_module._lock():
            handled = await dispatch_pending(db)
            await db.commit()
        return handled
    except Exception as exc:
        logger.warning("Alert hand-out failed: %s", type(exc).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        return 0


async def _my_org_ids(db: AsyncSession, user: User) -> List[UUID]:
    rows = (await db.execute(
        select(OrganizationMember.organization_id)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.user_id == user.id, OrganizationMember.status == "ACTIVE",
            Organization.is_active.is_(True),
        )
    )).all()
    return [r[0] for r in rows]


async def _poll_sweeps(db: AsyncSession, user: User) -> None:
    """Throttled checks for this person's banks (and platform queues for staff). Each in its own try."""
    now = _now()
    gap = timedelta(minutes=settings.ALERTS_ON_POLL_SWEEP_MINUTES)
    emitted = False
    for org_id in await _my_org_ids(db, user):
        key = str(org_id)
        last = _last_poll_sweep.get(key)
        if last is not None and now - last < gap:
            continue
        _last_poll_sweep[key] = now
        for step in (sweeps.ensure_deadline_events, sweeps.ensure_source_change_events):
            try:
                emitted = bool(await step(db, org_id)) or emitted
            except Exception as exc:
                logger.warning("Alert check failed: %s", type(exc).__name__)
    if user.is_superuser:
        last = _last_poll_sweep.get("admin")
        if last is None or now - last >= gap:
            _last_poll_sweep["admin"] = now
            for step in (sweeps.ensure_admin_queue_events, sweeps.sweep_published):
                try:
                    emitted = bool(await step(db)) or emitted
                except Exception as exc:
                    logger.warning("Alert check failed: %s", type(exc).__name__)
    if emitted:
        await _dispatch(db)


# ---------------------------------------------------------------------------
# N1 summary (the poll)
# ---------------------------------------------------------------------------
@router.get("/summary", response_model=SummaryRead)
async def summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await _dispatch(db)
    try:
        await _poll_sweeps(db, user)
    except Exception as exc:
        logger.warning("Alert check failed: %s", type(exc).__name__)
    latest_id, latest_at = await inbox.latest(db, user)
    return SummaryRead(
        unread_count=await inbox.unread_count(db, user), latest_id=latest_id, latest_created_at=latest_at,
        email_configured=mailer.email_configured(), server_time=_now(),
    )


# ---------------------------------------------------------------------------
# N2 list
# ---------------------------------------------------------------------------
@router.get("", response_model=AlertListRead)
async def list_alerts(
    filter: str = Query("all", pattern="^(all|unread)$"),
    group: Optional[str] = None,
    before: Optional[datetime] = None,
    after: Optional[datetime] = None,
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    await _dispatch(db)
    if group and group not in GROUPS and inbox.group_filter(group) is None:
        raise HTTPException(status_code=422, detail="Unknown group.")
    q = select(AN).where(inbox.visible_condition(user.id, user.is_superuser))
    if filter == "unread":
        q = q.where(AN.read_at.is_(None))
    gf = inbox.group_filter(group)
    if gf is not None:
        q = q.where(gf)
    if before is not None:
        q = q.where(AN.created_at < inbox.utc(before))
    if after is not None:
        q = q.where(AN.created_at > inbox.utc(after))
    rows = list((await db.execute(q.order_by(AN.created_at.desc(), AN.id.desc()).limit(limit + 1))).scalars().all())
    next_before = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_before = inbox.utc(rows[-1].created_at)
    return AlertListRead(alerts=await inbox.to_read(db, rows), next_before=next_before,
                         unread_count=await inbox.unread_count(db, user))


# ---------------------------------------------------------------------------
# N3-N5 read state
# ---------------------------------------------------------------------------
@router.post("/read-all", response_model=ReadAllRead)
async def read_all(body: ReadAllBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    q = select(AN).where(
        inbox.visible_condition(user.id, user.is_superuser), AN.read_at.is_(None),
        AN.created_at <= inbox.utc(body.up_to),
    )
    if body.group:
        gf = inbox.group_filter(body.group)
        if gf is None:
            raise HTTPException(status_code=422, detail="Unknown group.")
        q = q.where(gf)
    rows = list((await db.execute(q)).scalars().all())
    now = _now()
    for r in rows:
        r.read_at = now
    await db.commit()
    return ReadAllRead(updated=len(rows), unread_count=await inbox.unread_count(db, user))


async def _one(db: AsyncSession, user: User, alert_id: UUID) -> AlertNotification:
    row = await inbox.get_visible(db, user, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return row


@router.post("/{alert_id}/read", response_model=AlertChangeRead)
async def mark_read(alert_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    row = await _one(db, user, alert_id)
    if row.read_at is None:
        row.read_at = _now()
        await db.commit()
    return AlertChangeRead(alert=(await inbox.to_read(db, [row]))[0], unread_count=await inbox.unread_count(db, user))


@router.post("/{alert_id}/unread", response_model=AlertChangeRead)
async def mark_unread(alert_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    row = await _one(db, user, alert_id)
    if row.read_at is not None:
        row.read_at = None
        await db.commit()
    return AlertChangeRead(alert=(await inbox.to_read(db, [row]))[0], unread_count=await inbox.unread_count(db, user))


# ---------------------------------------------------------------------------
# N6-N7 preferences
# ---------------------------------------------------------------------------
async def build_preferences(db: AsyncSession, user: User) -> PreferencesRead:
    has_membership = bool(await _my_org_ids(db, user))
    visible = prefs.visible_group_ids(is_superuser=user.is_superuser, has_membership=has_membership)
    row = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))).scalar_one_or_none()
    channels = {}
    for gid in visible:
        in_app, email = prefs.channel_for(row, gid)
        if row is not None and not row.email_enabled:
            # show the person's own choice, not the master switch override
            setting = (row.channels or {}).get(gid) or {}
            email = setting.get("email") if setting.get("email") in EMAIL_MODES else GROUPS[gid]["email"]
        channels[gid] = ChannelSetting(in_app=in_app, email=email)
    depts = (await db.execute(
        select(InstitutionDepartment.code, InstitutionDepartment.name).order_by(InstitutionDepartment.code)
    )).all()
    seen, dept_opts = set(), []
    for code, name in depts:
        if code not in seen:
            seen.add(code)
            dept_opts.append(DepartmentOption(code=code, name=name))
    types = [r[0] for r in (await db.execute(
        select(Document.document_type).where(Document.owner_user_id.is_(None)).distinct().order_by(Document.document_type)
    )).all() if r[0]]
    def _days(d):
        return "1 day" if d == 1 else f"{d} days"
    ds = sorted(settings.due_soon_days, reverse=True)
    days = " and ".join([", ".join(_days(d) for d in ds[:-1]), _days(ds[-1])] if len(ds) > 1 else [_days(ds[0])]) if ds else "Some days"
    options = PreferenceOptions(
        groups=[GroupOption(id=g, label=GROUPS[g]["label"], description=GROUPS[g]["description"].replace("{days}", days))
                for g in visible],
        department_codes=dept_opts, document_types=types,
    )
    return PreferencesRead(
        channels=channels, email_enabled=True if row is None else row.email_enabled,
        library_department_codes=list(row.library_department_codes or []) if row else [],
        library_document_types=list(row.library_document_types or []) if row else [],
        library_keywords=list(row.library_keywords or []) if row else [],
        lock_version=row.lock_version if row else 1,
        email_configured=mailer.email_configured(), due_soon_days=settings.due_soon_days,
        digest_time=settings.ALERTS_DIGEST_TIME, options=options,
    )


@router.get("/preferences", response_model=PreferencesRead)
async def get_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await build_preferences(db, user)


def _bad(detail: str):
    return HTTPException(status_code=422, detail=detail)


@router.put("/preferences", response_model=PreferencesRead)
async def put_preferences(
    body: PreferencesWrite, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    for gid, setting in body.channels.items():
        if gid not in GROUPS:
            raise _bad(f"Unknown alert group: {gid}")
        if setting.email not in EMAIL_MODES:
            raise _bad("Email must be OFF, INSTANT or DIGEST.")
    known_codes = {r[0] for r in (await db.execute(select(InstitutionDepartment.code))).all()}
    codes = []
    for c in body.library_department_codes:
        if c not in known_codes:
            raise _bad(f"Unknown department code: {c}")
        if c not in codes:
            codes.append(c)
    types = []
    for t in body.library_document_types:
        t = str(t).strip()
        if not t or len(t) > 64:
            raise _bad("Document types must be 1 to 64 characters.")
        if t not in types:
            types.append(t)
    words: List[str] = []
    for w in body.library_keywords:
        w = " ".join(str(w).split())
        if len(w) < 2 or len(w) > 60:
            raise _bad("Each keyword must be 2 to 60 characters.")
        if w.casefold() in [x.casefold() for x in words]:
            raise _bad("Keywords must not repeat.")
        words.append(w)
    if len(words) > 20:
        raise _bad("You can add up to 20 keywords.")

    has_membership = bool(await _my_org_ids(db, user))
    visible = set(prefs.visible_group_ids(is_superuser=user.is_superuser, has_membership=has_membership))
    row = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))).scalar_one_or_none()
    current_version = row.lock_version if row else 1
    if body.lock_version is not None and body.lock_version != current_version:
        raise ConflictError("Your settings were changed in another window. You now see the latest.",
                            (await build_preferences(db, user)).model_dump(mode="json"))
    channels = dict((row.channels or {}) if row else {})
    for gid, setting in body.channels.items():
        if gid in visible:
            channels[gid] = {"in_app": setting.in_app, "email": setting.email}
    if row is None:
        row = AlertPreference(user_id=user.id, lock_version=1)
        db.add(row)
    else:
        row.lock_version = current_version + 1
    row.channels = channels
    row.email_enabled = body.email_enabled
    row.library_department_codes = codes
    row.library_document_types = types
    row.library_keywords = words
    await db.commit()
    return await build_preferences(db, user)


# ---------------------------------------------------------------------------
# E1-E4 email box (platform staff)
# ---------------------------------------------------------------------------
def _mask(address: str) -> str:
    local, _, domain = (address or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _row(r: EmailOutbox) -> OutboxRowRead:
    return OutboxRowRead(
        id=r.id, kind=r.kind, status=r.status, attempts=r.attempts, next_attempt_at=inbox.utc(r.next_attempt_at),
        sent_at=inbox.utc(r.sent_at), last_error=r.last_error, created_at=inbox.utc(r.created_at),
        to_masked=_mask(r.to_address),
    )


@router.get("/admin/email-status", response_model=EmailStatusRead)
async def email_status(admin: User = Depends(get_current_superuser), db: AsyncSession = Depends(get_async_db)):
    counts = dict((await db.execute(select(EmailOutbox.status, func.count(EmailOutbox.id)).group_by(EmailOutbox.status))).all())
    sent_24h = (await db.execute(
        select(func.count(EmailOutbox.id)).where(EmailOutbox.status == "SENT", EmailOutbox.sent_at >= _now() - timedelta(hours=24))
    )).scalar_one()
    last_error = (await db.execute(
        select(EmailOutbox.last_error).where(EmailOutbox.last_error.is_not(None)).order_by(EmailOutbox.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    pw = settings.SMTP_PASSWORD
    return EmailStatusRead(
        configured=mailer.email_configured(), host=settings.SMTP_HOST or None, port=settings.SMTP_PORT,
        tls_mode=settings.SMTP_TLS_MODE, from_address=settings.SMTP_FROM or None,
        username_set=bool(settings.SMTP_USERNAME), password_set=bool(pw is not None and pw.get_secret_value()),
        worker_running=alerts_worker_module.alerts_worker.running,
        outbox=OutboxCounts(
            pending=counts.get("PENDING", 0), sending=counts.get("SENDING", 0), sent_24h=int(sent_24h),
            failed=counts.get("FAILED", 0), expired=counts.get("EXPIRED", 0),
        ),
        last_error=mailer.redact(last_error) if last_error else None,
    )


@router.post("/admin/test-email", response_model=TestEmailRead)
async def test_email(admin: User = Depends(get_current_superuser), db: AsyncSession = Depends(get_async_db)):
    if not mailer.email_configured():
        raise HTTPException(status_code=409, detail="Email is not set up. Set SMTP_HOST and SMTP_FROM on the server.")
    key = str(admin.id)
    now = _time.monotonic()
    last = _last_test_email.get(key)
    if last is not None and now - last < 30:
        raise HTTPException(status_code=429, detail="Please wait 30 seconds between test emails.")
    _last_test_email[key] = now
    stamp = datetime.now(ZoneInfo(settings.MONITOR_TIMEZONE)).strftime("%d %b %Y, %H:%M")
    text = f"Email from RegWatch works. Sent {stamp} Dhaka time."
    row = EmailOutbox(
        user_id=admin.id, to_address=admin.email, kind="TEST", dedupe_key=f"test:{uuid4()}", notification_ids=[],
        subject="RegWatch test email", text_body=text, html_body=f"<p>{html.escape(text)}</p>",
        status="SENDING", attempts=0, next_attempt_at=_now(), locked_until=_now() + timedelta(minutes=5),
    )
    db.add(row)
    await db.commit()
    started = _now()
    result = await asyncio.to_thread(
        mailer.send_now, mailer.build_message(row.to_address, row.subject, row.text_body, row.html_body)
    )
    if not result.ok and result.outcome == "RETRY":
        result.outcome = "FAILED"  # a test is never retried in the background
    await alerts_worker_module.record_attempt(db, row, result, started)
    detail = f"Test email sent to {admin.email}." if result.ok else (result.error or "The email server refused the message.")
    return TestEmailRead(ok=result.ok, outcome=result.outcome, smtp_code=result.smtp_code, detail=detail)


@router.get("/admin/outbox", response_model=OutboxListRead)
async def outbox(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    q = select(EmailOutbox)
    if status_filter:
        q = q.where(EmailOutbox.status == status_filter.upper())
    rows = (await db.execute(q.order_by(EmailOutbox.created_at.desc(), EmailOutbox.id.desc()).limit(limit))).scalars().all()
    return OutboxListRead(rows=[_row(r) for r in rows])


@router.post("/admin/outbox/{outbox_id}/retry", response_model=OutboxRowRead)
async def retry_outbox(outbox_id: UUID, admin: User = Depends(get_current_superuser), db: AsyncSession = Depends(get_async_db)):
    row = await db.get(EmailOutbox, outbox_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Email not found.")
    if row.status not in ("FAILED", "EXPIRED"):
        raise HTTPException(status_code=409, detail="Only failed or expired emails can be retried.")
    row.status = "PENDING"
    row.attempts = 0
    row.next_attempt_at = _now()
    row.created_at = _now()  # so the age check does not expire it again at once
    await db.commit()
    alerts_worker_module.alerts_worker.kick()
    return _row(row)
