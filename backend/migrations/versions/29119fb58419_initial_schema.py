"""initial_schema

Revision ID: 29119fb58419
Revises: 
Create Date: 2026-11-05 19:53:54.523544

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import backend.app.database.base
from backend.app.database.base import GUID

revision: str = "29119fb58419"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        insp = sa.inspect(bind)
        has_table = insp.has_table
    except Exception:
        has_table = lambda t: False

    if not has_table("institutions"):
        op.create_table(
            "institutions",
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("name_bn", sa.String(length=255), nullable=True),
            sa.Column("website_url", sa.String(length=512), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("institution_departments"):
        op.create_table(
            "institution_departments",
            sa.Column("institution_id", backend.app.database.base.GUID(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("name_bn", sa.String(length=255), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("sources"):
        op.create_table(
            "sources",
            sa.Column("institution_id", backend.app.database.base.GUID(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("base_url", sa.String(length=512), nullable=True),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("source_runs"):
        op.create_table(
            "source_runs",
            sa.Column("source_id", backend.app.database.base.GUID(), sa.ForeignKey("sources.id"), nullable=False),
            sa.Column("run_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("discovered_count", sa.Integer(), nullable=False),
            sa.Column("downloaded_count", sa.Integer(), nullable=False),
            sa.Column("error_count", sa.Integer(), nullable=False),
            sa.Column("error_log", sa.String(length=None), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("source_discoveries"):
        op.create_table(
            "source_discoveries",
            sa.Column("source_run_id", backend.app.database.base.GUID(), sa.ForeignKey("source_runs.id"), nullable=False),
            sa.Column("source_url", sa.String(length=1024), nullable=False),
            sa.Column("discovered_metadata", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("documents"):
        op.create_table(
            "documents",
            sa.Column("institution_id", backend.app.database.base.GUID(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("department_id", backend.app.database.base.GUID(), sa.ForeignKey("institution_departments.id"), nullable=True),
            sa.Column("reference_number", sa.String(length=128), nullable=True),
            sa.Column("title", sa.String(length=None), nullable=False),
            sa.Column("title_bn", sa.String(length=None), nullable=True),
            sa.Column("document_type", sa.String(length=64), nullable=False),
            sa.Column("publication_date", sa.Date(), nullable=False),
            sa.Column("effective_date", sa.Date(), nullable=True),
            sa.Column("source_url", sa.String(length=1024), nullable=True),
            sa.Column("current_version_id", backend.app.database.base.GUID(), nullable=True),
            sa.Column("publication_status", sa.String(length=64), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("document_versions"):
        op.create_table(
            "document_versions",
            sa.Column("document_id", backend.app.database.base.GUID(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("file_mime_type", sa.String(length=64), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=False),
            sa.Column("language", sa.String(length=16), nullable=False),
            sa.Column("is_scanned", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("document_pages"):
        op.create_table(
            "document_pages",
            sa.Column("document_version_id", backend.app.database.base.GUID(), sa.ForeignKey("document_versions.id"), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("raw_text", sa.String(length=None), nullable=False),
            sa.Column("cleaned_text", sa.String(length=None), nullable=True),
            sa.Column("extraction_method", sa.String(length=32), nullable=False),
            sa.Column("ocr_confidence", sa.Float(), nullable=True),
            sa.Column("has_tables", sa.Boolean(), nullable=False),
            sa.Column("extracted_tables", sa.JSON(), nullable=False),
            sa.Column("page_image_path", sa.String(length=512), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("provisions"):
        op.create_table(
            "provisions",
            sa.Column("document_version_id", backend.app.database.base.GUID(), sa.ForeignKey("document_versions.id"), nullable=False),
            sa.Column("page_id", backend.app.database.base.GUID(), sa.ForeignKey("document_pages.id"), nullable=False),
            sa.Column("provision_number", sa.String(length=64), nullable=True),
            sa.Column("heading", sa.String(length=None), nullable=True),
            sa.Column("verbatim_text", sa.String(length=None), nullable=False),
            sa.Column("parent_provision_id", backend.app.database.base.GUID(), sa.ForeignKey("provisions.id"), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("document_relationships"):
        op.create_table(
            "document_relationships",
            sa.Column("source_document_id", backend.app.database.base.GUID(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("target_document_id", backend.app.database.base.GUID(), sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("target_reference_hint", sa.String(length=255), nullable=True),
            sa.Column("relationship_type", sa.String(length=32), nullable=False),
            sa.Column("source_provision_id", backend.app.database.base.GUID(), sa.ForeignKey("provisions.id"), nullable=True),
            sa.Column("source_page_id", backend.app.database.base.GUID(), sa.ForeignKey("document_pages.id"), nullable=True),
            sa.Column("supporting_quote", sa.String(length=None), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("detection_method", sa.String(length=32), nullable=False),
            sa.Column("verification_status", sa.String(length=32), nullable=False),
            sa.Column("reviewed_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("obligations"):
        op.create_table(
            "obligations",
            sa.Column("document_version_id", backend.app.database.base.GUID(), sa.ForeignKey("document_versions.id"), nullable=False),
            sa.Column("provision_id", backend.app.database.base.GUID(), sa.ForeignKey("provisions.id"), nullable=True),
            sa.Column("page_id", backend.app.database.base.GUID(), sa.ForeignKey("document_pages.id"), nullable=False),
            sa.Column("obligation_type", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=None), nullable=False),
            sa.Column("requirement_description", sa.String(length=None), nullable=False),
            sa.Column("supporting_text", sa.String(length=None), nullable=False),
            sa.Column("applicability_summary", sa.String(length=None), nullable=False),
            sa.Column("explicit_deadline", sa.Date(), nullable=True),
            sa.Column("deadline_description", sa.String(length=None), nullable=True),
            sa.Column("frequency", sa.String(length=32), nullable=False),
            sa.Column("inferable_responsible_dept", sa.String(length=128), nullable=True),
            sa.Column("is_inferred", sa.Boolean(), nullable=False),
            sa.Column("verification_status", sa.String(length=32), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("obligation_applicability"):
        op.create_table(
            "obligation_applicability",
            sa.Column("obligation_id", backend.app.database.base.GUID(), sa.ForeignKey("obligations.id"), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("conditions", sa.String(length=None), nullable=True),
            sa.Column("is_exempt", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("document_analyses"):
        op.create_table(
            "document_analyses",
            sa.Column("document_version_id", backend.app.database.base.GUID(), sa.ForeignKey("document_versions.id"), nullable=False),
            sa.Column("executive_summary", sa.String(length=None), nullable=False),
            sa.Column("purpose", sa.String(length=None), nullable=True),
            sa.Column("background", sa.String(length=None), nullable=True),
            sa.Column("key_changes", sa.JSON(), nullable=False),
            sa.Column("impact_summary", sa.JSON(), nullable=False),
            sa.Column("model_name", sa.String(length=64), nullable=False),
            sa.Column("prompt_version", sa.String(length=32), nullable=False),
            sa.Column("structured_payload", sa.JSON(), nullable=False),
            sa.Column("citation_coverage_score", sa.Float(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("users"):
        op.create_table(
            "users",
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("phone_number", sa.String(length=32), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("is_superuser", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("user_profiles"):
        op.create_table(
            "user_profiles",
            sa.Column("user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("designation", sa.String(length=128), nullable=True),
            sa.Column("bio", sa.String(length=None), nullable=True),
            sa.Column("preferences", sa.JSON(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("registration_number", sa.String(length=128), nullable=True),
            sa.Column("license_number", sa.String(length=128), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("departments"):
        op.create_table(
            "departments",
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("head_user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("organization_members"):
        op.create_table(
            "organization_members",
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("department_id", backend.app.database.base.GUID(), sa.ForeignKey("departments.id"), nullable=True),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("compliance_registers"):
        op.create_table(
            "compliance_registers",
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=None), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("compliance_items"):
        op.create_table(
            "compliance_items",
            sa.Column("register_id", backend.app.database.base.GUID(), sa.ForeignKey("compliance_registers.id"), nullable=False),
            sa.Column("obligation_id", backend.app.database.base.GUID(), sa.ForeignKey("obligations.id"), nullable=False),
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("internal_code", sa.String(length=64), nullable=True),
            sa.Column("department_id", backend.app.database.base.GUID(), sa.ForeignKey("departments.id"), nullable=True),
            sa.Column("assigned_lead_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("internal_deadline", sa.Date(), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("compliance_tasks"):
        op.create_table(
            "compliance_tasks",
            sa.Column("compliance_item_id", backend.app.database.base.GUID(), sa.ForeignKey("compliance_items.id"), nullable=False),
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=None), nullable=True),
            sa.Column("assigned_to_user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.Column("priority", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("task_evidence"):
        op.create_table(
            "task_evidence",
            sa.Column("task_id", backend.app.database.base.GUID(), sa.ForeignKey("compliance_tasks.id"), nullable=False),
            sa.Column("organization_id", backend.app.database.base.GUID(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("submitted_by_user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("notes", sa.String(length=None), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("task_reviews"):
        op.create_table(
            "task_reviews",
            sa.Column("task_id", backend.app.database.base.GUID(), sa.ForeignKey("compliance_tasks.id"), nullable=False),
            sa.Column("reviewer_user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("comments", sa.String(length=None), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("task_events"):
        op.create_table(
            "task_events",
            sa.Column("task_id", backend.app.database.base.GUID(), sa.ForeignKey("compliance_tasks.id"), nullable=False),
            sa.Column("actor_user_id", backend.app.database.base.GUID(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("event_payload", sa.JSON(), nullable=False),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not has_table("audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("organization_id", backend.app.database.base.GUID(), nullable=True),
            sa.Column("actor_user_id", backend.app.database.base.GUID(), nullable=True),
            sa.Column("action", sa.String(length=128), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", backend.app.database.base.GUID(), nullable=False),
            sa.Column("before_state", sa.JSON(), nullable=True),
            sa.Column("after_state", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=None), nullable=True),
            sa.Column("id", backend.app.database.base.GUID(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    try:
        insp = sa.inspect(bind)
        has_table = insp.has_table
    except Exception:
        has_table = lambda t: True
    if has_table("audit_events"):
        op.drop_table("audit_events")
    if has_table("task_events"):
        op.drop_table("task_events")
    if has_table("task_reviews"):
        op.drop_table("task_reviews")
    if has_table("task_evidence"):
        op.drop_table("task_evidence")
    if has_table("compliance_tasks"):
        op.drop_table("compliance_tasks")
    if has_table("compliance_items"):
        op.drop_table("compliance_items")
    if has_table("compliance_registers"):
        op.drop_table("compliance_registers")
    if has_table("organization_members"):
        op.drop_table("organization_members")
    if has_table("departments"):
        op.drop_table("departments")
    if has_table("organizations"):
        op.drop_table("organizations")
    if has_table("user_profiles"):
        op.drop_table("user_profiles")
    if has_table("users"):
        op.drop_table("users")
    if has_table("document_analyses"):
        op.drop_table("document_analyses")
    if has_table("obligation_applicability"):
        op.drop_table("obligation_applicability")
    if has_table("obligations"):
        op.drop_table("obligations")
    if has_table("document_relationships"):
        op.drop_table("document_relationships")
    if has_table("provisions"):
        op.drop_table("provisions")
    if has_table("document_pages"):
        op.drop_table("document_pages")
    if has_table("document_versions"):
        op.drop_table("document_versions")
    if has_table("documents"):
        op.drop_table("documents")
    if has_table("source_discoveries"):
        op.drop_table("source_discoveries")
    if has_table("source_runs"):
        op.drop_table("source_runs")
    if has_table("sources"):
        op.drop_table("sources")
    if has_table("institution_departments"):
        op.drop_table("institution_departments")
    if has_table("institutions"):
        op.drop_table("institutions")