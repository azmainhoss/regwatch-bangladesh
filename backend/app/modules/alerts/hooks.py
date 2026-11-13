"""One call per bank event, used by the compliance routes. Each one copies its values from the records,
adds the event inside the caller's transaction and can never break the main action."""
from typing import Optional

from sqlalchemy import select

from backend.app.core.logging import logger
from backend.app.modules.alerts import recipients
from backend.app.modules.alerts.emit import emit
from backend.app.modules.compliance.models import TaskEvidence


def _title(item) -> str:
    return item.obligation_title or item.source_title or "Item"


async def _base(db, org_id, actor_user_id, item, task=None):
    p = await recipients.names(db, org_id, actor_user_id)
    p.update({"item_id": str(item.id), "item_title": _title(item), "register_id": str(item.register_id)})
    if task is not None:
        p.update({"task_id": str(task.id), "task_title": task.title})
    return p


async def _guard(fn):
    try:
        return await fn()
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)
        return None


async def task_assigned(db, org_id, task, item, actor_user_id) -> None:
    async def run():
        who = task.assigned_to_user_id
        if who is None or str(who) == str(actor_user_id):
            return
        p = await _base(db, org_id, actor_user_id, item, task)
        p["due_date"] = task.due_date.isoformat() if task.due_date else None
        await emit(
            db, kind="TASK_ASSIGNED", dedupe_key=f"TASK_ASSIGNED:{task.id}:{who}:{task.lock_version}",
            organization_id=org_id, entity_type="compliance_task", entity_id=task.id, actor_user_id=actor_user_id,
            recipient_user_ids=[who], payload=p,
        )
    await _guard(run)


async def item_lead_assigned(db, org_id, item, actor_user_id) -> None:
    async def run():
        who = item.assigned_lead_id
        if who is None or str(who) == str(actor_user_id):
            return
        p = await _base(db, org_id, actor_user_id, item)
        deadline = item.internal_deadline or item.regulatory_deadline
        p["deadline"] = deadline.isoformat() if deadline else None
        await emit(
            db, kind="ITEM_LEAD_ASSIGNED", dedupe_key=f"ITEM_LEAD_ASSIGNED:{item.id}:{who}:{item.lock_version}",
            organization_id=org_id, entity_type="compliance_item", entity_id=item.id, actor_user_id=actor_user_id,
            recipient_user_ids=[who], payload=p,
        )
    await _guard(run)


async def task_cancelled(db, org_id, task, item, actor_user_id) -> None:
    async def run():
        who = task.assigned_to_user_id
        if who is None:
            return
        await emit(
            db, kind="TASK_CANCELLED", dedupe_key=f"TASK_CANCELLED:{task.id}:{task.lock_version}",
            organization_id=org_id, entity_type="compliance_task", entity_id=task.id, actor_user_id=actor_user_id,
            recipient_user_ids=[who], payload=await _base(db, org_id, actor_user_id, item, task),
        )
    await _guard(run)


async def evidence_awaiting_review(db, org_id, task, item, actor_user_id) -> None:
    async def run():
        who = await recipients.reviewers_for_task(db, org_id, task, item)
        await emit(
            db, kind="EVIDENCE_AWAITING_REVIEW", dedupe_key=f"EVIDENCE_AWAITING_REVIEW:{task.id}:{task.lock_version}",
            organization_id=org_id, entity_type="compliance_task", entity_id=task.id, actor_user_id=actor_user_id,
            recipient_user_ids=who, payload=await _base(db, org_id, actor_user_id, item, task),
        )
    await _guard(run)


async def item_awaiting_signoff(db, org_id, item, actor_user_id) -> None:
    async def run():
        who = await recipients.signers_for_item(db, org_id, item)
        await emit(
            db, kind="ITEM_AWAITING_SIGNOFF", dedupe_key=f"ITEM_AWAITING_SIGNOFF:{item.id}:{item.lock_version}",
            organization_id=org_id, entity_type="compliance_item", entity_id=item.id, actor_user_id=actor_user_id,
            recipient_user_ids=who, payload=await _base(db, org_id, actor_user_id, item),
        )
    await _guard(run)


async def task_reviewed(db, org_id, task, item, review, actor_user_id) -> None:
    async def run():
        rows = (await db.execute(
            select(TaskEvidence.submitted_by_user_id).where(TaskEvidence.task_id == task.id, TaskEvidence.withdrawn_at.is_(None))
        )).all()
        who = [r[0] for r in rows] + [task.assigned_to_user_id]
        p = await _base(db, org_id, actor_user_id, item, task)
        p.update({"decision": review.decision, "comments": review.comments})
        await emit(
            db, kind="TASK_REVIEWED", dedupe_key=f"TASK_REVIEWED:{review.id}",
            organization_id=org_id, entity_type="compliance_task", entity_id=task.id, actor_user_id=actor_user_id,
            recipient_user_ids=[w for w in who if w is not None], payload=p,
        )
    await _guard(run)


async def item_signoff_decided(db, org_id, item, review, actor_user_id, submitted_by) -> None:
    """`submitted_by` must be read before the item moves, because moving it clears that field."""
    async def run():
        p = await _base(db, org_id, actor_user_id, item)
        p.update({"decision": review.decision, "comments": review.comments})
        who = [w for w in (submitted_by, item.assigned_lead_id) if w is not None]
        await emit(
            db, kind="ITEM_SIGNOFF_DECIDED", dedupe_key=f"ITEM_SIGNOFF:{review.id}",
            organization_id=org_id, entity_type="compliance_item", entity_id=item.id, actor_user_id=actor_user_id,
            recipient_user_ids=who, payload=p,
        )
    await _guard(run)
