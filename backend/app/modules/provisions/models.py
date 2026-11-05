from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Provision(Base):
    __tablename__ = "provisions"

    document_version_id = Column(GUID(), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(GUID(), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    provision_number = Column(String(64), nullable=True, index=True)  # e.g. Para 3.1, Clause 4(b)
    heading = Column(Text, nullable=True)
    verbatim_text = Column(Text, nullable=False)
    parent_provision_id = Column(GUID(), ForeignKey("provisions.id", ondelete="SET NULL"), nullable=True)
    order_index = Column(Integer, default=0, nullable=False)

    version = relationship("DocumentVersion", back_populates="provisions")
    page = relationship("DocumentPage", back_populates="provisions")
    obligations = relationship("Obligation", back_populates="provision")
    child_provisions = relationship("Provision", backref="parent_provision", remote_side="Provision.id")
