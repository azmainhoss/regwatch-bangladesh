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
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. source_discoveries
    existing_disc = {c["name"] for c in insp.get_columns("source_discoveries")} if insp.has_table("source_discoveries") else set()
    with op.batch_alter_table('source_discoveries', schema=None) as batch_op:
        if 'document_id' not in existing_disc:
            batch_op.add_column(sa.Column('document_id', backend.app.database.base.GUID(), nullable=True))
        if 'file_url' not in existing_disc:
            batch_op.add_column(sa.Column('file_url', sa.String(length=1024), nullable=True))
        if 'title' not in existing_disc:
            batch_op.add_column(sa.Column('title', sa.Text(), nullable=True))
        if 'department_code' not in existing_disc:
            batch_op.add_column(sa.Column('department_code', sa.String(length=32), nullable=True))
        if 'reference_number' not in existing_disc:
            batch_op.add_column(sa.Column('reference_number', sa.String(length=128), nullable=True))
        if 'publication_date' not in existing_disc:
            batch_op.add_column(sa.Column('publication_date', sa.Date(), nullable=True))
        if 'rejection_reason' not in existing_disc:
            batch_op.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))

    # 2. source_runs
    existing_runs = {c["name"] for c in insp.get_columns("source_runs")} if insp.has_table("source_runs") else set()
    with op.batch_alter_table('source_runs', schema=None) as batch_op:
        if 'pages_inspected' not in existing_runs:
            batch_op.add_column(sa.Column('pages_inspected', sa.Integer(), server_default='0', nullable=False))
        if 'candidate_links_discovered' not in existing_runs:
            batch_op.add_column(sa.Column('candidate_links_discovered', sa.Integer(), server_default='0', nullable=False))
        if 'valid_documents_discovered' not in existing_runs:
            batch_op.add_column(sa.Column('valid_documents_discovered', sa.Integer(), server_default='0', nullable=False))
        if 'downloads_attempted' not in existing_runs:
            batch_op.add_column(sa.Column('downloads_attempted', sa.Integer(), server_default='0', nullable=False))
        if 'downloads_successful' not in existing_runs:
            batch_op.add_column(sa.Column('downloads_successful', sa.Integer(), server_default='0', nullable=False))
        if 'duplicate_count' not in existing_runs:
            batch_op.add_column(sa.Column('duplicate_count', sa.Integer(), server_default='0', nullable=False))
        if 'access_restricted' not in existing_runs:
            batch_op.add_column(sa.Column('access_restricted', sa.Boolean(), server_default='0', nullable=False))
        if 'access_restriction_details' not in existing_runs:
            batch_op.add_column(sa.Column('access_restriction_details', sa.JSON(), server_default='{}', nullable=False))
        if 'retry_count' not in existing_runs:
            batch_op.add_column(sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))

    # 3. sources
    existing_sources = {c["name"] for c in insp.get_columns("sources")} if insp.has_table("sources") else set()
    with op.batch_alter_table('sources', schema=None) as batch_op:
        if 'department_id' not in existing_sources:
            batch_op.add_column(sa.Column('department_id', backend.app.database.base.GUID(), nullable=True))
        if 'monitoring_method' not in existing_sources:
            batch_op.add_column(sa.Column('monitoring_method', sa.String(length=32), server_default='POLLING_HTTP', nullable=False))
        if 'polling_frequency_minutes' not in existing_sources:
            batch_op.add_column(sa.Column('polling_frequency_minutes', sa.Integer(), server_default='60', nullable=False))
        if 'last_attempted_run_at' not in existing_sources:
            batch_op.add_column(sa.Column('last_attempted_run_at', sa.DateTime(timezone=True), nullable=True))
        if 'last_successful_run_at' not in existing_sources:
            batch_op.add_column(sa.Column('last_successful_run_at', sa.DateTime(timezone=True), nullable=True))
        if 'last_discovered_publication_at' not in existing_sources:
            batch_op.add_column(sa.Column('last_discovered_publication_at', sa.DateTime(timezone=True), nullable=True))
        if 'last_error' not in existing_sources:
            batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))
        if 'access_restriction_status' not in existing_sources:
            batch_op.add_column(sa.Column('access_restriction_status', sa.String(length=64), server_default='CLEAR', nullable=False))


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
