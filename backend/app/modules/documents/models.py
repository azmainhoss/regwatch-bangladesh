from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Document(Base):
    __tablename__ = "documents"

    institution_id = Column(GUID(), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True)
    department_id = Column(GUID(), ForeignKey("institution_departments.id", ondelete="SET NULL"), nullable=True, index=True)
    reference_number = Column(String(128), nullable=True, index=True)
    title = Column(Text, nullable=False)
    title_bn = Column(Text, nullable=True)
    document_type = Column(String(64), nullable=False, default="CIRCULAR", index=True)  # CIRCULAR, CIRCULAR_LETTER, GUIDELINE, NOTIFICATION, POLICY
    publication_date = Column(Date, nullable=False, index=True)
    effective_date = Column(Date, nullable=True)
    source_url = Column(String(1024), nullable=True)
    current_version_id = Column(GUID(), nullable=True)
    # Explicit marker for sample/fixture records so they are kept out of the genuine corpus.
    is_synthetic_fixture = Column(Boolean, default=False, server_default="0", nullable=False)
    # NULL = shared library (visible to everyone). Set = a private upload only this user can see.
    owner_user_id = Column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_documents_owner_user_id_users"),
        nullable=True,
        index=True,
    )
    publication_status = Column(
        String(64),
        nullable=False,
        default="DISCOVERED",
        index=True
    )  # DISCOVERED, EXTRACTED, ANALYZING, AWAITING_REVIEW, PUBLISHED_MACHINE_PROCESSED, PUBLISHED_HUMAN_REVIEWED, SUPERSEDED, WITHDRAWN

    institution = relationship("Institution", back_populates="documents")
    department = relationship("InstitutionDepartment", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", foreign_keys="DocumentVersion.document_id", cascade="all, delete-orphan")
    outgoing_relationships = relationship("DocumentRelationship", back_populates="source_document", foreign_keys="DocumentRelationship.source_document_id")
    incoming_relationships = relationship("DocumentRelationship", back_populates="target_document", foreign_keys="DocumentRelationship.target_document_id")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, default=1, nullable=False)
    file_sha256 = Column(String(64), nullable=False, index=True)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_mime_type = Column(String(64), default="application/pdf", nullable=False)
    storage_path = Column(String(512), nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    # en, bn or mixed. An English and a Bangla file of the same circular are language variants:
    # two versions that are both CURRENT and never replace each other.
    language = Column(String(16), default="en", nullable=False)
    is_scanned = Column(Boolean, default=False, nullable=False)
    # Where the file came from and the reply headers at download time (DECISIONS.md 5).
    source_url = Column(String(1024), nullable=True)
    etag = Column(String(256), nullable=True)
    last_modified = Column(String(64), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=True)
    # CURRENT, or SUPERSEDED once a newer file with the same language and source URL is stored.
    # Old versions are kept.
    status = Column(String(32), default="CURRENT", server_default="CURRENT", nullable=False)

    document = relationship("Document", back_populates="versions", foreign_keys=[document_id])
    pages = relationship("DocumentPage", back_populates="version", cascade="all, delete-orphan", order_by="DocumentPage.page_number")
    provisions = relationship("Provision", back_populates="version", cascade="all, delete-orphan")
    obligations = relationship("Obligation", back_populates="version", cascade="all, delete-orphan")
    analyses = relationship("DocumentAnalysis", back_populates="version", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_num"),
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"

    document_version_id = Column(GUID(), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    cleaned_text = Column(Text, nullable=True)
    # TEXT_LAYER, GEMINI_VISION, MANUAL_SUBSCRIPTION_READING, HUMAN_CORRECTED
    extraction_method = Column(String(32), default="TEXT_LAYER", nullable=False)
    ocr_confidence = Column(Float, nullable=True)
    has_tables = Column(Boolean, default=False, nullable=False)
    extracted_tables = Column(JSON, default=list, nullable=False)
    page_image_path = Column(String(512), nullable=True)
    # SUCCESS_NATIVE, SUCCESS_VISION, SUCCESS_VISION_MANUAL, PENDING_VISION, NEEDS_HUMAN_REVIEW
    quality_status = Column(String(32), default="SUCCESS_NATIVE", nullable=False)
    quality_score = Column(Float, default=1.0, nullable=False)
    layout_hierarchy = Column(JSON, default=dict, nullable=False)
    native_text = Column(Text, nullable=True)
    ocr_text = Column(Text, nullable=True)
    human_corrected_text = Column(Text, nullable=True)
    is_human_corrected = Column(Boolean, default=False, nullable=False)
    # One entry per text line: {"text": ..., "box_2d": [ymin, xmin, ymax, xmax]} on a 0-1000
    # page scale, from the PDF text layer or from the page-image reading. Lets a viewer
    # highlight a quote on the page.
    line_boxes = Column(JSON, nullable=True)
    # Page-image reading jobs that failed on this page, and the last error.
    vision_attempts = Column(Integer, default=0, server_default="0", nullable=False)
    vision_error = Column(Text, nullable=True)
    # Who last corrected this page's text, when, and why. Every correction is also kept in
    # `page_corrections`, so earlier ones are never overwritten.
    correction_reason = Column(Text, nullable=True)
    corrected_by_user_id = Column(GUID(), nullable=True)
    corrected_by_name = Column(String(255), nullable=True)
    corrected_at = Column(DateTime(timezone=True), nullable=True)

    version = relationship("DocumentVersion", back_populates="pages")
    provisions = relationship("Provision", back_populates="page")
    obligations = relationship("Obligation", back_populates="page")

    __table_args__ = (
        UniqueConstraint("document_version_id", "page_number", name="uq_doc_version_page_num"),
    )


class PageCorrection(Base):
    """One row per human correction of a page's text. Rows are only ever added."""
    __tablename__ = "page_corrections"

    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    document_version_id = Column(GUID(), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    corrected_by_user_id = Column(GUID(), nullable=True, index=True)
    corrected_by_name = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    # The text the reader saw before this correction, and the text that replaced it.
    previous_text = Column(Text, nullable=True)
    corrected_text = Column(Text, nullable=False)
