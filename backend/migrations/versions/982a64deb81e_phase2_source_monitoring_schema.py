"""phase2_source_monitoring_schema

Revision ID: 982a64deb81e
Revises: 29119fb58419
Create Date: 2026-11-05 21:03:05.899034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import backend.app.database.base


# revision identifiers, used by Alembic.
revision: str = '982a64deb81e'
down_revision: Union[str, Sequence[str], None] = '29119fb58419'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. source_discoveries
    with op.batch_alter_table('source_discoveries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_id', backend.app.database.base.GUID(), nullable=True))
        batch_op.add_column(sa.Column('file_url', sa.String(length=1024), nullable=True))
        batch_op.add_column(sa.Column('title', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('department_code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('reference_number', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('publication_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_source_discoveries_document_id'), ['document_id'], unique=False)
        batch_op.create_foreign_key('fk_source_discoveries_document_id', 'documents', ['document_id'], ['id'], ondelete='SET NULL')

    # 2. source_runs
    with op.batch_alter_table('source_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pages_inspected', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('candidate_links_discovered', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('valid_documents_discovered', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('downloads_attempted', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('downloads_successful', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('duplicate_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('access_restricted', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('access_restriction_details', sa.JSON(), server_default='{}', nullable=False))
        batch_op.add_column(sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))

    # 3. sources
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('department_id', backend.app.database.base.GUID(), nullable=True))
        batch_op.add_column(sa.Column('monitoring_method', sa.String(length=32), server_default='POLLING_HTTP', nullable=False))
        batch_op.add_column(sa.Column('polling_frequency_minutes', sa.Integer(), server_default='60', nullable=False))
        batch_op.add_column(sa.Column('last_attempted_run_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_successful_run_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_discovered_publication_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('access_restriction_status', sa.String(length=64), server_default='CLEAR', nullable=False))
        batch_op.create_index(batch_op.f('ix_sources_department_id'), ['department_id'], unique=False)
        batch_op.create_foreign_key('fk_sources_department_id', 'institution_departments', ['department_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sources_department_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_sources_department_id'))
        batch_op.drop_column('access_restriction_status')
        batch_op.drop_column('last_error')
        batch_op.drop_column('last_discovered_publication_at')
        batch_op.drop_column('last_successful_run_at')
        batch_op.drop_column('last_attempted_run_at')
        batch_op.drop_column('polling_frequency_minutes')
        batch_op.drop_column('monitoring_method')
        batch_op.drop_column('department_id')

    with op.batch_alter_table('source_runs', schema=None) as batch_op:
        batch_op.drop_column('retry_count')
        batch_op.drop_column('access_restriction_details')
        batch_op.drop_column('access_restricted')
        batch_op.drop_column('duplicate_count')
        batch_op.drop_column('downloads_successful')
        batch_op.drop_column('downloads_attempted')
        batch_op.drop_column('valid_documents_discovered')
        batch_op.drop_column('candidate_links_discovered')
        batch_op.drop_column('pages_inspected')

    with op.batch_alter_table('source_discoveries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_source_discoveries_document_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_source_discoveries_document_id'))
        batch_op.drop_column('rejection_reason')
        batch_op.drop_column('publication_date')
        batch_op.drop_column('reference_number')
        batch_op.drop_column('department_code')
        batch_op.drop_column('title')
        batch_op.drop_column('file_url')
        batch_op.drop_column('document_id')
