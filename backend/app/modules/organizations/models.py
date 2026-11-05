from sqlalchemy import Boolean, Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class Organization(Base):
    __tablename__ = "organizations"

    name = Column(String(255), nullable=False)
    entity_type = Column(
        String(64),
        nullable=False,
        default="COMMERCIAL_BANK"
    )  # COMMERCIAL_BANK, ISLAMIC_BANK, NBFI, LAW_FIRM, CONSULTING_FIRM, OTHER
    registration_number = Column(String(128), nullable=True)
    license_number = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    departments = relationship("Department", back_populates="organization", cascade="all, delete-orphan")
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    registers = relationship("ComplianceRegister", back_populates="organization", cascade="all, delete-orphan")
    compliance_items = relationship("ComplianceItem", back_populates="organization", cascade="all, delete-orphan")
    tasks = relationship("ComplianceTask", back_populates="organization", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    head_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    organization = relationship("Organization", back_populates="departments")
    members = relationship("OrganizationMember", back_populates="department")
    compliance_items = relationship("ComplianceItem", back_populates="department")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_department_name"),
    )


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(GUID(), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    role = Column(
        String(32),
        nullable=False,
        default="ANALYST"
    )  # ORG_ADMIN, COMPLIANCE_HEAD, DEPARTMENT_LEAD, ANALYST, AUDITOR, VIEWER
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, INVITED, SUSPENDED

    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="memberships")
    department = relationship("Department", back_populates="members")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user_membership"),
    )
