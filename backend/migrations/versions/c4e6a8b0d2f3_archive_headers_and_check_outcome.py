"""archive headers and check outcome

Adds what the archive keeps for every downloaded file (DECISIONS.md 5):
- `document_versions`: source_url, etag, last_modified, fetched_at, and a status
  (CURRENT or SUPERSEDED) so a replaced file becomes a new version and the old one is kept.
- `source_discoveries`: etag, last_modified, fetched_at.
- `source_runs.outcome`: the listing check result (OK, CHALLENGE, NO_TABLE, HTTP_ERROR, NETWORK_ERROR).

Revision ID: c4e6a8b0d2f3
Revises: b2d4f6a8c0e1
Create Date: 2026-11-12 18:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "c4e6a8b0d2f3"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = {
    "document_versions": [
        lambda: sa.Column("source_url", sa.String(length=1024), nullable=True),
        lambda: sa.Column("etag", sa.String(length=256), nullable=True),
        lambda: sa.Column("last_modified", sa.String(length=64), nullable=True),
        lambda: sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        lambda: sa.Column("status", sa.String(length=32), nullable=False, server_default="CURRENT"),
    ],
    "source_discoveries": [
        lambda: sa.Column("etag", sa.String(length=256), nullable=True),
        lambda: sa.Column("last_modified", sa.String(length=64), nullable=True),
        lambda: sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    ],
    "source_runs": [
        lambda: sa.Column("outcome", sa.String(length=32), nullable=True),
    ],
}


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, makers in NEW_COLUMNS.items():
        existing = _columns(table)
        for make in makers:
            column = make()
            if column.name not in existing:
                op.add_column(table, column)

    # Versions that already exist: copy the document's source URL so the re-check can find them.
    if not context.is_offline_mode():
        op.execute(
            "UPDATE document_versions SET source_url = "
            "(SELECT documents.source_url FROM documents WHERE documents.id = document_versions.document_id) "
            "WHERE source_url IS NULL"
        )
        # A document with several versions: every version but the current one is superseded.
        op.execute(
            "UPDATE document_versions SET status = 'SUPERSEDED' "
            "WHERE document_id IN (SELECT id FROM documents WHERE current_version_id IS NOT NULL) "
            "AND id NOT IN (SELECT current_version_id FROM documents WHERE current_version_id IS NOT NULL)"
        )


def downgrade() -> None:
    for table, makers in NEW_COLUMNS.items():
        existing = _columns(table)
        names = [make().name for make in makers]
        if context.is_offline_mode():
            names_to_drop = names
        else:
            names_to_drop = [n for n in names if n in existing]
        if not names_to_drop:
            continue
        if op.get_context().dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table, schema=None) as batch_op:
                for name in names_to_drop:
                    batch_op.drop_column(name)
        else:
            for name in names_to_drop:
                op.drop_column(table, name)
