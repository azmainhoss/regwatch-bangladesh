"""The once-a-day emails: the daily update of new circulars for everyone, and a digest of waiting work alerts."""
import re
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


async def new_circulars(db: AsyncSession, start: datetime, end: datetime) -> List:
    """Shared circulars that came into the library between start and end (by when they were added), published in
    the last 7 days, newest first, as brand.DigestCircular. Old archive circulars loaded in bulk are not "new"."""
    from backend.app.modules.alerts import brand, reader_mail
    from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
    from backend.app.modules.documents.access import shared_documents_condition
    from backend.app.modules.documents.models import Document
    from backend.app.modules.documents.synthetic import synthetic_sql_condition
    from backend.app.modules.library.public import INDEXABLE, path_index

    docs = (await db.execute(
        select(Document).where(
            shared_documents_condition(), ~synthetic_sql_condition(),
            Document.created_at >= start, Document.created_at < end,
            Document.publication_date >= (end - timedelta(days=7)).date(),
        ).order_by(Document.publication_date.desc(), Document.created_at.desc())
    )).scalars().all()
    idx = await path_index(db, fresh=True)
    base = reader_mail.base_url()
    items = []
    for d in docs:
        point = None
        if d.publication_status in INDEXABLE and d.current_version_id:
            claim = (await db.execute(
                select(AnalysisClaim)
                .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
                .where(DocumentAnalysis.document_version_id == d.current_version_id, AnalysisClaim.kind == "SUMMARY_POINT",
                       AnalysisClaim.check_status.in_(("PASSED", "APPROVED", "FIXED")))
                .order_by(DocumentAnalysis.created_at.desc(), AnalysisClaim.order_index).limit(1)
            )).scalars().first()
            point = ((claim.fields or {}).get("text") if claim else None) or None
        hit = idx["by_id"].get(str(d.id))
        url = f"{base}{hit[0]}" if hit else f"{base}/dashboard?doc={d.id}"
        title = templates.clip(re.sub(r"^[^:]{0,80}\bNo\.?\s*[0-9]+[^:]*:\s*", "", d.title or "").rstrip(".") or d.title, 200)
        items.append(brand.DigestCircular(reference=d.reference_number or "Circular", title=title,
                                          date=templates.fmt_date(d.publication_date), url=url, point=point))
    return items


def _window_start(now: datetime) -> datetime:
    start = now - timedelta(hours=24)
    if settings.ALERTS_DIGEST_SINCE:
        try:
            since = datetime.fromisoformat(str(settings.ALERTS_DIGEST_SINCE).replace("Z", "+00:00"))
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            start = max(start, since)
        except ValueError:
            pass
    return start


async def build_daily_updates(db: AsyncSession, now: datetime, local: datetime) -> int:
    """Every day, to every registered person who has not unsubscribed: how many circulars came in the last 24 hours,
    each listed (owner, 2026-11-25). Nothing is sent on a day with none (owner, 2026-11-27). Their new-circular alerts are marked emailed so
    they are not repeated in another digest. Does not commit."""
    from backend.app.modules.alerts import brand, reader_mail

    today = local.date().isoformat()
    items = await new_circulars(db, _window_start(now), now)
    if not items:
        return 0  # No email on a day with no new circulars (owner, 2026-11-27).
    day = f"{local.strftime('%A')} {local.day} {local.strftime('%B %Y')}"
    users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    pref_map = await prefs.load_many(db, [str(u.id) for u in users])
    made = 0
    for user in users:
        if not user.email:
            continue
        pref = pref_map.get(str(user.id))
        if prefs.channel_for(pref, "library")[1] == "OFF":
            continue
        key = f"daily:{user.id}:{today}"
        if (await db.execute(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == key))).first():
            continue
        email = brand.daily_digest(reader_mail.base_url(), day, items, reader_mail.unsubscribe_page_url(user.id))
        db.add(EmailOutbox(
            user_id=user.id, organization_id=None, to_address=user.email, kind="DIGEST", dedupe_key=key,
            notification_ids=[], subject=email.subject, text_body=email.text, html_body=email.html,
            status="PENDING", attempts=0, next_attempt_at=now,
        ))
        # The same circulars as inbox alerts: counted as emailed, so no second digest repeats them.
        for r in (await db.execute(select(AN).where(
            AN.user_id == user.id, AN.kind == "CIRCULAR_PUBLISHED", AN.email_mode == "DIGEST", AN.emailed_at.is_(None),
        ))).scalars():
            r.emailed_at = now
        await db.flush()
        made += 1
    return made


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
    # 1. The daily update of new circulars, to everyone subscribed.
    made_daily = await build_daily_updates(db, now, local)
    # 2. Work alerts (bank registers, admin queues) that wait for a digest, as before.
    since = now - timedelta(days=7)
    if settings.ALERTS_DIGEST_SINCE:
        try:
            start = datetime.fromisoformat(str(settings.ALERTS_DIGEST_SINCE).replace("Z", "+00:00"))
            since = max(since, start if start.tzinfo else start.replace(tzinfo=timezone.utc))
        except ValueError:
            pass
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
        # New circulars go in the daily update (build_daily_updates); only work alerts are left here.
        rows = [r for r in rows if r.kind != "CIRCULAR_PUBLISHED"]
        if not rows:
            continue
        admin: List = []
        banks: Dict[str, List] = {}
        for r in rows:
            line = (r.title, r.link)
            if r.organization_id:
                banks.setdefault(orgs.get(str(r.organization_id), "Your bank"), []).append(line)
            elif r.kind == "ADMIN_QUEUE":
                admin.append(line)
        sections = []
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
    return made + made_daily
