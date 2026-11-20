"""Builds points (claims) and their checks for analyses made before points existed.

For the latest analysis of every circular version it:
  - builds one claim per item from the old answer: obligations, links and clauses use their quoted
    sentences as evidence for every field; the old summary, key changes, applicability and dates
    carry no evidence, so they are not shown ("This point does not say which sentence it comes from.");
  - runs the code checks, queues second readings for image-read pages, routes each claim and
    brings the obligation and link rows and the circular's status in step with the claims;
  - sends a change-the-law link that no person confirmed back to "waiting", so it stops changing
    another circular's in-force status (the script says so for each one). A link a person
    confirmed or rejected keeps that decision.

By default this is a dry run: it prints one line per circular and writes nothing.
`--apply` writes. It is safe to run twice: analyses that already have points of a kind other than
"clause" are skipped. No alert is written.

Usage (from the repo root, with the repo .venv):
    .venv\\Scripts\\python.exe backend\\scripts\\backfill_claims.py
    .venv\\Scripts\\python.exe backend\\scripts\\backfill_claims.py --apply
"""
import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

import backend.app.database.models  # noqa: E402,F401  (registers all models)
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis  # noqa: E402
from backend.app.modules.analysis.sentences import SentenceIndex  # noqa: E402
from backend.app.modules.claims import checks as claim_checks  # noqa: E402
from backend.app.modules.claims import reading as claim_reading  # noqa: E402
from backend.app.modules.claims import status as claim_status  # noqa: E402
from backend.app.modules.claims.build import build_claims, save_claims  # noqa: E402
from backend.app.modules.claims.checks import set_field  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentVersion  # noqa: E402
from backend.app.modules.obligations.models import Obligation  # noqa: E402
from backend.app.modules.relationships.models import DocumentRelationship  # noqa: E402

NO_EVIDENCE = "This point does not say which sentence it comes from."


@dataclass
class Line:
    reference: str
    shown: int = 0
    waiting: int = 0
    not_shown: int = 0
    checking: int = 0
    notes: List[str] = field(default_factory=list)

    def text(self) -> str:
        return f"{self.reference}: {self.shown} shown, {self.waiting} waiting for a person, {self.not_shown} not shown, {self.checking} checking"


def upgrade_payload(old: Dict[str, Any]) -> Dict[str, Any]:
    """The old answer in the shape the claim builder reads. Fields that had no evidence get none."""
    payload = dict(old or {})
    summary = old.get("executive_summary") if isinstance(old.get("executive_summary"), dict) else {}
    points = []
    if isinstance(summary.get("short_summary"), str) and summary["short_summary"].strip():
        points.append({"text": summary["short_summary"].strip(), "evidence_ids": []})
    changes = [{"text": t.strip(), "evidence_ids": []} for t in (summary.get("key_changes") or []) if isinstance(t, str) and t.strip()]
    payload["executive_summary"] = {"summary_points": points, "key_changes": changes}

    obligations = []
    for obl in old.get("obligations") or []:
        if not isinstance(obl, dict):
            continue
        ids = obl.get("quote_span_ids") or []
        item = dict(obl)
        item.update(who_ids=ids, deadline_ids=ids, effective_date_ids=ids, consequence_ids=ids)
        obligations.append(item)
    payload["obligations"] = obligations

    applicability = old.get("applicability") if isinstance(old.get("applicability"), dict) else {}
    payload["applicability"] = {
        "covered": [{"entity": e, "evidence_ids": []} for e in (applicability.get("covered_entities") or []) if isinstance(e, str) and e.strip()],
        "exemptions": [{"text": e, "evidence_ids": []} for e in (applicability.get("exemptions") or []) if isinstance(e, str) and e.strip()],
    }
    deadlines = old.get("deadlines") if isinstance(old.get("deadlines"), dict) else {}
    payload["deadlines"] = {
        key: ({"date": deadlines[key], "evidence_ids": []} if isinstance(deadlines.get(key), str) and deadlines[key].strip() else None)
        for key in ("effective_date", "compliance_deadline", "reporting_deadline")
    }
    return payload


def _pair_rows(drafts, rows, same) -> None:
    """Gives each draft the first unused row that `same` accepts. Returns nothing; sets `draft.row`."""
    used = set()
    for d in drafts:
        d.row = None
        for r in rows:
            if id(r) in used:
                continue
            if same(d, r):
                d.row = r
                used.add(id(r))
                break


async def _backfill_one(db, analysis: DocumentAnalysis, doc: Document, version: DocumentVersion, line: Line) -> None:
    from backend.app.modules.analysis.service import pages_payload_for

    payload = upgrade_payload(analysis.structured_payload if isinstance(analysis.structured_payload, dict) else {})
    pages_payload = pages_payload_for(version)
    index = SentenceIndex.build(pages_payload)
    page_id_map = {p.page_number: p.id for p in version.pages}

    obligations = list((await db.execute(select(Obligation).where(Obligation.document_version_id == version.id).order_by(Obligation.created_at))).scalars().all())
    relationships = list((await db.execute(select(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id).order_by(DocumentRelationship.created_at))).scalars().all())

    drafts = build_claims(payload, index, doc)
    obl_drafts = [d for d in drafts if d.kind == "OBLIGATION"]
    link_drafts = [d for d in drafts if d.kind == "LINK"]
    _pair_rows(obl_drafts, obligations, lambda d, r: (r.title or "") == (d.fields.get("title") or "Regulatory Obligation") and (r.requirement_description or "") == (d.fields.get("description") or ""))
    _pair_rows(
        link_drafts,
        relationships,
        lambda d, r: (r.relationship_type or "").upper() == d.fields.get("claimed_type") and (r.target_reference_hint or "") == (d.fields.get("target_hint") or ""),
    )
    for d in obl_drafts:
        d.obligation_id = d.row.id if d.row is not None else None
    for d in link_drafts:
        d.relationship_id = d.row.id if d.row is not None else None

    reading = await claim_reading.ensure_reading_checks(db, drafts, index, version.pages)
    await claim_checks.run_code_checks(db, drafts, index, doc, version.pages, reading)
    for d in drafts:
        claim_status.route(d, doc)

    # Anything about no evidence is held back for the plain reason, whatever else was found.
    for d in drafts:
        if not (d.evidence.get("quote")) and d.kind in ("SUMMARY_POINT", "KEY_CHANGE", "APPLIES_TO", "EXEMPTION", "DATE"):
            d.check_status, d.review_queue = claim_status.NOT_SHOWN, claim_status.OPTIONAL
            if not any(c["name"] == "HAS_EVIDENCE" and c["result"] == "FAIL" for c in d.checks):
                d.checks = [c for c in d.checks if c["name"] != "HAS_EVIDENCE"] + [
                    {"name": "HAS_EVIDENCE", "result": "FAIL", "message": NO_EVIDENCE}
                ]

    # A link a person already decided keeps that decision. A change-the-law link nobody confirmed goes back to waiting.
    for d in link_drafts:
        row = d.row
        if row is None:
            continue
        if row.reviewed_by and row.verification_status == "VERIFIED":
            d.check_status, d.review_queue = claim_status.APPROVED, None
            d.reviewed_by, d.reviewed_at = row.reviewed_by, row.reviewed_at
            if d.fields.get("claimed_type") in ("AMENDS", "REPEALS", "SUPERSEDES", "REPLACES"):
                d.fields["shown_type"] = d.fields["claimed_type"]
        elif row.reviewed_by and row.verification_status == "REJECTED":
            d.check_status, d.review_queue = claim_status.REJECTED, None
            d.reviewed_by, d.reviewed_at = row.reviewed_by, row.reviewed_at
        elif row.verification_status == "VERIFIED" and d.fields.get("claimed_type") in ("AMENDS", "REPEALS", "SUPERSEDES", "REPLACES"):
            target = _target_label(row, relationships)
            verb = {"AMENDS": "amends", "REPEALS": "repeals", "SUPERSEDES": "supersedes", "REPLACES": "replaces"}[d.fields["claimed_type"]]
            line.notes.append(
                f"  {doc.reference_number or 'A circular'} said it {verb} {target}. No person confirmed that, so it is now only a mention until someone does."
            )

    claim_rows = await save_claims(db, analysis, drafts, index, page_id_map)
    await claim_status.sync_rows(db, claim_rows)

    # Rows with no point cannot be shown to anyone.
    matched_obl = {str(c.obligation_id) for c in claim_rows if c.obligation_id}
    for r in obligations:
        if str(r.id) not in matched_obl:
            r.verification_status = "PENDING_REVIEW"
    matched_rel = {str(c.relationship_id) for c in claim_rows if c.relationship_id}
    for r in relationships:
        if str(r.id) not in matched_rel and r.verification_status == "VERIFIED" and not r.reviewed_by:
            r.verification_status = "PENDING_REVIEW"

    analysis.executive_summary = claim_status.shown_text_for_summary(claim_rows)
    analysis.key_changes = [
        (c.fields or {}).get("text")
        for c in sorted(claim_rows, key=lambda c: c.order_index or 0)
        if c.kind == "KEY_CHANGE" and claim_status.is_shown(c) and (c.fields or {}).get("text")
    ]
    if doc.current_version_id == version.id:
        claim_status.apply_document_status(doc, claim_rows)

    counts = claim_status.counts([c for c in claim_rows if c.kind != "PROVISION"])
    line.shown, line.waiting, line.not_shown, line.checking = counts["shown"], counts["waiting_for_team"], counts["not_shown"], counts["checking"]


def _target_label(row: DocumentRelationship, _all) -> str:
    return row.target_reference_hint or "another circular"


async def backfill(session_factory, apply: bool = False, only_documents: Optional[set] = None) -> List[Line]:
    """Runs the backfill. Returns one line per circular version it handled; writes only when `apply`.
    `only_documents` (a set of circular ids as text) limits the run."""
    lines: List[Line] = []
    async with session_factory() as db:
        analyses = (await db.execute(select(DocumentAnalysis).order_by(DocumentAnalysis.created_at.desc()))).scalars().all()
        latest: Dict[Any, DocumentAnalysis] = {}
        for a in analyses:
            latest.setdefault(str(a.document_version_id), a)
        todo = list(latest.values())

    for analysis_stub in sorted(todo, key=lambda a: a.created_at):
        async with session_factory() as db:
            analysis = await db.get(DocumentAnalysis, analysis_stub.id)
            existing = (await db.execute(select(AnalysisClaim.kind).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all()
            if any(k != "PROVISION" for k in existing):
                continue  # already done
            version = (
                await db.execute(select(DocumentVersion).options(selectinload(DocumentVersion.pages)).where(DocumentVersion.id == analysis.document_version_id))
            ).scalar_one_or_none()
            doc = await db.get(Document, version.document_id) if version else None
            if version is None or doc is None or not version.pages:
                continue
            if only_documents is not None and str(doc.id) not in only_documents:
                continue
            # The old placeholder claims (one per clause, never checked) are replaced.
            for old in (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all():
                await db.delete(old)
            await db.flush()
            line = Line(reference=doc.reference_number or doc.title[:60])
            await _backfill_one(db, analysis, doc, version, line)
            if apply:
                await db.commit()
            else:
                await db.rollback()
            lines.append(line)
    return lines


async def main(apply: bool) -> None:
    from backend.app.database.session import AsyncSessionLocal, async_engine

    lines = await backfill(AsyncSessionLocal, apply=apply)
    for line in lines:
        print(line.text())
        for note in line.notes:
            print(note)
    if not lines:
        print("Nothing to do: every analysis already has its points.")
    print(f"{len(lines)} circular(s) {'updated' if apply else 'checked (dry run, nothing written; add --apply to write)'}.")
    await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
