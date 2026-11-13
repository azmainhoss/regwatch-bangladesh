"""Whether a circular is still in force, worked out from the links other circulars state about it.

Only links whose quote was checked (VERIFIED) change the status. Links awaiting review
(PENDING_REVIEW) are listed next to it as "unconfirmed" and change nothing. Rejected links
are ignored everywhere. A link only counts for a caller who may read the circular that states it.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.identity.models import User
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.relationships.schemas import DocumentRef, LinkRead

IN_FORCE = "IN_FORCE"
AMENDED = "AMENDED"
REPLACED = "REPLACED"
REPEALED = "REPEALED"

# What an incoming link of each type does to the circular it points at.
STATUS_BY_TYPE = {"AMENDS": AMENDED, "SUPERSEDES": REPLACED, "REPLACES": REPLACED, "REPEALS": REPEALED}
# Links that pass the rule on to a newer circular.
SUCCESSOR_TYPES = ("SUPERSEDES", "REPLACES", "REPEALS")
# Links that make up the history of one rule.
CHAIN_TYPES = tuple(STATUS_BY_TYPE.keys())
# Strongest first.
_PRECEDENCE = (REPEALED, REPLACED, AMENDED)

MAX_CHAIN_DEPTH = 50


def visible_to(alias, user: Optional[User]):
    """SQL condition: the (aliased) document may be read by this caller."""
    if user is None:
        return alias.owner_user_id.is_(None)
    return or_(alias.owner_user_id.is_(None), alias.owner_user_id == user.id)


def can_read(doc: Optional[Document], user: Optional[User]) -> bool:
    if doc is None:
        return False
    if doc.owner_user_id is None:
        return True
    return user is not None and str(doc.owner_user_id) == str(user.id)


def _sort_key(doc: Document):
    return (doc.publication_date, doc.created_at)


@dataclass
class InForce:
    status: str = IN_FORCE
    by: Optional[Document] = None


async def bulk_in_force(db: AsyncSession, doc_ids: Iterable[UUID], user: Optional[User]) -> Dict[str, InForce]:
    """In-force status of many circulars with one query (verified incoming links only)."""
    ids = list({str(d): d for d in doc_ids}.values())
    result: Dict[str, InForce] = {str(d): InForce() for d in ids}
    if not ids:
        return result
    rows = (
        await db.execute(
            select(DocumentRelationship.target_document_id, DocumentRelationship.relationship_type, Document)
            .join(Document, Document.id == DocumentRelationship.source_document_id)
            .where(
                DocumentRelationship.target_document_id.in_(ids),
                DocumentRelationship.verification_status == "VERIFIED",
                DocumentRelationship.relationship_type.in_(CHAIN_TYPES),
                visible_to(Document, user),
            )
        )
    ).all()
    best: Dict[str, Dict[str, Document]] = {}
    for target_id, rel_type, source in rows:
        if str(target_id) == str(source.id):
            continue  # a circular cannot change itself
        status = STATUS_BY_TYPE[rel_type]
        per_status = best.setdefault(str(target_id), {})
        current = per_status.get(status)
        if current is None or _sort_key(source) > _sort_key(current):
            per_status[status] = source
    for key, per_status in best.items():
        for status in _PRECEDENCE:
            if status in per_status:
                result[key] = InForce(status=status, by=per_status[status])
                break
    return result


def doc_ref(doc: Document, in_force: Optional[InForce] = None) -> DocumentRef:
    return DocumentRef(
        id=doc.id,
        reference_number=doc.reference_number,
        title=doc.title,
        publication_date=doc.publication_date,
        current_version_id=doc.current_version_id,
        is_private=doc.owner_user_id is not None,
        in_force_status=in_force.status if in_force else None,
    )


async def _page_info(db: AsyncSession, page_ids: Sequence[UUID]) -> Dict[str, Tuple[UUID, int]]:
    ids = [p for p in set(page_ids) if p is not None]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(DocumentPage.id, DocumentPage.document_version_id, DocumentPage.page_number).where(DocumentPage.id.in_(ids))
        )
    ).all()
    return {str(r[0]): (r[1], r[2]) for r in rows}


async def build_links(
    db: AsyncSession,
    rels: Sequence[DocumentRelationship],
    docs: Dict[str, Document],
    statuses: Optional[Dict[str, InForce]] = None,
) -> List[LinkRead]:
    """Turns relationship rows into API links. `docs` holds the circulars the caller may read, by id;
    a link whose source is missing from it is dropped, and a target missing from it is shown as not in the library."""
    pages = await _page_info(db, [r.source_page_id for r in rels])
    out: List[LinkRead] = []
    for rel in rels:
        source = docs.get(str(rel.source_document_id))
        if source is None:
            continue
        target = docs.get(str(rel.target_document_id)) if rel.target_document_id else None
        version_id, page_number = pages.get(str(rel.source_page_id), (None, None))
        if page_number is None:
            first_box = (rel.quote_boxes or [None])[0]
            if isinstance(first_box, dict) and isinstance(first_box.get("page_number"), int):
                page_number = first_box["page_number"]
        if version_id is None and page_number is not None:
            version_id = source.current_version_id
        out.append(
            LinkRead(
                id=rel.id,
                relationship_type=rel.relationship_type,
                verification_status=rel.verification_status,
                confidence=rel.confidence if rel.confidence is not None else 1.0,
                detection_method=rel.detection_method,
                supporting_quote=rel.supporting_quote,
                page_number=page_number,
                source_version_id=version_id,
                quote_span_ids=rel.quote_span_ids if isinstance(rel.quote_span_ids, list) else None,
                quote_boxes=rel.quote_boxes if isinstance(rel.quote_boxes, list) else None,
                source=doc_ref(source, (statuses or {}).get(str(source.id))),
                target=doc_ref(target, (statuses or {}).get(str(target.id))) if target else None,
                target_reference_hint=rel.target_reference_hint,
                reviewed_at=rel.reviewed_at,
            )
        )
    return out


async def load_visible_docs(db: AsyncSession, ids: Iterable[UUID], user: Optional[User]) -> Dict[str, Document]:
    wanted = list({str(i): i for i in ids if i is not None}.values())
    if not wanted:
        return {}
    rows = (await db.execute(select(Document).where(Document.id.in_(wanted), visible_to(Document, user)))).scalars().all()
    return {str(d.id): d for d in rows}


async def follow_current(db: AsyncSession, doc: Document, user: Optional[User]) -> Tuple[Document, bool]:
    """Follows verified REPLACES/SUPERSEDES/REPEALS links forward to the newest circular still in force.
    Returns (that circular, whether a loop was found). Stops after 50 steps."""
    visited = {str(doc.id)}
    current = doc
    for _ in range(MAX_CHAIN_DEPTH):
        rows = (
            await db.execute(
                select(Document)
                .join(DocumentRelationship, DocumentRelationship.source_document_id == Document.id)
                .where(
                    DocumentRelationship.target_document_id == current.id,
                    DocumentRelationship.verification_status == "VERIFIED",
                    DocumentRelationship.relationship_type.in_(SUCCESSOR_TYPES),
                    visible_to(Document, user),
                )
            )
        ).scalars().all()
        rows = [r for r in rows if str(r.id) != str(current.id)]
        if not rows:
            return current, False
        nxt = max(rows, key=_sort_key)
        if str(nxt.id) in visited:
            return current, True
        visited.add(str(nxt.id))
        current = nxt
    return current, False


async def document_links(
    db: AsyncSession, doc: Document, user: Optional[User]
) -> Tuple[List[DocumentRelationship], List[DocumentRelationship], List[DocumentRelationship], Dict[str, Document]]:
    """(verified incoming, unconfirmed incoming, outgoing not rejected, readable circulars by id)."""
    source_alias = aliased(Document)
    incoming = (
        await db.execute(
            select(DocumentRelationship)
            .join(source_alias, source_alias.id == DocumentRelationship.source_document_id)
            .where(
                DocumentRelationship.target_document_id == doc.id,
                DocumentRelationship.verification_status.in_(("VERIFIED", "PENDING_REVIEW")),
                visible_to(source_alias, user),
            )
            .order_by(DocumentRelationship.created_at)
        )
    ).scalars().all()
    outgoing = (
        await db.execute(
            select(DocumentRelationship)
            .where(
                DocumentRelationship.source_document_id == doc.id,
                DocumentRelationship.verification_status.in_(("VERIFIED", "PENDING_REVIEW")),
            )
            .order_by(DocumentRelationship.confidence.desc(), DocumentRelationship.created_at)
        )
    ).scalars().all()
    ids = [doc.id]
    for r in incoming:
        ids.append(r.source_document_id)
    for r in outgoing:
        ids.append(r.target_document_id)
    docs = await load_visible_docs(db, ids, user)
    docs[str(doc.id)] = doc
    verified = [r for r in incoming if r.verification_status == "VERIFIED"]
    pending = [r for r in incoming if r.verification_status == "PENDING_REVIEW"]
    return verified, pending, list(outgoing), docs
