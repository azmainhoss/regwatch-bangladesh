"""Who each circular is addressed to, and each reader's "Applies to me" / "Not for me" marks."""
from sqlalchemy import Column, ForeignKey, Index, Integer, String, UniqueConstraint

from backend.app.database.base import Base, GUID


class DocumentAudience(Base):
    """One row per (circular, institution kind) it applies to, e.g. AUTHORIZED_DEALER.
    source: ANALYSIS (the checked analysis), ADDRESSEE (the circular's addressee line), DEPARTMENT (fallback)."""
    __tablename__ = "document_audiences"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    entity = Column(String(48), nullable=False, index=True)
    source = Column(String(16), nullable=False, default="ADDRESSEE")

    __table_args__ = (UniqueConstraint("document_id", "entity", name="uq_document_audience"),)


class CircularMark(Base):
    """A reader's own call on one circular: 1 = applies to me, -1 = not for me. organization_id is set when the
    reader belongs to a workspace, so the mark counts for the whole team."""
    __tablename__ = "circular_marks"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), nullable=True, index=True)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_circular_mark"),
        Index("ix_circular_marks_org_doc", "organization_id", "document_id"),
    )
