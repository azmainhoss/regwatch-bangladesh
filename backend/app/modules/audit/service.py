"""Writes audit events inside the caller's transaction (no commit here)."""
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.audit.models import AuditEvent


def record(
    db: AsyncSession,
    *,
    organization_id: Optional[UUID],
    actor_user_id: Optional[UUID],
    action: str,
    entity_type: str,
    entity_id: UUID,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditEvent:
    ip = None
    browser = None
    if request is not None:
        if request.client:
            ip = request.client.host
        browser = request.headers.get("user-agent")
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before,
        after_state=after,
        ip_address=ip,
        user_agent=browser,
    )
    db.add(event)
    return event


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def pick(obj: Any, fields) -> Dict[str, Any]:
    """The named fields of a record as JSON-safe values."""
    return {f: _safe(getattr(obj, f, None)) for f in fields}


def changed(before: Dict[str, Any], after: Dict[str, Any]):
    """Only the fields whose value differs, as (before, after)."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}
