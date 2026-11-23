"""The three plans and what each one allows. Prices live here only (shown on the Plans page).

- FREE: one person. Read and search every circular, checked summaries, favourites and read later,
  a few questions a day.
- PRO: one person. Everything, with unlimited questions, own lists, mind maps, email sharing.
- ENTERPRISE: a bank or company, at least 20 seats. Everything in Pro for each seat, plus the
  compliance workspace (registers, tasks, evidence, reports) and assigning circulars to the team.

A person's plan is the best of: their own plan, and the plan of any organization they are an active member of.
Platform administrators can use everything.
"""
from dataclasses import dataclass, field
from typing import Dict, List

FREE, PRO, ENTERPRISE = "FREE", "PRO", "ENTERPRISE"
RANK = {FREE: 0, PRO: 1, ENTERPRISE: 2}
ENTERPRISE_MIN_SEATS = 20


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_bdt_month: int  # per seat; 0 for free
    per: str
    min_seats: int
    questions_per_day: int  # 0 = no limit
    custom_lists: int  # 0 = no limit
    features: List[str] = field(default_factory=list)
    allows: List[str] = field(default_factory=list)


PLANS: Dict[str, Plan] = {
    FREE: Plan(
        FREE, "Free", 0, "person", 1, questions_per_day=0, custom_lists=0,
        features=[
            "Every Bangladesh Bank circular, searchable",
            "Checked summaries with page sources",
            "Original PDF side by side",
            "Favourites and read later",
            "Unlimited questions",
        ],
        allows=["mind_map", "email", "lists", "assign", "workspace"],  # launch: everything is free for everyone
    ),
    PRO: Plan(
        PRO, "Pro", 2500, "person", 1, questions_per_day=0, custom_lists=0,
        features=[
            "Everything in Free",
            "Unlimited questions",
            "Mind map of every circular",
            "Email a circular with its summary and PDF",
            "Your own lists",
            "Instant alerts",
        ],
        allows=["mind_map", "email", "lists"],
    ),
    ENTERPRISE: Plan(
        ENTERPRISE, "Enterprise", 1800, "seat", ENTERPRISE_MIN_SEATS, questions_per_day=0, custom_lists=0,
        features=[
            "Everything in Pro, for every seat",
            "Minimum 20 seats",
            "Assign circulars to your team",
            "Compliance registers, tasks and evidence",
            "Board reports and audit trail",
            "Your bank's data kept apart from every other bank",
        ],
        allows=["mind_map", "email", "lists", "assign", "workspace"],
    ),
}


def allows(plan_code: str, feature: str) -> bool:
    return feature in PLANS.get(plan_code, PLANS[FREE]).allows


def best(*codes: str) -> str:
    return max((c for c in codes if c in RANK), key=lambda c: RANK[c], default=FREE)
