"""A circular handed to a team member to read and act on. Shown on both people's home screens."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Text

from backend.app.database.base import Base, GUID


class CircularAssignment(Base):
    __tablename__ = "circular_assignments"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    note = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String(12), nullable=False, default="OPEN")  # OPEN, DONE
    done_at = Column(DateTime(timezone=True), nullable=True)
    # Whether the email to the assignee went out: SENT, OFF (email not set up), FAILED.
    email_status = Column(String(12), nullable=True)

    __table_args__ = (Index("ix_assignments_assignee_status", "assignee_user_id", "status"),)
