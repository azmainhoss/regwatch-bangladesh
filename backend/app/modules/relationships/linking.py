"""Fills in which stored circular a relationship's reference hint names.

The relationship itself (who amends whom, and the quote that says so) always comes from the
text of the circular. Linking only answers "which document in the library is
'BRPD Circular No. 14'?". If the answer is not exactly one shared-library document, nothing
is linked: a link is never guessed.
"""
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.modules.documents.access import shared_documents_condition
from backend.app.modules.documents.models import Document
from backend.app.modules.documents.synthetic import synthetic_sql_condition
from backend.app.modules.relationships.models import DocumentRelationship

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# "BRPD Circular No. 14 dated 23 September 2012": everything from "dated" on is a date, not part of the number.
_DATE_TAIL = re.compile(r"\b(?:dated|date|issued\s+on|issued)\b.*$|তারিখ.*$|তাং.*$", re.IGNORECASE | re.DOTALL)
_NO_WORD = re.compile(r"\b(?:nos?|number|num)\b\.?|\b(?:nos?|number)(?=\d)|নং|নম্বর")
_YEAR_IN_DATE = re.compile(r"\b((?:19|20)\d{2})\b")


# Bangla circulars name other circulars in Bangla ("বিআরপিডি সার্কুলার নং-১১/২০২২"). These are turned into
# the English form the library is filed under ("brpd circular no-11/2022"). Spellings counted on the archive's
# image-read pages on 14 Nov 2026, including frequent misreadings of BRPD, SMESPD and DOS.
_BANGLA_DEPARTMENTS = {
    "brpd": ("বিআরপিডি", "বিআরিপিডি", "বিআর্পিডি", "বিএআরপিডি", "বিএরিপিডি", "বিঅরপিডি"),
    "fepd": ("এফইপিডি",),
    "feod": ("এফইওডি",),
    "fe": ("এফই",),
    "dfim": ("ডিএফআইএম",),
    "smespd": ("এসএমইএসপিডি", "এসএমএসপিডি", "এসএমএএসপিডি"),
    "dos": ("ডিওএস", "ডিঅএস", "ডিওয়াস"),
    "psd": ("পিএসডি",),
    "dmd": ("ডিএমডি",),
    "acd": ("এসিডি",),
    "sfd": ("এসএফডি",),
    "fid": ("এফআইডি",),
    "fcrpd": ("এফসিআরপিডি",),
    "cib": ("সিআইবি",),
    "bfiu": ("বিএফআইইউ",),
    "mpd": ("এমপিডি",),
    "dcm": ("ডিসিএম", "ডিসএম"),
    "ismd": ("আইএসএমডি",),
    "did": ("ডিআইডি",),
    "gbcsrd": ("জিবিসিএসআরডি",),
}
_BANGLA_WORDS = (
    ("মাস্টার সার্কুলার", "master circular"), ("সার্কুলার লেটার", "circular letter"), ("সার্কুলার-লেটার", "circular letter"),
    ("সার্কুলার", "circular"), ("পরিপত্র", "circular"),
)
_BANGLA_NAME_PATTERNS = [
    (re.compile(r"(?<![ঀ-৿])" + re.escape(unicodedata.normalize("NFKC", bn)) + r"(?![ঀ-৿])"), f" {en} ")
    for en, spellings in _BANGLA_DEPARTMENTS.items() for bn in spellings
] + [
    (re.compile(r"(?<![ঀ-৿])" + re.escape(unicodedata.normalize("NFKC", bn)) + r"(?![ঀ-৿])"), f" {en} ") for bn, en in _BANGLA_WORDS
]
_BANGLA_NAME_PATTERNS.sort(key=lambda p: -len(p[0].pattern))  # longest spelling first


def _prepare(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_BANGLA_DIGITS).lower()
    text = text.replace("‌", "").replace("‍", "")
    if any("ঀ" <= ch <= "৿" for ch in text):
        for pattern, english in _BANGLA_NAME_PATTERNS:
            text = pattern.sub(english, text)
    return text


def normalize_reference(text: Optional[str]) -> Optional[str]:
    """A comparable form of a circular reference.

    'BRPD Circular No. 14/2023', 'BRPD circular no.14 / 2023' and 'BRPD Circular No ১৪/২০২৩' all
    give 'brpd circular no 14/2023'. The department, the kind of instrument (circular, circular
    letter, master circular) and the number and year are kept, so 'Circular Letter No. 3' is never
    the same as 'Circular No. 3'. Text with no number in it gives None.
    """
    if not text:
        return None
    s = _prepare(text)
    s = _DATE_TAIL.sub(" ", s)
    s = _NO_WORD.sub(" no ", s)
    s = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", "/", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"[^\w/]+", " ", s)
    s = s.replace("_", " ")
    # "05" and "5" are the same number.
    s = re.sub(r"(?<![\d/])0+(?=\d)", "", s)
    s = re.sub(r"(?<=/)0+(?=\d)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not re.search(r"\d", s):
        return None
    return s


def reference_keys(hint: Optional[str]) -> List[str]:
    """Every form a hint may be stored under. Usually just the normalized hint; when the hint carries a
    date ('No. 14 dated 23 September 2012') and no year of its own, the circular may also be filed as '14/2012'."""
    primary = normalize_reference(hint)
    if not primary:
        return []
    keys = [primary]
    if hint and "/" not in primary:
        date_part = _DATE_TAIL.search(_prepare(hint))
        if date_part:
            year = _YEAR_IN_DATE.search(date_part.group(0))
            if year:
                keys.append(f"{primary}/{year.group(1)}")
    return keys


# "acd 1 circular no 3/2026" -> "acd circular no 3/2026": a department's section number (ACD-1, BRPD-2) is often
# left out when another circular cites it ("ACD Circular No. 03 dated 16 August 2026").
_SECTION_NO = re.compile(r"^([a-z&]+) \d{1,2} (?=[a-z])")


# One department under two names: older circulars say "FE Circular", the library files them as "FEPD Circular".
_DEPARTMENT_ALIASES = {"fe": "fepd"}


def base_key(key: str) -> str:
    key = _SECTION_NO.sub(r"\1 ", key)
    dept, _, rest = key.partition(" ")
    return f"{_DEPARTMENT_ALIASES.get(dept, dept)} {rest}" if rest else key


def hint_date(hint: Optional[str]):
    """The date a hint gives for the cited circular ('dated 16 August 2026'), or None."""
    if not hint:
        return None
    from backend.app.modules.claims import wording as W

    tail = _DATE_TAIL.search(_prepare(hint))
    if not tail:
        return None
    found = W.date_matches(W.norm(tail.group(0)))
    return found[0][2] if found else None


@dataclass
class ReferenceIndex:
    exact: Dict[str, Set[UUID]]
    base: Dict[str, Set[UUID]]
    dates: Dict[UUID, Any]


async def reference_index(db: AsyncSession) -> ReferenceIndex:
    rows = (
        await db.execute(
            select(Document.id, Document.reference_number, Document.publication_date).where(
                shared_documents_condition(),
                ~synthetic_sql_condition(),
                Document.reference_number.isnot(None),
            )
        )
    ).all()
    exact: Dict[str, Set[UUID]] = defaultdict(set)
    base: Dict[str, Set[UUID]] = defaultdict(set)
    dates: Dict[UUID, Any] = {}
    for doc_id, reference, published in rows:
        key = normalize_reference(reference)
        if key:
            exact[key].add(doc_id)
            base[base_key(key)].add(doc_id)
            dates[doc_id] = published
    return ReferenceIndex(exact, base, dates)


def match_target(hint: Optional[str], idx: ReferenceIndex, exclude: Any) -> Optional[UUID]:
    """The one library circular a hint names, or None. Never a guess:

    1. the exact number (department, section, kind, number, year) names one circular; when it names several,
       the hint's date picks one;
    2. otherwise, without the department's section number ("ACD" for "ACD-1"): one candidate whose publication
       date equals the hint's date, or, when the hint gives no date, the only candidate.
    """
    keys = reference_keys(hint)
    if not keys:
        return None
    when = hint_date(hint)

    def pick(found: Set[UUID], need_date: bool) -> Optional[UUID]:
        found = {d for d in found if str(d) != str(exclude)}
        if when is not None:
            dated = {d for d in found if idx.dates.get(d) == when}
            if len(dated) == 1:
                return next(iter(dated))
            if need_date or len(found) != 1:
                return None
        return next(iter(found)) if len(found) == 1 else None

    for key in keys:
        found = idx.exact.get(key, set())
        if found:
            return pick(found, need_date=False)
    candidates: Set[UUID] = set()
    for key in keys:
        candidates |= idx.base.get(base_key(key), set())
    return pick(candidates, need_date=True) if candidates else None


async def _shared_reference_index(db: AsyncSession) -> Dict[str, Set[UUID]]:
    rows = (
        await db.execute(
            select(Document.id, Document.reference_number).where(
                shared_documents_condition(),
                ~synthetic_sql_condition(),
                Document.reference_number.isnot(None),
            )
        )
    ).all()
    index: Dict[str, Set[UUID]] = defaultdict(set)
    for doc_id, reference in rows:
        key = normalize_reference(reference)
        if key:
            index[key].add(doc_id)
    return index


def _unique_match(keys: Iterable[str], index: Dict[str, Set[UUID]], exclude: UUID) -> Optional[UUID]:
    """The one document named by the hint, or None when it names none or several."""
    for key in keys:
        found = {d for d in index.get(key, set()) if str(d) != str(exclude)}
        if len(found) == 1:
            return next(iter(found))
        if len(found) > 1:
            return None
    return None


async def link_relationship_targets(db: AsyncSession, document_id: Optional[UUID] = None) -> int:
    """Sets target_document_id on relationships whose hint names exactly one shared-library circular.

    Runs both ways: relationships written by a circular whose cited circular is already stored, and
    relationships written earlier that cite a circular which has just arrived (or whose reference
    number was just corrected). With document_id, only relationships that start at that circular or
    that name it are looked at. Safe to run again: linked rows are not touched. Returns how many
    rows were linked, and commits when it linked any.
    """
    unlinked = (
        await db.execute(
            select(DocumentRelationship).where(
                DocumentRelationship.target_document_id.is_(None),
                DocumentRelationship.target_reference_hint.isnot(None),
                DocumentRelationship.target_reference_hint != "",
            )
        )
    ).scalars().all()
    if not unlinked:
        return 0

    idx = await reference_index(db)
    if not idx.exact:
        return 0

    linked = 0
    linked_targets: List[UUID] = []
    for rel in unlinked:
        target_id = match_target(rel.target_reference_hint, idx, exclude=rel.source_document_id)
        if target_id is None:
            continue
        if document_id is not None and str(target_id) != str(document_id) and str(rel.source_document_id) != str(document_id):
            continue
        rel.target_document_id = target_id
        linked_targets.append(target_id)
        linked += 1
    if linked:
        await db.commit()
        try:
            from backend.app.modules.alerts.sweeps import library_changed
            await library_changed(db, linked_targets)
        except Exception as exc:
            logger.warning("Alert not recorded: %s", type(exc).__name__)
    return linked
