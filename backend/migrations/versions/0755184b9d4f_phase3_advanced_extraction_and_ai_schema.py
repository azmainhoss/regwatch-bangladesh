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
    with op.batch_alter_table('document_analyses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('raw_model_response', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('validation_errors', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('tokens_used', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default='0.0'))
        batch_op.add_column(sa.Column('processing_time_ms', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('publication_decision', sa.String(length=32), nullable=False, server_default='AWAITING_REVIEW'))
        batch_op.add_column(sa.Column('reviewed_by', backend.app.database.base.GUID(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))
        batch_op.create_foreign_key('fk_document_analyses_reviewed_by_users', 'users', ['reviewed_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('quality_status', sa.String(length=32), nullable=False, server_default='SUCCESS_NATIVE'))
        batch_op.add_column(sa.Column('quality_score', sa.Float(), nullable=False, server_default='1.0'))
        batch_op.add_column(sa.Column('layout_hierarchy', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('native_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ocr_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('human_corrected_text', sa.Text(), nullable=True))
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
