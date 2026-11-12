"""phase0 schema alignment

Brings a database built by `alembic upgrade head` in line with the models:

* analysis_leases gets the `id` column and the (id, document_id) primary key
  the model declares (leases are short-lived; existing rows are copied over).
* source_discoveries gets the download-tracking columns the code writes to.
* documents gets the explicit `is_synthetic_fixture` marker.
* Missing model indexes are created, and the model's unique rules are added
  as unique indexes when the existing data already satisfies them.

Every step checks the live schema first, so it is safe on databases that were
created with `create_all` and already have some of these pieces.

Revision ID: a1c3e5f7b9d2
Revises: 0755184b9d4f
Create Date: 2026-11-12 00:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "0755184b9d4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID

SOURCE_DISCOVERY_COLUMNS = [
    ("language", lambda: sa.Column("language", sa.String(length=32), nullable=True)),
    ("publication_type", lambda: sa.Column("publication_type", sa.String(length=64), nullable=False, server_default="CIRCULAR")),
    ("file_hash", lambda: sa.Column("file_hash", sa.String(length=64), nullable=True)),
    ("file_size", lambda: sa.Column("file_size", sa.Integer(), nullable=True)),
    ("retry_count", lambda: sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")),
    ("last_attempted_at", lambda: sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True)),
    ("error_message", lambda: sa.Column("error_message", sa.Text(), nullable=True)),
]

# (index name, table, columns, unique)
INDEXES = [
    ("ix_audit_events_action", "audit_events", ["action"], False),
    ("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"], False),
    ("ix_audit_events_entity_id", "audit_events", ["entity_id"], False),
    ("ix_audit_events_entity_type", "audit_events", ["entity_type"], False),
    ("ix_audit_events_organization_id", "audit_events", ["organization_id"], False),
    ("ix_compliance_items_department_id", "compliance_items", ["department_id"], False),
    ("ix_compliance_items_obligation_id", "compliance_items", ["obligation_id"], False),
    ("ix_compliance_items_organization_id", "compliance_items", ["organization_id"], False),
    ("ix_compliance_items_register_id", "compliance_items", ["register_id"], False),
    ("ix_compliance_items_status", "compliance_items", ["status"], False),
    ("ix_compliance_registers_organization_id", "compliance_registers", ["organization_id"], False),
    ("ix_compliance_tasks_assigned_to_user_id", "compliance_tasks", ["assigned_to_user_id"], False),
    ("ix_compliance_tasks_compliance_item_id", "compliance_tasks", ["compliance_item_id"], False),
    ("ix_compliance_tasks_due_date", "compliance_tasks", ["due_date"], False),
    ("ix_compliance_tasks_organization_id", "compliance_tasks", ["organization_id"], False),
    ("ix_compliance_tasks_status", "compliance_tasks", ["status"], False),
    ("ix_departments_organization_id", "departments", ["organization_id"], False),
    ("ix_document_analyses_document_version_id", "document_analyses", ["document_version_id"], False),
    ("ix_document_pages_document_version_id", "document_pages", ["document_version_id"], False),
    ("ix_document_pages_page_number", "document_pages", ["page_number"], False),
    ("ix_document_relationships_relationship_type", "document_relationships", ["relationship_type"], False),
    ("ix_document_relationships_source_document_id", "document_relationships", ["source_document_id"], False),
    ("ix_document_relationships_target_document_id", "document_relationships", ["target_document_id"], False),
    ("ix_document_versions_document_id", "document_versions", ["document_id"], False),
    ("ix_document_versions_file_sha256", "document_versions", ["file_sha256"], False),
    ("ix_documents_department_id", "documents", ["department_id"], False),
    ("ix_documents_document_type", "documents", ["document_type"], False),
    ("ix_documents_institution_id", "documents", ["institution_id"], False),
    ("ix_documents_publication_date", "documents", ["publication_date"], False),
    ("ix_documents_publication_status", "documents", ["publication_status"], False),
    ("ix_documents_reference_number", "documents", ["reference_number"], False),
    ("ix_institution_departments_code", "institution_departments", ["code"], False),
    ("ix_institution_departments_institution_id", "institution_departments", ["institution_id"], False),
    ("ix_institutions_code", "institutions", ["code"], True),
    ("ix_obligation_applicability_entity_type", "obligation_applicability", ["entity_type"], False),
    ("ix_obligation_applicability_obligation_id", "obligation_applicability", ["obligation_id"], False),
    ("ix_obligations_document_version_id", "obligations", ["document_version_id"], False),
    ("ix_obligations_obligation_type", "obligations", ["obligation_type"], False),
    ("ix_obligations_page_id", "obligations", ["page_id"], False),
    ("ix_obligations_provision_id", "obligations", ["provision_id"], False),
    ("ix_organization_members_organization_id", "organization_members", ["organization_id"], False),
    ("ix_organization_members_user_id", "organization_members", ["user_id"], False),
    ("ix_provisions_document_version_id", "provisions", ["document_version_id"], False),
    ("ix_provisions_page_id", "provisions", ["page_id"], False),
    ("ix_provisions_provision_number", "provisions", ["provision_number"], False),
    ("ix_source_discoveries_document_id", "source_discoveries", ["document_id"], False),
    ("ix_source_discoveries_source_run_id", "source_discoveries", ["source_run_id"], False),
    ("ix_source_runs_source_id", "source_runs", ["source_id"], False),
    ("ix_sources_department_id", "sources", ["department_id"], False),
    ("ix_sources_institution_id", "sources", ["institution_id"], False),
    ("ix_task_events_task_id", "task_events", ["task_id"], False),
    ("ix_task_evidence_organization_id", "task_evidence", ["organization_id"], False),
    ("ix_task_evidence_task_id", "task_evidence", ["task_id"], False),
    ("ix_task_reviews_task_id", "task_reviews", ["task_id"], False),
    ("ix_user_profiles_user_id", "user_profiles", ["user_id"], True),
    ("ix_users_email", "users", ["email"], True),
]

# (constraint name, table, columns) as declared in the models.
UNIQUE_CONSTRAINTS = [
    ("uq_org_department_name", "departments", ["organization_id", "name"]),
    ("uq_doc_version_page_num", "document_pages", ["document_version_id", "page_number"]),
    ("uq_document_version_num", "document_versions", ["document_id", "version_number"]),
    ("uq_institution_dept_code", "institution_departments", ["institution_id", "code"]),
    ("uq_org_user_membership", "organization_members", ["organization_id", "user_id"]),
]


# In offline (--sql) mode there is no database to inspect: assume the schema left by
# the previous revisions and emit every statement.
def _offline() -> bool:
    return context.is_offline_mode()


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    if _offline():
        return True
    return name in _inspector().get_table_names()


def _columns(table: str) -> set:
    if _offline():
        return set()
    return {c["name"] for c in _inspector().get_columns(table)}


def _index_names(table: str) -> set:
    if _offline():
        return set()
    return {i["name"] for i in _inspector().get_indexes(table)}


def _unique_names(table: str) -> set:
    if _offline():
        return set()
    return {u["name"] for u in _inspector().get_unique_constraints(table) if u.get("name")}


def _has_duplicates(table: str, columns: list) -> bool:
    if _offline():
        return False
    cols = ", ".join(columns)
    not_null = " AND ".join(f"{c} IS NOT NULL" for c in columns)
    sql = f"SELECT 1 FROM {table} WHERE {not_null} GROUP BY {cols} HAVING COUNT(*) > 1 LIMIT 1"
    return op.get_bind().execute(sa.text(sql)).first() is not None


def _rebuild_analysis_leases() -> None:
    rows = [] if _offline() else op.get_bind().execute(sa.text(
        "SELECT document_id, owner_worker_id, lease_token, acquired_at, expires_at, heartbeat_at, status, created_at, updated_at "
        "FROM analysis_leases"
    )).mappings().all()
    op.drop_table("analysis_leases")
    leases = op.create_table(
        "analysis_leases",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_worker_id", sa.String(length=128), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "document_id"),
    )
    if rows:
        op.bulk_insert(leases, [dict(r, id=uuid.uuid4()) for r in rows])


def upgrade() -> None:
    # 1. analysis_leases: add id / composite primary key
    if _has_table("analysis_leases") and "id" not in _columns("analysis_leases"):
        _rebuild_analysis_leases()

    # 2. source_discoveries: download tracking columns
    if _has_table("source_discoveries"):
        existing = _columns("source_discoveries")
        for name, factory in SOURCE_DISCOVERY_COLUMNS:
            if name not in existing:
                op.add_column("source_discoveries", factory())

    # 3. documents: explicit synthetic marker
    if _has_table("documents") and "is_synthetic_fixture" not in _columns("documents"):
        op.add_column("documents", sa.Column("is_synthetic_fixture", sa.Boolean(), nullable=False, server_default=sa.false()))

    # 4. indexes declared on the models
    for name, table, cols, unique in INDEXES:
        if not _has_table(table) or name in _index_names(table):
            continue
        if unique and _has_duplicates(table, cols):
            print(f"[migration] Skipping unique index {name}: existing rows in {table} have duplicates.")
            continue
        op.create_index(name, table, cols, unique=unique)

    # 5. unique constraints declared on the models (only when the existing data allows)
    for name, table, cols in UNIQUE_CONSTRAINTS:
        if not _has_table(table):
            continue
        if name in _index_names(table) or name in _unique_names(table):
            continue
        if _has_duplicates(table, cols):
            print(f"[migration] Skipping unique constraint {name}: existing rows in {table} have duplicates.")
            continue
        if _offline() and op.get_context().dialect.name == "sqlite":
            # SQLite cannot add a constraint without reading the live table.
            op.create_index(name, table, cols, unique=True)
        else:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_unique_constraint(name, cols)


def downgrade() -> None:
    for name, table, _cols in reversed(UNIQUE_CONSTRAINTS):
        if not _has_table(table):
            continue
        if name in _unique_names(table):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_constraint(name, type_="unique")
        elif name in _index_names(table):
            op.drop_index(name, table_name=table)

    for name, table, _cols, _unique in reversed(INDEXES):
        if _has_table(table) and name in _index_names(table):
            op.drop_index(name, table_name=table)

    if _has_table("documents") and "is_synthetic_fixture" in _columns("documents"):
        with op.batch_alter_table("documents", schema=None) as batch_op:
            batch_op.drop_column("is_synthetic_fixture")

    if _has_table("source_discoveries"):
        existing = _columns("source_discoveries")
        drop = [name for name, _f in SOURCE_DISCOVERY_COLUMNS if name in existing]
        if drop:
            with op.batch_alter_table("source_discoveries", schema=None) as batch_op:
                for name in drop:
                    batch_op.drop_column(name)

    # analysis_leases keeps its id column on downgrade: removing it would break the model.
