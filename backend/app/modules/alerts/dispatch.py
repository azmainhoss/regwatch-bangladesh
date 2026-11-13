"""Turns pending alert events into per-person inbox rows (and instant email rows)."""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.alerts import mailer, prefs, recipients, templates
from backend.app.modules.alerts.kinds import KIND_GROUP
from backend.app.modules.alerts.models import AlertEvent, AlertNotification, EmailOutbox
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.models import User

MAX_EVENT_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _library_recipients(db: AsyncSession, ev: AlertEvent) -> Optional[Dict[str, object]]:
    """(user id -> preference row or None) for a new-circular event, or None when it must be suppressed."""
    doc = await db.get(Document, ev.document_id) if ev.document_id else None
    if doc is None or doc.owner_user_id is not None or not str(doc.publication_status or "").startswith("PUBLISHED"):
        return None
    p = ev.payload or {}
    haystack = " ".join([str(p.get("reference_number") or ""), str(p.get("title") or ""), str(p.get("title_bn") or "")])
    users = (await db.execute(select(User.id).where(User.is_active.is_(True)))).all()
    ids = [str(u[0]) for u in users]
    pref_rows = await prefs.load_many(db, ids)
    out = {}
    for uid in ids:
        row = pref_rows.get(uid)
        in_app, email = prefs.channel_for(row, "library")
        if not in_app and email == "OFF":
            continue
        if not prefs.library_matches(
            row, department_code=p.get("department_code"), document_type=p.get("document_type"), haystack=haystack,
        ):
            continue
        out[uid] = row
    return out


async def _event_recipients(db: AsyncSession, ev: AlertEvent) -> Optional[Dict[str, object]]:
    if ev.kind == "CIRCULAR_PUBLISHED":
        found = await _library_recipients(db, ev)
        if found is not None and ev.actor_user_id:
            found.pop(str(ev.actor_user_id), None)
        return found
    if ev.organization_id is not None:
        ids = await recipients.active_member_ids(db, ev.organization_id, ev.recipient_user_ids or [])
    elif ev.kind == "ADMIN_QUEUE":
        ids = set(await recipients.active_superuser_ids(db))
    else:
        ids = set(str(u) for u in (ev.recipient_user_ids or []))
    if ev.actor_user_id:
        ids.discard(str(ev.actor_user_id))
    rows = await prefs.load_many(db, ids)
    return {uid: rows.get(uid) for uid in ids}


async def _dispatch_one(db: AsyncSession, ev: AlertEvent) -> int:
    """Returns how many instant email rows were queued."""
    found = await _event_recipients(db, ev)
    if found is None:
        ev.status = "SUPPRESSED"
        ev.dispatched_at = _now()
        return 0
    group = KIND_GROUP[ev.kind]
    r = templates.render(ev.kind, ev.payload or {}, str(ev.organization_id) if ev.organization_id else None)
    if ev.kind == "ADMIN_QUEUE" and not found:
        ev.status = "DISPATCHED"
        ev.dispatched_at = _now()
        return 0
    have = set()
    if found:
        have = {str(x[0]) for x in (await db.execute(
            select(AlertNotification.user_id).where(
                AlertNotification.dedupe_key == ev.dedupe_key,
                AlertNotification.user_id.in_(list(found.keys())),
            )
        )).all()}
    users = {}
    if found:
        users = {str(u.id): u for u in (await db.execute(select(User).where(User.id.in_(list(found.keys()))))).scalars().all()}
    queued = 0
    can_email = mailer.email_configured()
    for uid, row in found.items():
        if uid in have:
            continue
        in_app, email = prefs.channel_for(row, group)
        if not in_app and email == "OFF":
            continue
        note = AlertNotification(
            user_id=uid, event_id=ev.id, organization_id=ev.organization_id, kind=ev.kind, group=group,
            dedupe_key=ev.dedupe_key, severity=r.severity, title=r.title[:300], body=r.body, detail=r.detail,
            link=r.link[:512], document_id=(ev.payload or {}).get("document_id"),
            quote_text=r.quote_text, quote_page_number=r.quote_page_number,
            quote_document_id=r.quote_document_id, in_app=in_app, email_mode=email,
        )
        db.add(note)
        await db.flush()
        user = users.get(uid)
        if can_email and email == "INSTANT" and user is not None and user.email:
            subject, text, html = templates.instant_email(r, settings.APP_PUBLIC_URL)
            db.add(EmailOutbox(
                user_id=uid, organization_id=ev.organization_id, to_address=user.email, kind="INSTANT",
                dedupe_key=f"instant:{note.id}", notification_ids=[str(note.id)], subject=subject,
                text_body=text, html_body=html, status="PENDING", attempts=0, next_attempt_at=_now(),
            ))
            queued += 1
    ev.status = "DISPATCHED"
    ev.dispatched_at = _now()
    return queued


async def dispatch_pending(db: AsyncSession, limit: int = 200) -> int:
    """Handles the oldest pending events. Does not commit; the caller does. Returns events handled."""
    events = list((await db.execute(
        select(AlertEvent).where(AlertEvent.status == "PENDING").order_by(AlertEvent.created_at, AlertEvent.id).limit(limit)
    )).scalars().all())
    handled = 0
    queued = 0
    for ev in events:
        ev_id, tries = ev.id, (ev.attempts or 0)
        try:
            async with db.begin_nested():
                queued += await _dispatch_one(db, ev)
            handled += 1
        except Exception as exc:
            tries += 1
            logger.warning("Alert event could not be handed out: %s", type(exc).__name__)
            await db.execute(update(AlertEvent).where(AlertEvent.id == ev_id).values(
                attempts=tries, last_error=mailer.redact(type(exc).__name__),
                status="FAILED" if tries >= MAX_EVENT_ATTEMPTS else "PENDING",
            ))
    if handled:
        await db.flush()
    if queued:
        try:
            from backend.app.modules.alerts.worker import alerts_worker
            alerts_worker.kick()
        except Exception:
            pass
    return handled
