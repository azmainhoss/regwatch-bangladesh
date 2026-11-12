"""Who can see which document.

Documents with no owner form the shared library and are visible to everyone.
Documents with an owner are private uploads: only the owner can see them.
Superusers get no exception here; they see the shared library plus their own
private uploads, never another user's.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.identity.deps import get_current_user_optional
from backend.app.modules.identity.models import User


async def get_document_reader(
    user: Optional[User] = Depends(get_current_user_optional),
) -> Optional[User]:
    """The caller for read endpoints: an active signed-in user, or None for anonymous reads."""
    if user is None or not user.is_active:
        return None
    return user


def visible_documents_condition(user: Optional[User]):
    """SQL condition matching documents the given user (or an anonymous caller) may read."""
    if user is None:
        return Document.owner_user_id.is_(None)
    return or_(Document.owner_user_id.is_(None), Document.owner_user_id == user.id)


def shared_documents_condition():
    """SQL condition matching only shared-library documents."""
    return Document.owner_user_id.is_(None)


def can_view_document(doc: Optional[Document], user: Optional[User]) -> bool:
    if doc is None:
        return False
    if doc.owner_user_id is None:
        return True
    return user is not None and str(doc.owner_user_id) == str(user.id)


async def get_visible_document(db: AsyncSession, document_id: UUID, user: Optional[User]) -> Document:
    """Loads a document the caller may read, or raises 404 (private documents of others look missing)."""
    doc = await db.get(Document, document_id)
    if not can_view_document(doc, user):
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


async def get_visible_version(
    db: AsyncSession, document_id: UUID, version_id: UUID, user: Optional[User]
) -> DocumentVersion:
    """Loads a version that belongs to a document the caller may read, or raises 404."""
    await get_visible_document(db, document_id, user)
    version = await db.get(DocumentVersion, version_id)
    if not version or str(version.document_id) != str(document_id):
        raise HTTPException(status_code=404, detail="Document version not found")
    return version
