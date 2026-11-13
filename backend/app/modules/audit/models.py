from sqlalchemy import Column, ForeignKey, Index, JSON, String, Text
from backend.app.database.base import Base, GUID


class AuditEvent(Base):
    __tablename__ = "audit_events"

    organization_id = Column(GUID(), nullable=True, index=True)
    actor_user_id = Column(GUID(), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)  # DOCUMENT_PUBLISHED, EVIDENCE_UPLOADED, TASK_REVIEWED, etc.
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(GUID(), nullable=False, index=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    __table_args__ = (Index("ix_audit_events_org_created", "organization_id", "created_at"),)
