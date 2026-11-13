from sqlalchemy import Boolean, Column, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.database.base import Base, GUID


class User(Base):
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    memberships = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")
    assigned_tasks = relationship("ComplianceTask", back_populates="assigned_to_user", foreign_keys="ComplianceTask.assigned_to_user_id")
    submitted_evidence = relationship("TaskEvidence", back_populates="submitted_by_user", foreign_keys="TaskEvidence.submitted_by_user_id")
    reviews = relationship("TaskReview", back_populates="reviewer_user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    designation = Column(String(128), nullable=True)
    bio = Column(Text, nullable=True)
    preferences = Column(JSON, default=dict, nullable=False)

    user = relationship("User", back_populates="profile")
