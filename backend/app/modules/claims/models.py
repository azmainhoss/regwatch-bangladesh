from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from backend.app.database.base import Base, GUID


class QuoteReadingCheck(Base):
    """Second reading of one quoted sentence on a page that was read from its image.

    One row per (page, sentence, page text). A page whose text changes gets new rows.
    """

    __tablename__ = "quote_reading_checks"

    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    sentence_id = Column(String(16), nullable=False)
    line_indexes = Column(JSON, default=list)
    page_text_sha = Column(String(64), nullable=False)
    # WAITING, CLEAN, MISREAD, UNCLEAR, NOT_NEEDED
    status = Column(String(16), nullable=False, default="WAITING", index=True)
    our_text = Column(Text, nullable=True)
    # List of {kind: CROP|SHARP_CROP|PAGE, text}. Internal fields stay on the server.
    reads = Column(JSON, default=list)
    numbers_confirmed = Column(JSON, default=list)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("page_id", "sentence_id", "page_text_sha", name="uq_quote_reading_page_sentence_sha"),
    )
