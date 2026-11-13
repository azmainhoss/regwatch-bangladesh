"""Alert tables: event outbox, per-user inbox, preferences, email outbox and delivery log."""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint,
)

from backend.app.database.base import Base, GUID


class AlertEvent(Base):
    """One real-world event worth an alert. Fanned out to people by the dispatcher."""
    __tablename__ = "alert_events"

    kind = Column(String(48), nullable=False, index=True)
    dedupe_key = Column(String(255), nullable=False, unique=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(GUID(), nullable=True)
    actor_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient_user_ids = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(16), nullable=False, default="PENDING", index=True)  # PENDING DISPATCHED SUPPRESSED FAILED
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)

    __table_args__ = (Index("ix_alert_events_status_created", "status", "created_at"),)


class AlertNotification(Base):
    """One alert in one person's inbox."""
    __tablename__ = "alert_notifications"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(GUID(), ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=True, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(String(48), nullable=False)
    group = Column(String(32), nullable=False)
    dedupe_key = Column(String(255), nullable=False)
    severity = Column(String(8), nullable=False, default="info")  # info warn bad
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)  # in-app only (reviewer comments); never emailed
    link = Column(String(512), nullable=False)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    quote_text = Column(Text, nullable=True)
    quote_page_number = Column(Integer, nullable=True)
    quote_document_id = Column(GUID(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    in_app = Column(Boolean, nullable=False, default=True)
    email_mode = Column(String(8), nullable=False, default="OFF")  # OFF INSTANT DIGEST
    emailed_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_alert_notification_user_key"),
        Index("ix_alert_notifications_user_inbox", "user_id", "in_app", "read_at", "created_at"),
    )


class AlertPreference(Base):
    __tablename__ = "alert_preferences"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    channels = Column(JSON, nullable=False, default=dict)
    email_enabled = Column(Boolean, nullable=False, default=True)
    library_department_codes = Column(JSON, nullable=False, default=list)
    library_document_types = Column(JSON, nullable=False, default=list)
    library_keywords = Column(JSON, nullable=False, default=list)
    lock_version = Column(Integer, nullable=False, default=1, server_default="1")


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    organization_id = Column(GUID(), nullable=True)
    to_address = Column(String(255), nullable=False)
    kind = Column(String(8), nullable=False)  # INSTANT DIGEST TEST
    dedupe_key = Column(String(255), nullable=False, unique=True)
    notification_ids = Column(JSON, nullable=False, default=list)
    subject = Column(String(300), nullable=False)
    text_body = Column(Text, nullable=False)
    html_body = Column(Text, nullable=False)
    status = Column(String(12), nullable=False, default="PENDING", index=True)  # PENDING SENDING SENT FAILED EXPIRED
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, index=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(500), nullable=True)
    smtp_message_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_email_outbox_due", "status", "next_attempt_at"),)


class EmailDeliveryAttempt(Base):
    __tablename__ = "email_delivery_attempts"

    outbox_id = Column(GUID(), ForeignKey("email_outbox.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String(8), nullable=False)  # SENT RETRY FAILED
    smtp_code = Column(Integer, nullable=True)
    error = Column(String(500), nullable=True)
