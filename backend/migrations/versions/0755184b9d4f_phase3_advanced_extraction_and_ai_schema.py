"""phase3_advanced_extraction_and_ai_schema

Revision ID: 0755184b9d4f
Revises: 982a64deb81e
Create Date: 2026-11-05 22:07:55.962509

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import backend.app.database.base

# revision identifiers, used by Alembic.
revision: str = '0755184b9d4f'
down_revision: Union[str, Sequence[str], None] = '982a64deb81e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_analyses = {c["name"] for c in insp.get_columns("document_analyses")} if insp.has_table("document_analyses") else set()
    with op.batch_alter_table('document_analyses', schema=None) as batch_op:
        if 'raw_model_response' not in existing_analyses:
            batch_op.add_column(sa.Column('raw_model_response', sa.Text(), nullable=True))
        if 'validation_errors' not in existing_analyses:
            batch_op.add_column(sa.Column('validation_errors', sa.JSON(), nullable=False, server_default='[]'))
        if 'tokens_used' not in existing_analyses:
            batch_op.add_column(sa.Column('tokens_used', sa.Integer(), nullable=False, server_default='0'))
        if 'estimated_cost_usd' not in existing_analyses:
            batch_op.add_column(sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default='0.0'))
        if 'processing_time_ms' not in existing_analyses:
            batch_op.add_column(sa.Column('processing_time_ms', sa.Integer(), nullable=False, server_default='0'))
        if 'publication_decision' not in existing_analyses:
            batch_op.add_column(sa.Column('publication_decision', sa.String(length=32), nullable=False, server_default='AWAITING_REVIEW'))
        if 'reviewed_by' not in existing_analyses:
            batch_op.add_column(sa.Column('reviewed_by', backend.app.database.base.GUID(), nullable=True))
        if 'reviewed_at' not in existing_analyses:
            batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        if 'review_notes' not in existing_analyses:
            batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))

    existing_pages = {c["name"] for c in insp.get_columns("document_pages")} if insp.has_table("document_pages") else set()
    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        if 'quality_status' not in existing_pages:
            batch_op.add_column(sa.Column('quality_status', sa.String(length=32), nullable=False, server_default='SUCCESS_NATIVE'))
        if 'quality_score' not in existing_pages:
            batch_op.add_column(sa.Column('quality_score', sa.Float(), nullable=False, server_default='1.0'))
        if 'layout_hierarchy' not in existing_pages:
            batch_op.add_column(sa.Column('layout_hierarchy', sa.JSON(), nullable=False, server_default='{}'))
        if 'native_text' not in existing_pages:
            batch_op.add_column(sa.Column('native_text', sa.Text(), nullable=True))
        if 'ocr_text' not in existing_pages:
            batch_op.add_column(sa.Column('ocr_text', sa.Text(), nullable=True))
        if 'human_corrected_text' not in existing_pages:
            batch_op.add_column(sa.Column('human_corrected_text', sa.Text(), nullable=True))
        if 'is_human_corrected' not in existing_pages:
            batch_op.add_column(sa.Column('is_human_corrected', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        batch_op.drop_column('is_human_corrected')
        batch_op.drop_column('human_corrected_text')
        batch_op.drop_column('ocr_text')
        batch_op.drop_column('native_text')
        batch_op.drop_column('layout_hierarchy')
        batch_op.drop_column('quality_score')
        batch_op.drop_column('quality_status')

    with op.batch_alter_table('document_analyses', schema=None) as batch_op:
        batch_op.drop_constraint('fk_document_analyses_reviewed_by_users', type_='foreignkey')
        batch_op.drop_column('review_notes')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('publication_decision')
        batch_op.drop_column('processing_time_ms')
        batch_op.drop_column('estimated_cost_usd')
        batch_op.drop_column('tokens_used')
        batch_op.drop_column('validation_errors')
        batch_op.drop_column('raw_model_response')
