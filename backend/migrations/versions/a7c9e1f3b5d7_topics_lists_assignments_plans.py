"""subject categories and saved lists

document_topics: the subject categories of each circular (several each).
user_lists / user_list_items: each person's Favourites, Read later and own named lists.
circular_assignments: a circular handed to a team member.
subscriptions / daily_usage: plans (Free, Pro, Enterprise) and the Free plan's daily question count.

Revision ID: a7c9e1f3b5d7
Revises: c7e9a1b3d5f8
Create Date: 2026-11-21 19:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "a7c9e1f3b5d7"
down_revision: Union[str, Sequence[str], None] = "c7e9a1b3d5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def _base_columns():
    return [
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    if not _has_table("document_topics"):
        op.create_table(
            "document_topics",
            *_base_columns(),
            sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("topic", sa.String(32), nullable=False),
            sa.Column("source", sa.String(16), nullable=False),
            sa.UniqueConstraint("document_id", "topic", name="uq_document_topic"),
        )
        op.create_index("ix_document_topics_document_id", "document_topics", ["document_id"])
        op.create_index("ix_document_topics_topic", "document_topics", ["topic"])
        op.create_index("ix_document_topics_topic_doc", "document_topics", ["topic", "document_id"])
    if not _has_table("user_lists"):
        op.create_table(
            "user_lists",
            *_base_columns(),
            sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
        )
        op.create_index("ix_user_lists_user_id", "user_lists", ["user_id"])
        op.create_index("ix_user_lists_user_kind", "user_lists", ["user_id", "kind"])
    if not _has_table("user_list_items"):
        op.create_table(
            "user_list_items",
            *_base_columns(),
            sa.Column("list_id", GUID(), sa.ForeignKey("user_lists.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("list_id", "document_id", name="uq_list_document"),
        )
        op.create_index("ix_user_list_items_list_id", "user_list_items", ["list_id"])
        op.create_index("ix_user_list_items_document_id", "user_list_items", ["document_id"])


    if not _has_table("circular_assignments"):
        op.create_table(
            "circular_assignments",
            *_base_columns(),
            sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("organization_id", GUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assigned_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assignee_user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("email_status", sa.String(12), nullable=True),
        )
        for col in ("document_id", "organization_id", "assigned_by_user_id", "assignee_user_id"):
            op.create_index(f"ix_circular_assignments_{col}", "circular_assignments", [col])
        op.create_index("ix_assignments_assignee_status", "circular_assignments", ["assignee_user_id", "status"])


    if not _has_table("subscriptions"):
        op.create_table(
            "subscriptions",
            *_base_columns(),
            sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("organization_id", GUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("plan", sa.String(16), nullable=False),
            sa.Column("seats", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("requested_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("organization_name", sa.String(255), nullable=True),
            sa.Column("contact_phone", sa.String(40), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("ends_on", sa.Date(), nullable=True),
        )
        for col in ("user_id", "organization_id", "status"):
            op.create_index(f"ix_subscriptions_{col}", "subscriptions", [col])
    if not _has_table("daily_usage"):
        op.create_table(
            "daily_usage",
            *_base_columns(),
            sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.UniqueConstraint("user_id", "day", "kind", name="uq_daily_usage"),
        )
        op.create_index("ix_daily_usage_user_day", "daily_usage", ["user_id", "day"])


def downgrade() -> None:
    for name in ("daily_usage", "subscriptions", "circular_assignments", "user_list_items", "user_lists", "document_topics"):
        if _has_table(name):
            op.drop_table(name)
