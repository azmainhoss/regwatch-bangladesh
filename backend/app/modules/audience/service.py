"""The "For you" flag: which circulars apply to a reader, from their institution type plus their own
"Applies to me" / "Not for me" marks. No AI; works off facts already stored for each circular.

Rules (owner, 2026-11-28):
- the institution type gives the starting point (an AD bank gets every circular for authorised dealers);
- one "Applies to me" teaches the circular's department, categories and audiences; later circulars sharing enough
  of them are flagged as similar;
- one "Not for me" never overrules the institution type: it takes repeated "Not for me" on the same kind;
- nothing is ever hidden: "Not for me" only drops the flag."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.audience.kinds import ALL, ENTITY_LABELS, INSTITUTION_TYPES, KNOWN_ENTITIES, ORG_TYPE_MAP, audiences_for
from backend.app.modules.audience.known import guess_institution
from backend.app.modules.audience.models import CircularMark, DocumentAudience
from backend.app.modules.audience.rules import derive
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.identity.models import User, UserProfile
from backend.app.modules.institutions.models import InstitutionDepartment
from backend.app.modules.organizations.models import Organization, OrganizationMember
from backend.app.modules.topics.models import DocumentTopic
from backend.app.modules.topics.taxonomy import TOPIC_BY_CODE

NONE = "NONE"  # stored when nothing was found, so the circular is not read again
# Which audience to name first in a reason: the most specific one.
_REASON_ORDER = [
    "ISLAMIC_BANK", "STATE_OWNED_BANK", "SPECIALIZED_BANK", "FOREIGN_BANK", "NBFI", "MOBILE_FINANCIAL_SERVICE",
    "PAYMENT_SERVICE_PROVIDER", "MONEY_CHANGER", "OFFSHORE_BANKING_UNIT", "AUTHORIZED_DEALER", "PRIVATE_COMMERCIAL_BANK",
    "SCHEDULED_BANK", "EXCHANGE_HOUSE", "MICROFINANCE_INSTITUTION",
]


# ---------------------------------------------------------------------------
# Who each circular applies to
# ---------------------------------------------------------------------------

async def _page_texts(db: AsyncSession, version_id) -> Tuple[str, str]:
    rows = (await db.execute(
        select(DocumentPage.page_number, DocumentPage.human_corrected_text, DocumentPage.cleaned_text, DocumentPage.raw_text)
        .where(DocumentPage.document_version_id == version_id, DocumentPage.page_number <= 3)
        .order_by(DocumentPage.page_number)
    )).all()
    texts = [(n, h or c or r or "") for n, h, c, r in rows]
    first = next((t for n, t in texts if n == 1), "")
    return first, " ".join(t for _, t in texts)


async def _analysis_entities(db: AsyncSession, doc: Document) -> Set[str]:
    """Audiences the circular's own analysis lists (who it applies to), when it has one."""
    from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis

    if not doc.current_version_id:
        return set()
    analysis_id = (await db.execute(
        select(DocumentAnalysis.id).where(DocumentAnalysis.document_version_id == doc.current_version_id)
        .order_by(DocumentAnalysis.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if not analysis_id:
        return set()
    out: Set[str] = set()
    for fields, status in (await db.execute(
        select(AnalysisClaim.fields, AnalysisClaim.check_status)
        .where(AnalysisClaim.analysis_id == analysis_id, AnalysisClaim.kind == "APPLIES_TO")
    )).all():
        entity = str((fields or {}).get("entity") or "").strip()
        if entity in KNOWN_ENTITIES and status not in ("REJECTED", "NOT_SHOWN"):
            out.add(entity)
    return out


async def refresh_document(db: AsyncSession, document_id) -> Set[str]:
    """Works out and stores who one circular applies to (analysis first, then the addressee line). No commit."""
    doc = await db.get(Document, document_id)
    if doc is None:
        return set()
    first, pages = await _page_texts(db, doc.current_version_id) if doc.current_version_id else ("", "")
    rule_set, rule_source = derive(doc.reference_number, doc.title, first, pages)
    from_analysis = await _analysis_entities(db, doc)
    await db.execute(delete(DocumentAudience).where(DocumentAudience.document_id == doc.id))
    rows = {e: "ANALYSIS" for e in from_analysis}
    for e in rule_set:
        rows.setdefault(e, rule_source)
    for e, src in (rows or {NONE: "ADDRESSEE"}).items():
        db.add(DocumentAudience(document_id=doc.id, entity=e, source=src))
    await db.flush()
    _INDEX["at"] = 0.0
    return set(rows)


async def fill_missing(db: AsyncSession, limit: int = 200) -> int:
    """Circulars not worked out yet (new arrivals). No commit."""
    ids = (await db.execute(
        select(Document.id).where(~Document.id.in_(select(DocumentAudience.document_id))).limit(limit)
    )).scalars().all()
    for i in ids:
        await refresh_document(db, i)
    return len(ids)


# ---------------------------------------------------------------------------
# The facts each circular carries (cached for a few minutes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DocFacts:
    reference: str
    department: str
    topics: FrozenSet[str]
    entities: FrozenSet[str]

    def tags(self) -> Set[str]:
        out = {f"topic:{t}" for t in self.topics if t != "OTHER"} | {f"entity:{e}" for e in self.entities}
        if self.department:
            out.add(f"dept:{self.department}")
        return out


_INDEX: Dict[str, object] = {"at": 0.0, "docs": {}}
_TTL = 600.0


def _dept_from_reference(ref: str) -> str:
    head = (ref or "").split(" ")[0].upper()
    return head.split("-")[0] if head.isascii() and 2 <= len(head) <= 12 else ""


async def facts(db: AsyncSession) -> Dict[UUID, DocFacts]:
    if time.monotonic() - float(_INDEX["at"]) < _TTL and _INDEX["docs"]:
        return _INDEX["docs"]  # type: ignore[return-value]
    if await fill_missing(db):
        await db.commit()
    depts = dict((await db.execute(select(InstitutionDepartment.id, InstitutionDepartment.code))).all())
    topics: Dict[UUID, Set[str]] = defaultdict(set)
    for d, t in (await db.execute(select(DocumentTopic.document_id, DocumentTopic.topic))).all():
        topics[d].add(t)
    ents: Dict[UUID, Set[str]] = defaultdict(set)
    for d, e in (await db.execute(select(DocumentAudience.document_id, DocumentAudience.entity))).all():
        if e != NONE:
            ents[d].add(e)
    out: Dict[UUID, DocFacts] = {}
    for did, ref, dept_id in (await db.execute(select(Document.id, Document.reference_number, Document.department_id))).all():
        code = (depts.get(dept_id) or "").upper().split("-")[0] or _dept_from_reference(ref or "")
        out[did] = DocFacts(ref or "", code, frozenset(topics.get(did, ())), frozenset(ents.get(did, ())))
    _INDEX.update(at=time.monotonic(), docs=out)
    return out


# ---------------------------------------------------------------------------
# A reader's institution type
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    kind: Optional[str] = None
    has_ad: Optional[bool] = None
    source: Optional[str] = None  # user, company, workspace
    company: Optional[str] = None
    muted: Set[str] = field(default_factory=set)
    organization_id: Optional[UUID] = None

    @property
    def audiences(self) -> FrozenSet[str]:
        return audiences_for(self.kind, self.has_ad)


async def _profile_row(db: AsyncSession, user_id) -> Optional[UserProfile]:
    return (await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))).scalar_one_or_none()


async def _organization(db: AsyncSession, user_id) -> Optional[Organization]:
    return (await db.execute(
        select(Organization).join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id, OrganizationMember.status == "ACTIVE", Organization.is_active.is_(True))
        .order_by(OrganizationMember.created_at).limit(1)
    )).scalar_one_or_none()


async def get_profile(db: AsyncSession, user: User, autosave: bool = True) -> Profile:
    """The reader's own choice; else a guess from their company name (saved, so it shows in Account);
    else their workspace's type."""
    row = await _profile_row(db, user.id)
    prefs = dict((row.preferences if row else None) or {})
    org = await _organization(db, user.id)
    p = Profile(
        kind=prefs.get("institution_type"), has_ad=prefs.get("has_ad"), source=prefs.get("institution_source"),
        company=prefs.get("company"), muted=set(prefs.get("audience_muted") or []), organization_id=org.id if org else None,
    )
    if not p.kind and p.company:
        guess = guess_institution(p.company)
        if guess:
            p.kind, p.has_ad, p.source = guess[0], guess[1], "company"
            if autosave and row is not None:
                row.preferences = {**prefs, "institution_type": p.kind, "has_ad": p.has_ad, "institution_source": "company"}
                await db.commit()
    if not p.kind and org and org.entity_type in ORG_TYPE_MAP:
        p.kind, p.has_ad = ORG_TYPE_MAP[org.entity_type]
        p.source = "workspace"
    return p


async def set_profile(db: AsyncSession, user: User, kind: Optional[str], has_ad: Optional[bool]) -> None:
    row = await _profile_row(db, user.id)
    if row is None:
        row = UserProfile(user_id=user.id, preferences={})
        db.add(row)
    prefs = dict(row.preferences or {})
    if kind:
        prefs.update(institution_type=kind, has_ad=bool(has_ad) if INSTITUTION_TYPES[kind][3] else False, institution_source="user")
    else:
        for k in ("institution_type", "has_ad", "institution_source"):
            prefs.pop(k, None)
    row.preferences = prefs
    await db.commit()


async def set_muted(db: AsyncSession, user: User, tag: str, muted: bool) -> None:
    row = await _profile_row(db, user.id)
    if row is None:
        row = UserProfile(user_id=user.id, preferences={})
        db.add(row)
    prefs = dict(row.preferences or {})
    current = set(prefs.get("audience_muted") or [])
    current = current | {tag} if muted else current - {tag}
    prefs["audience_muted"] = sorted(current)
    row.preferences = prefs
    await db.commit()


# ---------------------------------------------------------------------------
# Marks and scoring
# ---------------------------------------------------------------------------

async def marks_for(db: AsyncSession, user: User, organization_id: Optional[UUID]) -> Dict[UUID, Tuple[int, bool]]:
    """{circular: (value, mine)}: the reader's own marks, plus their team's (their own win)."""
    out: Dict[UUID, Tuple[int, bool]] = {}
    if organization_id:
        for d, v in (await db.execute(
            select(CircularMark.document_id, CircularMark.value).where(CircularMark.organization_id == organization_id)
        )).all():
            out[d] = (v, False)
    for d, v in (await db.execute(
        select(CircularMark.document_id, CircularMark.value).where(CircularMark.user_id == user.id)
    )).all():
        out[d] = (v, True)
    return out


def tag_label(tag: str) -> str:
    kind, _, code = tag.partition(":")
    if kind == "topic":
        t = TOPIC_BY_CODE.get(code)
        return t.label if t else code.title()
    if kind == "entity":
        label = ENTITY_LABELS.get(code, code)
        return label[0].upper() + label[1:]
    return code


@dataclass
class Verdict:
    for_you: bool
    reason: str = ""
    mark: int = 0


class Scorer:
    """Decides "For you" for any circular, for one reader."""

    def __init__(self, profile: Profile, docs: Dict[UUID, DocFacts], marks: Dict[UUID, Tuple[int, bool]]):
        self.profile, self.docs, self.marks = profile, docs, marks
        self.audiences = profile.audiences
        self.weights: Dict[str, int] = defaultdict(int)
        self.examples: Dict[str, List[UUID]] = defaultdict(list)
        for did, (value, _mine) in marks.items():
            f = docs.get(did)
            if not f:
                continue
            for tag in f.tags() - profile.muted:
                self.weights[tag] += value
                if value > 0:
                    self.examples[tag].append(did)

    def interests(self) -> List[Tuple[str, int]]:
        return sorted(((t, w) for t, w in self.weights.items() if w), key=lambda x: (-abs(x[1]), x[0]))

    def _profile_reason(self, f: DocFacts) -> str:
        kind = self.profile.kind
        if ALL in self.audiences:
            return "You follow every circular as an auditor or consultant."
        hit = [e for e in _REASON_ORDER if e in f.entities and e in self.audiences]
        if not hit:
            return ""
        e = hit[0]
        if kind == "COMPANY":
            return "Foreign exchange rule for authorised dealers, the banks that handle your imports and exports."
        if e in ("AUTHORIZED_DEALER", "OFFSHORE_BANKING_UNIT") and self.profile.has_ad:
            return f"Applies to {ENTITY_LABELS[e]}. Your institution has AD branches."
        phrase = INSTITUTION_TYPES.get(kind or "", ("", ""))[1]
        return f"Applies to {ENTITY_LABELS[e]}. Your institution is {phrase}." if phrase else f"Applies to {ENTITY_LABELS[e]}."

    def verdict(self, did: UUID) -> Verdict:
        mark = self.marks.get(did)
        if mark:
            value, mine = mark
            if value > 0:
                return Verdict(True, "You marked this as applying to you." if mine else "Your team marked this as applying to you.", value)
            return Verdict(False, "", value)
        f = self.docs.get(did)
        if not f:
            return Verdict(False)
        tags = f.tags() - self.profile.muted
        score = sum(self.weights.get(t, 0) for t in tags)
        matches = bool(self.audiences) and (ALL in self.audiences or bool(f.entities & self.audiences))
        if matches:
            # Only repeated "Not for me" on the same kind of circular drops a profile match.
            if score <= -3 and any(self.weights.get(t, 0) <= -2 for t in tags):
                return Verdict(False)
            return Verdict(True, self._profile_reason(f))
        positive = [t for t in tags if self.weights.get(t, 0) > 0]
        if score >= 2 and any(t.startswith("dept:") for t in positive) and len(positive) >= 2:
            example = self._best_example(positive)
            ref = self.docs[example].reference if example and example in self.docs else "a circular"
            return Verdict(True, f"Similar to {ref}, which you marked as applying to you.")
        return Verdict(False)

    def _best_example(self, tags: Iterable[str]) -> Optional[UUID]:
        counts: Dict[UUID, int] = defaultdict(int)
        for t in tags:
            for d in self.examples.get(t, ()):
                counts[d] += 1
        return max(counts, key=lambda d: counts[d]) if counts else None


async def scorer_for(db: AsyncSession, user: User, autosave: bool = True) -> Scorer:
    profile = await get_profile(db, user, autosave=autosave)
    return Scorer(profile, await facts(db), await marks_for(db, user, profile.organization_id))


async def for_you_ids(db: AsyncSession, user: User) -> List[UUID]:
    s = await scorer_for(db, user)
    return [d for d in s.docs if s.verdict(d).for_you]


async def set_mark(db: AsyncSession, user: User, document_id: UUID, value: int, request=None) -> None:
    """value 1 / -1 sets the mark, 0 removes it. In a workspace the mark counts for the team and is audited."""
    from backend.app.modules.audit.service import record

    org = await _organization(db, user.id)
    row = (await db.execute(
        select(CircularMark).where(CircularMark.user_id == user.id, CircularMark.document_id == document_id)
    )).scalar_one_or_none()
    before = row.value if row else 0
    if value == 0:
        if row is not None:
            await db.delete(row)
    elif row is None:
        db.add(CircularMark(user_id=user.id, organization_id=org.id if org else None, document_id=document_id, value=value))
    else:
        row.value, row.organization_id = value, org.id if org else None
    if org and before != value:
        record(db, organization_id=org.id, actor_user_id=user.id, action="CIRCULAR_MARKED", entity_type="DOCUMENT",
               entity_id=document_id, before={"applies": before}, after={"applies": value}, request=request)
    await db.commit()


def audience_labels(f: Optional[DocFacts]) -> List[str]:
    if not f:
        return []
    order = {e: i for i, e in enumerate(_REASON_ORDER)}
    return [ENTITY_LABELS[e][0].upper() + ENTITY_LABELS[e][1:] for e in sorted(f.entities, key=lambda e: order.get(e, 99)) if e in ENTITY_LABELS]


async def count_audiences(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(func.distinct(DocumentAudience.document_id))))).scalar_one()
