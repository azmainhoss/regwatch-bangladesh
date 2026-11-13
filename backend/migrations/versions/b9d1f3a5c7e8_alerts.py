"""alerts

Alert tables: the event outbox, each person's inbox, preferences, the email outbox and its
delivery log. Circulars that are already published stay quiet: each one gets a SUPPRESSED
"already announced" event so turning alerts on never floods anyone with old circulars.

Revision ID: b9d1f3a5c7e8
Revises: a3c5e7f9b1d4
Create Date: 2026-11-13 18:00:00.000000
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "b9d1f3a5c7e8"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID
TABLES = ["email_delivery_attempts", "email_outbox", "alert_preferences", "alert_notifications", "alert_events"]


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def _base():
    return [
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _fk(col: str, target: str, ondelete: str, table: str):
    return sa.ForeignKey(target, ondelete=ondelete, name=f"fk_{table}_{col}_{target.split('.')[0]}")


def upgrade() -> None:
    if not _has_table("alert_events"):
        op.create_table(
            "alert_events", *_base(),
            sa.Column("kind", sa.String(48), nullable=False),
            sa.Column("dedupe_key", sa.String(255), nullable=False),
            sa.Column("organization_id", GUID(), _fk("organization_id", "organizations.id", "CASCADE", "alert_events"), nullable=True),
            sa.Column("document_id", GUID(), _fk("document_id", "documents.id", "CASCADE", "alert_events"), nullable=True),
            sa.Column("entity_type", sa.String(64), nullable=True),
            sa.Column("entity_id", GUID(), nullable=True),
            sa.Column("actor_user_id", GUID(), _fk("actor_user_id", "users.id", "SET NULL", "alert_events"), nullable=True),
            sa.Column("recipient_user_ids", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.String(500), nullable=True),
            sa.UniqueConstraint("dedupe_key", name="uq_alert_events_dedupe_key"),
        )
        op.create_index("ix_alert_events_kind", "alert_events", ["kind"])
        op.create_index("ix_alert_events_organization_id", "alert_events", ["organization_id"])
        op.create_index("ix_alert_events_document_id", "alert_events", ["document_id"])
        op.create_index("ix_alert_events_status", "alert_events", ["status"])
        op.create_index("ix_alert_events_status_created", "alert_events", ["status", "created_at"])

    if not _has_table("alert_notifications"):
        t = "alert_notifications"
        op.create_table(
            t, *_base(),
            sa.Column("user_id", GUID(), _fk("user_id", "users.id", "CASCADE", t), nullable=False),
            sa.Column("event_id", GUID(), _fk("event_id", "alert_events.id", "CASCADE", t), nullable=True),
            sa.Column("organization_id", GUID(), _fk("organization_id", "organizations.id", "CASCADE", t), nullable=True),
            sa.Column("kind", sa.String(48), nullable=False),
            sa.Column("group", sa.String(32), nullable=False),
            sa.Column("dedupe_key", sa.String(255), nullable=False),
            sa.Column("severity", sa.String(8), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("link", sa.String(512), nullable=False),
            sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="SET NULL", name="fk_alert_notifications_document_id_documents"), nullable=True),
            sa.Column("quote_text", sa.Text(), nullable=True),
            sa.Column("quote_page_number", sa.Integer(), nullable=True),
            sa.Column("quote_document_id", GUID(), sa.ForeignKey("documents.id", ondelete="SET NULL", name="fk_alert_notifications_quote_document_id_documents"), nullable=True),
            sa.Column("in_app", sa.Boolean(), nullable=False),
            sa.Column("email_mode", sa.String(8), nullable=False),
            sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "dedupe_key", name="uq_alert_notification_user_key"),
        )
        op.create_index("ix_alert_notifications_user_id", t, ["user_id"])
        op.create_index("ix_alert_notifications_event_id", t, ["event_id"])
        op.create_index("ix_alert_notifications_organization_id", t, ["organization_id"])
        op.create_index("ix_alert_notifications_user_inbox", t, ["user_id", "in_app", "read_at", "created_at"])

    if not _has_table("alert_preferences"):
        op.create_table(
            "alert_preferences", *_base(),
            sa.Column("user_id", GUID(), _fk("user_id", "users.id", "CASCADE", "alert_preferences"), nullable=False),
            sa.Column("channels", sa.JSON(), nullable=False),
            sa.Column("email_enabled", sa.Boolean(), nullable=False),
            sa.Column("library_department_codes", sa.JSON(), nullable=False),
            sa.Column("library_document_types", sa.JSON(), nullable=False),
            sa.Column("library_keywords", sa.JSON(), nullable=False),
            sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("user_id", name="uq_alert_preferences_user_id"),
        )

    if not _has_table("email_outbox"):
        op.create_table(
            "email_outbox", *_base(),
            sa.Column("user_id", GUID(), _fk("user_id", "users.id", "CASCADE", "email_outbox"), nullable=True),
            sa.Column("organization_id", GUID(), nullable=True),
            sa.Column("to_address", sa.String(255), nullable=False),
            sa.Column("kind", sa.String(8), nullable=False),
            sa.Column("dedupe_key", sa.String(255), nullable=False),
            sa.Column("notification_ids", sa.JSON(), nullable=False),
            sa.Column("subject", sa.String(300), nullable=False),
            sa.Column("text_body", sa.Text(), nullable=False),
            sa.Column("html_body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(500), nullable=True),
            sa.Column("smtp_message_id", sa.String(255), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
        )
        op.create_index("ix_email_outbox_user_id", "email_outbox", ["user_id"])
        op.create_index("ix_email_outbox_status", "email_outbox", ["status"])
        op.create_index("ix_email_outbox_next_attempt_at", "email_outbox", ["next_attempt_at"])
        op.create_index("ix_email_outbox_due", "email_outbox", ["status", "next_attempt_at"])

    if not _has_table("email_delivery_attempts"):
        op.create_table(
            "email_delivery_attempts", *_base(),
            sa.Column("outbox_id", GUID(), _fk("outbox_id", "email_outbox.id", "CASCADE", "email_delivery_attempts"), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome", sa.String(8), nullable=False),
            sa.Column("smtp_code", sa.Integer(), nullable=True),
            sa.Column("error", sa.String(500), nullable=True),
        )
        op.create_index("ix_email_delivery_attempts_outbox_id", "email_delivery_attempts", ["outbox_id"])

    _backfill_announced()


def _backfill_announced() -> None:
    """Every published shared circular counts as already announced."""
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("documents"):
        return
    events = sa.table(
        "alert_events",
        sa.column("id", GUID()), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)), sa.column("kind", sa.String),
        sa.column("dedupe_key", sa.String), sa.column("document_id", GUID()),
        sa.column("entity_type", sa.String), sa.column("entity_id", GUID()),
        sa.column("payload", sa.JSON()), sa.column("status", sa.String),
        sa.column("attempts", sa.Integer),
    )
    existing = {r[0] for r in bind.execute(sa.text("SELECT dedupe_key FROM alert_events"))}
    docs = bind.execute(sa.text(
        "SELECT id FROM documents WHERE owner_user_id IS NULL AND publication_status LIKE 'PUBLISHED%'"
    )).fetchall()
    now = datetime.now(timezone.utc)
    rows = []
    for (doc_id,) in docs:
        did = uuid.UUID(str(doc_id))
        key = f"CIRCULAR_PUBLISHED:{did}"
        if key in existing:
            continue
        rows.append({
            "id": uuid.uuid4(), "created_at": now, "updated_at": now, "kind": "CIRCULAR_PUBLISHED",
            "dedupe_key": key, "document_id": did, "entity_type": "document", "entity_id": did,
            "payload": {}, "status": "SUPPRESSED", "attempts": 0,
        })
    if rows:
        op.bulk_insert(events, rows)


def downgrade() -> None:
    for name in TABLES:
        if _has_table(name):
            op.drop_table(name)
