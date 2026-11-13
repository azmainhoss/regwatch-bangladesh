"""Plain rules for the compliance workspace: today's date, overdue, deadlines, source changes.

Overdue is worked out here, never stored, so it is always right and an edited deadline flips it at once.
Other modules call `rules.today_dhaka()` through this module so tests can freeze the date.
"""
import hashlib
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from backend.app.core.config import settings

ITEM_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED", "COMPLIANT", "EXEMPTED")
TASK_STATUSES = ("PENDING", "IN_PROGRESS", "SUBMITTED", "APPROVED", "REJECTED", "CANCELLED")
TASK_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
ROLES = (
    "ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD",
    "REVIEWER", "ANALYST", "AUDITOR", "VIEWER",
)

ITEM_OVERDUE_STATUSES = ("NOT_STARTED", "IN_PROGRESS")
TASK_OVERDUE_STATUSES = ("PENDING", "IN_PROGRESS", "REJECTED")
TASK_OPEN_STATUSES = ("PENDING", "IN_PROGRESS", "REJECTED")


def today_dhaka() -> date:
    return datetime.now(ZoneInfo(settings.MONITOR_TIMEZONE)).date()


def effective_deadline(internal: Optional[date], regulatory: Optional[date]) -> Optional[date]:
    return internal or regulatory


def is_item_overdue(status: str, internal: Optional[date], regulatory: Optional[date], today: date) -> bool:
    deadline = effective_deadline(internal, regulatory)
    return status in ITEM_OVERDUE_STATUSES and deadline is not None and deadline < today


def display_status(status: str, overdue: bool) -> str:
    return "OVERDUE" if overdue else status


def days_left(deadline: Optional[date], today: date) -> Optional[int]:
    return None if deadline is None else (deadline - today).days


def is_task_overdue(status: str, due: Optional[date], today: date) -> bool:
    return status in TASK_OVERDUE_STATUSES and due is not None and due < today


def source_key(version_id, page_number, quote) -> str:
    return hashlib.sha256(f"{version_id}|{page_number}|{quote}".encode("utf-8")).hexdigest()


def source_signature(in_force_status: str, in_force_by_id, current_version_id, withdrawn: bool) -> str:
    return f"{in_force_status}|{in_force_by_id or ''}|{current_version_id or ''}|{'W' if withdrawn else ''}"


def baseline_signature(source_version_id) -> str:
    return f"IN_FORCE||{source_version_id or ''}|"


def change_kind(in_force_status: str, current_version_id, source_version_id, withdrawn: bool) -> Optional[str]:
    """Kind of change, strongest first: WITHDRAWN, REPEALED, REPLACED, AMENDED, NEW_VERSION."""
    if withdrawn:
        return "WITHDRAWN"
    if in_force_status in ("REPEALED", "REPLACED", "AMENDED"):
        return in_force_status
    if current_version_id and source_version_id and str(current_version_id) != str(source_version_id):
        return "NEW_VERSION"
    return None


def change_text(kind: str, by_reference: Optional[str]) -> str:
    ref = by_reference or "another circular"
    return {
        "AMENDED": f"{ref} amends this circular.",
        "REPLACED": f"{ref} replaces this circular.",
        "REPEALED": f"{ref} repeals this circular.",
        "NEW_VERSION": "A newer version of this circular was published.",
        "WITHDRAWN": "This circular was withdrawn.",
    }[kind]
