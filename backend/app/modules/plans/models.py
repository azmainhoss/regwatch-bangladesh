"""Who is on which plan, upgrade requests, and the daily question count for the Free plan."""
from sqlalchemy import Column, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from backend.app.database.base import Base, GUID


class Subscription(Base):
    """One plan for one person (user_id) or one organization (organization_id)."""
    __tablename__ = "subscriptions"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    plan = Column(String(16), nullable=False)  # FREE PRO ENTERPRISE
    seats = Column(Integer, nullable=False, default=1)
    # REQUESTED (waiting for the platform team to confirm payment), ACTIVE, ENDED
    status = Column(String(12), nullable=False, default="REQUESTED", index=True)
    requested_by_user_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_name = Column(String(255), nullable=True)
    contact_phone = Column(String(40), nullable=True)
    note = Column(Text, nullable=True)
    ends_on = Column(Date, nullable=True)


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day = Column(Date, nullable=False)
    kind = Column(String(24), nullable=False)  # QUESTION
    count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "day", "kind", name="uq_daily_usage"),
        Index("ix_daily_usage_user_day", "user_id", "day"),
    )
