"""The review queue: held points waiting for a person, in the order they should be looked at (spec 5.2, 6.2).

Only the latest analysis of each circular counts. Private uploads of other people never show here.
`review_items` answers `GET /claims/review`; `review_counts` answers `GET /claims/review/counts`.
"""
import base64
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import aliased, selectinload

from backend.app.core.config import settings
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import status as S
from backend.app.modules.claims import view
from backend.app.modules.claims.checks import _page_of
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.compliance import rules
from backend.app.modules.documents.models import Document, DocumentVersion

REQUIRED, OPTIONAL = S.REQUIRED, S.OPTIONAL
FAR = date.max.toordinal()
MAX_SENTENCE_CHARS = 1500


def _latest_analysis_filter():
    """A condition that keeps only the newest analysis of each circular's current file."""
    newer = aliased(DocumentAnalysis)
    newest = (
        select(newer.id)
        .where(newer.document_version_id == Document.current_version_id)
        .order_by(newer.created_at.desc())
        .limit(1)
        .correlate(Document)
        .scalar_subquery()
    )
    return DocumentAnalysis.id == newest


def _readable_by(user):
    return or_(Document.owner_user_id.is_(None), Document.owner_user_id == user.id)


async def latest_claims(db, user, queue: Optional[str] = None, document_ids: Optional[List[Any]] = None) -> List[Tuple[AnalysisClaim, Document]]:
    """(claim, circular) for every point of the newest analyses. `queue` keeps only points waiting in that queue."""
    stmt = (
        select(AnalysisClaim, Document)
        .join(DocumentAnalysis, DocumentAnalysis.id == AnalysisClaim.analysis_id)
        .join(Document, Document.current_version_id == DocumentAnalysis.document_version_id)
        .where(_latest_analysis_filter(), _readable_by(user), Document.publication_status.notin_(S.PROTECTED_DOCUMENT_STATUSES))
        .options(selectinload(AnalysisClaim.citations))
    )
    if queue:
        stmt = stmt.where(
            AnalysisClaim.review_queue == queue,
            AnalysisClaim.check_status.in_((S.WAITING_FOR_PERSON, S.NOT_SHOWN)),
        )
    if document_ids is not None:
        stmt = stmt.where(Document.id.in_(document_ids))
    return [(c, d) for c, d in (await db.execute(stmt)).all()]


# ---------------------------------------------------------------------------
# Order and cursor
# ---------------------------------------------------------------------------
def _ts(value) -> float:
    try:
        return float(value.timestamp()) if value is not None else 0.0
    except Exception:
        return 0.0


def sort_key(claim: AnalysisClaim, doc: Document, queue: str, today: date) -> List[Any]:
    """REQUIRED: high-stakes first, then the soonest deadline, then the oldest. OPTIONAL: newest circular first."""
    if queue == REQUIRED:
        upcoming = [d.toordinal() for d in S.own_dates(claim) if d >= today]
        return [0 if claim.is_high_stakes else 1, min(upcoming) if upcoming else FAR, _ts(claim.created_at), str(claim.id)]
    published = doc.publication_date.toordinal() if doc.publication_date else 0
    return [-published, int(claim.order_index or 0), _ts(claim.created_at), str(claim.id)]


def encode_cursor(key: List[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode("utf-8")).decode("ascii")


def decode_cursor(value: Optional[str]) -> Optional[List[Any]]:
    if not value:
        return None
    try:
        key = json.loads(base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8"))
        return key if isinstance(key, list) and len(key) == 4 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# One review row
# ---------------------------------------------------------------------------
async def _versions(db, doc_ids: List[Any]) -> Dict[str, DocumentVersion]:
    version_ids = {d for d in doc_ids}
    if not version_ids:
        return {}
    rows = (
        await db.execute(
            select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id.in_(version_ids))
        )
    ).scalars().all()
    return {str(v.id): v for v in rows}


def _index_of(version: DocumentVersion) -> SentenceIndex:
    from backend.app.modules.analysis.service import pages_payload_for

    return SentenceIndex.build(pages_payload_for(version))


def _evidence_pages(claim: AnalysisClaim) -> List[int]:
    pages: List[int] = []
    for ids in (claim.evidence or {}).values():
        for sid in ids or []:
            n = _page_of(sid)
            if n not in pages:
                pages.append(n)
    return sorted(pages)


async def _misreads(db, claims: List[AnalysisClaim], versions: Dict[str, DocumentVersion], docs: Dict[str, Document]) -> Dict[str, str]:
    """Claim id -> the second reading of its first misread sentence."""
    wanted: Dict[Tuple[str, str], str] = {}
    for c in claims:
        doc = docs.get(str(c.id))
        version = versions.get(str(doc.current_version_id)) if doc is not None else None
        if version is None:
            continue
        by_number = {p.page_number: p for p in version.pages}
        for ids in (c.evidence or {}).values():
            for sid in ids or []:
                page = by_number.get(_page_of(sid))
                if page is not None:
                    wanted[(str(page.id), sid)] = str(c.id)
    if not wanted:
        return {}
    rows = (
        await db.execute(
            select(QuoteReadingCheck).where(
                QuoteReadingCheck.status == "MISREAD", QuoteReadingCheck.page_id.in_({k[0] for k in wanted})
            )
        )
    ).scalars().all()
    out: Dict[str, str] = {}
    for r in rows:
        claim_id = wanted.get((str(r.page_id), r.sentence_id))
        reads = r.reads if isinstance(r.reads, list) else []
        texts = [x.get("text") for x in reads if isinstance(x, dict) and x.get("text")]
        if claim_id and texts and claim_id not in out:
            out[claim_id] = str(texts[-1])
    return out


async def build_review_rows(db, user, pairs: List[Tuple[AnalysisClaim, Document]]) -> List[Dict[str, Any]]:
    if not pairs:
        return []
    versions = await _versions(db, [d.current_version_id for _c, d in pairs if d.current_version_id])
    docs_by_claim = {str(c.id): d for c, d in pairs}
    claims = [c for c, _d in pairs]
    pages_map: Dict[str, int] = {}
    for v in versions.values():
        for p in v.pages:
            pages_map[str(p.id)] = p.page_number
    targets = await view._link_targets(db, [c for c in claims if c.kind == "LINK"], user)
    misread = await _misreads(db, claims, versions, docs_by_claim)
    indexes: Dict[str, SentenceIndex] = {}

    rows: List[Dict[str, Any]] = []
    for claim, doc in pairs:
        version = versions.get(str(doc.current_version_id))
        item = view._item(claim, pages_map, targets, True)
        cited = _evidence_pages(claim) or [1]
        page_number = item.get("page_number") or cited[0]
        page_row = None
        sentences: List[Dict[str, Any]] = []
        if version is not None:
            page_row = next((p for p in version.pages if p.page_number == page_number), None)
            index = indexes.get(str(version.id))
            if index is None:
                index = indexes[str(version.id)] = _index_of(version)
            for n in cited:
                for sid in index.order.get(n, []):
                    sentences.append({"sentence_id": sid, "page_number": n, "text": index.sentences[sid].text.strip()[:MAX_SENTENCE_CHARS]})
        rows.append(
            {
                "claim": item,
                "circular": {"id": str(doc.id), "reference_number": doc.reference_number, "title": doc.title},
                "page": {"id": str(page_row.id), "page_number": page_number} if page_row is not None else None,
                "version_id": str(version.id) if version is not None else None,
                "second_reading": misread.get(str(claim.id)),
                "sentences": sentences,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# The two endpoints' answers
# ---------------------------------------------------------------------------
async def review_items(db, user, queue: str, limit: int = 20, after: Optional[str] = None) -> Dict[str, Any]:
    today = rules.today_dhaka()
    pairs = await latest_claims(db, user, queue=queue)
    keyed = sorted(((sort_key(c, d, queue, today), c, d) for c, d in pairs), key=lambda t: tuple(t[0]))
    cursor = decode_cursor(after)
    if cursor is not None:
        keyed = [t for t in keyed if tuple(t[0]) > tuple(cursor)]
    page = keyed[: max(1, min(limit, 50))]
    items = await build_review_rows(db, user, [(c, d) for _k, c, d in page])
    for row, (key, _c, _d) in zip(items, page):
        row["cursor"] = encode_cursor(key)
    more = len(keyed) > len(page)
    return {"queue": queue, "items": items, "next": items[-1]["cursor"] if more and items else None, "total": len(pairs)}


async def review_point(db, user, claim_id) -> Dict[str, Any]:
    """One point by its id (for a link from the circular page). It is returned even when it was decided already,
    so the screen can say so. None when it does not exist or its circular is not readable."""
    from backend.app.modules.claims import decide

    claim = (
        await db.execute(select(AnalysisClaim).options(selectinload(AnalysisClaim.citations)).where(AnalysisClaim.id == claim_id))
    ).scalars().first()
    if claim is None:
        return {"queue": None, "items": [], "next": None, "total": 0}
    doc = await decide.document_of(db, claim)
    if doc is None or (doc.owner_user_id is not None and doc.owner_user_id != user.id):
        return {"queue": None, "items": [], "next": None, "total": 0}
    rows = await build_review_rows(db, user, [(claim, doc)])
    for row in rows:
        row["cursor"] = encode_cursor(sort_key(claim, doc, claim.review_queue or OPTIONAL, rules.today_dhaka()))
    return {"queue": claim.review_queue, "items": rows, "next": None, "total": len(rows)}


async def review_counts(db, user) -> Dict[str, Any]:
    today = rules.today_dhaka()
    pairs = await latest_claims(db, user)
    required = sum(1 for c, _d in pairs if c.review_queue == REQUIRED and c.check_status in (S.WAITING_FOR_PERSON, S.NOT_SHOWN))
    optional = sum(1 for c, _d in pairs if c.review_queue == OPTIONAL and c.check_status in (S.WAITING_FOR_PERSON, S.NOT_SHOWN))
    checking = sum(1 for c, _d in pairs if c.check_status == S.CHECKING)

    # New circulars that were analysed and have nothing to show.
    by_doc: Dict[str, List[AnalysisClaim]] = {}
    docs: Dict[str, Document] = {}
    for c, d in pairs:
        docs[str(d.id)] = d
        if c.kind != "PROVISION":
            by_doc.setdefault(str(d.id), []).append(c)
    since = today - timedelta(days=settings.CLAIM_NEW_CIRCULAR_DAYS)
    analysed = (
        await db.execute(
            select(Document)
            .join(DocumentAnalysis, DocumentAnalysis.document_version_id == Document.current_version_id)
            .where(
                _readable_by(user),
                Document.publication_status.notin_(S.PROTECTED_DOCUMENT_STATUSES),
                Document.publication_date >= since,
            )
            .distinct()
        )
    ).scalars().all()
    empty: List[Dict[str, Any]] = []
    for d in sorted(analysed, key=lambda x: x.publication_date or date.min, reverse=True):
        counts = S.counts(by_doc.get(str(d.id), []))
        if counts["shown"] == 0 and counts["checking"] == 0:
            empty.append({"id": str(d.id), "reference_number": d.reference_number, "title": d.title})
    return {"required": required, "optional": optional, "checking": checking, "empty_circulars": empty[:50]}
