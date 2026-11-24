"""Summary screen: how much of the archive is read and analysed, and which new circulars were caught."""
import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.documents.access import get_document_reader
from backend.app.modules.identity.models import User

router = APIRouter(prefix="/summary", tags=["Summary"])
logger = logging.getLogger("regwatch")

# DECISIONS.md 14: circulars issued on or after this date, plus every Master Circular, are analysed before launch.
ANALYSIS_CUTOFF = "2024-11-14"

SHARED = ("coalesce(d.is_synthetic_fixture, 0) = 0 and d.owner_user_id is null "
          "and d.current_version_id is not null and d.source_url like '%bb.org.bd/%'")
ANALYSED = ("exists (select 1 from document_analyses a where a.document_version_id = d.current_version_id)")
CHECKED = "d.publication_status in ('PUBLISHED_MACHINE_VERIFIED', 'PUBLISHED_HUMAN_REVIEWED')"


class DayCount(BaseModel):
    day: str
    count: int


class CaughtCircular(BaseModel):
    title: str
    reference: Optional[str] = None
    published: Optional[str] = None
    state: str  # "added", "analysed", "waiting"
    document_id: Optional[str] = None


class SummaryRead(BaseModel):
    library_total: int
    first_year: Optional[int] = None
    last_date: Optional[str] = None
    pages_total: int
    pages_read: int
    target_total: int
    target_analysed: int
    target_checked: int
    target_cutoff: str
    target_recent: int
    target_older_master: int
    target_pages_total: int
    target_pages_read: int
    target_circulars_with_unread: int
    analysed_total: int
    caught_since: str
    caught_count: int
    caught_per_day: List[DayCount]
    caught: List[CaughtCircular]


def _day(v) -> Optional[str]:
    return str(v)[:10] if v else None


# The numbers cover only the shared library (the same for every reader), so one cached copy serves everyone.
# A request gets the cached copy at once; a copy older than STALE_AFTER is refreshed in the background.
STALE_AFTER = 60.0
_cache: Dict[int, Tuple[float, "SummaryRead"]] = {}
_refreshing: set = set()


async def _refresh(days: int) -> "SummaryRead":
    async with AsyncSessionLocal() as db:
        result = await _compute(db, days)
    _cache[days] = (time.monotonic(), result)
    return result


async def _refresh_quietly(days: int) -> None:
    try:
        await _refresh(days)
    except Exception as e:  # a failed refresh keeps the last good copy
        logger.warning(f"Summary refresh failed: {e}")
    finally:
        _refreshing.discard(days)


async def warm_summary_cache() -> None:
    """Called at startup so the first visit to the Summary screen is instant."""
    await _refresh_quietly(14)


@router.get("", response_model=SummaryRead)
async def get_summary(
    days: int = 14,
    current_user: Optional[User] = Depends(get_document_reader),
):
    # Internal progress page for the platform team (the screen is admin-only too).
    if current_user is None:
        raise HTTPException(status_code=401, detail="Sign in as an administrator.", headers={"WWW-Authenticate": "Bearer"})
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Administrators only.")
    days = max(1, min(days, 90))
    hit = _cache.get(days)
    if hit is None:
        return await _refresh(days)
    if time.monotonic() - hit[0] > STALE_AFTER and days not in _refreshing:
        _refreshing.add(days)
        asyncio.create_task(_refresh_quietly(days))
    return hit[1]


async def _compute(db: AsyncSession, days: int) -> "SummaryRead":
    q = lambda sql, **p: db.execute(text(sql), p)  # noqa: E731

    lib = (await q(f"select count(*), min(d.publication_date), max(d.publication_date) from documents d where {SHARED}")).one()
    pages = (await q(
        f"select count(*), sum(case when p.quality_status like 'SUCCESS%' then 1 else 0 end) "
        f"from document_pages p join documents d on p.document_version_id = d.current_version_id where {SHARED}")).one()
    target_where = f"{SHARED} and (d.publication_date >= :cut or lower(d.title) like '%master circular%')"
    tgt = (await q(
        f"select count(*), sum(case when {ANALYSED} then 1 else 0 end), sum(case when {CHECKED} then 1 else 0 end), "
        f"sum(case when d.publication_date >= :cut then 1 else 0 end) "
        f"from documents d where {target_where}", cut=ANALYSIS_CUTOFF)).one()
    tgt_pages = (await q(
        f"select count(*), sum(case when p.quality_status like 'SUCCESS%' then 1 else 0 end), "
        f"count(distinct case when p.quality_status not like 'SUCCESS%' then d.id end) "
        f"from document_pages p join documents d on p.document_version_id = d.current_version_id where {target_where}",
        cut=ANALYSIS_CUTOFF)).one()
    analysed_all = (await q(f"select count(*) from documents d where {SHARED} and {ANALYSED}")).scalar() or 0

    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = (await q(
        "select s.title, s.reference_number, s.publication_date, s.status, s.document_id, "
        "(select count(*) from documents d join document_analyses a on a.document_version_id = d.current_version_id "
        " where d.id = s.document_id) "
        "from source_discoveries s where s.publication_date >= :since "
        "and s.status in ('INGESTED', 'VALIDATED', 'APPROVED', 'DISCOVERED', 'DOWNLOAD_PENDING') "
        "order by s.publication_date desc, s.title", since=since)).all()

    seen = set()
    caught: List[CaughtCircular] = []
    per_day = {(date.fromisoformat(since) + timedelta(days=i)).isoformat(): 0 for i in range(days)}
    for title, ref, pub, st, doc_id, n_analyses in rows:
        key = (ref or title or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        day = _day(pub)
        if day in per_day:
            per_day[day] += 1
        state = "analysed" if n_analyses else ("added" if st == "INGESTED" else "waiting")
        caught.append(CaughtCircular(title=title or ref or "Untitled circular", reference=ref, published=day,
                                     state=state, document_id=str(doc_id) if doc_id else None))

    return SummaryRead(
        library_total=lib[0] or 0,
        first_year=int(str(lib[1])[:4]) if lib[1] else None,
        last_date=_day(lib[2]),
        pages_total=pages[0] or 0,
        pages_read=int(pages[1] or 0),
        target_total=tgt[0] or 0,
        target_analysed=int(tgt[1] or 0),
        target_checked=int(tgt[2] or 0),
        target_cutoff=ANALYSIS_CUTOFF,
        target_recent=int(tgt[3] or 0),
        target_older_master=(tgt[0] or 0) - int(tgt[3] or 0),
        target_pages_total=tgt_pages[0] or 0,
        target_pages_read=int(tgt_pages[1] or 0),
        target_circulars_with_unread=int(tgt_pages[2] or 0),
        analysed_total=int(analysed_all),
        caught_since=since,
        caught_count=len(caught),
        caught_per_day=[DayCount(day=k, count=v) for k, v in per_day.items()],
        caught=caught,
    )
