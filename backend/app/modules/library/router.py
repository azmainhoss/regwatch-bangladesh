"""Saved circulars: GET/POST /me/lists, and add or remove a circular from a list."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.documents.access import visible_documents_condition
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.library.models import UserList, UserListItem

router = APIRouter(prefix="/me/lists", tags=["Saved circulars"])

BUILT_IN = (("FAVOURITES", "Favourites"), ("READ_LATER", "Read later"))


class ListRead(BaseModel):
    id: UUID
    name: str
    kind: str
    document_ids: List[UUID] = []


class ListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ListRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


async def ensure_built_in(db: AsyncSession, user: User) -> None:
    have = set((await db.execute(select(UserList.kind).where(UserList.user_id == user.id))).scalars().all())
    added = False
    for kind, name in BUILT_IN:
        if kind not in have:
            db.add(UserList(user_id=user.id, name=name, kind=kind))
            added = True
    if added:
        await db.commit()


async def read_lists(db: AsyncSession, user: User) -> List[ListRead]:
    await ensure_built_in(db, user)
    lists = (await db.execute(select(UserList).where(UserList.user_id == user.id).order_by(UserList.created_at))).scalars().all()
    rows = (await db.execute(
        select(UserListItem.list_id, UserListItem.document_id)
        .join(UserList, UserList.id == UserListItem.list_id)
        .where(UserList.user_id == user.id)
        .order_by(UserListItem.added_at.desc())
    )).all()
    items = {}
    for list_id, doc_id in rows:
        items.setdefault(list_id, []).append(doc_id)
    order = {"FAVOURITES": 0, "READ_LATER": 1}
    lists = sorted(lists, key=lambda l: (order.get(l.kind, 2), l.created_at))
    return [ListRead(id=l.id, name=l.name, kind=l.kind, document_ids=items.get(l.id, [])) for l in lists]


async def _own_list(db: AsyncSession, user: User, list_id: UUID) -> UserList:
    lst = await db.get(UserList, list_id)
    if not lst or lst.user_id != user.id:
        raise HTTPException(status_code=404, detail="List not found.")
    return lst


@router.get("", response_model=List[ListRead])
async def get_lists(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await read_lists(db, user)


@router.post("", response_model=List[ListRead], status_code=201)
async def create_list(body: ListCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the list a name.")
    count = (await db.execute(select(func.count()).select_from(UserList).where(UserList.user_id == user.id))).scalar_one()
    from backend.app.modules.plans.plans import PLANS
    from backend.app.modules.plans.router import _enforced, effective_plan
    plan, _ = await effective_plan(db, user)
    limit = PLANS[plan].custom_lists
    if limit and _enforced() and count - len(BUILT_IN) >= limit:
        raise HTTPException(status_code=402, detail=f"The Free plan has {limit} list of your own. Move to Pro for as many as you like.")
    if count >= 52:
        raise HTTPException(status_code=422, detail="You have reached the limit of 50 lists.")
    db.add(UserList(user_id=user.id, name=name, kind="CUSTOM"))
    await db.commit()
    return await read_lists(db, user)


@router.patch("/{list_id}", response_model=List[ListRead])
async def rename_list(list_id: UUID, body: ListRename, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    lst = await _own_list(db, user, list_id)
    if lst.kind != "CUSTOM":
        raise HTTPException(status_code=422, detail="This list cannot be renamed.")
    lst.name = body.name.strip() or lst.name
    await db.commit()
    return await read_lists(db, user)


@router.delete("/{list_id}", response_model=List[ListRead])
async def delete_list(list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    lst = await _own_list(db, user, list_id)
    if lst.kind != "CUSTOM":
        raise HTTPException(status_code=422, detail="This list cannot be deleted.")
    await db.delete(lst)
    await db.commit()
    return await read_lists(db, user)


@router.put("/{list_id}/items/{document_id}", response_model=List[ListRead])
async def add_to_list(list_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await _own_list(db, user, list_id)
    visible = (await db.execute(select(Document.id).where(Document.id == document_id, visible_documents_condition(user)))).scalar_one_or_none()
    if not visible:
        raise HTTPException(status_code=404, detail="Circular not found.")
    exists_ = (await db.execute(select(UserListItem.id).where(UserListItem.list_id == list_id, UserListItem.document_id == document_id))).scalar_one_or_none()
    if not exists_:
        db.add(UserListItem(list_id=list_id, document_id=document_id, added_at=datetime.now(timezone.utc)))
        await db.commit()
    return await read_lists(db, user)


@router.delete("/{list_id}/items/{document_id}", response_model=List[ListRead])
async def remove_from_list(list_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await _own_list(db, user, list_id)
    await db.execute(delete(UserListItem).where(UserListItem.list_id == list_id, UserListItem.document_id == document_id))
    await db.commit()
    return await read_lists(db, user)
