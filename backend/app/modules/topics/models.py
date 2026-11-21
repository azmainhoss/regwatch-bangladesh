"""Which subject categories each circular belongs to (several per circular is normal)."""
from sqlalchemy import Column, ForeignKey, Index, String, UniqueConstraint

from backend.app.database.base import Base, GUID


class DocumentTopic(Base):
    __tablename__ = "document_topics"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = Column(String(32), nullable=False, index=True)
    # How it was set: AI (the classifier) or RULE (the reference number or title made it certain).
    source = Column(String(16), nullable=False, default="AI")

    __table_args__ = (
        UniqueConstraint("document_id", "topic", name="uq_document_topic"),
        Index("ix_document_topics_topic_doc", "topic", "document_id"),
    )
