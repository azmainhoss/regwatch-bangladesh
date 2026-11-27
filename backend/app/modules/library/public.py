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
from backend.app.modules.topics.models import DocumentTopic
from backend.app.modules.topics.taxonomy import TOPIC_BY_CODE, TOPICS

router = APIRouter(prefix="/public", tags=["Public circular pages"])

# Circulars whose analysis passed the automated checks ("Ready" for readers) are the only indexable ones (DECISIONS.md 16).
INDEXABLE = {"PUBLISHED_MACHINE_VERIFIED", "PUBLISHED_HUMAN_REVIEWED", "AWAITING_REVIEW"}

_NUMBER = re.compile(r"No\.?\s*([0-9]+)(?:\s*[/-]\s*((?:19|20)[0-9]{2}))?", re.I)
_TITLE_REF = re.compile(r"^[^:]{0,80}\bNo\.?\s*[0-9]+(?:\s*[/-]\s*[0-9]{2,4})?\s*[:.\-–]\s*", re.I)
_FILLER = {"regarding", "re", "about", "the", "a", "an", "of", "on", "in", "for", "and", "to", "with", "by", "at", "from"}
_MAX_WORDS = 8


_REF_IN_TITLE = re.compile(r"^([^:]{0,80}\bNo\.?\s*[0-9]+(?:\s*[/-]\s*[0-9]{2,4})?)\s*[:.\-–]", re.I)


def _reference_from_title(title: Optional[str]) -> Optional[str]:
    """"BRD Circular No. 04" from "BRD Circular No. 04: Regarding ..." when the reference field is empty."""
    m = _REF_IN_TITLE.match(title or "")
    return m.group(1).strip() if m else None


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
_index: Dict[str, Any] = {"at": 0.0, "by_path": {}, "by_id": {}, "by_prefix": {}, "items": []}


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
    items: List[Dict[str, Any]] = []
    topic_rows = (await db.execute(select(DocumentTopic.document_id, DocumentTopic.topic))).all()
    topics_of: Dict[str, List[str]] = {}
    for doc_id, topic in topic_rows:
        topics_of.setdefault(str(doc_id), []).append(topic)
    for doc, dept in rows:
        path = path_of(doc, dept)
        if path in by_path:  # Two circulars with the same number, year and title words: the later one gets its id.
            path = f"{path}-{str(doc.id)[:6]}"
        by_path[path] = str(doc.id)
        by_id[str(doc.id)] = (path, doc.publication_status in INDEXABLE, doc.publication_date)
        prefix = f"{dept_code(doc, dept)}/{number_part(doc)}"
        by_prefix.setdefault(prefix, []).append(str(doc.id))
        items.append(
            {
                "id": str(doc.id),
                "path": path,
                "dept": dept_code(doc, dept),
                "reference_number": doc.reference_number or _reference_from_title(doc.title),
                "title": _TITLE_REF.sub("", doc.title or "", count=1) or (doc.title or ""),
                "title_bn": doc.title_bn,
                "publication_date": doc.publication_date,
                "indexable": doc.publication_status in INDEXABLE,
                "topics": topics_of.get(str(doc.id), []),
            }
        )
    items.reverse()  # newest first
    return {"at": time.monotonic(), "by_path": by_path, "by_id": by_id, "by_prefix": by_prefix, "items": items}


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
    source_url: Optional[str] = None


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
        status_label = "Ready" if shown else "Analysing"
    elif doc.publication_status == "PUBLISHED_MACHINE_PROCESSED":
        status_label = "Analysing"
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
        source_url=doc.source_url if (doc.source_url or "").startswith("https://www.bb.org.bd/") else None,
        **out,
    )


# ------------------------------------------------------------------------------------------- hub pages (SEO)

# Full names of the Bangladesh Bank departments that issue most circulars. A department not listed shows its code.
DEPARTMENT_NAMES: Dict[str, str] = {
    "brpd": "Banking Regulation and Policy Department",
    "fepd": "Foreign Exchange Policy Department",
    "feod": "Foreign Exchange Operation Department",
    "dos": "Department of Off-site Supervision",
    "dfim": "Department of Financial Institutions and Markets",
    "psd": "Payment Systems Department",
    "dmd": "Debt Management Department",
    "smespd": "SME and Special Programmes Department",
    "acd": "Agricultural Credit Department",
    "acspd": "Agricultural Credit and Special Programs Department",
    "sfd": "Sustainable Finance Department",
    "bfiu": "Bangladesh Financial Intelligence Unit",
    "mpd": "Monetary Policy Department",
    "dcm": "Department of Currency Management",
    "gbcsrd": "Green Banking and CSR Department",
    "cib": "Credit Information Bureau",
    "dbi": "Department of Banking Inspection",
    "fe": "Foreign Exchange",
}
# A hub page needs this many analysed circulars, so search engines never see thin pages.
HUB_MIN_INDEXABLE = 3
HUB_LIMIT = 300


class HubLink(BaseModel):
    code: str
    name: str
    total: int
    analysed: int


class Hubs(BaseModel):
    departments: List[HubLink]
    topics: List[HubLink]
    years: List[HubLink]
    total: int
    analysed: int


class ListItem(BaseModel):
    path: str
    reference_number: Optional[str] = None
    title: str
    title_bn: Optional[str] = None
    department: str
    publication_date: Optional[date] = None
    analysed: bool
    topics: List[str] = []


class CircularList(BaseModel):
    kind: str
    code: str
    name: str
    name_bn: Optional[str] = None
    total: int
    analysed: int
    items: List[ListItem]
    indexable: bool


def _item(it: Dict[str, Any]) -> ListItem:
    return ListItem(
        path=it["path"],
        reference_number=it["reference_number"],
        title=it["title"],
        title_bn=it["title_bn"],
        department=it["dept"].upper(),
        publication_date=it["publication_date"],
        analysed=it["indexable"],
        topics=it["topics"],
    )


def _hubs_from(items: List[Dict[str, Any]]) -> Hubs:
    dept: Dict[str, List[int]] = {}
    topic: Dict[str, List[int]] = {}
    year: Dict[str, List[int]] = {}
    for it in items:
        ok = 1 if it["indexable"] else 0
        keys = [(dept, it["dept"])] + [(topic, t) for t in it["topics"]]
        if it["publication_date"]:
            keys.append((year, str(it["publication_date"].year)))
        for bucket, key in keys:
            c = bucket.setdefault(key, [0, 0])
            c[0] += 1
            c[1] += ok
    depts = [
        HubLink(code=k, name=DEPARTMENT_NAMES.get(k, k.upper()), total=v[0], analysed=v[1])
        for k, v in dept.items()
        if v[1] >= HUB_MIN_INDEXABLE and k != "bb"  # "bb": circulars whose department is unknown
    ]
    depts.sort(key=lambda h: -h.total)
    topics = [
        HubLink(code=t.code.lower().replace("_", "-"), name=t.label, total=topic[t.code][0], analysed=topic[t.code][1])
        for t in TOPICS
        if t.code in topic and t.code != "OTHER" and topic[t.code][1] >= HUB_MIN_INDEXABLE
    ]
    topics.sort(key=lambda h: -h.total)
    years = [HubLink(code=k, name=k, total=v[0], analysed=v[1]) for k, v in year.items() if v[1] >= HUB_MIN_INDEXABLE]
    years.sort(key=lambda h: h.code, reverse=True)
    return Hubs(
        departments=depts, topics=topics, years=years, total=len(items), analysed=sum(1 for i in items if i["indexable"])
    )


@router.get("/hubs", response_model=Hubs)
async def hubs(db: AsyncSession = Depends(get_async_db)):
    """Departments, subjects and years that have their own list page (only those with enough analysed circulars)."""
    return _hubs_from((await path_index(db))["items"])


def _topic_code(slug: str) -> Optional[str]:
    code = slug.upper().replace("-", "_")
    return code if code in TOPIC_BY_CODE and code != "OTHER" else None


@router.get("/lists/{kind}/{code}", response_model=CircularList)
async def circular_list(kind: str, code: str, db: AsyncSession = Depends(get_async_db)):
    """Circulars of one department (`dept/brpd`), subject (`topic/ecl`), year (`year/2026`) or the newest
    (`latest/all`), newest first. Analysed circulars are kept first when the list is capped."""
    items = (await path_index(db))["items"]
    code = code.lower()
    name_bn = None
    if kind == "dept":
        chosen = [i for i in items if i["dept"] == code]
        name = DEPARTMENT_NAMES.get(code, code.upper())
        name_bn = (
            await db.execute(
                select(InstitutionDepartment.name_bn).where(InstitutionDepartment.code == code.upper()).limit(1)
            )
        ).scalar()
    elif kind == "topic":
        t = _topic_code(code)
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        chosen = [i for i in items if t in i["topics"]]
        name = TOPIC_BY_CODE[t].label
    elif kind == "year":
        if not re.fullmatch(r"(19|20)[0-9]{2}", code):
            raise HTTPException(status_code=404, detail="Not found")
        chosen = [i for i in items if i["publication_date"] and str(i["publication_date"].year) == code]
        name = code
    elif kind == "latest":
        chosen = items
        name = "Latest"
    else:
        raise HTTPException(status_code=404, detail="Not found")
    if not chosen:
        raise HTTPException(status_code=404, detail="Not found")
    analysed = [i for i in chosen if i["indexable"]]
    rest = [i for i in chosen if not i["indexable"]]
    if kind == "latest":
        shown = chosen[:60]
    else:
        shown = analysed[:HUB_LIMIT] + rest[: max(0, HUB_LIMIT - len(analysed))]
        shown.sort(key=lambda i: (i["publication_date"] or date.min), reverse=True)
    return CircularList(
        kind=kind,
        code=code,
        name=name,
        name_bn=name_bn,
        total=len(chosen),
        analysed=len(analysed),
        items=[_item(i) for i in shown],
        indexable=len(analysed) >= HUB_MIN_INDEXABLE,
    )


@router.get("/related/{document_id}", response_model=List[ListItem])
async def related(document_id: str, db: AsyncSession = Depends(get_async_db)):
    """Up to 8 analysed circulars close to this one: same department and shared subjects first, newest first."""
    items = (await path_index(db))["items"]
    me = next((i for i in items if i["id"] == document_id), None)
    if not me:
        raise HTTPException(status_code=404, detail="Circular not found")
    mine = set(me["topics"]) - {"OTHER"}

    def score(i: Dict[str, Any]) -> int:
        return (2 if i["dept"] == me["dept"] else 0) + len(mine & set(i["topics"]))

    cands = [i for i in items if i["id"] != document_id and i["indexable"] and score(i) > 0]
    cands.sort(key=lambda i: (score(i), i["publication_date"] or date.min), reverse=True)
    return [_item(i) for i in cands[:8]]


@router.get("/topics-of/{document_id}", response_model=List[HubLink])
async def circular_topics(document_id: str, db: AsyncSession = Depends(get_async_db)):
    """The subject pages this circular belongs to (for links on its page)."""
    idx = await path_index(db)
    me = next((i for i in idx["items"] if i["id"] == document_id), None)
    if not me:
        raise HTTPException(status_code=404, detail="Circular not found")
    hub = {h.code for h in _hubs_from(idx["items"]).topics}
    out = []
    for t in me["topics"]:
        slug = t.lower().replace("_", "-")
        if slug in hub:
            out.append(HubLink(code=slug, name=TOPIC_BY_CODE[t].label, total=0, analysed=0))
    return out


# --- Home page grid (owner, 2026-11-28): this year's circulars by who they apply to and how urgent they are. ---

class GridCircular(BaseModel):
    id: str
    path: Optional[str] = None
    ref: Optional[str] = None
    title: str
    published: Optional[date] = None
    ents: List[str] = []
    mand: int = 0
    deadline: Optional[str] = None


class GridOut(BaseModel):
    year: int
    library: int
    circulars: List[GridCircular]


_GRID_CACHE: Dict[str, Any] = {"at": 0.0, "data": None}
_DUTY_TYPES = {"MANDATORY", "PROHIBITION", "REPORTING"}


@router.get("/grid", response_model=GridOut)
async def applies_grid(db: AsyncSession = Depends(get_async_db)):
    """Every shared circular published this year with: who it applies to (APPLIES_TO points), how many duties it has
    and its latest dated deadline. Cached 10 minutes; the home page sorts them per institution type in the browser."""
    import json as _json
    from sqlalchemy import func
    from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis

    if _GRID_CACHE["data"] is not None and time.time() - _GRID_CACHE["at"] < 600:
        return _GRID_CACHE["data"]
    year = date.today().year
    base = [shared_documents_condition(), ~synthetic_sql_condition()]
    library = (await db.execute(select(func.count()).select_from(Document).where(*base))).scalar_one()
    docs = (await db.execute(select(Document).where(*base, Document.publication_date >= date(year, 1, 1)))).scalars().all()
    vids = [d.current_version_id for d in docs if d.current_version_id]
    latest: Dict[Any, Any] = {}
    if vids:
        for vid, aid in (await db.execute(
            select(DocumentAnalysis.document_version_id, DocumentAnalysis.id)
            .where(DocumentAnalysis.document_version_id.in_(vids)).order_by(DocumentAnalysis.created_at)
        )).all():
            latest[vid] = aid
    per: Dict[Any, Dict[str, Any]] = {aid: {"ents": set(), "mand": 0, "deadline": None} for aid in latest.values()}
    if per:
        rows = await db.execute(
            select(AnalysisClaim.analysis_id, AnalysisClaim.kind, AnalysisClaim.fields)
            .where(AnalysisClaim.analysis_id.in_(list(per)), AnalysisClaim.kind.in_(["APPLIES_TO", "OBLIGATION"]))
        )
        for aid, kind, f in rows.all():
            f = _json.loads(f) if isinstance(f, str) else (f or {})
            p = per[aid]
            if kind == "APPLIES_TO" and re.fullmatch(r"[A-Z_]+", str(f.get("entity") or "")):
                p["ents"].add(f["entity"])
            elif kind == "OBLIGATION":
                if str(f.get("obligation_type") or "").upper() in _DUTY_TYPES:
                    p["mand"] += 1
                d = str(f.get("explicit_deadline") or f.get("deadline") or "")[:10]
                if re.fullmatch(r"\d{4}-\d\d-\d\d", d):
                    p["deadline"] = max(p["deadline"] or "", d)
    idx = await path_index(db)
    out = []
    for d in docs:
        p = per.get(latest.get(d.current_version_id), {"ents": set(), "mand": 0, "deadline": None})
        hit = idx["by_id"].get(str(d.id))
        out.append(GridCircular(
            id=str(d.id), path=hit[0] if hit else None, ref=d.reference_number or _reference_from_title(d.title),
            title=(_TITLE_REF.sub("", d.title or "", count=1) or d.title or "")[:160], published=d.publication_date,
            ents=sorted(p["ents"]), mand=p["mand"], deadline=p["deadline"],
        ))
    data = GridOut(year=year, library=library, circulars=out)
    _GRID_CACHE.update(at=time.time(), data=data)
    return data
