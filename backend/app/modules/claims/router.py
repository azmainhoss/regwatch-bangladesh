"""Endpoints for the checked view of a circular and for asking that points be looked at again."""
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_async_db
from backend.app.modules.analysis.models import AnalysisClaim
from backend.app.modules.claims import decide, review, view
from backend.app.modules.claims import status as S
from backend.app.modules.documents.access import get_document_reader, get_visible_document
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.identity.deps import get_current_superuser
from backend.app.modules.identity.models import User

router = APIRouter(tags=["Checked points"])


@router.get("/documents/{document_id}/claims")
async def get_checked_view(
    document_id: UUID,
    all: int = Query(0, ge=0, le=1),
    current_user: Optional[User] = Depends(get_document_reader),
    db: AsyncSession = Depends(get_async_db),
):
    """The points of a circular that passed their checks, and a plain line for each one held back.
    `all=1` (administrators) also lists the held points with their checks."""
    doc = await get_visible_document(db, document_id, current_user)
    if all:
        if current_user is None or not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Only administrators can see every point.")
    return await view.build_view(db, doc, current_user, admin=bool(all))


async def _answer(db: AsyncSession, claim: AnalysisClaim, doc: Optional[Document], user: User) -> Dict[str, Any]:
    """What a decision returns: the updated claim, the circular's counts and its status."""
    row = (
        await db.execute(select(AnalysisClaim).options(selectinload(AnalysisClaim.citations)).where(AnalysisClaim.id == claim.id))
    ).scalars().first()
    pages: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    if doc is not None:
        pages = {
            str(pid): n
            for pid, n in (
                await db.execute(select(DocumentPage.id, DocumentPage.page_number).where(DocumentPage.document_version_id == doc.current_version_id))
            ).all()
        }
        siblings = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == claim.analysis_id))).scalars().all()
        counts = S.counts([c for c in siblings if c.kind != "PROVISION"])
    return {
        "claim": view.claim_summary(row or claim, pages),
        "counts": counts,
        "document_status": doc.publication_status if doc is not None else None,
        "document_id": str(doc.id) if doc is not None else None,
    }


async def _announce_links(db: AsyncSession, claims) -> None:
    """A link going on or off the record can change another circular's in-force status: check the banks that use it."""
    from backend.app.modules.analysis.service import _announce_library_change
    from backend.app.modules.relationships.models import DocumentRelationship

    ids = [c.relationship_id for c in claims if c.kind == "LINK" and c.relationship_id]
    if not ids:
        return
    targets = (
        await db.execute(select(DocumentRelationship.target_document_id).where(DocumentRelationship.id.in_(ids)))
    ).scalars().all()
    await _announce_library_change(db, [t for t in targets if t])


class ApproveBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class FixBody(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    confirm_checked: bool = False
    note: Optional[str] = Field(default=None, max_length=2000)


class RejectBody(BaseModel):
    reason: str = Field(default="OTHER", max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)


async def _current(db: AsyncSession, claim_id: UUID, version_id: Any) -> Dict[str, Any]:
    row = (
        await db.execute(select(AnalysisClaim).options(selectinload(AnalysisClaim.citations)).where(AnalysisClaim.id == claim_id))
    ).scalars().first()
    pages: Dict[str, int] = {}
    if version_id is not None:
        pages = {
            str(pid): n
            for pid, n in (await db.execute(select(DocumentPage.id, DocumentPage.page_number).where(DocumentPage.document_version_id == version_id))).all()
        }
    return view.claim_summary(row, pages) if row is not None else {}


async def _decide(
    db: AsyncSession,
    claim_id: UUID,
    user: User,
    run: Callable[[AnalysisClaim, Optional[Document]], Awaitable[Any]],
    already: str,
) -> Dict[str, Any]:
    """Runs one decision: 404 for an unknown point, 409 when it was already decided, 400 when a fix cannot be saved yet."""
    claim = await decide.load_claim(db, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Point not found.")
    doc = await decide.document_of(db, claim)
    version_id = doc.current_version_id if doc is not None else None
    if doc is not None:
        await get_visible_document(db, doc.id, user)
    try:
        await run(claim, doc)
    except decide.DecisionConflict:
        await db.rollback()
        raise HTTPException(status_code=409, detail={"message": already, "claim": await _current(db, claim_id, version_id)})
    except decide.DecisionProblem as problem:
        await db.rollback()
        messages = [m for m in problem.messages if m] or ["This point cannot be saved yet."]
        raise HTTPException(status_code=400, detail={"message": messages[0], "problems": messages, "checks": problem.checks})
    await db.commit()
    await _announce_links(db, [claim])
    return await _answer(db, claim, doc, user)


@router.get("/claims/review")
async def review_list(
    queue: str = Query("REQUIRED", pattern="^(REQUIRED|OPTIONAL)$"),
    limit: int = Query(20, ge=1, le=50),
    after: Optional[str] = Query(None, max_length=512),
    point: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Held points waiting for a person, in the order to look at them (administrators).
    `point` asks for that one point only, even if it was decided already."""
    if point is not None:
        return await review.review_point(db, current_user, point)
    return await review.review_items(db, current_user, queue, limit, after)


@router.get("/claims/review/counts")
async def review_counts(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """How many points wait, how many are still being checked, and the circulars with nothing to show."""
    return await review.review_counts(db, current_user)


@router.post("/claims/{claim_id}/approve")
async def approve_claim(
    claim_id: UUID,
    body: Optional[ApproveBody] = None,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """The point is checked by a person and shown."""
    note = body.note if body else None
    return await _decide(db, claim_id, current_user, lambda c, d: decide.approve(db, c, current_user, note), "Someone else already decided this point.")


@router.post("/claims/{claim_id}/fix")
async def fix_claim(
    claim_id: UUID,
    body: FixBody,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """A person corrects the point. The checks run again; failing ones need the tick `confirm_checked`."""
    return await _decide(
        db,
        claim_id,
        current_user,
        lambda c, d: decide.fix(db, c, current_user, body.fields, body.evidence_ids, body.confirm_checked, body.note),
        "Someone else already decided this point.",
    )


@router.post("/claims/{claim_id}/reject")
async def reject_claim(
    claim_id: UUID,
    body: Optional[RejectBody] = None,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """The point is never shown."""
    reason = body.reason if body else "OTHER"
    note = body.note if body else None
    return await _decide(db, claim_id, current_user, lambda c, d: decide.reject(db, c, current_user, reason, note), "Someone else already decided this point.")


@router.post("/claims/{claim_id}/ask-review")
async def ask_for_review(
    claim_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Hides one shown point until a person decides it (administrators)."""
    return await _decide(db, claim_id, current_user, lambda c, d: decide.ask_review(db, c, current_user), "This point is not shown, so there is nothing to hide.")


@router.post("/documents/{document_id}/claims/ask-review")
async def ask_for_review_of_all(
    document_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Hides every shown point of the circular until a person decides each one (administrators)."""
    doc = await get_visible_document(db, document_id, current_user)
    hidden = await decide.ask_review_all(db, doc, current_user)
    await db.commit()
    await _announce_links(db, hidden)
    return {"hidden": len(hidden), "document_status": doc.publication_status, **{"view": await view.build_view(db, doc, current_user, admin=True)}}
