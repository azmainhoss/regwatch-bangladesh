"""Provider health as last seen by a real call.

Nothing is pre-filled: until a real call to the configured provider and model has happened in
this process, the status is NOT_TESTED. Every real call (analysis, research, the admin probe)
records its outcome here.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

NOT_TESTED = "NOT_TESTED"
CONNECTED_TESTED = "CONNECTED_TESTED"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
AUTH_FAILED = "AUTH_FAILED"
CALL_FAILED = "CALL_FAILED"


def _empty() -> Dict[str, Any]:
    return {
        "status": NOT_TESTED,
        "provider": None,
        "model": None,
        "checked_at": None,
        "last_latency_ms": None,
        "last_status_code": None,
        "last_error": None,
    }


_HEALTH: Dict[str, Any] = _empty()


def reset_health() -> None:
    _HEALTH.clear()
    _HEALTH.update(_empty())


def status_for_http(status_code: Optional[int], success: bool) -> str:
    if success:
        return CONNECTED_TESTED
    if status_code == 429:
        return QUOTA_EXCEEDED
    if status_code in (401, 403):
        return AUTH_FAILED
    if status_code is None or status_code >= 500:
        return TEMPORARILY_UNAVAILABLE
    return CALL_FAILED


def record_call(
    provider: str,
    model: str,
    success: bool,
    latency_ms: Optional[int] = None,
    status_code: Optional[int] = None,
    error: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    _HEALTH.update({
        "status": status or status_for_http(status_code, success),
        "provider": provider,
        "model": model,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "last_latency_ms": latency_ms,
        "last_status_code": status_code,
        "last_error": None if success else error,
    })


def health_for(provider: str, model: str) -> Dict[str, Any]:
    """The last real result for this provider and model, or NOT_TESTED."""
    if _HEALTH.get("provider") == provider and _HEALTH.get("model") == model:
        return dict(_HEALTH)
    return _empty()
