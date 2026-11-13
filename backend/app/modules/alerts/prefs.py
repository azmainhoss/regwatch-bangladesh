"""Each person's alert settings, with defaults for anything they have not set."""
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.alerts.kinds import EMAIL_MODES, GROUPS
from backend.app.modules.alerts.models import AlertPreference


async def load_many(db: AsyncSession, user_ids: Iterable) -> Dict[str, AlertPreference]:
    ids = list({str(u) for u in user_ids})
    if not ids:
        return {}
    rows = (await db.execute(select(AlertPreference).where(AlertPreference.user_id.in_(ids)))).scalars().all()
    return {str(r.user_id): r for r in rows}


def channel_for(pref: Optional[AlertPreference], group: str) -> Tuple[bool, str]:
    """(in_app, email mode) for one group. The master email switch turns every email off."""
    base = GROUPS[group]
    in_app = base["in_app"]
    email = base["email"]
    if pref is not None:
        setting = (pref.channels or {}).get(group)
        if isinstance(setting, dict):
            if isinstance(setting.get("in_app"), bool):
                in_app = setting["in_app"]
            if setting.get("email") in EMAIL_MODES:
                email = setting["email"]
        if not pref.email_enabled:
            email = "OFF"
    return in_app, email


def library_filters(pref: Optional[AlertPreference]) -> Tuple[List[str], List[str], List[str]]:
    if pref is None:
        return [], [], []
    return (
        list(pref.library_department_codes or []),
        list(pref.library_document_types or []),
        list(pref.library_keywords or []),
    )


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").casefold()


def library_matches(pref: Optional[AlertPreference], *, department_code: Optional[str],
                    document_type: Optional[str], haystack: str) -> bool:
    """All non-empty filter groups must match (AND across groups, OR inside a group)."""
    codes, types, words = library_filters(pref)
    if codes and (department_code or "") not in codes:
        return False
    if types and (document_type or "") not in types:
        return False
    if words:
        hay = _norm(haystack)
        if not any(_norm(w) in hay for w in words):
            return False
    return True


def visible_group_ids(*, is_superuser: bool, has_membership: bool) -> List[str]:
    out = []
    for gid, g in GROUPS.items():
        scope = g["scope"]
        if scope == "all" or (scope == "bank" and has_membership) or (scope == "admin" and is_superuser):
            out.append(gid)
    return out
