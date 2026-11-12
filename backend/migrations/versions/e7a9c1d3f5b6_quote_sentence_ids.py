"""quote sentence ids

Quotes picked by sentence ID (DECISIONS.md 7, prompt v2). Each quoted item keeps where its
quote came from, so a viewer can highlight it on the page image:
- `quote_span_ids` (JSON): sentence IDs such as "p3.s12" (page 3, sentence 12).
- `quote_boxes` (JSON): [{page_number, line_index, box_2d}] from the page's line_boxes, when known.

Added to provisions, obligations, document_relationships and claim_citations. Old rows keep NULL.

Revision ID: e7a9c1d3f5b6
Revises: d5f7b9c1e3a4
Create Date: 2026-11-12 23:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "e7a9c1d3f5b6"
down_revision: Union[str, Sequence[str], None] = "d5f7b9c1e3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("provisions", "obligations", "document_relationships", "claim_citations")
COLUMNS = ("quote_span_ids", "quote_boxes")


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table in TABLES:
        existing = _columns(table)
        for name in COLUMNS:
            if name not in existing:
                op.add_column(table, sa.Column(name, sa.JSON(), nullable=True))


def downgrade() -> None:
    sqlite = op.get_context().dialect.name == "sqlite" and not context.is_offline_mode()
    for table in TABLES:
        existing = _columns(table)
        names = list(COLUMNS) if context.is_offline_mode() else [n for n in COLUMNS if n in existing]
        if not names:
            continue
        if sqlite:
            with op.batch_alter_table(table, schema=None) as batch_op:
                for name in names:
                    batch_op.drop_column(name)
        else:
            for name in names:
                op.drop_column(table, name)
