"""Public circular pages for search engines and shared links (SEO, owner-approved 2026-11-24).

Every shared circular gets one readable address:  /circular/<department>/<number>-<year>-<title-words>
for example /circular/brpd/49-2024-transfer-of-jute-sector-outstanding-loans-to-block-account.

- Only circulars with an AI-verified analysis are indexable (in the sitemap, no `noindex`). The rest still open at
  their address, marked `noindex`, so links work without flooding search engines with thin pages.
- No login is needed: only shared (not private) library circulars are served, with the reader-safe fields the
  dashboard already shows to visitors (claims/view.py).
"""
import re
import time
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.documents.access import shared_documents_condition
from backend.app.modules.documents.models import Document
from backend.app.modules.documents.synthetic import synthetic_sql_condition
from backend.app.modules.institutions.models import InstitutionDepartment

router = APIRouter(prefix="/public", tags=["Public circular pages"])

# Circulars whose analysis passed the automated checks ("AI verified" for readers).
INDEXABLE = {"PUBLISHED_MACHINE_VERIFIED", "PUBLISHED_HUMAN_REVIEWED", "AWAITING_REVIEW"}

_NUMBER = re.compile(r"No\.?\s*([0-9]+)(?:\s*[/-]\s*((?:19|20)[0-9]{2}))?", re.I)
_TITLE_REF = re.compile(r"^[^:]{0,80}\bNo\.?\s*[0-9]+(?:\s*[/-]\s*[0-9]{2,4})?\s*[:.\-–]\s*", re.I)
_FILLER = {"regarding", "re", "about", "the", "a", "an", "of", "on", "in", "for", "and", "to", "with", "by", "at", "from"}
_MAX_WORDS = 8


def _ascii_words(text: str) -> List[str]:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", text)


def dept_code(doc: Document, dept: Optional[str]) -> str:
    """BRPD, FEPD, ...: from the department table, else the first word of the reference ("BRPD-1 ..." -> brpd)."""
    if dept:
        return "-".join(_ascii_words(dept)) or "bb"
    words = _ascii_words((doc.reference_number or "").split(" ")[0].split("-")[0])
    return words[0] if words else "bb"


def number_part(doc: Document) -> str:
    """"49-2024": the circular's number and year (the publication year when the reference has none)."""
    m = _NUMBER.search(doc.reference_number or "")
    year = (m.group(2) if m and m.group(2) else None) or (str(doc.publication_date.year) if doc.publication_date else "")
    num = (m.group(1).lstrip("0") or "0") if m else ""
    return "-".join(p for p in (num, year) if p) or "circular"


def title_part(doc: Document) -> str:
    title = _TITLE_REF.sub("", doc.title or "", count=1)
    words = _ascii_words(title)
    # Drop a leading filler word ("Regarding ...") and keep the first few meaningful words.
    while words and words[0] in _FILLER:
        words = words[1:]
    words = words[:_MAX_WORDS]
    while words and words[-1] in _FILLER:
        words = words[:-1]
    return "-".join(words)


def path_of(doc: Document, dept: Optional[str]) -> str:
    slug = "-".join(p for p in (number_part(doc), title_part(doc)) if p)
    return f"/circular/{dept_code(doc, dept)}/{slug}"


# ---------------------------------------------------------------------------------------------- the path index

_INDEX_TTL = 600.0
_index: Dict[str, Any] = {"at": 0.0, "by_path": {}, "by_id": {}, "by_prefix": {}}


async def _build_index(db: AsyncSession) -> Dict[str, Any]:
    rows = (
        await db.execute(
            select(Document, InstitutionDepartment.code)
            .outerjoin(InstitutionDepartment, InstitutionDepartment.id == Document.department_id)
            .where(shared_documents_condition(), ~synthetic_sql_condition())
            .order_by(Document.publication_date, Document.created_at, Document.id)
        )
    ).all()
    by_path: Dict[str, str] = {}
    by_id: Dict[str, Tuple[str, bool, Optional[date]]] = {}
    by_prefix: Dict[str, List[str]] = {}
    for doc, dept in rows:
        path = path_of(doc, dept)
        if path in by_path:  # Two circulars with the same number, year and title words: the later one gets its id.
            path = f"{path}-{str(doc.id)[:6]}"
        by_path[path] = str(doc.id)
        by_id[str(doc.id)] = (path, doc.publication_status in INDEXABLE, doc.publication_date)
        prefix = f"{dept_code(doc, dept)}/{number_part(doc)}"
        by_prefix.setdefault(prefix, []).append(str(doc.id))
    return {"at": time.monotonic(), "by_path": by_path, "by_id": by_id, "by_prefix": by_prefix}


async def path_index(db: AsyncSession, fresh: bool = False) -> Dict[str, Any]:
    global _index
    if fresh or time.monotonic() - _index["at"] > _INDEX_TTL or not _index["by_id"]:
        _index = await _build_index(db)
    return _index


# ------------------------------------------------------------------------------------------------ endpoints


class PathEntry(BaseModel):
    path: str
    lastmod: Optional[date] = None


class PublicPoint(BaseModel):
    text: str
    page: Optional[int] = None
    verified: bool = True


class PublicCircular(BaseModel):
    id: str
    path: str
    indexable: bool
    reference_number: Optional[str] = None
    title: str
    title_bn: Optional[str] = None
    department: str
    publication_date: Optional[date] = None
    status_label: Optional[str] = None
    summary: List[PublicPoint] = []
    changes: List[PublicPoint] = []
    requirements: List[PublicPoint] = []
    dates: List[PublicPoint] = []
    applies_to: List[PublicPoint] = []
    exemptions: List[PublicPoint] = []
    pages: int = 0


@router.get("/circulars/paths", response_model=List[PathEntry])
async def circular_paths(db: AsyncSession = Depends(get_async_db)):
    """The indexable circular addresses, for the sitemap."""
    idx = await path_index(db)
    out = [PathEntry(path=p, lastmod=d) for (p, ok, d) in idx["by_id"].values() if ok]
    out.sort(key=lambda e: (e.lastmod or date.min), reverse=True)
    return out


@router.get("/circulars/by-id/{document_id}", response_model=PathEntry)
async def circular_path_by_id(document_id: str, db: AsyncSession = Depends(get_async_db)):
    idx = await path_index(db)
    hit = idx["by_id"].get(document_id)
    if not hit:
        raise HTTPException(status_code=404, detail="Circular not found")
    return PathEntry(path=hit[0], lastmod=hit[2])


def _text(kind: str, f: Dict[str, Any]) -> str:
    if kind == "OBLIGATION":
        title, desc = (f.get("title") or "").strip(), (f.get("description") or "").strip()
        return f"{title}: {desc}" if title and desc else (title or desc)
    if kind == "APPLIES_TO":
        return str(f.get("entity") or "").strip()
    if kind == "DATE":
        kind_word = str(f.get("date_kind") or "date").replace("_", " ").lower()
        return f"{kind_word.capitalize()}: {f.get('date')}" if f.get("date") else ""
    return str(f.get("text") or "").strip()


@router.get("/circulars/{dept}/{slug}", response_model=PublicCircular)
async def circular_by_path(dept: str, slug: str, db: AsyncSession = Depends(get_async_db)):
    """One circular by its readable address. A different spelling of the same number and year still finds it; the
    answer's `path` is then the address to redirect to."""
    from backend.app.modules.claims.view import build_view

    idx = await path_index(db)
    wanted = f"/circular/{dept.lower()}/{slug.lower()}"
    doc_id = idx["by_path"].get(wanted)
    if doc_id is None:
        # Old or shortened address: match on department + number-year when that is unique.
        m = re.match(r"^([0-9]+(?:-(?:19|20)[0-9]{2})?)", slug)
        cands = idx["by_prefix"].get(f"{dept.lower()}/{m.group(1)}", []) if m else []
        if len(cands) == 1:
            doc_id = cands[0]
    if doc_id is None:
        raise HTTPException(status_code=404, detail="Circular not found")
    doc = await db.get(Document, doc_id)
    if doc is None or doc.owner_user_id is not None:
        raise HTTPException(status_code=404, detail="Circular not found")
    path, indexable, _ = idx["by_id"][doc_id]

    view = await build_view(db, doc, None)
    out: Dict[str, List[PublicPoint]] = {k: [] for k in ("summary", "changes", "requirements", "dates", "applies_to", "exemptions")}
    for section, items in view.get("sections", {}).items():
        if section not in out:
            continue
        for it in items:
            text = _text(it.get("kind", ""), it.get("fields") or {})
            if text:
                out[section].append(PublicPoint(text=text, page=it.get("page_number"), verified=not it.get("check_page")))
    dept_row = await db.get(InstitutionDepartment, doc.department_id) if doc.department_id else None
    shown = view.get("counts", {}).get("shown", 0)
    status_label = None
    if doc.publication_status in INDEXABLE:
        status_label = "AI verified" if shown else "AI draft"
    elif doc.publication_status == "PUBLISHED_MACHINE_PROCESSED":
        status_label = "AI draft"
    pages = 0
    if doc.current_version_id:
        from sqlalchemy import func
        from backend.app.modules.documents.models import DocumentPage

        pages = (await db.execute(select(func.count()).select_from(DocumentPage).where(DocumentPage.document_version_id == doc.current_version_id))).scalar_one()
    return PublicCircular(
        id=str(doc.id),
        path=path,
        indexable=indexable and bool(out["summary"] or out["requirements"]),
        reference_number=doc.reference_number,
        title=_TITLE_REF.sub("", doc.title or "", count=1) or doc.title,
        title_bn=doc.title_bn,
        department=(dept_row.code if dept_row and dept_row.code else dept_code(doc, None).upper()),
        publication_date=doc.publication_date,
        status_label=status_label,
        pages=pages,
        **out,
    )
