"""page correction history

Every human correction of a page's text is kept: who made it, when, why, the text before and the
text after (`page_corrections`, add-only). The page row carries the latest correction's author,
time and reason so a page can be shown with them at once.

Revision ID: f1b3d5a7c9e2
Revises: e7a9c1d3f5b6
Create Date: 2026-11-13 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "f1b3d5a7c9e2"
down_revision: Union[str, Sequence[str], None] = "e7a9c1d3f5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID

PAGE_COLUMNS = [
    lambda: sa.Column("correction_reason", sa.Text(), nullable=True),
    lambda: sa.Column("corrected_by_user_id", GUID(), nullable=True),
    lambda: sa.Column("corrected_by_name", sa.String(255), nullable=True),
    lambda: sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
]


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    existing = _columns("document_pages")
    for make in PAGE_COLUMNS:
        column = make()
        if column.name not in existing:
            op.add_column("document_pages", column)

    if not _has_table("page_corrections"):
        op.create_table(
            "page_corrections",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("page_id", GUID(), nullable=False),
            sa.Column("document_version_id", GUID(), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("corrected_by_user_id", GUID(), nullable=True),
            sa.Column("corrected_by_name", sa.String(255), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("previous_text", sa.Text(), nullable=True),
            sa.Column("corrected_text", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["page_id"], ["document_pages.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_page_corrections_page_id", "page_corrections", ["page_id"])
        op.create_index("ix_page_corrections_document_version_id", "page_corrections", ["document_version_id"])
        op.create_index("ix_page_corrections_corrected_by_user_id", "page_corrections", ["corrected_by_user_id"])


def downgrade() -> None:
    if context.is_offline_mode() or _has_table("page_corrections"):
        op.drop_table("page_corrections")
    existing = _columns("document_pages")
    names = [make().name for make in PAGE_COLUMNS]
    names = names if context.is_offline_mode() else [n for n in names if n in existing]
    if not names:
        return
    if op.get_context().dialect.name == "sqlite" and not context.is_offline_mode():
        with op.batch_alter_table("document_pages", schema=None) as batch_op:
            for name in names:
                batch_op.drop_column(name)
    else:
        for name in names:
            op.drop_column("document_pages", name)
