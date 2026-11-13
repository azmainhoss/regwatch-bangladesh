"""Records alert events inside the caller's transaction (no commit here), like audit.record."""
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.modules.alerts.kinds import KIND_GROUP
from backend.app.modules.alerts.models import AlertEvent

_KICK_FLAG = "alerts_kick_registered"


def _kick(_session) -> None:
    """After the caller's commit: hand pending events to people right away."""
    try:
        from backend.app.modules.alerts.worker import kick_dispatch
        kick_dispatch()
    except Exception as exc:  # never let an alert break a save
        logger.warning("Alert hand-off not started: %s", type(exc).__name__)


def _uuid_str(value) -> Optional[str]:
    return str(value) if value is not None else None


async def emit(
    db: AsyncSession,
    *,
    kind: str,
    dedupe_key: str,
    organization_id: Optional[UUID] = None,
    document_id: Optional[UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    actor_user_id: Optional[UUID] = None,
    recipient_user_ids: Optional[Iterable] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[AlertEvent]:
    """Adds one event. Returns None when this event was already recorded or nobody would be told."""
    if kind not in KIND_GROUP:
        raise ValueError(f"Unknown alert kind: {kind}")
    recipients: Optional[List[str]] = None
    if recipient_user_ids is not None:
        actor = _uuid_str(actor_user_id)
        recipients = []
        for r in recipient_user_ids:
            r = _uuid_str(r)
            if r and r != actor and r not in recipients:
                recipients.append(r)
        if not recipients:
            return None
    key = dedupe_key[:255]
    if (await db.execute(select(AlertEvent.id).where(AlertEvent.dedupe_key == key))).first() is not None:
        return None
    row = AlertEvent(
        kind=kind, dedupe_key=key, organization_id=organization_id, document_id=document_id,
        entity_type=entity_type, entity_id=entity_id, actor_user_id=actor_user_id,
        recipient_user_ids=recipients, payload=payload or {}, status="PENDING", attempts=0,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        # Another process recorded the same event at the same moment. Nothing more to do.
        return None
    sync = db.sync_session
    if not sync.info.get(_KICK_FLAG):
        sync.info[_KICK_FLAG] = True
        event.listen(sync, "after_commit", _kick, once=True)
    return row


async def safe_emit(db: AsyncSession, **kwargs) -> Optional[AlertEvent]:
    """emit() that can never break the main action."""
    try:
        return await emit(db, **kwargs)
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Library: a circular was published
# ---------------------------------------------------------------------------
async def circular_fields(db: AsyncSession, doc) -> Dict[str, Any]:
    from backend.app.modules.institutions.models import InstitutionDepartment
    code = None
    if doc.department_id:
        code = (await db.execute(
            select(InstitutionDepartment.code).where(InstitutionDepartment.id == doc.department_id)
        )).scalar_one_or_none()
    return {
        "document_id": str(doc.id),
        "reference_number": doc.reference_number,
        "title": doc.title,
        "title_bn": getattr(doc, "title_bn", None),
        "document_type": str(doc.document_type) if doc.document_type is not None else None,
        "department_code": code,
        "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
    }


def is_published_shared(doc) -> bool:
    return doc.owner_user_id is None and str(doc.publication_status or "").startswith("PUBLISHED")


async def circular_published(db: AsyncSession, doc) -> Optional[AlertEvent]:
    """Once per shared circular, ever. Private uploads never alert anyone."""
    try:
        if not is_published_shared(doc):
            return None
        return await emit(
            db, kind="CIRCULAR_PUBLISHED", dedupe_key=f"CIRCULAR_PUBLISHED:{doc.id}", document_id=doc.id,
            entity_type="document", entity_id=doc.id, payload=await circular_fields(db, doc),
        )
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)
        return None
