"""private document ownership

Adds `documents.owner_user_id`. NULL means the document sits in the shared
library everyone can read; a user id means it is a private upload only that
user can see.

Also repairs document pages imported from the old seed fixture, where the
JSON columns `extracted_tables` and `layout_hierarchy` were stored as a JSON
string instead of a list/object.

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-11-12 12:00:00.000000
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID

FK_NAME = "fk_documents_owner_user_id_users"
INDEX_NAME = "ix_documents_owner_user_id"


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _stringified_json(value):
    """Returns the decoded value when a JSON column holds a JSON string of a list/object, else None."""
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except ValueError:
        return None
    if op.get_bind().dialect.name == "sqlite":
        # SQLite hands back the stored text: a healthy row decodes to a list/dict,
        # a broken one decodes to a string that itself holds JSON.
        if not isinstance(decoded, str):
            return None
        try:
            decoded = json.loads(decoded)
        except ValueError:
            return None
    return decoded if isinstance(decoded, (list, dict)) else None


def _repair_page_json() -> None:
    if context.is_offline_mode() or "extracted_tables" not in _columns("document_pages"):
        return
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, extracted_tables, layout_hierarchy FROM document_pages")).all()
    for row_id, tables, layout in rows:
        fixed_tables = _stringified_json(tables)
        fixed_layout = _stringified_json(layout)
        if fixed_tables is None and fixed_layout is None:
            continue
        if fixed_tables is None:
            fixed_tables = tables if isinstance(tables, list) else json.loads(tables) if isinstance(tables, str) else []
        elif not isinstance(fixed_tables, list):
            fixed_tables = [fixed_tables]
        if fixed_layout is None:
            fixed_layout = layout if isinstance(layout, dict) else json.loads(layout) if isinstance(layout, str) else {}
        elif not isinstance(fixed_layout, dict):
            fixed_layout = {"blocks": fixed_layout}
        # The id is passed back exactly as the database returned it (no type conversion).
        stmt = sa.text(
            "UPDATE document_pages SET extracted_tables = :tables, layout_hierarchy = :layout WHERE id = :row_id"
        ).bindparams(
            sa.bindparam("tables", type_=sa.JSON()),
            sa.bindparam("layout", type_=sa.JSON()),
        )
        bind.execute(stmt, {"tables": fixed_tables, "layout": fixed_layout, "row_id": row_id})


def _is_sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


def upgrade() -> None:
    if "owner_user_id" not in _columns("documents"):
        if _is_sqlite():
            # SQLite cannot add a foreign key to an existing table without rebuilding it
            # (and batch rebuilds need a live connection). It does not enforce foreign keys
            # by default, so the plain column is enough there.
            op.add_column("documents", sa.Column("owner_user_id", GUID(), nullable=True))
        else:
            op.add_column("documents", sa.Column("owner_user_id", GUID(), nullable=True))
            op.create_foreign_key(FK_NAME, "documents", "users", ["owner_user_id"], ["id"], ondelete="CASCADE")
        op.create_index(INDEX_NAME, "documents", ["owner_user_id"], unique=False)
    _repair_page_json()


def downgrade() -> None:
    if not context.is_offline_mode() and "owner_user_id" not in _columns("documents"):
        return
    op.drop_index(INDEX_NAME, table_name="documents")
    if _is_sqlite():
        if context.is_offline_mode():
            op.drop_column("documents", "owner_user_id")
        else:
            with op.batch_alter_table("documents", schema=None) as batch_op:
                batch_op.drop_column("owner_user_id")
    else:
        op.drop_constraint(FK_NAME, "documents", type_="foreignkey")
        op.drop_column("documents", "owner_user_id")
