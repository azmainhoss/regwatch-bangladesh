"""Search across all circulars: title, reference number and the text of every page.

Method: a case-insensitive substring (LIKE) match, one query word at a time, all words must
appear. It is used instead of SQLite FTS5 because
  * the same code runs on SQLite (local) and PostgreSQL (hosted), with no second index to keep in sync;
  * pages change in many places (re-extraction, page-image reading, manual reading import, human
    corrections), and an index that misses one of them would silently hide a circular;
  * Bangla text is matched as plain characters, with no tokeniser deciding where a word ends
    (FTS5's default tokeniser splits Bangla words at their vowel signs).
The library is a few thousand pages, so a scan is fast. Each hit carries up to 3 snippets cut
straight out of the stored page text.

Access follows documents/access.py: the shared library for everyone, private uploads for their owner
only, and synthetic fixtures never.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.modules.documents.access import visible_documents_condition
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.schemas import SearchHit, SearchResponse, SearchSnippet
from backend.app.modules.documents.synthetic import synthetic_sql_condition
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import InstitutionDepartment

MAX_TERMS = 8
SNIPPETS_PER_DOCUMENT = 3
SNIPPET_LENGTH = 200
SNIPPET_LEAD = 60  # characters of context kept before the first match

# Letters, digits and the Bangla block (its vowel signs are not "word" characters in Python's \w).
_WORD = re.compile(r"[\wঀ-৿]+")


def query_terms(query: str) -> List[str]:
    """The distinct words of a search query, in order, without duplicates (case-insensitively)."""
    seen: List[str] = []
    for word in _WORD.findall(query or ""):
        if word.lower() not in (s.lower() for s in seen):
            seen.append(word)
    return seen[:MAX_TERMS]


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def page_text_expression():
    """The text a reader sees for a page: the cleaned text, else the raw text (same rule as the API)."""
    cleaned = DocumentPage.cleaned_text
    return case((and_(cleaned.isnot(None), cleaned != ""), cleaned), else_=DocumentPage.raw_text)


def page_matches_condition(terms: Sequence[str]):
    text = page_text_expression()
    return and_(*[text.ilike(_like(t), escape="\\") for t in terms])


def meta_matches_condition(terms: Sequence[str]):
    return and_(*[
        or_(
            Document.title.ilike(_like(t), escape="\\"),
            func.coalesce(Document.title_bn, "").ilike(_like(t), escape="\\"),
            func.coalesce(Document.reference_number, "").ilike(_like(t), escape="\\"),
        )
        for t in terms
    ])


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def make_snippet(text: str, terms: Sequence[str]) -> Dict[str, Any]:
    """Cuts about 200 characters of the page text around the best place the words occur.

    The snippet is always an exact substring of `text`. `matches` holds [start, end) offsets of
    every query word inside the snippet, counted in UTF-16 units so a browser can slice with them.
    """
    pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    found = [m for _, m in zip(range(300), pattern.finditer(text))]
    if not found:
        start = 0
    else:
        best_start, best_score = found[0].start(), -1
        for m in found:
            window_start = max(0, m.start() - SNIPPET_LEAD)
            window = text[window_start:window_start + SNIPPET_LENGTH].lower()
            score = sum(1 for t in terms if t.lower() in window)
            if score > best_score:
                best_start, best_score = m.start(), score
            if score == len(terms):
                break
        start = max(0, best_start - SNIPPET_LEAD)
    end = min(len(text), start + SNIPPET_LENGTH)

    # Move the cut points to a space so words are not sliced, but never past a match.
    first_match = next((m.start() for m in pattern.finditer(text, start, end)), end)
    if start > 0:
        nudge = text.find(" ", start, min(first_match, start + 20))
        if nudge != -1:
            start = nudge + 1
    if end < len(text):
        nudge = text.rfind(" ", max(start, end - 20), end)
        last_end = max((m.end() for m in pattern.finditer(text, start, end)), default=start)
        if nudge != -1 and nudge >= last_end:
            end = nudge
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1

    snippet = text[start:end]
    matches: List[List[int]] = []
    for m in pattern.finditer(snippet):
        matches.append([_utf16_len(snippet[:m.start()]), _utf16_len(snippet[:m.end()])])
    return {
        "text": snippet,
        "matches": matches,
        "starts_mid_text": start > 0,
        "ends_mid_text": end < len(text),
    }


async def search_documents(
    db: AsyncSession,
    user: Optional[User],
    query: str,
    department: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    terms = query_terms(query)
    if not terms or sum(len(t) for t in terms) < 2:
        return SearchResponse(query=query or "", terms=[], total=0, limit=limit, offset=offset, results=[])

    live_version = DocumentVersion.status != "SUPERSEDED"
    page_match = page_matches_condition(terms)
    has_page_match = exists(
        select(1)
        .select_from(DocumentPage)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .where(DocumentVersion.document_id == Document.id, live_version, page_match)
    )

    conditions = [
        visible_documents_condition(user),
        ~synthetic_sql_condition(),
        or_(meta_matches_condition(terms), has_page_match),
    ]
    dept = (department or "").strip()
    if dept and dept.upper() != "ALL":
        conditions.append(or_(
            Document.department_id.in_(select(InstitutionDepartment.id).where(func.upper(InstitutionDepartment.code) == dept.upper())),
            func.coalesce(Document.reference_number, "").ilike(_like(dept), escape="\\"),
        ))
    if year_from:
        conditions.append(Document.publication_date >= date(year_from, 1, 1))
    if year_to:
        conditions.append(Document.publication_date <= date(year_to, 12, 31))
    if doc_type and doc_type.strip():
        conditions.append(Document.document_type == doc_type.strip().upper())
    if status and status.strip():
        wanted = status.strip().upper()
        if wanted == "PUBLISHED":
            conditions.append(Document.publication_status.like("PUBLISHED%"))
        else:
            conditions.append(Document.publication_status == wanted)

    total = (await db.execute(select(func.count()).select_from(Document).where(*conditions))).scalar_one()
    docs = (
        await db.execute(
            select(Document)
            .options(selectinload(Document.department))
            .where(*conditions)
            .order_by(Document.publication_date.desc(), Document.created_at.desc(), Document.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    if not docs:
        return SearchResponse(query=query, terms=terms, total=total, limit=limit, offset=offset, results=[])
    doc_ids = [d.id for d in docs]

    # Up to 3 matching pages per document, in page order.
    rank = func.row_number().over(
        partition_by=DocumentVersion.document_id,
        order_by=(DocumentPage.page_number, DocumentVersion.version_number),
    )
    ranked = (
        select(DocumentPage.id.label("page_id"), rank.label("rank"))
        .select_from(DocumentPage)
        .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
        .where(DocumentVersion.document_id.in_(doc_ids), live_version, page_match)
        .subquery()
    )
    page_rows: List[Tuple[DocumentPage, Any, str]] = (
        await db.execute(
            select(DocumentPage, DocumentVersion.document_id, DocumentVersion.language)
            .join(ranked, ranked.c.page_id == DocumentPage.id)
            .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
            .where(ranked.c.rank <= SNIPPETS_PER_DOCUMENT)
            .order_by(DocumentPage.page_number)
        )
    ).all()
    counts = dict(
        (
            await db.execute(
                select(DocumentVersion.document_id, func.count(DocumentPage.id))
                .select_from(DocumentPage)
                .join(DocumentVersion, DocumentVersion.id == DocumentPage.document_version_id)
                .where(DocumentVersion.document_id.in_(doc_ids), live_version, page_match)
                .group_by(DocumentVersion.document_id)
            )
        ).all()
    )

    snippets: Dict[str, List[SearchSnippet]] = {}
    for page, document_id, language in page_rows:
        text = page.cleaned_text or page.raw_text or ""
        if not text:
            continue
        snippets.setdefault(str(document_id), []).append(
            SearchSnippet(
                page_number=page.page_number,
                version_id=page.document_version_id,
                language=language or "en",
                **make_snippet(text, terms),
            )
        )

    lowered = [t.lower() for t in terms]
    results: List[SearchHit] = []
    for d in docs:
        meta = " ".join([d.title or "", d.title_bn or "", d.reference_number or ""]).lower()
        results.append(
            SearchHit(
                document_id=d.id,
                reference_number=d.reference_number,
                title=d.title,
                title_bn=d.title_bn,
                publication_date=d.publication_date,
                publication_status=d.publication_status,
                document_type=d.document_type,
                department_code=d.department.code if d.department else None,
                current_version_id=d.current_version_id,
                is_private=d.owner_user_id is not None,
                title_match=all(t in meta for t in lowered),
                matching_pages=int(counts.get(d.id, 0)),
                snippets=snippets.get(str(d.id), []),
            )
        )
    return SearchResponse(query=query, terms=terms, total=total, limit=limit, offset=offset, results=results)
