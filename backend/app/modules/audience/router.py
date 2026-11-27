"""Institution type, "Applies to me" / "Not for me", and the "For you" flag for lists and circular pages."""
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.audience import service
from backend.app.modules.audience.kinds import INSTITUTION_TYPES
from backend.app.modules.audience.known import guess_institution
from backend.app.modules.identity.deps import get_current_user, get_current_user_optional
from backend.app.modules.identity.models import User

router = APIRouter(prefix="/audience", tags=["For you"])


class Kind(BaseModel):
    code: str
    label: str
    bank: bool  # asks "Do you have AD branches?"


class Interest(BaseModel):
    tag: str
    label: str
    weight: int


class Me(BaseModel):
    institution_type: Optional[str] = None
    institution_label: Optional[str] = None
    has_ad: Optional[bool] = None
    source: Optional[str] = None  # user, company, workspace
    company: Optional[str] = None
    interests: List[Interest] = []
    not_interested: List[Interest] = []
    kinds: List[Kind] = []


class ProfileIn(BaseModel):
    institution_type: Optional[str] = Field(None, description="One of the institution type codes, or null to clear")
    has_ad: Optional[bool] = None


class MarkIn(BaseModel):
    value: int = Field(..., ge=-1, le=1, description="1 applies to me, -1 not for me, 0 undo")


class MuteIn(BaseModel):
    tag: str = Field(..., max_length=80)
    muted: bool = True


class Flag(BaseModel):
    for_you: bool
    reason: str = ""
    mark: int = 0
    applies_to: List[str] = []


class Guess(BaseModel):
    institution_type: Optional[str] = None
    has_ad: Optional[bool] = None


def _kinds() -> List[Kind]:
    return [Kind(code=c, label=v[0], bank=v[3]) for c, v in INSTITUTION_TYPES.items()]


async def _me(db: AsyncSession, user: User) -> Me:
    s = await service.scorer_for(db, user)
    p = s.profile
    items = s.interests()
    return Me(
        institution_type=p.kind, institution_label=INSTITUTION_TYPES[p.kind][0] if p.kind in INSTITUTION_TYPES else None,
        has_ad=p.has_ad, source=p.source, company=p.company,
        interests=[Interest(tag=t, label=service.tag_label(t), weight=w) for t, w in items if w > 0][:12],
        not_interested=[Interest(tag=t, label=service.tag_label(t), weight=w) for t, w in items if w < 0][:12],
        kinds=_kinds(),
    )


@router.get("/kinds", response_model=List[Kind])
async def kinds():
    return _kinds()


@router.get("/guess", response_model=Guess)
async def guess(company: str = Query(..., max_length=255)):
    """Institution type for a company name, when we recognise it (sign-up uses this to skip the question)."""
    g = guess_institution(company)
    return Guess(institution_type=g[0], has_ad=g[1]) if g else Guess()


@router.get("/me", response_model=Me)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await _me(db, user)


@router.put("/me/profile", response_model=Me)
async def set_profile(body: ProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    if body.institution_type and body.institution_type not in INSTITUTION_TYPES:
        raise HTTPException(status_code=422, detail="Unknown institution type.")
    await service.set_profile(db, user, body.institution_type, body.has_ad)
    return await _me(db, user)


@router.put("/me/interests", response_model=Me)
async def mute_interest(body: MuteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """Removes (or restores) one learned interest, e.g. "dept:FEPD"."""
    await service.set_muted(db, user, body.tag, body.muted)
    return await _me(db, user)


@router.put("/marks/{document_id}", response_model=Flag)
async def mark(document_id: UUID, body: MarkIn, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    docs = await service.facts(db)
    if document_id not in docs:
        raise HTTPException(status_code=404, detail="Circular not found.")
    await service.set_mark(db, user, document_id, body.value, request=request)
    s = await service.scorer_for(db, user)
    v = s.verdict(document_id)
    return Flag(for_you=v.for_you, reason=v.reason, mark=v.mark, applies_to=service.audience_labels(docs.get(document_id)))


@router.get("/flags", response_model=Dict[str, Flag])
async def flags(
    ids: str = Query(..., max_length=4000, description="Comma-separated circular ids"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db),
):
    """For you or not, with the reason, for the circulars on screen. Visitors get who each one applies to only."""
    wanted: List[UUID] = []
    for part in ids.split(",")[:120]:
        try:
            wanted.append(UUID(part.strip()))
        except ValueError:
            continue
    docs = await service.facts(db)
    s = await service.scorer_for(db, user) if user else None
    out: Dict[str, Flag] = {}
    for d in wanted:
        v = s.verdict(d) if s else service.Verdict(False)
        out[str(d)] = Flag(for_you=v.for_you, reason=v.reason, mark=v.mark, applies_to=service.audience_labels(docs.get(d)))
    return out
