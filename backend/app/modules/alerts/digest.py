"""The once-a-day summary email."""
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


async def _branded_library_digest(db: AsyncSession, user, rows, local: datetime):
    """The owner-approved daily digest (brand.daily_digest) for a day that has only new circulars."""
    from backend.app.modules.alerts import brand, reader_mail
    from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
    from backend.app.modules.documents.models import Document
    from backend.app.modules.library.public import INDEXABLE, path_index

    ids = [r.document_id for r in rows if r.document_id]
    docs = {str(d.id): d for d in (await db.execute(select(Document).where(Document.id.in_(ids)))).scalars()} if ids else {}
    idx = await path_index(db)
    base = reader_mail.base_url()
    items = []
    for r in rows:
        d = docs.get(str(r.document_id)) if r.document_id else None
        if d is None:
            continue
        point = None
        verified = d.publication_status in INDEXABLE
        if verified and d.current_version_id:
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
                                          date=templates.fmt_date(d.publication_date), url=url, point=point, verified=verified))
    if not items:
        return None
    day = f"{local.strftime('%A')} {local.day} {local.strftime('%B %Y')}"
    return brand.daily_digest(base, day, items, reader_mail.unsubscribe_page_url(user.id))


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
    if settings.ALERTS_DIGEST_SINCE:
        try:
            start = datetime.fromisoformat(str(settings.ALERTS_DIGEST_SINCE).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            since = max(since, start)
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
        branded = None
        if library and not banks and not admin:
            branded = await _branded_library_digest(db, user, rows, local)
        if branded is not None:
            subject, text, html = branded.subject, branded.text, branded.html
        else:
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
