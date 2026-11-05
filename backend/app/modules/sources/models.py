from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Source(Base):
    __tablename__ = "sources"

    institution_id = Column(GUID(), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False, default="WEB_CRAWLER")  # WEB_CRAWLER, MANUAL_UPLOAD, API_FEED
    base_url = Column(String(512), nullable=True)
    config = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)

    institution = relationship("Institution", back_populates="sources")
    runs = relationship("SourceRun", back_populates="source", cascade="all, delete-orphan")


class SourceRun(Base):
    __tablename__ = "source_runs"

    source_id = Column(GUID(), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    run_type = Column(String(32), nullable=False, default="SCHEDULED")  # SCHEDULED, MANUAL_TRIGGER, DIRECT_UPLOAD
    status = Column(String(32), nullable=False, default="STARTED")  # STARTED, COMPLETED, FAILED, CANCELLED
    discovered_count = Column(Integer, default=0, nullable=False)
    downloaded_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    error_log = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    source = relationship("Source", back_populates="runs")
    discoveries = relationship("SourceDiscovery", back_populates="source_run", cascade="all, delete-orphan")


class SourceDiscovery(Base):
    __tablename__ = "source_discoveries"

    source_run_id = Column(GUID(), ForeignKey("source_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url = Column(String(1024), nullable=False)
    discovered_metadata = Column(JSON, default=dict, nullable=False)
    status = Column(String(32), nullable=False, default="NEW")  # NEW, EXISTING_HASH, QUEUED, PROCESSED, FAILED

    source_run = relationship("SourceRun", back_populates="discoveries")
