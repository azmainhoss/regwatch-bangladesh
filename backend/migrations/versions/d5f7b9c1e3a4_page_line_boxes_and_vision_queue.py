"""page line boxes and vision queue

Page reading by fonts (DECISIONS.md 6 and 10):
- `document_pages.line_boxes` (JSON): one box per text line, 0-1000 page scale, so a viewer
  can highlight a quote on the page.
- `document_pages.vision_attempts`, `vision_error`: the background page-image job's retries.

Data:
- PYMUPDF_NATIVE pages are renamed TEXT_LAYER.
- Pages read by the dropped methods (Tesseract, Bijoy converter) or holding the old
  "[Scanned document page]" placeholder go back in the page-image queue (PENDING_VISION, text
  emptied). Their old text is kept in ocr_text when that column was empty. Pages a person
  corrected are left alone.
- An English and a Bangla file of the same circular are language variants, not versions.
  Versions marked SUPERSEDED without a newer version of the same language and source URL are
  made CURRENT again.

Revision ID: d5f7b9c1e3a4
Revises: c4e6a8b0d2f3
Create Date: 2026-11-12 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "d5f7b9c1e3a4"
down_revision: Union[str, Sequence[str], None] = "c4e6a8b0d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    lambda: sa.Column("line_boxes", sa.JSON(), nullable=True),
    lambda: sa.Column("vision_attempts", sa.Integer(), nullable=False, server_default="0"),
    lambda: sa.Column("vision_error", sa.Text(), nullable=True),
]

DROPPED_METHODS = "('OCR_TESSERACT', 'BIJOY_UNICODE_CONVERTED', 'OCR_SKIPPED_LARGE_SCAN', 'SCANNED_PAGE_DEFERRED')"


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _columns("document_pages")
    for make in NEW_COLUMNS:
        column = make()
        if column.name not in existing:
            op.add_column("document_pages", column)

    op.execute("UPDATE document_pages SET extraction_method = 'TEXT_LAYER' WHERE extraction_method = 'PYMUPDF_NATIVE'")
    requeue = (
        f"(extraction_method IN {DROPPED_METHODS} OR raw_text = '[Scanned document page]') "
        "AND is_human_corrected = false"
    )
    op.execute(
        "UPDATE document_pages SET ocr_text = raw_text "
        f"WHERE {requeue} AND ocr_text IS NULL AND raw_text <> '[Scanned document page]'"
    )
    op.execute(
        "UPDATE document_pages SET raw_text = '', cleaned_text = '', extraction_method = 'GEMINI_VISION', "
        f"quality_status = 'PENDING_VISION', quality_score = 0 WHERE {requeue}"
    )

    op.execute(
        "UPDATE document_versions SET status = 'CURRENT' WHERE status = 'SUPERSEDED' AND NOT EXISTS ("
        "SELECT 1 FROM document_versions newer "
        "WHERE newer.document_id = document_versions.document_id "
        "AND newer.language = document_versions.language "
        "AND COALESCE(newer.source_url, '') = COALESCE(document_versions.source_url, '') "
        "AND newer.version_number > document_versions.version_number)"
    )


def downgrade() -> None:
    existing = _columns("document_pages")
    names = [make().name for make in NEW_COLUMNS]
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
