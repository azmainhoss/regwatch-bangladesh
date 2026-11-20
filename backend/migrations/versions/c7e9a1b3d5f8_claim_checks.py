"""claim checks

Each shown item of an analysis becomes its own claim with its own checks and status, and the
second reading of quoted sentences on image-read pages gets its own table.

Revision ID: c7e9a1b3d5f8
Revises: b9d1f3a5c7e8
Create Date: 2026-11-13 21:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "c7e9a1b3d5f8"
down_revision: Union[str, Sequence[str], None] = "b9d1f3a5c7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID

NEW_INDEXES = {
    "ix_analysis_claims_kind": "kind",
    "ix_analysis_claims_check_status": "check_status",
    "ix_analysis_claims_review_queue": "review_queue",
    "ix_analysis_claims_fingerprint": "fingerprint",
}


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def _is_sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


def _new_columns():
    # (name, column, foreign key target or None)
    return [
        ("kind", sa.Column("kind", sa.String(32), nullable=False, server_default="PROVISION"), None),
        ("order_index", sa.Column("order_index", sa.Integer(), nullable=True, server_default="0"), None),
        ("fields", sa.Column("fields", sa.JSON(), nullable=True), None),
        ("evidence", sa.Column("evidence", sa.JSON(), nullable=True), None),
        ("checks", sa.Column("checks", sa.JSON(), nullable=True), None),
        ("check_status", sa.Column("check_status", sa.String(32), nullable=False, server_default="CHECKING"), None),
        ("review_queue", sa.Column("review_queue", sa.String(16), nullable=True), None),
        ("is_high_stakes", sa.Column("is_high_stakes", sa.Boolean(), nullable=True, server_default=sa.false()), None),
        ("obligation_id", sa.Column("obligation_id", GUID(), nullable=True), ("obligations", "SET NULL")),
        ("relationship_id", sa.Column("relationship_id", GUID(), nullable=True), ("document_relationships", "SET NULL")),
        ("fingerprint", sa.Column("fingerprint", sa.String(64), nullable=True), None),
        ("carried_from_claim_id", sa.Column("carried_from_claim_id", GUID(), nullable=True), None),
        ("original_fields", sa.Column("original_fields", sa.JSON(), nullable=True), None),
        ("reviewed_by", sa.Column("reviewed_by", GUID(), nullable=True), ("users", "SET NULL")),
        ("reviewed_at", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True), None),
        ("review_note", sa.Column("review_note", sa.Text(), nullable=True), None),
        ("reject_reason", sa.Column("reject_reason", sa.String(64), nullable=True), None),
    ]


def upgrade() -> None:
    have = _columns("analysis_claims")
    for name, column, fk in _new_columns():
        if name in have:
            continue
        op.add_column("analysis_claims", column)
        if fk and not _is_sqlite():
            op.create_foreign_key(f"fk_analysis_claims_{name}_{fk[0]}", "analysis_claims", fk[0], [name], ["id"], ondelete=fk[1])
    existing_indexes = set()
    if not context.is_offline_mode():
        existing_indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("analysis_claims")}
    for index_name, column in NEW_INDEXES.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, "analysis_claims", [column], unique=False)

    if not _has_table("quote_reading_checks"):
        op.create_table(
            "quote_reading_checks",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("page_id", GUID(), sa.ForeignKey("document_pages.id", ondelete="CASCADE", name="fk_quote_reading_checks_page_id_document_pages"), nullable=False),
            sa.Column("sentence_id", sa.String(16), nullable=False),
            sa.Column("line_indexes", sa.JSON(), nullable=True),
            sa.Column("page_text_sha", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("our_text", sa.Text(), nullable=True),
            sa.Column("reads", sa.JSON(), nullable=True),
            sa.Column("numbers_confirmed", sa.JSON(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("page_id", "sentence_id", "page_text_sha", name="uq_quote_reading_page_sentence_sha"),
        )
        op.create_index("ix_quote_reading_checks_page_id", "quote_reading_checks", ["page_id"], unique=False)
        op.create_index("ix_quote_reading_checks_status", "quote_reading_checks", ["status"], unique=False)


def downgrade() -> None:
    if _has_table("quote_reading_checks"):
        op.drop_index("ix_quote_reading_checks_status", table_name="quote_reading_checks")
        op.drop_index("ix_quote_reading_checks_page_id", table_name="quote_reading_checks")
        op.drop_table("quote_reading_checks")
    have = _columns("analysis_claims")
    for index_name in NEW_INDEXES:
        try:
            op.drop_index(index_name, table_name="analysis_claims")
        except Exception:
            pass
    names = [name for name, _c, _fk in _new_columns() if name in have]
    if _is_sqlite():
        with op.batch_alter_table("analysis_claims", schema=None) as batch_op:
            for name in names:
                batch_op.drop_column(name)
    else:
        for name, _c, fk in _new_columns():
            if name in names and fk:
                op.drop_constraint(f"fk_analysis_claims_{name}_{fk[0]}", "analysis_claims", type_="foreignkey")
        for name in names:
            op.drop_column("analysis_claims", name)
