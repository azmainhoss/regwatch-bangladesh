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
    try:
        insp = sa.inspect(bind)
        get_cols = lambda t: {c["name"] for c in insp.get_columns(t)} if insp.has_table(t) else set()
        has_table = insp.has_table
    except Exception:
        get_cols = lambda t: set()
        has_table = lambda t: False

    existing_analyses = get_cols("document_analyses")
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

    existing_pages = get_cols("document_pages")
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

    # 3. Create analysis_claims table
    if not has_table('analysis_claims'):
        op.create_table(
            'analysis_claims',
            sa.Column('id', backend.app.database.base.GUID(), primary_key=True),
            sa.Column('analysis_id', backend.app.database.base.GUID(), sa.ForeignKey('document_analyses.id', ondelete='CASCADE'), nullable=False),
            sa.Column('claim_type', sa.String(length=64), nullable=False),
            sa.Column('statement', sa.Text(), nullable=False),
            sa.Column('verification_status', sa.String(length=32), nullable=False, server_default='VERIFIED'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_analysis_claims_analysis_id', 'analysis_claims', ['analysis_id'])

    # 4. Create claim_citations table
    if not has_table('claim_citations'):
        op.create_table(
            'claim_citations',
            sa.Column('id', backend.app.database.base.GUID(), primary_key=True),
            sa.Column('claim_id', backend.app.database.base.GUID(), sa.ForeignKey('analysis_claims.id', ondelete='CASCADE'), nullable=False),
            sa.Column('page_id', backend.app.database.base.GUID(), sa.ForeignKey('document_pages.id', ondelete='CASCADE'), nullable=False),
            sa.Column('quoted_text', sa.Text(), nullable=False),
            sa.Column('match_score', sa.Float(), nullable=False, server_default='1.0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_claim_citations_claim_id', 'claim_citations', ['claim_id'])
        op.create_index('ix_claim_citations_page_id', 'claim_citations', ['page_id'])

    # 5. Create analysis_leases table for distributed lease locking
    if not has_table('analysis_leases'):
        op.create_table(
            'analysis_leases',
            sa.Column('document_id', backend.app.database.base.GUID(), sa.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('owner_worker_id', sa.String(length=128), nullable=False),
            sa.Column('lease_token', sa.String(length=64), nullable=False),
            sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='ACTIVE'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    try:
        insp = sa.inspect(bind)
        has_table = insp.has_table
    except Exception:
        has_table = lambda t: True

    if has_table('analysis_leases'):
        op.drop_table('analysis_leases')

    if has_table('claim_citations'):
        op.drop_table('claim_citations')

    if has_table('analysis_claims'):
        op.drop_table('analysis_claims')

    with op.batch_alter_table('document_pages', schema=None) as batch_op:
        batch_op.drop_column('is_human_corrected')
        batch_op.drop_column('human_corrected_text')
        batch_op.drop_column('ocr_text')
        batch_op.drop_column('native_text')
        batch_op.drop_column('layout_hierarchy')
        batch_op.drop_column('quality_score')
        batch_op.drop_column('quality_status')

    with op.batch_alter_table('document_analyses', schema=None) as batch_op:
        batch_op.drop_column('review_notes')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('publication_decision')
        batch_op.drop_column('processing_time_ms')
        batch_op.drop_column('estimated_cost_usd')
        batch_op.drop_column('tokens_used')
        batch_op.drop_column('validation_errors')
        batch_op.drop_column('raw_model_response')
