from sqlalchemy import BigInteger, Boolean, Column, Date, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    language = Column(String(16), default="en", nullable=False)  # en, bn, mixed
    is_scanned = Column(Boolean, default=False, nullable=False)

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
    extraction_method = Column(String(32), default="PYMUPDF_NATIVE", nullable=False)  # PYMUPDF_NATIVE, OCR_TESSERACT, BIJOY_UNICODE_CONVERTED
    ocr_confidence = Column(Float, nullable=True)
    has_tables = Column(Boolean, default=False, nullable=False)
    extracted_tables = Column(JSON, default=list, nullable=False)
    page_image_path = Column(String(512), nullable=True)

    version = relationship("DocumentVersion", back_populates="pages")
    provisions = relationship("Provision", back_populates="page")
    obligations = relationship("Obligation", back_populates="page")

    __table_args__ = (
        UniqueConstraint("document_version_id", "page_number", name="uq_doc_version_page_num"),
    )
