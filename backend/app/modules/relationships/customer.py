"""What a reader (anyone who is not an administrator) may see of a link between circulars.

A link is shown only while its point is shown (docs/specs/CLAIM_CHECKS_SPEC.md 4.5). It is called by the
type its point may carry: "Mentions" until a person confirms a change-the-law type. Links that have
no point (made before points existed) follow their own status: confirmed ones show as they are.
Administrators see every link with its real type, so nothing here applies to them.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import select


@dataclass
class LinkView:
    # Relationship id -> the type a reader sees. A link missing from it is not shown.
    types: Dict[str, str] = field(default_factory=dict)

    def type_of(self, rel: Any) -> Optional[str]:
        return self.types.get(str(rel.id))

    def keeps(self, rel: Any) -> bool:
        return str(rel.id) in self.types


async def link_view(db, rels: Sequence[Any], user: Optional[Any]) -> Optional[LinkView]:
    """None for administrators (no change). Otherwise which of `rels` a reader sees, and as what."""
    if user is not None and getattr(user, "is_superuser", False):
        return None
    from backend.app.modules.analysis.models import AnalysisClaim
    from backend.app.modules.claims import status as S

    ids = [r.id for r in rels]
    by_rel: Dict[str, Any] = {}
    if ids:
        claims = (
            await db.execute(select(AnalysisClaim).where(AnalysisClaim.kind == "LINK", AnalysisClaim.relationship_id.in_(ids)))
        ).scalars().all()
        by_rel = {str(c.relationship_id): c for c in claims}
    view = LinkView()
    for r in rels:
        claim = by_rel.get(str(r.id))
        if claim is not None:
            if S.is_shown(claim):
                view.types[str(r.id)] = S.shown_link_type(claim)
        elif r.verification_status == "VERIFIED":
            view.types[str(r.id)] = r.relationship_type
    return view
