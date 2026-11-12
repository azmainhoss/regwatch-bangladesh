from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Source(Base):
    __tablename__ = "sources"

    institution_id = Column(GUID(), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(GUID(), ForeignKey("institution_departments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False, default="WEB_CRAWLER")  # WEB_CRAWLER, MANUAL_UPLOAD, API_FEED
    monitoring_method = Column(String(32), default="POLLING_HTTP", nullable=False)  # POLLING_HTTP, MANUAL_ONLY, RSS
    base_url = Column(String(512), nullable=True)
    polling_frequency_minutes = Column(Integer, default=60, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_attempted_run_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_run_at = Column(DateTime(timezone=True), nullable=True)
    last_discovered_publication_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    access_restriction_status = Column(String(64), default="CLEAR", nullable=False)  # CLEAR, RESTRICTED_BOT_CHALLENGE, RATE_LIMITED, HTTP_ERROR

    institution = relationship("Institution", back_populates="sources")
    department = relationship("InstitutionDepartment")
    runs = relationship("SourceRun", back_populates="source", cascade="all, delete-orphan", order_by="desc(SourceRun.started_at)")


class SourceRun(Base):
    __tablename__ = "source_runs"

    source_id = Column(GUID(), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    run_type = Column(String(32), nullable=False, default="SCHEDULED")  # SCHEDULED, MANUAL_TRIGGER, DIRECT_UPLOAD
    status = Column(
        String(32),
        nullable=False,
        default="STARTED"
    )  # STARTED, COMPLETED, FAILED, FAILED_RETRY, RESTRICTED, CANCELLED
    # Result of the listing check: OK, CHALLENGE, NO_TABLE, HTTP_ERROR, NETWORK_ERROR.
    # Anything but OK leaves the run FAILED_RETRY, never COMPLETED with 0 new.
    outcome = Column(String(32), nullable=True)
    discovered_count = Column(Integer, default=0, nullable=False)
    downloaded_count = Column(Integer, default=0, nullable=False)
    pages_inspected = Column(Integer, default=0, nullable=False)
    candidate_links_discovered = Column(Integer, default=0, nullable=False)
    valid_documents_discovered = Column(Integer, default=0, nullable=False)
    downloads_attempted = Column(Integer, default=0, nullable=False)
    downloads_successful = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    access_restricted = Column(Boolean, default=False, nullable=False)
    access_restriction_details = Column(JSON, default=dict, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    error_log = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    source = relationship("Source", back_populates="runs")
    discoveries = relationship("SourceDiscovery", back_populates="source_run", cascade="all, delete-orphan", order_by="desc(SourceDiscovery.created_at)")


class SourceDiscovery(Base):
    __tablename__ = "source_discoveries"

    source_run_id = Column(GUID(), ForeignKey("source_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    source_url = Column(String(1024), nullable=False)
    file_url = Column(String(1024), nullable=True)
    title = Column(Text, nullable=True)
    department_code = Column(String(32), nullable=True)
    reference_number = Column(String(128), nullable=True)
    publication_date = Column(Date, nullable=True)
    language = Column(String(32), nullable=True)
    publication_type = Column(String(64), default="CIRCULAR", nullable=False)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)
    # Reply headers of the download, kept for the archive re-check.
    etag = Column(String(256), nullable=True)
    last_modified = Column(String(64), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    discovered_metadata = Column(JSON, default=dict, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    status = Column(
        String(32),
        nullable=False,
        default="DISCOVERED"
    )  # DISCOVERED, VALIDATED, DUPLICATE, REJECTED, DOWNLOAD_PENDING, DOWNLOADED, INGESTED, RESTRICTED, FAILED,
    # REVIEW_REQUIRED, SKIPPED_REJECTED (the site answered "Request Rejected" for this one file)

    source_run = relationship("SourceRun", back_populates="discoveries")
    document = relationship("Document")
