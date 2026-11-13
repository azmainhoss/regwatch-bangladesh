"""Builds the status, graph and timeline views of a circular's links for one caller."""
from typing import Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.documents.models import Document
from backend.app.modules.identity.models import User
from backend.app.modules.relationships.linking import normalize_reference
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.relationships.schemas import (
    GraphEdge,
    GraphNode,
    GraphRead,
    StatusRead,
    TimelineItem,
    TimelineRead,
)
from backend.app.modules.relationships.status import (
    CHAIN_TYPES,
    InForce,
    build_links,
    bulk_in_force,
    doc_ref,
    document_links,
    follow_current,
    load_visible_docs,
    visible_to,
)

MAX_GRAPH_NODES = 80
MAX_TIMELINE_DOCS = 50
MAX_TIMELINE_DEPTH = 10


def _newest(rels, docs: Dict[str, Document]) -> Optional[Document]:
    sources = [docs[str(r.source_document_id)] for r in rels if str(r.source_document_id) in docs]
    return max(sources, key=lambda d: (d.publication_date, d.created_at)) if sources else None


async def build_status(db: AsyncSession, doc: Document, user: Optional[User]) -> StatusRead:
    verified, pending, outgoing, docs = await document_links(db, doc, user)
    statuses = await bulk_in_force(db, [d.id for d in docs.values()], user)
    own = statuses[str(doc.id)]
    current, cycle = await follow_current(db, doc, user)
    if str(current.id) not in statuses:
        statuses.update(await bulk_in_force(db, [current.id], user))
    return StatusRead(
        document_id=doc.id,
        in_force_status=own.status,
        in_force_by=doc_ref(own.by, statuses.get(str(own.by.id))) if own.by is not None else None,
        current_version=doc_ref(current, statuses.get(str(current.id))),
        chain_has_cycle=cycle,
        verified_incoming=await build_links(db, verified, docs, statuses),
        unconfirmed_incoming=await build_links(db, pending, docs, statuses),
        outgoing=await build_links(db, outgoing, docs, statuses),
    )


def _hint_key(hint: Optional[str]) -> str:
    text = (hint or "").strip()
    return "hint:" + (normalize_reference(text) or text.lower())


async def build_graph(db: AsyncSession, doc: Document, user: Optional[User], depth: int) -> GraphRead:
    depth = max(1, min(int(depth), 3))
    seen: Dict[str, Document] = {str(doc.id): doc}
    frontier: Set[str] = {str(doc.id)}
    rels_by_id: Dict[str, DocumentRelationship] = {}
    truncated = False

    for _ in range(depth):
        if not frontier:
            break
        ids = list(frontier)
        rows = (
            await db.execute(
                select(DocumentRelationship).where(
                    or_(DocumentRelationship.source_document_id.in_(ids), DocumentRelationship.target_document_id.in_(ids)),
                    DocumentRelationship.verification_status.in_(("VERIFIED", "PENDING_REVIEW")),
                )
            )
        ).scalars().all()
        other_ids = set()
        for rel in rows:
            other_ids.add(str(rel.source_document_id))
            if rel.target_document_id:
                other_ids.add(str(rel.target_document_id))
        unknown = [UUID(i) for i in other_ids if i not in seen]
        readable = await load_visible_docs(db, unknown, user)
        next_frontier: Set[str] = set()
        for rel in rows:
            src, tgt = str(rel.source_document_id), str(rel.target_document_id) if rel.target_document_id else None
            src_ok = src in seen or src in readable
            tgt_ok = tgt is None or tgt in seen or tgt in readable
            if not (src_ok and tgt_ok):
                continue  # one end is somebody else's private upload: the link is not shown at all
            new_nodes = [i for i in (src, tgt) if i and i not in seen]
            if len(seen) + len(set(new_nodes)) > MAX_GRAPH_NODES:
                truncated = True
                continue
            for i in new_nodes:
                seen[i] = readable[i]
                next_frontier.add(i)
            rels_by_id[str(rel.id)] = rel
        frontier = next_frontier

    statuses = await bulk_in_force(db, [d.id for d in seen.values()], user)
    links = await build_links(db, list(rels_by_id.values()), seen, statuses)
    link_by_id = {str(link.id): link for link in links}

    nodes: Dict[str, GraphNode] = {}
    for d in seen.values():
        nodes[str(d.id)] = GraphNode(
            key=str(d.id),
            document_id=d.id,
            reference_number=d.reference_number,
            title=d.title,
            publication_date=d.publication_date,
            in_force_status=statuses[str(d.id)].status,
            in_library=True,
            is_private=d.owner_user_id is not None,
            is_center=str(d.id) == str(doc.id),
            current_version_id=d.current_version_id,
        )
    edges: List[GraphEdge] = []
    for rel in rels_by_id.values():
        link = link_by_id.get(str(rel.id))
        if link is None:
            continue
        if rel.target_document_id:
            target_key = str(rel.target_document_id)
        else:
            hint = (rel.target_reference_hint or "").strip()
            if not hint:
                continue
            target_key = _hint_key(hint)
            if target_key not in nodes:
                nodes[target_key] = GraphNode(
                    key=target_key, title=hint, reference_number=hint, in_library=False, in_force_status=None
                )
        edges.append(
            GraphEdge(
                id=rel.id,
                source=str(rel.source_document_id),
                target=target_key,
                relationship_type=rel.relationship_type,
                verification_status=rel.verification_status,
                supporting_quote=rel.supporting_quote,
                page_number=link.page_number,
                source_version_id=link.source_version_id,
                source_document_id=rel.source_document_id,
                target_document_id=rel.target_document_id,
                target_reference_hint=rel.target_reference_hint,
                confidence=link.confidence,
            )
        )
    return GraphRead(document_id=doc.id, depth=depth, nodes=list(nodes.values()), edges=edges, truncated=truncated)


async def build_timeline(db: AsyncSession, doc: Document, user: Optional[User]) -> TimelineRead:
    """Every circular that changed, or was changed by, the rule in this one, oldest first, with the quote and page of each change."""
    family: Dict[str, Document] = {str(doc.id): doc}
    rels: Dict[str, DocumentRelationship] = {}
    frontier = {str(doc.id)}
    for _ in range(MAX_TIMELINE_DEPTH):
        if not frontier or len(family) >= MAX_TIMELINE_DOCS:
            break
        ids = list(frontier)
        rows = (
            await db.execute(
                select(DocumentRelationship).where(
                    or_(DocumentRelationship.source_document_id.in_(ids), DocumentRelationship.target_document_id.in_(ids)),
                    DocumentRelationship.relationship_type.in_(CHAIN_TYPES),
                    DocumentRelationship.verification_status.in_(("VERIFIED", "PENDING_REVIEW")),
                )
            )
        ).scalars().all()
        wanted = set()
        for rel in rows:
            wanted.add(str(rel.source_document_id))
            if rel.target_document_id:
                wanted.add(str(rel.target_document_id))
        readable = await load_visible_docs(db, [UUID(i) for i in wanted if i not in family], user)
        next_frontier: Set[str] = set()
        for rel in rows:
            src = str(rel.source_document_id)
            tgt = str(rel.target_document_id) if rel.target_document_id else None
            if not (src in family or src in readable):
                continue
            if tgt is not None and not (tgt in family or tgt in readable):
                continue
            for i in (src, tgt):
                if i and i not in family and len(family) < MAX_TIMELINE_DOCS:
                    family[i] = readable[i]
                    next_frontier.add(i)
            rels[str(rel.id)] = rel
        frontier = next_frontier

    statuses = await bulk_in_force(db, [d.id for d in family.values()], user)
    current, cycle = await follow_current(db, doc, user)
    if str(current.id) not in statuses:
        statuses.update(await bulk_in_force(db, [current.id], user))
    # Hide changes whose source fell outside the family cap.
    kept = [r for r in rels.values() if str(r.source_document_id) in family]
    links = await build_links(db, kept, family, statuses)
    by_source: Dict[str, List] = {}
    for link in links:
        by_source.setdefault(str(link.source.id), []).append(link)

    items: List[TimelineItem] = []
    for d in sorted(family.values(), key=lambda x: (x.publication_date, x.created_at)):
        changes = sorted(by_source.get(str(d.id), []), key=lambda l: (l.page_number or 0, l.relationship_type))
        items.append(
            TimelineItem(
                document=doc_ref(d, statuses.get(str(d.id))),
                is_selected=str(d.id) == str(doc.id),
                is_current=str(d.id) == str(current.id),
                changes=changes,
            )
        )
    own = statuses[str(doc.id)]
    return TimelineRead(
        document_id=doc.id,
        in_force_status=own.status,
        in_force_by=doc_ref(own.by, statuses.get(str(own.by.id))) if own.by is not None else None,
        current_version=doc_ref(current, statuses.get(str(current.id))),
        chain_has_cycle=cycle,
        has_unconfirmed=any(l.verification_status == "PENDING_REVIEW" for l in links),
        items=items,
    )
