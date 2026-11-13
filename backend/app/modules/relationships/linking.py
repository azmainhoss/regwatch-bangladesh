"""Fills in which stored circular a relationship's reference hint names.

The relationship itself (who amends whom, and the quote that says so) always comes from the
text of the circular. Linking only answers "which document in the library is
'BRPD Circular No. 14'?". If the answer is not exactly one shared-library document, nothing
is linked: a link is never guessed.
"""
import re
import unicodedata
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set
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


def _prepare(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_BANGLA_DIGITS).lower()
    text = text.replace("‌", "").replace("‍", "")
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

    index = await _shared_reference_index(db)
    if not index:
        return 0

    linked = 0
    linked_targets: List[UUID] = []
    for rel in unlinked:
        keys = reference_keys(rel.target_reference_hint)
        if not keys:
            continue
        target_id = _unique_match(keys, index, exclude=rel.source_document_id)
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
