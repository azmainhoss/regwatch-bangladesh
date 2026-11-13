"""compliance workspace

Register items keep a full snapshot of the obligation they came from (exact quote, page,
circular and file fingerprint), so reading a circular again never breaks them. Items and tasks
get lock versions, sign-off fields and a source-change acknowledgement; evidence can be
withdrawn; item sign-offs get their own add-only table; "overdue" stops being a stored status.

Revision ID: a3c5e7f9b1d4
Revises: f1b3d5a7c9e2
Create Date: 2026-11-13 12:00:00.000000
"""
import contextlib
import hashlib
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

import backend.app.database.base

revision: str = "a3c5e7f9b1d4"
down_revision: Union[str, Sequence[str], None] = "f1b3d5a7c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = backend.app.database.base.GUID

NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
OBLIGATION_FK = "fk_compliance_items_obligation_id_obligations"

ITEM_COLUMNS = [
    lambda: sa.Column("source_document_id", GUID(), sa.ForeignKey("documents.id", ondelete="RESTRICT", name="fk_compliance_items_source_document_id_documents"), nullable=True),
    lambda: sa.Column("source_version_id", GUID(), sa.ForeignKey("document_versions.id", ondelete="RESTRICT", name="fk_compliance_items_source_version_id_document_versions"), nullable=True),
    lambda: sa.Column("source_file_sha256", sa.String(64), nullable=True),
    lambda: sa.Column("source_reference_number", sa.String(128), nullable=True),
    lambda: sa.Column("source_title", sa.Text(), nullable=True),
    lambda: sa.Column("source_publication_date", sa.Date(), nullable=True),
    lambda: sa.Column("source_page_number", sa.Integer(), nullable=True),
    lambda: sa.Column("source_quote", sa.Text(), nullable=True),
    lambda: sa.Column("source_quote_span_ids", sa.JSON(), nullable=True),
    lambda: sa.Column("source_quote_boxes", sa.JSON(), nullable=True),
    lambda: sa.Column("source_key", sa.String(64), nullable=True),
    lambda: sa.Column("obligation_title", sa.Text(), nullable=True),
    lambda: sa.Column("requirement_description", sa.Text(), nullable=True),
    lambda: sa.Column("obligation_type", sa.String(32), nullable=True),
    lambda: sa.Column("applicability_summary", sa.Text(), nullable=True),
    lambda: sa.Column("regulatory_deadline", sa.Date(), nullable=True),
    lambda: sa.Column("deadline_description", sa.Text(), nullable=True),
    lambda: sa.Column("frequency", sa.String(32), nullable=True),
    lambda: sa.Column("notes", sa.Text(), nullable=True),
    lambda: sa.Column("exemption_reason", sa.Text(), nullable=True),
    lambda: sa.Column("submitted_for_signoff_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_compliance_items_submitted_for_signoff_by_user_id_users"), nullable=True),
    lambda: sa.Column("submitted_for_signoff_at", sa.DateTime(timezone=True), nullable=True),
    lambda: sa.Column("signed_off_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_compliance_items_signed_off_by_user_id_users"), nullable=True),
    lambda: sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
    lambda: sa.Column("source_ack_signature", sa.String(255), nullable=True),
    lambda: sa.Column("source_ack_at", sa.DateTime(timezone=True), nullable=True),
    lambda: sa.Column("source_ack_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_compliance_items_source_ack_by_user_id_users"), nullable=True),
    lambda: sa.Column("source_ack_note", sa.Text(), nullable=True),
    lambda: sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
]
TASK_COLUMNS = [
    lambda: sa.Column("cancelled_reason", sa.Text(), nullable=True),
    lambda: sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
]
EVIDENCE_COLUMNS = [
    lambda: sa.Column("mime_type", sa.String(128), nullable=True),
    lambda: sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
    lambda: sa.Column("withdrawn_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_task_evidence_withdrawn_by_user_id_users"), nullable=True),
]
REVIEW_COLUMNS = [
    lambda: sa.Column("organization_id", GUID(), nullable=True),
    lambda: sa.Column("evidence_ids", sa.JSON(), nullable=True),
]
INDEXES = [
    ("ix_compliance_items_org_updated", "compliance_items", ["organization_id", "updated_at"]),
    ("ix_compliance_items_source_document_id", "compliance_items", ["source_document_id"]),
    ("ix_compliance_tasks_org_updated", "compliance_tasks", ["organization_id", "updated_at"]),
    ("ix_task_reviews_organization_id", "task_reviews", ["organization_id"]),
    ("ix_audit_events_org_created", "audit_events", ["organization_id", "created_at"]),
]


def _sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


def _columns(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def _indexes(table: str) -> set:
    if context.is_offline_mode():
        return set()
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


class _Direct:
    """Plain ALTER statements, used when no live database is available (offline SQL for PostgreSQL)."""

    def __init__(self, table: str):
        self.table = table

    def add_column(self, column):
        if _sqlite():  # no constraints can be added to an existing SQLite table
            column = sa.Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default)
        op.add_column(self.table, column)

    def drop_column(self, name):
        op.drop_column(self.table, name)

    # SQLite cannot alter constraints in place; its real upgrade uses the table-rebuild path above.
    def alter_column(self, name, **kw):
        if not _sqlite():
            op.alter_column(self.table, name, **kw)

    def drop_constraint(self, name, type_=None):
        if not _sqlite():
            op.drop_constraint(name, self.table, type_=type_)

    def create_foreign_key(self, name, referent, local, remote, ondelete=None):
        if not _sqlite():
            op.create_foreign_key(name, self.table, referent, local, remote, ondelete=ondelete)

    def create_unique_constraint(self, name, columns):
        if not _sqlite():
            op.create_unique_constraint(name, self.table, columns)


@contextlib.contextmanager
def _batch(table: str):
    if context.is_offline_mode():
        yield _Direct(table)
    elif _sqlite():
        with op.batch_alter_table(table, recreate="always", naming_convention=NAMING) as batch_op:
            yield batch_op
    else:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            yield batch_op


def _add_columns(table: str, makers) -> None:
    existing = _columns(table)
    todo = [make() for make in makers]
    todo = [c for c in todo if c.name not in existing]
    if not todo:
        return
    with _batch(table) as batch_op:
        for column in todo:
            batch_op.add_column(column)


def _source_key(version_id, page_number, quote) -> str:
    return hashlib.sha256(f"{version_id}|{page_number}|{quote}".encode("utf-8")).hexdigest()


def _backfill_snapshots(bind) -> None:
    meta = sa.MetaData()
    items = sa.Table("compliance_items", meta, autoload_with=bind)
    obligations = sa.Table("obligations", meta, autoload_with=bind)
    versions = sa.Table("document_versions", meta, autoload_with=bind)
    documents = sa.Table("documents", meta, autoload_with=bind)
    pages = sa.Table("document_pages", meta, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            items.c.id, items.c.register_id, items.c.obligation_id,
            obligations.c.document_version_id, obligations.c.supporting_text,
            obligations.c.quote_span_ids, obligations.c.quote_boxes, obligations.c.title,
            obligations.c.requirement_description, obligations.c.obligation_type,
            obligations.c.applicability_summary, obligations.c.explicit_deadline,
            obligations.c.deadline_description, obligations.c.frequency,
            versions.c.document_id, versions.c.file_sha256,
            documents.c.reference_number, documents.c.title.label("doc_title"), documents.c.publication_date,
            pages.c.page_number,
        )
        .select_from(
            items.join(obligations, obligations.c.id == items.c.obligation_id)
            .join(versions, versions.c.id == obligations.c.document_version_id)
            .join(documents, documents.c.id == versions.c.document_id)
            .outerjoin(pages, pages.c.id == obligations.c.page_id)
        )
        .order_by(items.c.created_at, items.c.id)
    ).all()

    seen = set()
    for r in rows:
        version_id = str(uuid.UUID(str(r.document_version_id)))
        key = _source_key(version_id, r.page_number, r.supporting_text)
        pair = (str(r.register_id), key)
        if pair in seen:
            key = f"{key[:27]}:{str(r.id)[:36]}"  # keeps the 64-character limit
        seen.add((str(r.register_id), key))
        bind.execute(
            items.update().where(items.c.id == r.id).values(
                source_document_id=r.document_id,
                source_version_id=r.document_version_id,
                source_file_sha256=r.file_sha256,
                source_reference_number=r.reference_number,
                source_title=r.doc_title,
                source_publication_date=r.publication_date,
                source_page_number=r.page_number,
                source_quote=r.supporting_text,
                source_quote_span_ids=r.quote_span_ids,
                source_quote_boxes=r.quote_boxes,
                source_key=key,
                obligation_title=r.title,
                requirement_description=r.requirement_description,
                obligation_type=r.obligation_type,
                applicability_summary=r.applicability_summary,
                regulatory_deadline=r.explicit_deadline,
                deadline_description=r.deadline_description,
                frequency=r.frequency,
            )
        )


def upgrade() -> None:
    # 1. New columns
    _add_columns("compliance_items", ITEM_COLUMNS)
    _add_columns("compliance_tasks", TASK_COLUMNS)
    _add_columns("task_evidence", EVIDENCE_COLUMNS)
    _add_columns("task_reviews", REVIEW_COLUMNS)

    if not context.is_offline_mode():
        bind = op.get_bind()
        # 3 + 4. Snapshot backfill (keys made unique per register)
        _backfill_snapshots(bind)
        # 5. OVERDUE is no longer a stored status
        bind.execute(sa.text("UPDATE compliance_items SET status='IN_PROGRESS' WHERE status='OVERDUE'"))
        # 6. Reviews learn their organization
        bind.execute(sa.text(
            "UPDATE task_reviews SET organization_id = "
            "(SELECT organization_id FROM compliance_tasks WHERE compliance_tasks.id = task_reviews.task_id) "
            "WHERE organization_id IS NULL"
        ))

    # 2 + 8. obligation_id becomes a nullable hint (SET NULL), and one item per source per register
    fk_name = OBLIGATION_FK
    if not context.is_offline_mode() and not _sqlite():
        for fk in sa.inspect(op.get_bind()).get_foreign_keys("compliance_items"):
            if fk.get("constrained_columns") == ["obligation_id"] and fk.get("name"):
                fk_name = fk["name"]
    with _batch("compliance_items") as batch_op:
        batch_op.alter_column("obligation_id", existing_type=GUID(), nullable=True)
        batch_op.drop_constraint(fk_name, type_="foreignkey")
        batch_op.create_foreign_key(OBLIGATION_FK, "obligations", ["obligation_id"], ["id"], ondelete="SET NULL")
        batch_op.create_unique_constraint("uq_register_item_source", ["register_id", "source_key"])

    # 7. Sign-off decisions on whole items
    if not _has_table("compliance_item_reviews"):
        op.create_table(
            "compliance_item_reviews",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("item_id", GUID(), nullable=False),
            sa.Column("organization_id", GUID(), nullable=False),
            sa.Column("reviewer_user_id", GUID(), nullable=False),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("comments", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["compliance_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_compliance_item_reviews_item_id", "compliance_item_reviews", ["item_id"])
        op.create_index("ix_compliance_item_reviews_organization_id", "compliance_item_reviews", ["organization_id"])

    # 8. Indexes (SQLite's table rebuild above may already have kept some)
    for name, table, cols in INDEXES:
        if name not in _indexes(table):
            op.create_index(name, table, cols)


def downgrade() -> None:
    if not context.is_offline_mode():
        bind = op.get_bind()
        nulls = bind.execute(sa.text("SELECT COUNT(*) FROM compliance_items WHERE obligation_id IS NULL")).scalar()
        if nulls:
            raise RuntimeError(
                f"Cannot downgrade: {nulls} register item(s) no longer point at an obligation. "
                "Remove them first, or keep this version."
            )

    for name, table, _cols in reversed(INDEXES):
        if name in _indexes(table):
            op.drop_index(name, table_name=table)

    if context.is_offline_mode() or _has_table("compliance_item_reviews"):
        op.drop_table("compliance_item_reviews")

    item_names = [make().name for make in ITEM_COLUMNS]
    existing = _columns("compliance_items")
    drop_names = item_names if context.is_offline_mode() else [n for n in item_names if n in existing]
    with _batch("compliance_items") as batch_op:
        batch_op.drop_constraint("uq_register_item_source", type_="unique")
        batch_op.drop_constraint(OBLIGATION_FK, type_="foreignkey")
        batch_op.alter_column("obligation_id", existing_type=GUID(), nullable=False)
        batch_op.create_foreign_key(OBLIGATION_FK, "obligations", ["obligation_id"], ["id"], ondelete="RESTRICT")
        for name in drop_names:
            batch_op.drop_column(name)

    for table, makers in (
        ("compliance_tasks", TASK_COLUMNS),
        ("task_evidence", EVIDENCE_COLUMNS),
        ("task_reviews", REVIEW_COLUMNS),
    ):
        existing = _columns(table)
        names = [make().name for make in makers]
        names = names if context.is_offline_mode() else [n for n in names if n in existing]
        if not names:
            continue
        with _batch(table) as batch_op:
            for name in names:
                batch_op.drop_column(name)
