"""The once-a-day summary email."""
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.modules.alerts import mailer, prefs, templates
from backend.app.modules.alerts.inbox import visible_condition
from backend.app.modules.alerts.models import AlertNotification, EmailOutbox
from backend.app.modules.identity.models import User
from backend.app.modules.organizations.models import Organization

AN = AlertNotification


def _digest_time() -> time:
    try:
        h, m = str(settings.ALERTS_DIGEST_TIME).split(":")
        return time(int(h), int(m))
    except Exception:
        return time(10, 30)


async def build_digests(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Makes one summary email per person per Dhaka day, once Dhaka time passes ALERTS_DIGEST_TIME.
    Returns how many were queued. Does not commit."""
    if not mailer.email_configured():
        return 0
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(settings.MONITOR_TIMEZONE))
    if local.time() < _digest_time():
        return 0
    today = local.date().isoformat()
    since = now - timedelta(days=7)
    user_ids = [str(r[0]) for r in (await db.execute(
        select(AN.user_id).where(
            AN.email_mode == "DIGEST", AN.emailed_at.is_(None), AN.read_at.is_(None), AN.created_at >= since,
        ).distinct()
    )).all()]
    made = 0
    for uid in user_ids:
        key = f"digest:{uid}:{today}"
        if (await db.execute(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == key))).first():
            continue
        user = await db.get(User, uid)
        if user is None or not user.is_active or not user.email:
            continue
        pref = (await prefs.load_many(db, [uid])).get(uid)
        if pref is not None and not pref.email_enabled:
            continue
        rows = list((await db.execute(
            select(AN).where(
                visible_condition(user.id, user.is_superuser, in_app_only=False),
                AN.email_mode == "DIGEST", AN.emailed_at.is_(None), AN.read_at.is_(None), AN.created_at >= since,
            ).order_by(AN.created_at, AN.id)
        )).scalars().all())
        if not rows:
            continue
        org_ids = {r.organization_id for r in rows if r.organization_id}
        orgs: Dict[str, str] = {}
        if org_ids:
            orgs = {str(o.id): o.name for o in (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars()}
        library: List = []
        admin: List = []
        banks: Dict[str, List] = {}
        for r in rows:
            line = (r.title, r.link)
            if r.organization_id:
                banks.setdefault(orgs.get(str(r.organization_id), "Your bank"), []).append(line)
            elif r.kind == "ADMIN_QUEUE":
                admin.append(line)
            else:
                library.append(line)
        sections = []
        if library:
            sections.append(("New circulars", library))
        for name in sorted(banks):
            sections.append((name, banks[name]))
        if admin:
            sections.append(("Platform review queues", admin))
        subject, text, html = templates.digest_email(sections, len(rows), settings.APP_PUBLIC_URL)
        db.add(EmailOutbox(
            user_id=user.id, organization_id=None, to_address=user.email, kind="DIGEST", dedupe_key=key,
            notification_ids=[str(r.id) for r in rows], subject=subject, text_body=text, html_body=html,
            status="PENDING", attempts=0, next_attempt_at=now,
        ))
        for r in rows:
            r.emailed_at = now
        await db.flush()
        made += 1
    return made
