"""Each person's own saved circulars: Favourites, Read later, and lists they name themselves."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from backend.app.database.base import Base, GUID


class UserList(Base):
    __tablename__ = "user_lists"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    # FAVOURITES and READ_LATER exist once per person and cannot be renamed or deleted; CUSTOM lists can.
    kind = Column(String(16), nullable=False, default="CUSTOM")

    __table_args__ = (Index("ix_user_lists_user_kind", "user_id", "kind"),)


class UserListItem(Base):
    __tablename__ = "user_list_items"

    list_id = Column(GUID(), ForeignKey("user_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    added_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("list_id", "document_id", name="uq_list_document"),)
