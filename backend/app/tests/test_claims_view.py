"""Claim checks, chunk 2 (docs/specs/CLAIM_CHECKS_SPEC.md): the checked view for readers, the links
and obligations readers get, the compliance rule, the publish rule, ask-for-review, and the backfill."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.models import AnalysisClaim, AnalysisLease, ClaimCitation, DocumentAnalysis
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.claims import status as S
from backend.app.modules.claims import view as claim_view
from backend.app.modules.claims.models import QuoteReadingCheck
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.tests import test_claim_checks as cc
from backend.app.tests import test_compliance_workspace as cw
from backend.app.tests.factories import make_document, make_institution, make_user, signed_in_reader
from backend.scripts import backfill_claims

TODAY = cc.TODAY


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await signed_in_reader(ac)
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


FORBIDDEN_KEYS = {
    "structured_payload", "raw_model_response", "model_name", "fingerprint", "checks", "evidence",
    "page_text_sha", "reads", "prompt_version", "tokens_used", "estimated_cost_usd", "claimed_type", "review_queue",
}


def all_keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            all_keys(v, found)
    elif isinstance(value, list):
        for v in value:
            all_keys(v, found)
    return found


async def library_target(code: str, ref_number: str = "14"):
    """An older shared circular that the analysed circular names."""
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc = Document(
            institution_id=inst.id,
            title=f"{code} Circular No. {ref_number}: an older rule",
            reference_number=f"{code} Circular No. {ref_number}",
            publication_date=date(2012, 9, 23),
            publication_status="PUBLISHED_HUMAN_REVIEWED",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc


async def analysed_circular(monkeypatch, with_target=True):
    """A live circular analysed end to end. Its points: 9 shown (one of them the link, as a mention),
    1 waiting for a person (a requirement with a late date), 1 not shown (a number not in the quote)."""
    code = "ZQ" + uuid.uuid4().hex[:6].upper()
    text = cc.PAGE_TEXT.replace("BRPD", code)
    target = await library_target(code) if with_target else None
    doc, version, pages = await cc.doc_with_text("PUBLISHED_MACHINE_PROCESSED", text)
    ctx = cc.make_ctx(text)
    payload = json.loads(json.dumps(cc.payload_for(ctx)).replace("BRPD", code))
    analysis = await cc.run_analysis(doc.id, payload, monkeypatch)
    return doc, version, pages, analysis, target, code


def titles(rows):
    return {r["title"] for r in rows}


# ---------------------------------------------------------------------------
# The checked view
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readers_see_only_shown_points_and_hidden_lines_carry_no_wording(client, monkeypatch):
    doc, _v, _p, _a, target, _code = await analysed_circular(monkeypatch)
    user, token = await make_user()
    admin, admin_token = await make_user(is_superuser=True)

    anon = await client.get(f"/api/v1/documents/{doc.id}/claims")
    assert anon.status_code == 200
    body = anon.json()
    assert body["state"] == "READY"
    assert body["counts"] == {"total": 11, "shown": 9, "checking": 0, "waiting_for_team": 1, "not_shown": 1}
    sec = body["sections"]
    assert [len(sec[k]) for k in ("summary", "changes", "requirements", "applies_to", "exemptions", "dates", "links", "clauses")] == [1, 1, 2, 1, 1, 2, 1, 0]
    assert {r["fields"]["title"] for r in sec["requirements"]} == {"Submit monthly liquidity report", "Do not open new branches"}
    assert all(r["checked_by"] == "CHECKS" and r["page_number"] == 1 and r["quote"] for r in sec["requirements"])
    assert sec["requirements"][0]["obligation_id"]

    # Held-back points: section, page and a plain state. Never their words.
    assert sorted((h["section"], h["state"]) for h in body["hidden"]) == [("requirements", "waiting_for_team"), ("summary", "not_shown")]
    for h in body["hidden"]:
        assert set(h) == {"section", "page_number", "state", "quote_boxes"}
        assert h["page_number"] == 1
    text = anon.text
    assert "File annual report" not in text and "5% extra liquidity" not in text

    # A link that would change another circular is shown only as a mention.
    link = sec["links"][0]["link"]
    assert link["shown_type"] == "REFERENCES" and link["target_document_id"] == str(target.id)
    assert sec["links"][0]["fields"] == {}

    # A bank user sees the same as a visitor.
    signed_in = await client.get(f"/api/v1/documents/{doc.id}/claims", headers=_auth(token))
    assert signed_in.json() == body

    # Administrators ask for everything and see the checks and the reasons.
    assert (await client.get(f"/api/v1/documents/{doc.id}/claims?all=1")).status_code == 403
    assert (await client.get(f"/api/v1/documents/{doc.id}/claims?all=1", headers=_auth(token))).status_code == 403
    full = await client.get(f"/api/v1/documents/{doc.id}/claims?all=1", headers=_auth(admin_token))
    assert full.status_code == 200
    items = [i for rows in full.json()["sections"].values() for i in rows]
    held = [i for i in items if not i["shown"]]
    assert {i["status"] for i in held} == {"NOT_SHOWN", "WAITING_FOR_PERSON"}
    assert all(i["checks"] and i["why"] for i in held)
    assert any("not in the quoted sentences" in " ".join(i["why"]) for i in held)
    mention = [i for i in items if i["kind"] == "LINK"][0]
    assert mention["fields"]["claimed_type"] == "AMENDS" and mention["shown"] is True


@pytest.mark.asyncio
async def test_no_analysis_and_analysing_states(client):
    doc, _v, _p = await make_document(pages=1, status="EXTRACTED")
    body = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert body["state"] == "NO_ANALYSIS" and body["counts"]["total"] == 0 and body["hidden"] == []
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.add(AnalysisLease(document_id=doc.id, owner_worker_id="w", lease_token="t", acquired_at=now,
                             expires_at=now + timedelta(minutes=10), heartbeat_at=now, status="ACTIVE"))
        await db.commit()
    assert (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()["state"] == "ANALYSING"


@pytest.mark.asyncio
async def test_private_circular_claims_look_missing_to_others(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await analysed_circular(monkeypatch)
    owner, _ = await make_user()
    async with AsyncSessionLocal() as db:
        row = await db.get(Document, doc.id)
        row.owner_user_id = owner.id
        await db.commit()
    assert (await client.get(f"/api/v1/documents/{doc.id}/claims")).status_code == 404


def test_quote_lines_are_offered_only_when_the_quote_and_page_passed():
    class C:
        def __init__(self, checks):
            self.checks = checks
    ok = C([{"name": "QUOTE_FOUND", "result": "PASS"}, {"name": "PAGE_READ", "result": "PASS"}, {"name": "NUMBERS", "result": "FAIL"}])
    bad_quote = C([{"name": "QUOTE_FOUND", "result": "FAIL"}, {"name": "PAGE_READ", "result": "PASS"}])
    bad_page = C([{"name": "QUOTE_FOUND", "result": "PASS"}, {"name": "PAGE_READ", "result": "FAIL"}])
    assert claim_view.lines_are_on_the_page(ok) is True
    assert claim_view.lines_are_on_the_page(bad_quote) is False
    assert claim_view.lines_are_on_the_page(bad_page) is False


@pytest.mark.asyncio
async def test_hidden_point_whose_quote_passed_gets_its_boxes(client, monkeypatch):
    doc, _v, pages, analysis, _t, _c = await analysed_circular(monkeypatch)
    box = {"page_number": 1, "line_index": 1, "box_2d": [10, 10, 20, 900]}
    async with AsyncSessionLocal() as db:
        claims = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all()
        bad_number = [c for c in claims if c.kind == "SUMMARY_POINT" and c.check_status == "NOT_SHOWN"][0]
        waiting = [c for c in claims if c.kind == "OBLIGATION" and c.check_status == "WAITING_FOR_PERSON"][0]
        for c in (bad_number, waiting):
            for cit in (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id == c.id))).scalars().all():
                cit.quote_boxes = [box]
        # The waiting one failed its quote check: no boxes may go out.
        waiting.checks = [{"name": "QUOTE_FOUND", "result": "FAIL", "message": "x"}, {"name": "PAGE_READ", "result": "PASS", "message": ""}]
        await db.commit()
    hidden = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()["hidden"]
    by_section = {h["section"]: h for h in hidden}
    assert by_section["summary"]["quote_boxes"] == [box]
    assert by_section["requirements"]["quote_boxes"] == []


# ---------------------------------------------------------------------------
# What the old endpoints give readers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reader_json_has_no_technical_fields(client, monkeypatch):
    doc, _v, _p, _a, target, _c = await analysed_circular(monkeypatch)
    for path in (
        f"/api/v1/documents/{doc.id}/claims",
        f"/api/v1/documents/{doc.id}/obligations",
        f"/api/v1/documents/{doc.id}/relationships",
        f"/api/v1/relationships/document/{doc.id}/status",
        f"/api/v1/relationships/document/{target.id}/status",
        f"/api/v1/relationships/document/{doc.id}/graph",
        f"/api/v1/relationships/document/{target.id}/timeline",
    ):
        r = await client.get(path)
        assert r.status_code == 200, path
        leaked = all_keys(r.json()) & FORBIDDEN_KEYS
        assert not leaked, (path, leaked)

    analysis = (await client.get(f"/api/v1/documents/{doc.id}/analysis")).json()
    assert analysis["structured_payload"] == {} and analysis["model_name"] == "" and analysis["prompt_version"] == ""
    assert analysis["tokens_used"] == 0 and analysis["estimated_cost_usd"] == 0.0
    assert analysis["claims"] == [] and analysis["executive_summary"] == "" and analysis["key_changes"] == []

    admin, token = await make_user(is_superuser=True)
    full = (await client.get(f"/api/v1/documents/{doc.id}/analysis", headers=_auth(token))).json()
    assert full["structured_payload"] and full["model_name"] and full["claims"]


@pytest.mark.asyncio
async def test_obligations_and_links_are_filtered_for_readers(client, monkeypatch):
    doc, _v, _p, _a, target, _c = await analysed_circular(monkeypatch)
    admin, token = await make_user(is_superuser=True)

    seen = (await client.get(f"/api/v1/documents/{doc.id}/obligations")).json()
    assert {o["title"] for o in seen} == {"Submit monthly liquidity report", "Do not open new branches"}
    everything = (await client.get(f"/api/v1/documents/{doc.id}/obligations", headers=_auth(token))).json()
    assert {o["title"] for o in everything} == {"Submit monthly liquidity report", "Do not open new branches", "File annual report"}

    # The waiting change-the-law link looks like a mention to a reader and like AMENDS to an administrator.
    rels = (await client.get(f"/api/v1/documents/{doc.id}/relationships")).json()
    assert [(r["relationship_type"], r["verification_status"]) for r in rels] == [("REFERENCES", "VERIFIED")]
    rels_admin = (await client.get(f"/api/v1/documents/{doc.id}/relationships", headers=_auth(token))).json()
    assert [(r["relationship_type"], r["verification_status"]) for r in rels_admin] == [("AMENDS", "PENDING_REVIEW")]

    status = (await client.get(f"/api/v1/relationships/document/{target.id}/status")).json()
    assert status["in_force_status"] == "IN_FORCE"
    assert [l["relationship_type"] for l in status["verified_incoming"]] == ["REFERENCES"] and status["unconfirmed_incoming"] == []
    status_admin = (await client.get(f"/api/v1/relationships/document/{target.id}/status", headers=_auth(token))).json()
    assert [l["relationship_type"] for l in status_admin["unconfirmed_incoming"]] == ["AMENDS"]
    timeline = (await client.get(f"/api/v1/relationships/document/{target.id}/timeline")).json()
    assert all(not item["changes"] for item in timeline["items"])
    graph = (await client.get(f"/api/v1/relationships/document/{target.id}/graph")).json()
    assert [e["relationship_type"] for e in graph["edges"]] == ["REFERENCES"]

    # A person confirms it on the old link screen: both views follow, and the target's status changes.
    rel_id = rels_admin[0]["id"]
    done = await client.post(f"/api/v1/relationships/{rel_id}/review", headers=_auth(token), json={"decision": "VERIFIED"})
    assert done.status_code == 200, done.text
    assert done.json()["target_in_force_status"] == "AMENDED"
    after = (await client.get(f"/api/v1/documents/{doc.id}/relationships")).json()
    assert [(r["relationship_type"], r["verification_status"]) for r in after] == [("AMENDS", "VERIFIED")]
    assert (await client.get(f"/api/v1/relationships/document/{target.id}/status")).json()["in_force_status"] == "AMENDED"
    async with AsyncSessionLocal() as db:
        claim = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.kind == "LINK", AnalysisClaim.relationship_id == uuid.UUID(rel_id)))).scalars().one()
        assert claim.check_status == "APPROVED" and claim.fields["shown_type"] == "AMENDS" and claim.reviewed_by == admin.id
    link_view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()["sections"]["links"][0]["link"]
    assert link_view["shown_type"] == "AMENDS"

    # Rejecting it is the same decision as on the review screen.
    again = await client.post(f"/api/v1/relationships/{rel_id}/review", headers=_auth(token), json={"decision": "REJECTED"})
    assert again.status_code == 200
    assert (await client.get(f"/api/v1/relationships/document/{target.id}/status")).json()["in_force_status"] == "IN_FORCE"
    assert (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()["sections"]["links"] == []


# ---------------------------------------------------------------------------
# Compliance and publish rules
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shown_obligation_of_a_circular_waiting_for_review_can_be_added(client, monkeypatch):
    doc, version, _p, analysis, _t, _c = await analysed_circular(monkeypatch)
    async with AsyncSessionLocal() as db:
        assert (await db.get(Document, doc.id)).publication_status == "AWAITING_REVIEW"
        obls = {o.title: o for o in (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id))).scalars().all()}
    ws = await cw.workspace()
    rid = await cw.new_register(client, ws)
    shown = await cw.add_items(client, ws, rid, doc, ids=[obls["Submit monthly liquidity report"].id])
    assert shown.status_code == 201 and len(shown.json()["items"]) == 1
    hidden = await cw.add_items(client, ws, rid, doc, ids=[obls["File annual report"].id])
    assert hidden.json()["items"] == []
    assert hidden.json()["skipped"][0]["reason"] == "This requirement is waiting for a check."


@pytest.mark.asyncio
async def test_publishing_as_human_reviewed_is_refused(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await analysed_circular(monkeypatch)
    admin, token = await make_user(is_superuser=True)
    r = await client.post(f"/api/v1/documents/{doc.id}/publish", headers=_auth(token),
                          json={"decision": "PUBLISHED_HUMAN_REVIEWED", "review_notes": "ok"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Decide each point on the Points to check screen."
    ok = await client.post(f"/api/v1/documents/{doc.id}/publish", headers=_auth(token),
                           json={"decision": "WITHDRAWN", "review_notes": "withdrawn"})
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# Ask for review
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ask_for_review_hides_a_shown_point_at_once(client, monkeypatch):
    doc, version, _p, analysis, _t, _c = await analysed_circular(monkeypatch)
    user, token = await make_user()
    admin, admin_token = await make_user(is_superuser=True)
    full = (await client.get(f"/api/v1/documents/{doc.id}/claims?all=1", headers=_auth(admin_token))).json()
    shown_req = [i for i in full["sections"]["requirements"] if i["shown"] and i["fields"]["title"] == "Submit monthly liquidity report"][0]

    assert (await client.post(f"/api/v1/claims/{shown_req['id']}/ask-review")).status_code in (401, 403)
    assert (await client.post(f"/api/v1/claims/{shown_req['id']}/ask-review", headers=_auth(token))).status_code == 403

    r = await client.post(f"/api/v1/claims/{shown_req['id']}/ask-review", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["claim"]["status"] == "WAITING_FOR_PERSON" and r.json()["claim"]["shown"] is False
    assert r.json()["counts"] == {"total": 11, "shown": 8, "checking": 0, "waiting_for_team": 2, "not_shown": 1}

    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert {x["fields"]["title"] for x in view["sections"]["requirements"]} == {"Do not open new branches"}
    assert view["counts"]["shown"] == 8 and view["counts"]["waiting_for_team"] == 2
    assert "Submit monthly liquidity report" not in json.dumps(view)
    assert {o["title"] for o in (await client.get(f"/api/v1/documents/{doc.id}/obligations")).json()} == {"Do not open new branches"}

    # Not shown any more, so there is nothing to hide again.
    assert (await client.post(f"/api/v1/claims/{shown_req['id']}/ask-review", headers=_auth(admin_token))).status_code == 409

    # Everything at once.
    allr = await client.post(f"/api/v1/documents/{doc.id}/claims/ask-review", headers=_auth(admin_token))
    assert allr.status_code == 200 and allr.json()["hidden"] == 8
    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert view["counts"]["shown"] == 0 and all(not rows for rows in view["sections"].values())
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.action == "claim.ask_review"))).scalars().all()
        assert len(events) >= 9


# ---------------------------------------------------------------------------
# The reading line
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reading_status_counts_quote_checks_waiting(monkeypatch):
    from backend.app.modules.analysis.auto import reading_status

    doc, version, pages = await make_document(pages=1, status="PUBLISHED_MACHINE_PROCESSED")
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, doc.id)
        none = await reading_status(db, d)
        assert none["quote_checks_waiting"] == 0 and none["state"] == "DONE" and none["minutes_left"] == 0
        db.add(QuoteReadingCheck(page_id=pages[0].id, sentence_id="p1.s1", line_indexes=[0], page_text_sha="a" * 64,
                                 status="WAITING", our_text="x", reads=[], numbers_confirmed=[], attempts=0))
        db.add(QuoteReadingCheck(page_id=pages[0].id, sentence_id="p1.s2", line_indexes=[1], page_text_sha="a" * 64,
                                 status="WAITING", our_text="y", reads=[], numbers_confirmed=[], attempts=0))
        await db.commit()
        waiting = await reading_status(db, d)
    assert waiting["quote_checks_waiting"] == 1  # one page, however many sentences
    assert waiting["minutes_left"] >= 1 and waiting["state"] != "DONE"


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------
V2_TEXT = (
    "All scheduled banks. "
    "Banks shall submit the monthly liquidity report by 31 December 2026. "
    "This amends {code} Circular No. 14 dated 23 September 2012. "
    "This comes into force with immediate effect."
)


async def old_style_analysis(code: str):
    """A circular analysed before points existed: an old-shaped answer, verified rows, one placeholder claim."""
    text = V2_TEXT.format(code=code)
    doc, version, pages = await cc.doc_with_text("PUBLISHED_HUMAN_REVIEWED", text)
    index = SentenceIndex.build([{"page_number": 1, "raw_text": text, "cleaned_text": text, "line_boxes": None}])
    s = lambda frag: [x.id for x in index.sentences.values() if frag in x.text][:1]  # noqa: E731
    payload = {
        "executive_summary": {"short_summary": "Banks report monthly.", "key_changes": ["A rule is amended."]},
        "applicability": {"covered_entities": ["SCHEDULED_BANK"], "exemptions": []},
        "deadlines": {"effective_date": "2026-01-01", "compliance_deadline": "2026-12-31", "reporting_deadline": None},
        "obligations": [{"title": "Submit monthly liquidity report", "obligation_type": "MANDATORY",
                         "requirement_description": "Banks shall submit the monthly liquidity report.",
                         "quote_span_ids": s("monthly liquidity"), "responsible_entity": "SCHEDULED_BANK",
                         "explicit_deadline": "2026-12-31"}],
        "relationships": [{"relationship_type": "AMENDS", "quote_span_ids": s("This amends"),
                           "target_reference_hint": f"{code} Circular No. 14 dated 23 September 2012"}],
        "provisions": [{"provision_number": "1.", "quote_span_ids": s("monthly liquidity"), "provision_type": "REPORTING",
                        "normalized_explanation": "Monthly report."}],
    }
    async with AsyncSessionLocal() as db:
        analysis = DocumentAnalysis(document_version_id=version.id, executive_summary="Banks report monthly.",
                                    model_name="old-model", prompt_version="v2", structured_payload=payload)
        db.add(analysis)
        await db.flush()
        db.add(AnalysisClaim(analysis_id=analysis.id, claim_type="PROVISION_ASSERTION", statement="Monthly report.",
                             verification_status="VERIFIED_EXACT"))
        db.add(Obligation(document_version_id=version.id, page_id=pages[0].id, obligation_type="MANDATORY",
                          title="Submit monthly liquidity report",
                          requirement_description="Banks shall submit the monthly liquidity report.",
                          supporting_text="x", applicability_summary="SCHEDULED_BANK", verification_status="VERIFIED"))
        db.add(DocumentRelationship(source_document_id=doc.id, target_reference_hint=f"{code} Circular No. 14 dated 23 September 2012",
                                    relationship_type="AMENDS", source_page_id=pages[0].id, supporting_quote="This amends",
                                    verification_status="VERIFIED", detection_method="AI_INFERRED"))
        await db.commit()
        return doc, version, analysis


async def claim_kinds(analysis_id):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis_id))).scalars().all()
        return sorted((c.kind, c.check_status) for c in rows)


@pytest.mark.asyncio
async def test_backfill_dry_run_apply_and_second_apply(monkeypatch):
    from backend.app.modules.compliance import rules
    monkeypatch.setattr(rules, "today_dhaka", lambda: TODAY)
    code = "ZB" + uuid.uuid4().hex[:6].upper()
    target = await library_target(code)
    doc, version, analysis = await old_style_analysis(code)
    only = {str(doc.id)}

    dry = await backfill_claims.backfill(AsyncSessionLocal, apply=False, only_documents=only)
    assert len(dry) == 1 and dry[0].reference
    assert await claim_kinds(analysis.id) == [("PROVISION", "CHECKING")]  # nothing written
    async with AsyncSessionLocal() as db:
        rel = (await db.execute(select(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id))).scalars().one()
        assert rel.verification_status == "VERIFIED"

    applied = await backfill_claims.backfill(AsyncSessionLocal, apply=True, only_documents=only)
    assert len(applied) == 1
    line = applied[0]
    # shown: the requirement and the link (as a mention); not shown: the five old points with no evidence
    assert (line.shown, line.waiting, line.not_shown, line.checking) == (2, 0, 5, 0)
    assert len(line.notes) == 1 and "amends" in line.notes[0] and "No person confirmed" in line.notes[0]
    kinds = await claim_kinds(analysis.id)
    by_kind = {}
    for k, st in kinds:
        by_kind.setdefault(k, []).append(st)
    # The old summary, key changes, applicability and dates had no evidence: they are not shown.
    assert by_kind["SUMMARY_POINT"] == ["NOT_SHOWN"] and by_kind["KEY_CHANGE"] == ["NOT_SHOWN"]
    assert by_kind["APPLIES_TO"] == ["NOT_SHOWN"] and by_kind["DATE"] == ["NOT_SHOWN", "NOT_SHOWN"]
    assert by_kind["OBLIGATION"] and by_kind["LINK"] == ["WAITING_FOR_PERSON"]

    async with AsyncSessionLocal() as db:
        rel = (await db.execute(select(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id))).scalars().one()
        assert rel.verification_status == "PENDING_REVIEW"  # an unreviewed AMENDS link no longer counts
        claims = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all()
        no_evidence = [c for c in claims if c.kind == "SUMMARY_POINT"][0]
        assert any(c["message"] == "This point does not say which sentence it comes from." for c in no_evidence.checks)
        refreshed = await db.get(Document, doc.id)
        assert refreshed.publication_status in ("AWAITING_REVIEW", "PUBLISHED_MACHINE_VERIFIED")
        before = {str(c.id) for c in claims}

    second = await backfill_claims.backfill(AsyncSessionLocal, apply=True, only_documents=only)
    assert second == []
    async with AsyncSessionLocal() as db:
        claims = (await db.execute(select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id))).scalars().all()
        assert {str(c.id) for c in claims} == before
