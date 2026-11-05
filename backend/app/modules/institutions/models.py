from sqlalchemy import Boolean, Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Institution(Base):
    __tablename__ = "institutions"

    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_bn = Column(String(255), nullable=True)
    website_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    departments = relationship("InstitutionDepartment", back_populates="institution", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="institution")
    sources = relationship("Source", back_populates="institution")


class InstitutionDepartment(Base):
    __tablename__ = "institution_departments"

    institution_id = Column(GUID(), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    name_bn = Column(String(255), nullable=True)

    institution = relationship("Institution", back_populates="departments")
    documents = relationship("Document", back_populates="department")

    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_institution_dept_code"),
    )
