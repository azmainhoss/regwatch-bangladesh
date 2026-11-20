"""Claim checks, chunk 3 (docs/specs/CLAIM_CHECKS_SPEC.md): the review screen's endpoints and the
decisions behind them (approve, fix, reject, ask for review), and the two carried-over rules:
a released circular sends its one alert, and a fixed point survives the next run."""
import copy
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.alerts.models import AlertEvent
from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.claims import review
from backend.app.modules.documents.models import Document
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.relationships.status import bulk_in_force
from backend.app.tests import test_claim_checks as cc
from backend.app.tests import test_claims_view as cv
from backend.app.tests.factories import make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def admin_items(client, token, doc_id):
    body = (await client.get(f"/api/v1/documents/{doc_id}/claims?all=1", headers=auth(token))).json()
    return [i for rows in body["sections"].values() for i in rows]


def pick(items, kind, title=None):
    for i in items:
        if i["kind"] == kind and (title is None or i["fields"].get("title") == title):
            return i
    raise AssertionError(f"no {kind} {title}")


async def queue_ids(client, token, doc_id, queue):
    rows = (await client.get(f"/api/v1/claims/review?queue={queue}&limit=50", headers=auth(token))).json()["items"]
    return [r for r in rows if r["circular"]["id"] == str(doc_id)]


async def doc_status(doc_id):
    async with AsyncSessionLocal() as db:
        return (await db.get(Document, doc_id)).publication_status


async def claim_row(claim_id):
    async with AsyncSessionLocal() as db:
        return await db.get(AnalysisClaim, claim_id)


async def alert_count(doc_id):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(func.count()).select_from(AlertEvent).where(AlertEvent.dedupe_key == f"CIRCULAR_PUBLISHED:{doc_id}"))
        ).scalar_one()


async def audit_actions(claim_id):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AuditEvent.action).where(AuditEvent.entity_id == claim_id))).scalars().all()
        return list(rows)


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_queue_lists_held_points_with_what_a_reviewer_needs(client, monkeypatch):
    doc, version, _p, analysis, target, _code = await cv.analysed_circular(monkeypatch)
    _u, token = await make_user()
    _a, admin_token = await make_user(is_superuser=True)

    required = await queue_ids(client, admin_token, doc.id, "REQUIRED")
    optional = await queue_ids(client, admin_token, doc.id, "OPTIONAL")
    assert [r["claim"]["kind"] for r in required] == ["OBLIGATION", "LINK"]  # a deadline first, then the link without one
    assert [r["claim"]["kind"] for r in optional] == ["SUMMARY_POINT"]

    first = required[0]
    assert first["circular"]["id"] == str(doc.id) and first["circular"]["title"]
    assert first["page"]["page_number"] == 1 and first["version_id"] == str(version.id)
    assert first["claim"]["fields"]["title"] == "File annual report"
    assert first["claim"]["is_high_stakes"] is True and first["claim"]["quote"]
    assert any("not in the quoted sentences" in m for m in first["claim"]["why"])
    # the sentence picker offers the cited page's sentences, with the current ones marked in the claim
    assert first["sentences"] and set(first["claim"]["quote_sentence_ids"]) <= {s["sentence_id"] for s in first["sentences"]}
    link = required[1]["claim"]
    assert link["relationship_id"] and link["why"] == ["It changes which rule is in force; a person confirms these."]
    assert link["link"]["target_document_id"] == str(target.id)

    # the counts agree with the lists
    counts = (await client.get("/api/v1/claims/review/counts", headers=auth(admin_token))).json()
    totals = {q: (await client.get(f"/api/v1/claims/review?queue={q}&limit=1", headers=auth(admin_token))).json()["total"] for q in ("REQUIRED", "OPTIONAL")}
    assert counts["required"] == totals["REQUIRED"] >= 2 and counts["optional"] == totals["OPTIONAL"] >= 1
    assert counts["checking"] >= 0

    # a bank user, and a visitor, cannot see the queue
    for url in ("/api/v1/claims/review", "/api/v1/claims/review/counts"):
        assert (await client.get(url, headers=auth(token))).status_code == 403
        assert (await client.get(url)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_queue_pages_with_a_cursor(client, monkeypatch):
    await cv.analysed_circular(monkeypatch)
    _a, admin_token = await make_user(is_superuser=True)
    seen = []
    after = None
    for _ in range(200):
        url = "/api/v1/claims/review?queue=REQUIRED&limit=2" + (f"&after={after}" if after else "")
        body = (await client.get(url, headers=auth(admin_token))).json()
        seen += [r["claim"]["id"] for r in body["items"]]
        after = body["next"]
        if not after:
            break
    assert len(seen) == len(set(seen)) == body["total"]


def test_queue_order_high_stakes_then_soonest_deadline_then_oldest():
    today = date(2026, 11, 13)

    def point(high, deadline, created, ident, kind="OBLIGATION"):
        fields = {"deadline": deadline} if deadline else {}
        return SimpleNamespace(
            id=ident, is_high_stakes=high, kind=kind, fields=fields, created_at=datetime(2026, 1, created, tzinfo=timezone.utc), order_index=0
        )

    doc = SimpleNamespace(publication_date=date(2026, 5, 1))
    rows = [
        point(False, "2026-11-20", 1, "e"),
        point(True, None, 2, "c"),
        point(True, "2026-12-31", 3, "b"),
        point(True, "2026-11-20", 4, "a"),
        point(True, None, 1, "d"),
        point(True, "2026-01-05", 5, "c2"),  # already past: counts as no upcoming deadline
    ]
    ordered = sorted(rows, key=lambda c: tuple(review.sort_key(c, doc, "REQUIRED", today)))
    assert [c.id for c in ordered] == ["a", "b", "d", "c", "c2", "e"]

    older = SimpleNamespace(publication_date=date(2025, 1, 1))
    newer = SimpleNamespace(publication_date=date(2026, 6, 1))
    a, b = point(False, None, 1, "x"), point(False, None, 1, "y")
    keys = sorted([(review.sort_key(a, older, "OPTIONAL", today), "old"), (review.sort_key(b, newer, "OPTIONAL", today), "new")], key=lambda t: tuple(t[0]))
    assert [k[1] for k in keys] == ["new", "old"]  # newest circular first


@pytest.mark.asyncio
async def test_circulars_with_nothing_to_show_are_listed_until_something_is_shown(client, monkeypatch):
    doc, _v, _p = await cc.doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    payload = {
        "classification": {"document_type": "CIRCULAR", "subject": "x", "language": "en"},
        "executive_summary": {"summary_points": [], "key_changes": []},
        "provisions": [],
        "obligations": [{"title": "File report", "obligation_type": "MANDATORY", "requirement_description": "Banks shall file.",
                         "quote_span_ids": cc.sids(cc.make_ctx(cc.PAGE_TEXT), "monthly liquidity"), "explicit_deadline": "2027-03-03",
                         "deadline_ids": cc.sids(cc.make_ctx(cc.PAGE_TEXT), "monthly liquidity")}],
        "relationships": [], "applicability": {"covered": [], "exemptions": []}, "deadlines": {},
    }
    await cc.run_analysis(doc.id, payload, monkeypatch)
    _a, admin_token = await make_user(is_superuser=True)
    counts = (await client.get("/api/v1/claims/review/counts", headers=auth(admin_token))).json()
    assert str(doc.id) in [c["id"] for c in counts["empty_circulars"]]
    assert set(counts["empty_circulars"][0]) == {"id", "reference_number", "title"}

    item = (await queue_ids(client, admin_token, doc.id, "REQUIRED"))[0]
    assert (await client.post(f"/api/v1/claims/{item['claim']['id']}/approve", headers=auth(admin_token))).status_code == 200
    counts = (await client.get("/api/v1/claims/review/counts", headers=auth(admin_token))).json()
    assert str(doc.id) not in [c["id"] for c in counts["empty_circulars"]]


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_a_point_then_the_last_required_point_publishes_the_circular(client, monkeypatch):
    doc, version, _p, _a, target, _c = await cv.analysed_circular(monkeypatch)
    admin, admin_token = await make_user(is_superuser=True)
    assert await doc_status(doc.id) == "AWAITING_REVIEW"
    items = await admin_items(client, admin_token, doc.id)
    annual = pick(items, "OBLIGATION", "File annual report")
    link = pick(items, "LINK")

    r = await client.post(f"/api/v1/claims/{annual['id']}/approve", json={"note": "date checked on the page"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["claim"]["status"] == "APPROVED" and body["claim"]["shown"] is True and body["claim"]["checked_by"] == "TEAM"
    assert body["document_id"] == str(doc.id)
    assert body["document_status"] == "AWAITING_REVIEW"  # the link still needs a person
    row = await claim_row(annual["id"])
    assert row.reviewed_by == admin.id and row.reviewed_at is not None and row.review_note == "date checked on the page"
    assert row.review_queue is None
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id, Obligation.title == "File annual report"))).scalars().one()
        assert obl.verification_status == "VERIFIED"
    assert "claim.approve" in await audit_actions(row.id)
    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert "File annual report" in json.dumps(view) and view["counts"]["shown"] == 10

    r = await client.post(f"/api/v1/claims/{link['id']}/approve", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["document_status"] == "PUBLISHED_HUMAN_REVIEWED"  # the last required point is decided
    assert await doc_status(doc.id) == "PUBLISHED_HUMAN_REVIEWED"


@pytest.mark.asyncio
async def test_approving_a_change_the_law_link_makes_it_count(client, monkeypatch):
    doc, _v, _p, _a, target, _c = await cv.analysed_circular(monkeypatch)
    admin, admin_token = await make_user(is_superuser=True)
    link = pick(await admin_items(client, admin_token, doc.id), "LINK")
    assert link["link"]["shown_type"] == "REFERENCES" and link["fields"]["claimed_type"] == "AMENDS"
    async with AsyncSessionLocal() as db:
        assert (await bulk_in_force(db, [target.id], None))[str(target.id)].status == "IN_FORCE"

    r = await client.post(f"/api/v1/claims/{link['id']}/approve", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["claim"]["link"]["shown_type"] == "AMENDS" and r.json()["claim"]["fields"]["shown_type"] == "AMENDS"
    async with AsyncSessionLocal() as db:
        rel = await db.get(DocumentRelationship, link["relationship_id"])
        assert rel.verification_status == "VERIFIED" and rel.relationship_type == "AMENDS"
        assert (await bulk_in_force(db, [target.id], None))[str(target.id)].status == "AMENDED"
    # a reader now sees it as "Amends"
    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert view["sections"]["links"][0]["link"]["shown_type"] == "AMENDS"


@pytest.mark.asyncio
async def test_the_old_link_review_and_the_claim_endpoint_end_in_the_same_state(client, monkeypatch):
    doc_a, _v, _p, _a, target_a, _c = await cv.analysed_circular(monkeypatch)
    doc_b, _v2, _p2, _a2, target_b, _c2 = await cv.analysed_circular(monkeypatch)
    _u, admin_token = await make_user(is_superuser=True)
    link_a = pick(await admin_items(client, admin_token, doc_a.id), "LINK")
    link_b = pick(await admin_items(client, admin_token, doc_b.id), "LINK")

    old = await client.post(f"/api/v1/relationships/{link_a['relationship_id']}/review", json={"decision": "VERIFIED"}, headers=auth(admin_token))
    new = await client.post(f"/api/v1/claims/{link_b['id']}/approve", headers=auth(admin_token))
    assert old.status_code == 200 and new.status_code == 200

    async def end_state(link, doc, target):
        row = await claim_row(link["id"])
        async with AsyncSessionLocal() as db:
            rel = await db.get(DocumentRelationship, link["relationship_id"])
            force = (await bulk_in_force(db, [target.id], None))[str(target.id)].status
        return row.check_status, row.fields["shown_type"], rel.verification_status, rel.relationship_type, force, await doc_status(doc.id)

    state_a = await end_state(link_a, doc_a, target_a)
    assert state_a == await end_state(link_b, doc_b, target_b)
    assert state_a == ("APPROVED", "AMENDS", "VERIFIED", "AMENDS", "AMENDED", "AWAITING_REVIEW")  # one required point is left

    # and the old endpoint's reject agrees with the claim endpoint's reject
    doc_c, _v3, _p3, _a3, _t3, _c3 = await cv.analysed_circular(monkeypatch)
    doc_d, _v4, _p4, _a4, _t4, _c4 = await cv.analysed_circular(monkeypatch)
    link_c = pick(await admin_items(client, admin_token, doc_c.id), "LINK")
    link_d = pick(await admin_items(client, admin_token, doc_d.id), "LINK")
    assert (await client.post(f"/api/v1/relationships/{link_c['relationship_id']}/review", json={"decision": "REJECTED"}, headers=auth(admin_token))).status_code == 200
    assert (await client.post(f"/api/v1/claims/{link_d['id']}/reject", json={"reason": "NOT_IN_CIRCULAR"}, headers=auth(admin_token))).status_code == 200
    for link in (link_c, link_d):
        row = await claim_row(link["id"])
        async with AsyncSessionLocal() as db:
            rel = await db.get(DocumentRelationship, link["relationship_id"])
        assert (row.check_status, rel.verification_status) == ("REJECTED", "REJECTED")


# ---------------------------------------------------------------------------
# Reject and ask for review
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_a_point_it_is_never_shown_and_its_row_is_rejected(client, monkeypatch):
    doc, version, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    admin, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")

    r = await client.post(f"/api/v1/claims/{annual['id']}/reject", json={"reason": "WRONG_DETAILS", "note": "not what the page says"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    row = await claim_row(annual["id"])
    assert row.check_status == "REJECTED" and row.reject_reason == "WRONG_DETAILS" and row.reviewed_by == admin.id and row.reviewed_at
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id, Obligation.title == "File annual report"))).scalars().one()
        assert obl.verification_status == "REJECTED"
    assert "claim.reject" in await audit_actions(row.id)
    # rejected points are not counted and have no placeholder
    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert view["counts"]["total"] == 10
    assert (await client.post(f"/api/v1/claims/{annual['id']}/approve", headers=auth(admin_token))).status_code == 409


@pytest.mark.asyncio
async def test_ask_for_review_joins_the_queue_and_is_decided_like_any_point(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    admin, admin_token = await make_user(is_superuser=True)
    items = await admin_items(client, admin_token, doc.id)
    summary = pick(items, "KEY_CHANGE")
    assert summary["shown"] is True
    r = await client.post(f"/api/v1/claims/{summary['id']}/ask-review", headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["claim"]["shown"] is False
    assert "claim.ask_review" in await audit_actions(summary["id"])
    queued = await queue_ids(client, admin_token, doc.id, "REQUIRED")
    assert summary["id"] in [q["claim"]["id"] for q in queued]
    assert (await client.post(f"/api/v1/claims/{summary['id']}/approve", headers=auth(admin_token))).status_code == 200
    view = (await client.get(f"/api/v1/documents/{doc.id}/claims")).json()
    assert [c["fields"]["text"] for c in view["sections"]["changes"]] == ["BRPD Circular No. 14 is amended.".replace("BRPD", _c)]


# ---------------------------------------------------------------------------
# Fix
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fix_runs_the_checks_again_and_needs_a_tick_when_one_fails(client, monkeypatch):
    doc, version, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    admin, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")
    url = f"/api/v1/claims/{annual['id']}/fix"

    # a date that is not in the quote: plain messages, nothing saved
    bad = await client.post(url, json={"fields": {"deadline": "2027-02-01"}, "evidence_ids": [], "confirm_checked": False}, headers=auth(admin_token))
    assert bad.status_code == 400
    detail = bad.json()["detail"]
    assert detail["problems"] and any("not in the quoted sentences" in m for m in detail["problems"])
    for m in detail["problems"]:
        assert not any(w in m for w in ("HTTP", "DATES", "FAIL", "Traceback"))
    assert (await claim_row(annual["id"])).check_status == "WAITING_FOR_PERSON"
    assert (await claim_row(annual["id"])).fields["deadline"] == "2027-01-31"

    # values that cannot be right are refused without the tick being a way round
    for fields in ({"deadline": "next week"}, {"who": "THE MOON"}, {"obligation_type": "SOMETIMES"}):
        r = await client.post(url, json={"fields": fields, "confirm_checked": True}, headers=auth(admin_token))
        assert r.status_code == 400 and r.json()["detail"]["problems"]

    # with the tick: saved as FIXED, the old values are kept, the row follows
    ok = await client.post(url, json={"fields": {"deadline": "2027-02-01", "title": "File the annual report"}, "evidence_ids": [], "confirm_checked": True}, headers=auth(admin_token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["claim"]["status"] == "FIXED" and ok.json()["claim"]["checked_by"] == "TEAM"
    row = await claim_row(annual["id"])
    assert row.check_status == "FIXED" and row.reviewed_by == admin.id and row.reviewed_at
    assert row.fields["deadline"] == "2027-02-01" and row.fields["title"] == "File the annual report"
    assert row.original_fields["deadline"] == "2027-01-31" and row.original_fields["title"] == "File annual report"
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id, Obligation.title == "File the annual report"))).scalars().one()
        assert obl.verification_status == "VERIFIED" and obl.explicit_deadline == date(2027, 2, 1)
    actions = await audit_actions(row.id)
    assert "claim.fix" in actions
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == row.id, AuditEvent.action == "claim.fix"))).scalars().one()
        assert event.before_state["fields"]["deadline"] == "2027-01-31" and event.after_state["fields"]["deadline"] == "2027-02-01"


@pytest.mark.asyncio
async def test_fix_that_passes_every_check_needs_no_tick_and_can_pick_other_sentences(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    _u, admin_token = await make_user(is_superuser=True)
    required = await queue_ids(client, admin_token, doc.id, "REQUIRED")
    annual = [r for r in required if r["claim"]["fields"].get("title") == "File annual report"][0]
    by_text = {s["text"].strip(): s["sentence_id"] for s in annual["sentences"]}
    url = f"/api/v1/claims/{annual['claim']['id']}/fix"

    ok = await client.post(url, json={"fields": {"deadline": "2026-12-31"}, "confirm_checked": False}, headers=auth(admin_token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["claim"]["fields"]["deadline"] == "2026-12-31"
    assert (await claim_row(annual["claim"]["id"])).check_status == "FIXED"

    # a second point: choose a different sentence as the evidence; the quote follows, the page link too
    summary = [r for r in await queue_ids(client, admin_token, doc.id, "OPTIONAL")][0]
    sentence = [sid for text, sid in by_text.items() if text.startswith("All scheduled")][0]
    r = await client.post(
        f"/api/v1/claims/{summary['claim']['id']}/fix",
        json={"fields": {"text": "Banks must submit a monthly liquidity report."}, "evidence_ids": [sentence], "confirm_checked": True},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["claim"]["quote"].startswith("All scheduled banks")
    async with AsyncSessionLocal() as db:
        cites = (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id == summary["claim"]["id"]))).scalars().all()
        assert len(cites) == 1 and cites[0].quoted_text.startswith("All scheduled banks")
    # without any sentence the fix is refused whatever the tick says
    other = (await queue_ids(client, admin_token, doc.id, "REQUIRED"))
    assert other  # the link still waits
    bad = await client.post(f"/api/v1/claims/{other[0]['claim']['id']}/fix", json={"fields": {"claimed_type": "REFERENCES"}, "evidence_ids": ["p9.s9"], "confirm_checked": True}, headers=auth(admin_token))
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_a_fixed_point_keeps_its_fingerprint_and_carries_over_to_the_next_run(client, monkeypatch):
    doc, version, _p = await cc.doc_with_text("PUBLISHED_MACHINE_PROCESSED")
    ctx = cc.make_ctx(cc.PAGE_TEXT)
    first = await cc.run_analysis(doc.id, cc.payload_for(ctx), monkeypatch)
    _u, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")
    before = await claim_row(annual["id"])
    fingerprint = before.fingerprint

    r = await client.post(f"/api/v1/claims/{annual['id']}/fix", json={"fields": {"deadline": "2027-02-01"}, "confirm_checked": True}, headers=auth(admin_token))
    assert r.status_code == 200
    fixed = await claim_row(annual["id"])
    assert fixed.fingerprint == fingerprint  # the edit is in `fields`, never in the fingerprint

    second = await cc.run_analysis(doc.id, cc.payload_for(ctx), monkeypatch)
    again = [c for c in await cc.load_claims(second.id) if c.kind == "OBLIGATION" and c.fingerprint == fingerprint]
    assert len(again) == 1
    carried = again[0]
    assert carried.check_status == "FIXED" and str(carried.carried_from_claim_id) == annual["id"]
    assert carried.fields["deadline"] == "2027-02-01"
    assert carried.original_fields["deadline"] == "2027-01-31"
    async with AsyncSessionLocal() as db:
        obl = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id, Obligation.title == "File annual report"))).scalars().all()
        assert any(o.explicit_deadline == date(2027, 2, 1) and o.verification_status == "VERIFIED" for o in obl)


# ---------------------------------------------------------------------------
# Who may decide, and who decides first
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deciding_twice_is_a_conflict_that_carries_the_current_point(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    _u, other_token = await make_user(is_superuser=True)
    _u2, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")
    assert (await client.post(f"/api/v1/claims/{annual['id']}/approve", headers=auth(admin_token))).status_code == 200
    for action, body in (("approve", None), ("reject", {"reason": "OTHER"}), ("fix", {"fields": {"title": "x"}})):
        r = await client.post(f"/api/v1/claims/{annual['id']}/{action}", json=body, headers=auth(other_token)) if body else await client.post(f"/api/v1/claims/{annual['id']}/{action}", headers=auth(other_token))
        assert r.status_code == 409, (action, r.text)
        detail = r.json()["detail"]
        assert detail["message"] == "Someone else already decided this point."
        assert detail["claim"]["id"] == annual["id"] and detail["claim"]["status"] == "APPROVED"
    assert (await claim_row(annual["id"])).reviewed_by is not None


@pytest.mark.asyncio
async def test_only_administrators_can_decide(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    _u, token = await make_user()
    _a2, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")
    for action in ("approve", "fix", "reject", "ask-review"):
        body = {"fields": {}} if action == "fix" else {"reason": "OTHER"} if action == "reject" else None
        for headers in (auth(token), {}):
            r = await client.post(f"/api/v1/claims/{annual['id']}/{action}", json=body, headers=headers) if body else await client.post(f"/api/v1/claims/{annual['id']}/{action}", headers=headers)
            assert r.status_code in (401, 403), (action, r.status_code)
    assert (await claim_row(annual["id"])).check_status == "WAITING_FOR_PERSON"
    assert (await client.post("/api/v1/claims/00000000-0000-0000-0000-000000000000/approve", headers=auth(admin_token))).status_code == 404


# ---------------------------------------------------------------------------
# The alert: sent once when a held circular is released, never for the archive
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_held_live_circular_sends_its_one_alert_when_a_decision_releases_it(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    _u, admin_token = await make_user(is_superuser=True)
    assert await doc_status(doc.id) == "AWAITING_REVIEW" and await alert_count(doc.id) == 0
    items = await admin_items(client, admin_token, doc.id)
    annual, link = pick(items, "OBLIGATION", "File annual report"), pick(items, "LINK")

    await client.post(f"/api/v1/claims/{annual['id']}/approve", headers=auth(admin_token))
    assert await alert_count(doc.id) == 0  # still held
    await client.post(f"/api/v1/claims/{link['id']}/approve", headers=auth(admin_token))
    assert await doc_status(doc.id) == "PUBLISHED_HUMAN_REVIEWED" and await alert_count(doc.id) == 1

    # held again and released again: the alert is not sent a second time
    assert (await client.post(f"/api/v1/claims/{annual['id']}/ask-review", headers=auth(admin_token))).status_code == 200
    assert await doc_status(doc.id) == "AWAITING_REVIEW"
    assert (await client.post(f"/api/v1/claims/{annual['id']}/approve", headers=auth(admin_token))).status_code == 200
    assert await doc_status(doc.id) == "PUBLISHED_HUMAN_REVIEWED" and await alert_count(doc.id) == 1


@pytest.mark.asyncio
async def test_a_released_archive_circular_never_alerts(client, monkeypatch):
    doc, _v, _p = await cc.doc_with_text("EXTRACTED")
    await cc.run_analysis(doc.id, cc.payload_for(cc.make_ctx(cc.PAGE_TEXT)), monkeypatch)
    _u, admin_token = await make_user(is_superuser=True)
    assert await doc_status(doc.id) == "AWAITING_REVIEW"
    for row in await queue_ids(client, admin_token, doc.id, "REQUIRED"):
        assert (await client.post(f"/api/v1/claims/{row['claim']['id']}/approve", headers=auth(admin_token))).status_code == 200
    assert await doc_status(doc.id) == "PUBLISHED_HUMAN_REVIEWED"
    assert await alert_count(doc.id) == 0
    # analysing it again later does not turn it into news either
    await cc.run_analysis(doc.id, cc.payload_for(cc.make_ctx(cc.PAGE_TEXT)), monkeypatch)
    assert await alert_count(doc.id) == 0


@pytest.mark.asyncio
async def test_a_single_point_can_be_opened_by_its_id_even_after_it_was_decided(client, monkeypatch):
    doc, _v, _p, _a, _t, _c = await cv.analysed_circular(monkeypatch)
    _u, token = await make_user()
    _a2, admin_token = await make_user(is_superuser=True)
    annual = pick(await admin_items(client, admin_token, doc.id), "OBLIGATION", "File annual report")

    one = (await client.get(f"/api/v1/claims/review?point={annual['id']}", headers=auth(admin_token))).json()
    assert [r["claim"]["id"] for r in one["items"]] == [annual["id"]] and one["queue"] == "REQUIRED"
    assert one["items"][0]["sentences"] and one["items"][0]["circular"]["id"] == str(doc.id)

    await client.post(f"/api/v1/claims/{annual['id']}/approve", headers=auth(admin_token))
    again = (await client.get(f"/api/v1/claims/review?point={annual['id']}", headers=auth(admin_token))).json()
    assert again["items"][0]["claim"]["status"] == "APPROVED"  # still returned, so the screen can say it was decided
    assert annual["id"] not in [r["claim"]["id"] for r in await queue_ids(client, admin_token, doc.id, "REQUIRED")]

    missing = (await client.get("/api/v1/claims/review?point=00000000-0000-0000-0000-000000000000", headers=auth(admin_token))).json()
    assert missing["items"] == []
    assert (await client.get(f"/api/v1/claims/review?point={annual['id']}", headers=auth(token))).status_code == 403
