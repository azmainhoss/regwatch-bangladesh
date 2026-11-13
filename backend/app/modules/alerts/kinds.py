"""Alert kinds and the preference groups they belong to."""
from typing import Dict, List

# Group id -> label, short description (the settings screen fills in the numbers), who sees it,
# default for the in-app inbox and default email mode.
# scope: "all" = everybody, "bank" = people with an active bank membership, "admin" = platform staff.
GROUPS: Dict[str, Dict] = {
    "library": {
        "label": "New circulars",
        "description": "A new circular is published in the library.",
        "scope": "all", "in_app": True, "email": "DIGEST",
    },
    "source_change": {
        "label": "A circular in my bank's register changed",
        "description": "A circular behind an item in your bank's registers was amended, replaced, repealed or withdrawn.",
        "scope": "bank", "in_app": True, "email": "INSTANT",
    },
    "assigned": {
        "label": "Work assigned to me",
        "description": "You were given a task or made the lead of an item, or a task of yours was cancelled.",
        "scope": "bank", "in_app": True, "email": "INSTANT",
    },
    "review_waiting": {
        "label": "Evidence or sign-off waiting for me",
        "description": "Evidence is waiting for your review, or an item is ready for your sign-off.",
        "scope": "bank", "in_app": True, "email": "INSTANT",
    },
    "my_work_decided": {
        "label": "My evidence or item was decided",
        "description": "Someone approved, rejected or asked for changes on work you sent in.",
        "scope": "bank", "in_app": True, "email": "INSTANT",
    },
    "due_soon": {
        "label": "Deadline coming up",
        "description": "{days} before a deadline. Sent to the item lead or the task owner.",
        "scope": "bank", "in_app": True, "email": "DIGEST",
    },
    "overdue": {
        "label": "Overdue",
        "description": "An item or task passed its deadline.",
        "scope": "bank", "in_app": True, "email": "DIGEST",
    },
    "admin_queue": {
        "label": "Review queues (platform staff)",
        "description": "Items are waiting in the admin review queues.",
        "scope": "admin", "in_app": True, "email": "DIGEST",
    },
}

KIND_GROUP: Dict[str, str] = {
    "CIRCULAR_PUBLISHED": "library",
    "REGISTER_SOURCE_CHANGED": "source_change",
    "TASK_ASSIGNED": "assigned",
    "ITEM_LEAD_ASSIGNED": "assigned",
    "TASK_CANCELLED": "assigned",
    "EVIDENCE_AWAITING_REVIEW": "review_waiting",
    "ITEM_AWAITING_SIGNOFF": "review_waiting",
    "TASK_REVIEWED": "my_work_decided",
    "ITEM_SIGNOFF_DECIDED": "my_work_decided",
    "ITEM_DUE_SOON": "due_soon",
    "TASK_DUE_SOON": "due_soon",
    "ITEM_OVERDUE": "overdue",
    "TASK_OVERDUE": "overdue",
    "ADMIN_QUEUE": "admin_queue",
}

EMAIL_MODES = ("OFF", "INSTANT", "DIGEST")

# Inbox filter chips group several preference groups together.
INBOX_GROUP_ALIASES: Dict[str, List[str]] = {
    "deadlines": ["due_soon", "overdue"],
}


def group_of(kind: str) -> str:
    return KIND_GROUP[kind]
