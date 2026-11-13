"""Bank compliance workspace: registers from circulars, snapshots, overdue, status rules, sign-off, evidence, audit, report."""
import hashlib
import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select

from backend.app.core.config import settings
from backend.app.core.storage import storage_service
from backend.app.database.session import AsyncSessionLocal, async_engine
from backend.app.main import app
from backend.app.modules.audit.models import AuditEvent
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import ComplianceItem, TaskEvidence
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.tests.factories import make_document, make_user, make_workspace

PUBLISHED = "PUBLISHED_MACHINE_PROCESSED"
PDF = b"%PDF-1.4 evidence bytes"

ROLES = {
    "ORG_ADMIN": None,
    "COMPLIANCE_HEAD": None,
    "COMPLIANCE_OFFICER": None,
    "DEPARTMENT_LEAD": "A",
    "DEPARTMENT_LEAD:B": "B",
    "REVIEWER": None,
    "REVIEWER:2": None,
    "ANALYST": "A",
    "AUDITOR": None,
    "VIEWER": None,
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def base(ws) -> str:
    return f"/api/v1/organizations/{ws.org_id}/compliance"


async def add_obligation(version_id, page_id, quote, verified=True, title="Duty"):
    async with AsyncSessionLocal() as db:
        obl = Obligation(
            document_version_id=version_id, page_id=page_id, obligation_type="MANDATORY", title=title,
            requirement_description="Do it.", supporting_text=quote, applicability_summary="Banks",
            verification_status="VERIFIED" if verified else "PENDING_REVIEW",
        )
        db.add(obl)
        await db.commit()
        await db.refresh(obl)
        return obl


async def circular(n_verified=2, status=PUBLISHED, extra_pending=0):
    doc, version, pages = await make_document(pages=2, status=status)
    obls = []
    for i in range(n_verified):
        obls.append(await add_obligation(version.id, pages[i % 2].id, f"Banks shall do thing {i} {uuid.uuid4().hex[:4]}.", title=f"Duty {i}"))
    for i in range(extra_pending):
        obls.append(await add_obligation(version.id, pages[0].id, f"Pending thing {i} {uuid.uuid4().hex[:4]}.", verified=False))
    return doc, version, pages, obls


async def workspace():
    return await make_workspace(ROLES)


async def new_register(client, ws, title="Register"):
    r = await client.post(f"{base(ws)}/registers", headers=ws.headers("COMPLIANCE_OFFICER"), json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def add_items(client, ws, register_id, doc, ids=None, role="COMPLIANCE_OFFICER"):
    body = {"document_id": str(doc.id)}
    if ids is not None:
        body["obligation_ids"] = [str(i) for i in ids]
    return await client.post(f"{base(ws)}/registers/{register_id}/items/from-document", headers=ws.headers(role), json=body)


async def one_item(client, ws, n=1):
    doc, version, pages, obls = await circular(n_verified=n)
    rid = await new_register(client, ws)
    r = await add_items(client, ws, rid, doc)
    assert r.status_code == 201, r.text
    return rid, r.json()["items"], doc, version, pages, obls


async def task_for(client, ws, item_id, role="COMPLIANCE_OFFICER", assignee=None, due=None):
    body = {"compliance_item_id": item_id, "title": "Collect proof", "due_date": str(due or date.today() + timedelta(days=30)), "priority": "HIGH"}
    if assignee:
        body["assigned_to_user_id"] = str(ws.users[assignee].id)
    r = await client.post(f"{base(ws)}/tasks", headers=ws.headers(role), json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def upload(client, ws, task_id, role="ANALYST", content=PDF, name="proof.pdf"):
    return await client.post(
        f"{base(ws)}/tasks/{task_id}/evidence", headers=ws.headers(role),
        files={"file": (name, content, "application/pdf")}, data={"notes": "n"},
    )


# ---------------------------------------------------------------------------
# 1-4: adding from a circular, snapshot, re-analysis, duplicates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_from_circular_only_verified_current_published(client):
    ws = await workspace()
    rid = await new_register(client, ws)
    doc, version, pages, obls = await circular(n_verified=2, extra_pending=1)
    resp = await add_items(client, ws, rid, doc)
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["items"]) == 2 and body["skipped"] == []

    # asking for the pending one by id reports why
    pending = obls[2]
    again = await add_items(client, ws, rid, doc, ids=[pending.id])
    assert again.json()["items"] == []
    assert again.json()["skipped"][0]["reason"] == "Awaiting quote check"

    # unpublished circular
    udoc, _v, _p, uobls = await circular(n_verified=1, status="EXTRACTED")
    unp = await add_items(client, ws, rid, udoc, ids=[uobls[0].id])
    assert unp.json()["skipped"][0]["reason"] == "Circular not published yet"

    # older version of a circular
    odoc, over, opages, oobls = await circular(n_verified=1)
    async with AsyncSessionLocal() as db:
        v2 = DocumentVersion(document_id=odoc.id, version_number=2, file_sha256="c" * 64, file_size_bytes=1, storage_path="x", page_count=1)
        db.add(v2)
        await db.flush()
        d = await db.get(Document, odoc.id)
        d.current_version_id = v2.id
        await db.commit()
    old = await add_items(client, ws, rid, odoc, ids=[oobls[0].id])
    assert old.json()["skipped"][0]["reason"] == "Older version of this circular"

    # private upload is not found at all
    owner, _ = await make_user()
    pdoc, _pv, _pp, pobls = await circular(n_verified=1)
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, pdoc.id)
        d.owner_user_id = owner.id
        await db.commit()
    priv = await add_items(client, ws, rid, pdoc)
    assert priv.status_code == 404
    single = await client.post(f"{base(ws)}/items", headers=ws.headers("COMPLIANCE_OFFICER"),
                               json={"register_id": rid, "obligation_id": str(pobls[0].id)})
    assert single.status_code == 400 and single.json()["detail"] == "Private upload"

    listing = await client.get(f"{base(ws)}/documents/{doc.id}/addable-obligations", headers=ws.headers("VIEWER"))
    flags = {o["id"]: (o["addable"], o["reason_not_addable"]) for o in listing.json()["obligations"]}
    assert flags[str(pending.id)] == (False, "Awaiting quote check")
    assert flags[str(obls[0].id)][0] is True
    assert len(listing.json()["obligations"][0]["already_in_register_ids"]) == 1


@pytest.mark.asyncio
async def test_item_keeps_snapshot_after_obligation_is_deleted(client):
    ws = await workspace()
    rid, items, doc, version, pages, obls = await one_item(client, ws)
    item = items[0]
    quote = obls[0].supporting_text
    assert item["source"]["quote"] == quote
    assert item["source"]["file_sha256"] == version.file_sha256
    assert item["source"]["version_id"] == str(version.id)
    assert item["source"]["page_number"] in (1, 2)
    assert item["source"]["page_link"].startswith(f"/?doc={doc.id}&version={version.id}&page=")
    assert item["lock_version"] == 1 and item["status"] == "NOT_STARTED"

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Obligation).where(Obligation.id == obls[0].id))
        await db.commit()
    detail = await client.get(f"{base(ws)}/items/{item['id']}", headers=ws.headers("VIEWER"))
    assert detail.status_code == 200
    got = detail.json()["item"]
    assert got["obligation_id"] is None or got["obligation_id"] == str(obls[0].id)  # SQLite does not enforce SET NULL
    assert got["source"]["quote"] == quote and got["obligation_title"] == "Duty 0"


@pytest.mark.asyncio
async def test_reanalysis_with_register_item_does_not_fail(client):
    ws = await workspace()
    rid, items, doc, version, pages, obls = await one_item(client, ws)
    item_id = items[0]["id"]
    quote = obls[0].supporting_text

    def pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    from backend.app.modules.analysis.service import AnalysisService
    event.listen(async_engine.sync_engine, "connect", pragma)
    await async_engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await AnalysisService.analyze_document_version(db=db, document_id=doc.id, provider_name="mock")
    finally:
        event.remove(async_engine.sync_engine, "connect", pragma)
        await async_engine.dispose()
    async with AsyncSessionLocal() as db:
        item = await db.get(ComplianceItem, uuid.UUID(item_id))
        assert item is not None and item.source_quote == quote and item.obligation_id is None


@pytest.mark.asyncio
async def test_duplicate_add_skipped_second_register_works(client):
    ws = await workspace()
    rid, items, doc, version, pages, obls = await one_item(client, ws, n=2)
    again = await add_items(client, ws, rid, doc)
    assert again.json()["items"] == []
    assert {s["reason"] for s in again.json()["skipped"]} == {"Already in this register"}
    rid2 = await new_register(client, ws, "Second")
    second = await add_items(client, ws, rid2, doc)
    assert len(second.json()["items"]) == 2
    # a new register straight from a circular
    doc2, *_ = await circular(n_verified=1)
    fresh = await client.post(f"{base(ws)}/registers/from-document", headers=ws.headers("ORG_ADMIN"), json={"document_id": str(doc2.id)})
    assert fresh.status_code == 201
    assert fresh.json()["register"]["title"].startswith(doc2.reference_number)
    assert fresh.json()["register"]["item_counts"]["total"] == 1


@pytest.mark.asyncio
async def test_client_status_is_ignored_on_create(client):
    ws = await workspace()
    rid = await new_register(client, ws)
    doc, version, pages, obls = await circular(n_verified=1)
    made = await client.post(f"{base(ws)}/items", headers=ws.headers("COMPLIANCE_OFFICER"),
                             json={"register_id": rid, "obligation_id": str(obls[0].id), "status": "COMPLIANT"})
    assert made.status_code == 201 and made.json()["status"] == "NOT_STARTED"
    t = await client.post(f"{base(ws)}/tasks", headers=ws.headers("COMPLIANCE_OFFICER"), json={
        "compliance_item_id": made.json()["id"], "title": "T", "due_date": "2030-01-01", "status": "APPROVED"})
    assert t.status_code == 201 and t.json()["task"]["status"] == "PENDING"


# ---------------------------------------------------------------------------
# 6: overdue
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overdue_is_derived_in_dhaka_time(client, monkeypatch):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws, n=3)
    today = date(2026, 6, 15)
    monkeypatch.setattr(rules, "today_dhaka", lambda: today)
    yesterday = str(today - timedelta(days=1))
    h = ws.headers("COMPLIANCE_OFFICER")
    ids = [i["id"] for i in items]

    for iid in ids[:2]:
        await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"internal_deadline": yesterday})
        await client.post(f"{base(ws)}/items/{iid}/status", headers=h, json={"to": "IN_PROGRESS"})
    r = await client.get(f"{base(ws)}/items", headers=h)
    by = {i["id"]: i for i in r.json()["items"]}
    assert by[ids[0]]["display_status"] == "OVERDUE" and by[ids[0]]["is_overdue"] and by[ids[0]]["days_left"] == -1
    assert r.json()["as_of"] == str(today)

    # waiting for sign-off is never overdue: set the second one up for it
    await task_for(client, ws, ids[1], assignee="ANALYST")
    t = (await client.get(f"{base(ws)}/tasks", headers=h, params={"item_id": ids[1]})).json()["tasks"][0]
    up = await upload(client, ws, t["id"])
    assert up.status_code == 201
    rev = await client.post(f"{base(ws)}/tasks/{t['id']}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED"})
    assert rev.status_code == 201
    sent = await client.post(f"{base(ws)}/items/{ids[1]}/status", headers=h, json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200 and sent.json()["display_status"] == "EVIDENCE_SUBMITTED" and not sent.json()["is_overdue"]

    only = await client.get(f"{base(ws)}/items", headers=h, params={"overdue": "true"})
    assert [i["id"] for i in only.json()["items"]] == [ids[0]]
    not_over = await client.get(f"{base(ws)}/items", headers=h, params={"display_status": "NOT_STARTED"})
    assert [i["id"] for i in not_over.json()["items"]] == [ids[2]]

    # regulatory deadline is used when there is no internal one; clearing the internal one flips it back
    await client.patch(f"{base(ws)}/items/{ids[0]}", headers=h, json={"internal_deadline": None})
    async with AsyncSessionLocal() as db:
        row = await db.get(ComplianceItem, uuid.UUID(ids[2]))
        row.regulatory_deadline = today - timedelta(days=3)
        await db.commit()
    got = (await client.get(f"{base(ws)}/items/{ids[2]}", headers=h)).json()["item"]
    assert got["display_status"] == "OVERDUE" and got["effective_deadline"] == str(today - timedelta(days=3))
    first = (await client.get(f"{base(ws)}/items/{ids[0]}", headers=h)).json()["item"]
    assert first["display_status"] == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# 7: state machine, automatic moves
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_item_and_task_state_machine(client):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws, n=2)
    iid = items[0]["id"]
    off = ws.headers("COMPLIANCE_OFFICER")
    head = ws.headers("COMPLIANCE_HEAD")

    # forbidden jumps
    bad = await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    assert bad.status_code == 409 and "cannot move" in bad.json()["detail"]
    assert (await client.post(f"{base(ws)}/items/{iid}/status", headers=head, json={"to": "NOT_STARTED"})).status_code == 409
    assert (await client.post(f"{base(ws)}/items/{iid}/reopen", headers=head, json={"reason": "x"})).status_code == 409

    # a task makes the item IN_PROGRESS; evidence makes the task SUBMITTED
    t = (await task_for(client, ws, iid, assignee="ANALYST"))
    assert t["item"]["status"] == "IN_PROGRESS" and t["task"]["status"] == "PENDING"
    tid = t["task"]["id"]
    # send for sign-off needs approved tasks and evidence
    early = await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    assert early.status_code == 409 and early.json()["detail"] == "Approve all tasks first."
    up = await upload(client, ws, tid)
    assert up.status_code == 201 and up.json()["task"]["status"] == "SUBMITTED"
    # another file, then withdraw both: task goes back to IN_PROGRESS
    ev1 = up.json()["evidence"]["id"]
    up2 = await upload(client, ws, tid, content=PDF + b" two")
    ev2 = up2.json()["evidence"]["id"]
    w1 = await client.post(f"{base(ws)}/tasks/{tid}/evidence/{ev1}/withdraw", headers=ws.headers("ANALYST"), json={"reason": "wrong file"})
    assert w1.status_code == 200 and w1.json()["task"]["status"] == "SUBMITTED"
    w2 = await client.post(f"{base(ws)}/tasks/{tid}/evidence/{ev2}/withdraw", headers=ws.headers("ANALYST"), json={"reason": "wrong file"})
    assert w2.json()["task"]["status"] == "IN_PROGRESS" and w2.json()["task"]["evidence_count"] == 0
    # withdrawn evidence is only withdrawable by its uploader
    assert (await client.post(f"{base(ws)}/tasks/{tid}/evidence/{ev1}/withdraw", headers=ws.headers("ANALYST"), json={"reason": "again"})).status_code == 409

    up3 = await upload(client, ws, tid, content=PDF + b" three")
    assert up3.json()["task"]["status"] == "SUBMITTED"
    # review: changes requested -> IN_PROGRESS, needs a comment
    need = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "CHANGES_REQUESTED"})
    assert need.status_code == 400
    ch = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "CHANGES_REQUESTED", "comments": "Add the signed page."})
    assert ch.status_code == 201 and ch.json()["task"]["status"] == "IN_PROGRESS"
    # reviewing a task that is not submitted is a conflict
    assert (await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED"})).status_code == 409
    await upload(client, ws, tid, content=PDF + b" four")
    rej = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "REJECTED", "comments": "Not acceptable."})
    assert rej.json()["task"]["status"] == "REJECTED"
    await upload(client, ws, tid, content=PDF + b" five")  # REJECTED -> SUBMITTED again
    ok = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED", "comments": ""})
    assert ok.status_code == 201 and ok.json()["task"]["status"] == "APPROVED"
    assert ok.json()["review"]["evidence_ids"]

    # evidence on an approved task is refused
    assert (await upload(client, ws, tid, content=PDF + b" six")).status_code == 409
    # approved task cannot be cancelled
    assert (await client.post(f"{base(ws)}/tasks/{tid}/cancel", headers=off, json={"reason": "x"})).status_code == 409

    # send for sign-off, then reject it: item goes back to IN_PROGRESS
    sent = await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200 and sent.json()["status"] == "EVIDENCE_SUBMITTED"
    assert sent.json()["submitted_for_signoff_by"]["id"] == str(ws.users["COMPLIANCE_OFFICER"].id)
    # adding a task pulls it back (automatic)
    t2 = await task_for(client, ws, iid, assignee="ANALYST")
    assert t2["item"]["status"] == "IN_PROGRESS" and t2["item"]["submitted_for_signoff_at"] is None
    # cancel the new task and send for sign-off again
    c = await client.post(f"{base(ws)}/tasks/{t2['task']['id']}/cancel", headers=off, json={"reason": "Not needed"})
    assert c.status_code == 200 and c.json()["task"]["status"] == "CANCELLED" and c.json()["task"]["cancelled_reason"] == "Not needed"
    sent = await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200
    back = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER:2"), json={"decision": "REJECTED"})
    assert back.status_code == 400
    back = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER:2"), json={"decision": "REJECTED", "comments": "Not yet."})
    assert back.status_code == 201 and back.json()["item"]["status"] == "IN_PROGRESS" and back.json()["review"]["decision"] == "REJECTED"
    await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    done = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER:2"), json={"decision": "APPROVED", "comments": "Good."})
    assert done.status_code == 201 and done.json()["item"]["status"] == "COMPLIANT"
    assert done.json()["item"]["signed_off_by"]["id"] == str(ws.users["REVIEWER:2"].id)

    # closed items take no new tasks or evidence; reopen needs a head
    closed = await client.post(f"{base(ws)}/tasks", headers=off, json={"compliance_item_id": iid, "title": "T", "due_date": "2030-01-01"})
    assert closed.status_code == 400 and closed.json()["detail"] == "Reopen it first."
    assert (await client.post(f"{base(ws)}/items/{iid}/reopen", headers=off, json={"reason": "x"})).status_code == 403
    re = await client.post(f"{base(ws)}/items/{iid}/reopen", headers=head, json={"reason": "New facts"})
    assert re.status_code == 200 and re.json()["status"] == "IN_PROGRESS" and re.json()["signed_off_at"] is None

    # exemption
    other = items[1]["id"]
    assert (await client.post(f"{base(ws)}/items/{other}/status", headers=head, json={"to": "EXEMPTED"})).status_code == 400
    assert (await client.post(f"{base(ws)}/items/{other}/status", headers=off, json={"to": "EXEMPTED", "reason": "n/a"})).status_code == 403
    ex = await client.post(f"{base(ws)}/items/{other}/status", headers=head, json={"to": "EXEMPTED", "reason": "Replaced by BRPD 9/2026"})
    assert ex.json()["status"] == "EXEMPTED" and ex.json()["exemption_reason"] == "Replaced by BRPD 9/2026"
    un = await client.post(f"{base(ws)}/items/{other}/status", headers=head, json={"to": "NOT_STARTED"})
    assert un.json()["status"] == "NOT_STARTED" and un.json()["exemption_reason"] is None


# ---------------------------------------------------------------------------
# 8: nobody reviews their own work
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_self_review_is_blocked_for_everyone(client):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    iid = items[0]["id"]
    # the task is assigned to the REVIEWER, who is therefore not allowed to review it
    t = await task_for(client, ws, iid, assignee="REVIEWER")
    tid = t["task"]["id"]
    up = await upload(client, ws, tid, role="COMPLIANCE_HEAD")  # the head uploads
    assert up.status_code == 201
    for role in ("COMPLIANCE_HEAD", "REVIEWER"):
        r = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers(role), json={"decision": "APPROVED"})
        assert r.status_code == 403, role
    assert "uploaded" in (await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("COMPLIANCE_HEAD"), json={"decision": "APPROVED"})).json()["detail"]
    # an admin who uploaded nothing may decide
    ok = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("ORG_ADMIN"), json={"decision": "APPROVED"})
    assert ok.status_code == 201

    # the head sends the item for sign-off, so the head cannot sign it off; nor can the uploader (head again)
    sent = await client.post(f"{base(ws)}/items/{iid}/status", headers=ws.headers("COMPLIANCE_HEAD"), json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200
    for role in ("COMPLIANCE_HEAD",):
        r = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers(role), json={"decision": "APPROVED"})
        assert r.status_code == 403 and r.json()["detail"] == "You cannot sign off an item you worked on."
    # an uploader on any task cannot sign off even if somebody else sent it: ORG_ADMIN uploads on a new task
    t2 = await task_for(client, ws, iid, role="COMPLIANCE_HEAD")
    up2 = await upload(client, ws, t2["task"]["id"], role="ORG_ADMIN")
    assert up2.status_code == 201
    ap = await client.post(f"{base(ws)}/tasks/{t2['task']['id']}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED"})
    assert ap.status_code == 201
    sent = await client.post(f"{base(ws)}/items/{iid}/status", headers=ws.headers("COMPLIANCE_OFFICER"), json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200
    blocked = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("ORG_ADMIN"), json={"decision": "APPROVED"})
    assert blocked.status_code == 403
    fine = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED"})
    assert fine.status_code == 201 and fine.json()["item"]["status"] == "COMPLIANT"


# ---------------------------------------------------------------------------
# 9: permission matrix
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("ORG_ADMIN", True), ("COMPLIANCE_HEAD", True), ("COMPLIANCE_OFFICER", True),
    ("DEPARTMENT_LEAD", False), ("REVIEWER", False), ("ANALYST", False), ("AUDITOR", False), ("VIEWER", False),
])
async def test_matrix_registers_and_adding(client, role, allowed):
    ws = await workspace()
    created = await client.post(f"{base(ws)}/registers", headers=ws.headers(role), json={"title": "R"})
    assert (created.status_code == 201) is allowed
    assert created.status_code in (201, 403)
    rid = await new_register(client, ws)
    doc, *_ = await circular(n_verified=1)
    add = await add_items(client, ws, rid, doc, role=role)
    assert (add.status_code == 201) is allowed
    patch = await client.patch(f"{base(ws)}/registers/{rid}", headers=ws.headers(role), json={"title": "New"})
    assert (patch.status_code == 200) is allowed
    # everybody can read
    assert (await client.get(f"{base(ws)}/registers", headers=ws.headers(role))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role,own,other", [
    ("ORG_ADMIN", True, True), ("COMPLIANCE_HEAD", True, True), ("COMPLIANCE_OFFICER", True, True),
    ("DEPARTMENT_LEAD", True, False), ("DEPARTMENT_LEAD:B", False, True),
    ("REVIEWER", False, False), ("ANALYST", False, False), ("AUDITOR", False, False), ("VIEWER", False, False),
])
async def test_matrix_item_edit_and_tasks_by_department(client, role, own, other):
    """`own` = the item is in department A; `other` = the item is in department B."""
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws, n=2)
    h = ws.headers(role)
    off = ws.headers("COMPLIANCE_OFFICER")
    a_item, b_item = items[0]["id"], items[1]["id"]
    await client.patch(f"{base(ws)}/items/{a_item}", headers=off, json={"department_id": ws.departments["A"]})
    await client.patch(f"{base(ws)}/items/{b_item}", headers=off, json={"department_id": ws.departments["B"]})
    for iid, expected in ((a_item, own), (b_item, other)):
        edit = await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"notes": "hello"})
        assert (edit.status_code == 200) is expected, (role, iid, edit.text)
        task = await client.post(f"{base(ws)}/tasks", headers=h, json={"compliance_item_id": iid, "title": "T", "due_date": "2030-01-01"})
        assert (task.status_code == 201) is expected, (role, iid, task.text)
        start = await client.post(f"{base(ws)}/items/{iid}/status", headers=h, json={"to": "IN_PROGRESS"})
        # the task above already started it for allowed roles; refused roles stay refused
        assert (start.status_code in (200, 409)) if expected else start.status_code == 403


@pytest.mark.asyncio
async def test_matrix_department_lead_limits_and_analyst_lead(client):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws, n=2)
    off = ws.headers("COMPLIANCE_OFFICER")
    lead = ws.headers("DEPARTMENT_LEAD")
    iid = items[0]["id"]
    await client.patch(f"{base(ws)}/items/{iid}", headers=off, json={"department_id": ws.departments["A"]})
    # cannot move it to another department or pick a lead from another department
    assert (await client.patch(f"{base(ws)}/items/{iid}", headers=lead, json={"department_id": ws.departments["B"]})).status_code == 403
    assert (await client.patch(f"{base(ws)}/items/{iid}", headers=lead, json={"assigned_lead_id": str(ws.users["DEPARTMENT_LEAD:B"].id)})).status_code == 403
    ok = await client.patch(f"{base(ws)}/items/{iid}", headers=lead, json={"assigned_lead_id": str(ws.users["ANALYST"].id)})
    assert ok.status_code == 200 and ok.json()["assigned_lead"]["id"] == str(ws.users["ANALYST"].id)
    # the analyst is now the item lead: may add tasks, start, upload; not edit the department
    analyst = ws.headers("ANALYST")
    t = await client.post(f"{base(ws)}/tasks", headers=analyst, json={"compliance_item_id": iid, "title": "Mine", "due_date": "2030-01-01"})
    assert t.status_code == 201
    other_item = items[1]["id"]
    assert (await client.post(f"{base(ws)}/tasks", headers=analyst, json={"compliance_item_id": other_item, "title": "No", "due_date": "2030-01-01"})).status_code == 403
    assert (await client.patch(f"{base(ws)}/items/{iid}", headers=analyst, json={"notes": "x"})).status_code == 403
    # an analyst who is only the assignee may change status and upload, but nothing else
    tid = (await task_for(client, ws, other_item, assignee="ANALYST"))["task"]["id"]
    assert (await client.patch(f"{base(ws)}/tasks/{tid}", headers=analyst, json={"status": "IN_PROGRESS"})).status_code == 200
    assert (await client.patch(f"{base(ws)}/tasks/{tid}", headers=analyst, json={"title": "Renamed"})).status_code == 403
    assert (await upload(client, ws, tid, role="ANALYST")).status_code == 201
    # an analyst not on a task cannot upload, a viewer cannot
    other_task = (await task_for(client, ws, other_item))["task"]["id"]
    assert (await upload(client, ws, other_task, role="ANALYST")).status_code == 403
    assert (await upload(client, ws, other_task, role="VIEWER")).status_code == 403
    assert (await upload(client, ws, other_task, role="AUDITOR")).status_code == 403
    # a department lead of the item's department may review its evidence, but cannot sign off the item
    await upload(client, ws, other_task, role="COMPLIANCE_OFFICER")
    b_lead = await client.post(f"{base(ws)}/tasks/{other_task}/reviews", headers=ws.headers("DEPARTMENT_LEAD:B"), json={"decision": "APPROVED"})
    assert b_lead.status_code == 403
    assert (await client.post(f"{base(ws)}/items/{other_item}/signoff", headers=lead, json={"decision": "APPROVED"})).status_code == 403
    await client.patch(f"{base(ws)}/items/{other_item}", headers=off, json={"department_id": ws.departments["A"]})
    a_lead = await client.post(f"{base(ws)}/tasks/{other_task}/reviews", headers=lead, json={"decision": "APPROVED"})
    assert a_lead.status_code == 201
    # exempt, reopen and acknowledging
    assert (await client.post(f"{base(ws)}/items/{iid}/status", headers=ws.headers("COMPLIANCE_OFFICER"), json={"to": "EXEMPTED", "reason": "x"})).status_code == 403
    assert (await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=lead, json={"note": "x"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role,can", [
    ("ORG_ADMIN", True), ("COMPLIANCE_HEAD", True), ("COMPLIANCE_OFFICER", True), ("DEPARTMENT_LEAD", True),
    ("REVIEWER", True), ("ANALYST", True), ("AUDITOR", True), ("VIEWER", False),
])
async def test_matrix_download_audit_report(client, role, can):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    up = await upload(client, ws, t["task"]["id"])
    eid = up.json()["evidence"]["id"]
    dl = await client.get(f"{base(ws)}/tasks/{t['task']['id']}/evidence/{eid}/download", headers=ws.headers(role))
    assert (dl.status_code == 200) is can
    whole_log = role in ("ORG_ADMIN", "COMPLIANCE_HEAD", "REVIEWER", "AUDITOR")
    log = await client.get(f"{base(ws)}/audit", headers=ws.headers(role))
    assert (log.status_code == 200) is whole_log
    history = await client.get(f"{base(ws)}/audit", headers=ws.headers(role), params={"entity_id": items[0]["id"]})
    assert history.status_code == 200
    assert (await client.get(f"{base(ws)}/report", headers=ws.headers(role))).status_code == 200


@pytest.mark.asyncio
async def test_matrix_members_departments_and_task_status(client):
    ws = await workspace()
    newbie, _ = await make_user()
    for role, ok in (("ORG_ADMIN", True), ("COMPLIANCE_HEAD", True), ("COMPLIANCE_OFFICER", False), ("VIEWER", False)):
        u, _t = await make_user()
        r = await client.post(f"/api/v1/organizations/{ws.org_id}/members/by-email", headers=ws.headers(role),
                              json={"email": u.email, "role": "ANALYST"})
        assert (r.status_code == 201) is ok, role
        d = await client.post(f"/api/v1/organizations/{ws.org_id}/departments", headers=ws.headers(role), json={"name": f"Dept {role}"})
        assert (d.status_code == 201) is ok, role
    # the head cannot hand out ORG_ADMIN nor change an admin
    r = await client.post(f"/api/v1/organizations/{ws.org_id}/members/by-email", headers=ws.headers("COMPLIANCE_HEAD"),
                          json={"email": newbie.email, "role": "ORG_ADMIN"})
    assert r.status_code == 403
    admin_member = ws.members["ORG_ADMIN"]
    assert (await client.patch(f"/api/v1/organizations/{ws.org_id}/members/{admin_member}", headers=ws.headers("COMPLIANCE_HEAD"), json={"role": "VIEWER"})).status_code == 403
    # the last administrator cannot be demoted
    last = await client.patch(f"/api/v1/organizations/{ws.org_id}/members/{admin_member}", headers=ws.headers("ORG_ADMIN"), json={"role": "VIEWER"})
    assert last.status_code == 400
    # unknown email, duplicate, department rules
    nope = await client.post(f"/api/v1/organizations/{ws.org_id}/members/by-email", headers=ws.headers("ORG_ADMIN"), json={"email": "nobody@nowhere.test", "role": "VIEWER"})
    assert nope.status_code == 404 and nope.json()["detail"].startswith("No RegWatch account")
    dup = await client.post(f"/api/v1/organizations/{ws.org_id}/members/by-email", headers=ws.headers("ORG_ADMIN"), json={"email": ws.users["VIEWER"].email, "role": "VIEWER"})
    assert dup.status_code == 400
    clash = await client.post(f"/api/v1/organizations/{ws.org_id}/departments", headers=ws.headers("ORG_ADMIN"), json={"name": "Dept ORG_ADMIN"})
    assert clash.status_code == 409
    # delete: only admin, and not while items use it
    rid, items, *_ = await one_item(client, ws)
    await client.patch(f"{base(ws)}/items/{items[0]['id']}", headers=ws.headers("COMPLIANCE_OFFICER"), json={"department_id": ws.departments["A"]})
    dpath = f"/api/v1/organizations/{ws.org_id}/departments/{ws.departments['A']}"
    assert (await client.delete(dpath, headers=ws.headers("COMPLIANCE_HEAD"))).status_code == 403
    blocked = await client.delete(dpath, headers=ws.headers("ORG_ADMIN"))
    assert blocked.status_code == 409 and blocked.json()["detail"] == "Move its items first."
    assert (await client.delete(f"/api/v1/organizations/{ws.org_id}/departments/{ws.departments['B']}", headers=ws.headers("ORG_ADMIN"))).status_code == 204
    # me and mine
    me = await client.get(f"/api/v1/organizations/{ws.org_id}/me", headers=ws.headers("REVIEWER"))
    assert me.json()["membership"]["role"] == "REVIEWER" and me.json()["permissions"]["sign_off_items"] is True
    assert me.json()["permissions"]["manage_members"] is False
    mine = await client.get("/api/v1/organizations/mine", headers=ws.headers("REVIEWER"))
    assert [o["id"] for o in mine.json()] == [ws.org_id] and mine.json()[0]["role"] == "REVIEWER"
    members = await client.get(f"/api/v1/organizations/{ws.org_id}/members", headers=ws.headers("VIEWER"))
    assert members.json()[0]["user"]["email"]


# ---------------------------------------------------------------------------
# 10: lock versions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_lock_version_returns_conflict_with_current(client):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    iid = items[0]["id"]
    h = ws.headers("COMPLIANCE_OFFICER")
    first = await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"notes": "one", "lock_version": 1})
    assert first.status_code == 200 and first.json()["lock_version"] == 2
    stale = await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"notes": "two", "lock_version": 1})
    assert stale.status_code == 409
    body = stale.json()
    assert body["current"]["id"] == iid and body["current"]["notes"] == "one" and body["current"]["lock_version"] == 2
    # an unchanged save does not bump
    same = await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"notes": "one", "lock_version": 2})
    assert same.json()["lock_version"] == 2
    tid = (await task_for(client, ws, iid))["task"]["id"]
    ok = await client.patch(f"{base(ws)}/tasks/{tid}", headers=h, json={"priority": "LOW", "lock_version": 1})
    assert ok.status_code == 200 and ok.json()["task"]["lock_version"] == 2
    bad = await client.patch(f"{base(ws)}/tasks/{tid}", headers=h, json={"priority": "HIGH", "lock_version": 1})
    assert bad.status_code == 409 and bad.json()["current"]["priority"] == "LOW"


# ---------------------------------------------------------------------------
# 11: source changes
# ---------------------------------------------------------------------------
async def relate(source_doc, target_doc, rel_type, status="VERIFIED"):
    async with AsyncSessionLocal() as db:
        db.add(DocumentRelationship(
            source_document_id=source_doc.id, target_document_id=target_doc.id, relationship_type=rel_type,
            supporting_quote="This circular changes the other.", verification_status=status, detection_method="AI_INFERRED",
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_source_change_flag_and_acknowledge(client):
    ws = await workspace()
    rid, items, doc, version, pages, obls = await one_item(client, ws)
    iid = items[0]["id"]
    h = ws.headers("COMPLIANCE_OFFICER")
    get = lambda: client.get(f"{base(ws)}/items/{iid}", headers=h)  # noqa: E731
    assert (await get()).json()["item"]["source_change"] is None

    newer, *_ = await circular(n_verified=0)
    # a link still awaiting review does not flag
    await relate(newer, doc, "AMENDS", status="PENDING_REVIEW")
    assert (await get()).json()["item"]["source_change"] is None
    # a link stated by a private upload does not flag
    owner, _t = await make_user()
    private, *_ = await circular(n_verified=0)
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, private.id)
        d.owner_user_id = owner.id
        await db.commit()
    await relate(private, doc, "REPEALS")
    assert (await get()).json()["item"]["source_change"] is None

    await relate(newer, doc, "AMENDS")
    change = (await get()).json()["item"]["source_change"]
    assert change["kind"] == "AMENDED" and change["by"]["id"] == str(newer.id) and "amends" in change["detail"]
    assert (await client.get(f"{base(ws)}/registers/{rid}", headers=h)).json()["item_counts"]["flagged"] == 1
    flagged = await client.get(f"{base(ws)}/items", headers=h, params={"flagged": "true"})
    assert flagged.json()["total"] == 1

    # acknowledging needs a note and a role; it clears the flag; the item itself never changed
    assert (await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=ws.headers("VIEWER"), json={"note": "ok"})).status_code == 403
    assert (await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=h, json={"note": ""})).status_code == 422
    acked = await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=h, json={"note": "Reporting form only."})
    assert acked.status_code == 200 and acked.json()["source_change"] is None
    assert acked.json()["status"] == "NOT_STARTED" and acked.json()["source"]["quote"] == obls[0].supporting_text
    assert (await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=h, json={"note": "again"})).status_code == 409

    # a repeal flags it again
    await relate(newer, doc, "REPEALS")
    again = (await get()).json()["item"]["source_change"]
    assert again["kind"] == "REPEALED"
    await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=h, json={"note": "seen"})

    # a new current version flags NEW_VERSION
    async with AsyncSessionLocal() as db:
        # clear the links so only the version change remains
        await db.execute(delete(DocumentRelationship).where(DocumentRelationship.target_document_id == doc.id))
        await db.commit()
    if (await get()).json()["item"]["source_change"]:
        await client.post(f"{base(ws)}/items/{iid}/acknowledge-source-change", headers=h, json={"note": "links gone"})
    async with AsyncSessionLocal() as db:
        v2 = DocumentVersion(document_id=doc.id, version_number=2, file_sha256="d" * 64, file_size_bytes=1, storage_path="x", page_count=1)
        db.add(v2)
        await db.flush()
        d = await db.get(Document, doc.id)
        d.current_version_id = v2.id
        await db.commit()
    nv = (await get()).json()["item"]
    assert nv["source_change"]["kind"] == "NEW_VERSION"
    assert nv["source"]["version_id"] == str(version.id)  # the item keeps the version it was built from

    # adding from an already-amended circular does not flag (the user was warned at add time)
    amended, _v, _p, aobls = await circular(n_verified=1)
    await relate(newer, amended, "AMENDS")
    rid2 = await new_register(client, ws, "Amended source")
    added = await add_items(client, ws, rid2, amended)
    assert added.json()["items"][0]["source_change"] is None
    assert added.json()["items"][0]["source"]["in_force_status"] == "AMENDED"
    listing = await client.get(f"{base(ws)}/documents/{amended.id}/addable-obligations", headers=h)
    assert listing.json()["document"]["in_force_status"] == "AMENDED"
    assert listing.json()["document"]["in_force_by"]["id"] == str(newer.id)


# ---------------------------------------------------------------------------
# 12: audit
# ---------------------------------------------------------------------------
async def audit_rows(org_id, action=None):
    async with AsyncSessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.organization_id == uuid.UUID(org_id))
        if action:
            q = q.where(AuditEvent.action == action)
        return list((await db.execute(q.order_by(AuditEvent.created_at))).scalars().all())


@pytest.mark.asyncio
async def test_every_write_is_audited_once_per_record(client):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws, n=2)
    assert len(await audit_rows(ws.org_id, "ITEM_ADDED")) == 2
    assert len(await audit_rows(ws.org_id, "REGISTER_CREATED")) == 1
    iid = items[0]["id"]
    h = ws.headers("COMPLIANCE_OFFICER")

    await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"department_id": ws.departments["A"], "notes": "n"})
    upd = await audit_rows(ws.org_id, "ITEM_UPDATED")
    assert len(upd) == 1 and set(upd[0].after_state) == {"department_id", "notes"} and upd[0].before_state["notes"] is None
    assert str(upd[0].actor_user_id) == str(ws.users["COMPLIANCE_OFFICER"].id)
    # an unchanged save writes nothing
    await client.patch(f"{base(ws)}/items/{iid}", headers=h, json={"notes": "n"})
    assert len(await audit_rows(ws.org_id, "ITEM_UPDATED")) == 1

    t = await task_for(client, ws, iid, assignee="ANALYST")
    assert len(await audit_rows(ws.org_id, "TASK_CREATED")) == 1
    auto = await audit_rows(ws.org_id, "ITEM_STATUS_CHANGED")
    assert len(auto) == 1 and auto[0].after_state["reason"].startswith("automatic:")
    tid = t["task"]["id"]
    up = await upload(client, ws, tid)
    assert len(await audit_rows(ws.org_id, "EVIDENCE_UPLOADED")) == 1
    assert len(await audit_rows(ws.org_id, "TASK_STATUS_CHANGED")) == 1
    await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"), json={"decision": "APPROVED"})
    assert len(await audit_rows(ws.org_id, "TASK_REVIEWED")) == 1
    await client.get(f"{base(ws)}/tasks/{tid}/evidence/{up.json()['evidence']['id']}/download", headers=h)
    assert len(await audit_rows(ws.org_id, "EVIDENCE_DOWNLOADED")) == 1
    await client.post(f"{base(ws)}/items/{iid}/status", headers=h, json={"to": "EVIDENCE_SUBMITTED"})
    await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER:2"), json={"decision": "APPROVED", "comments": "ok"})
    assert len(await audit_rows(ws.org_id, "ITEM_SIGNED_OFF")) == 1
    await client.post(f"{base(ws)}/items/{iid}/reopen", headers=ws.headers("COMPLIANCE_HEAD"), json={"reason": "again"})
    await client.get(f"{base(ws)}/report", headers=h)
    await client.get(f"{base(ws)}/report", headers=h, params={"format": "csv"})
    assert len(await audit_rows(ws.org_id, "REPORT_EXPORTED")) == 2
    await client.post(f"/api/v1/organizations/{ws.org_id}/departments", headers=ws.headers("ORG_ADMIN"), json={"name": "Treasury"})
    assert len(await audit_rows(ws.org_id, "DEPARTMENT_CREATED")) == 1
    newbie, _ = await make_user()
    await client.post(f"/api/v1/organizations/{ws.org_id}/members/by-email", headers=ws.headers("ORG_ADMIN"), json={"email": newbie.email, "role": "VIEWER"})
    assert len(await audit_rows(ws.org_id, "MEMBER_ADDED")) == 1

    # the log: whole-org for admin, item history (items + tasks + evidence) for anyone
    log = await client.get(f"{base(ws)}/audit", headers=ws.headers("ORG_ADMIN"), params={"limit": 5})
    assert len(log.json()["events"]) == 5 and log.json()["next_before"]
    page2 = await client.get(f"{base(ws)}/audit", headers=ws.headers("ORG_ADMIN"), params={"limit": 500, "before": log.json()["next_before"]})
    assert page2.status_code == 200 and page2.json()["events"]
    history = await client.get(f"{base(ws)}/audit", headers=ws.headers("VIEWER"), params={"entity_id": iid})
    kinds = {e["action"] for e in history.json()["events"]}
    assert {"ITEM_ADDED", "ITEM_UPDATED", "TASK_CREATED", "EVIDENCE_UPLOADED", "TASK_REVIEWED", "ITEM_SIGNED_OFF"} <= kinds
    assert history.json()["events"][0]["actor"]["email"]
    filtered = await client.get(f"{base(ws)}/audit", headers=ws.headers("AUDITOR"), params={"action": "ITEM_ADDED"})
    assert len(filtered.json()["events"]) == 2


# ---------------------------------------------------------------------------
# 13: report
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_json_and_csv(client, monkeypatch):
    ws = await workspace()
    today = date(2026, 6, 15)
    monkeypatch.setattr(rules, "today_dhaka", lambda: today)
    rid, items, *_ = await one_item(client, ws, n=4)
    h = ws.headers("COMPLIANCE_OFFICER")
    await client.patch(f"{base(ws)}/items/{items[0]['id']}", headers=h, json={"internal_deadline": str(today - timedelta(days=2)), "department_id": ws.departments["A"]})
    await client.post(f"{base(ws)}/items/{items[0]['id']}/status", headers=h, json={"to": "IN_PROGRESS"})
    await client.patch(f"{base(ws)}/items/{items[1]['id']}", headers=h, json={"internal_deadline": str(today + timedelta(days=5)), "department_id": ws.departments["A"]})
    await client.post(f"{base(ws)}/items/{items[2]['id']}/status", headers=ws.headers("COMPLIANCE_HEAD"), json={"to": "EXEMPTED", "reason": "n/a"})
    # a formula-looking circular title must be neutralised in the CSV
    async with AsyncSessionLocal() as db:
        row = await db.get(ComplianceItem, uuid.UUID(items[3]["id"]))
        row.obligation_title = "=HYPERLINK(\"http://x\")"
        row.source_quote = "বাংলা উদ্ধৃতি"
        await db.commit()

    rep = (await client.get(f"{base(ws)}/report", headers=ws.headers("VIEWER"))).json()
    assert rep["as_of"] == str(today) and rep["totals"]["total"] == 4
    assert rep["totals"]["overdue"] == 1 and rep["totals"]["exempted"] == 1 and rep["totals"]["not_started"] == 2
    assert rep["totals"]["open"] == 3
    assert len(rep["overdue_items"]) == 1 and len(rep["upcoming_items"]) == 1 and len(rep["items"]) == 4
    dept_a = [d for d in rep["by_department"] if d["department_id"] == ws.departments["A"]][0]
    assert dept_a["total"] == 2 and dept_a["overdue"] == 1
    none = [d for d in rep["by_department"] if d["department_id"] is None][0]
    assert none["total"] == 2 and none["exempted"] == 1
    assert rep["generated_by"]["email"] == ws.users["VIEWER"].email

    csv_resp = await client.get(f"{base(ws)}/report", headers=h, params={"format": "csv"})
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-disposition"] == f'attachment; filename="regwatch-report-{today.isoformat()}.csv"'
    raw = csv_resp.content
    assert raw.startswith("﻿".encode("utf-8"))
    text = raw.decode("utf-8-sig")
    lines = [l for l in text.split("\r\n") if l]
    assert lines[0].startswith("Register,Internal code,Obligation,Circular reference,Circular title,Page,Exact quote,File SHA-256,Department,Lead,Regulatory deadline,Internal deadline,Status (display),Days left,Open tasks,Evidence files,Signed off by,Signed off at,Source change")
    import csv as _csv, io as _io
    rows = list(_csv.reader(_io.StringIO(text)))
    assert len(rows) == 5
    assert any(r[2].startswith("'=HYPERLINK") for r in rows[1:])
    assert any("বাংলা" in r[6] for r in rows[1:])
    assert any(r[13] == "-2" for r in rows[1:])  # a negative number is not treated as a formula


# ---------------------------------------------------------------------------
# 14: evidence files
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evidence_validation_storage_and_download(client, monkeypatch):
    ws = await workspace()
    rid, items, *_ = await one_item(client, ws)
    iid = items[0]["id"]
    tid = (await task_for(client, ws, iid, assignee="ANALYST"))["task"]["id"]

    monkeypatch.setattr(settings, "EVIDENCE_MAX_BYTES", 100)
    big = await upload(client, ws, tid, content=b"%PDF-" + b"x" * 200)
    assert big.status_code == 413 and "larger than" in big.json()["detail"]
    monkeypatch.undo()

    assert (await upload(client, ws, tid, content=b"MZ not a pdf", name="x.exe")).status_code == 415
    fake = await upload(client, ws, tid, content=b"not really a pdf", name="fake.pdf")
    assert fake.status_code == 415 and fake.json()["detail"] == "Allowed files: PDF, PNG, JPG, DOCX, XLSX, CSV, TXT."
    assert (await upload(client, ws, tid, content=b"", name="empty.pdf")).status_code == 400
    assert (await upload(client, ws, tid, content=b"\xff\xfe\x00bad", name="bad.txt")).status_code == 415
    assert (await upload(client, ws, tid, content=b"\x89PNG\r\n\x1a\nrest", name="p.png")).status_code == 201
    assert (await upload(client, ws, tid, content="a,b\n১,২".encode("utf-8"), name="d.csv")).status_code == 201

    name = 'we"ird/..\\বাংলা report.pdf'
    up = await upload(client, ws, tid, content=PDF + b" named", name=name)
    assert up.status_code == 201
    ev = up.json()["evidence"]
    assert '"' not in ev["original_filename"] and "/" not in ev["original_filename"] and "\\" not in ev["original_filename"]
    assert ev["file_sha256"] == hashlib.sha256(PDF + b" named").hexdigest() and ev["mime_type"] == "application/pdf"
    assert "storage_path" not in ev
    async with AsyncSessionLocal() as db:
        row = await db.get(TaskEvidence, uuid.UUID(ev["id"]))
        assert f"evidence/{ws.org_id}/" in row.storage_path.replace("\\", "/")
        assert row.storage_path.endswith(".pdf")

    dl = await client.get(f"{base(ws)}/tasks/{tid}/evidence/{ev['id']}/download", headers=ws.headers("AUDITOR"))
    assert dl.status_code == 200 and dl.content == PDF + b" named"
    assert dl.headers["x-content-type-options"] == "nosniff"
    assert dl.headers["x-sha256-checksum"] == ev["file_sha256"]
    assert dl.headers["cache-control"] == "private, no-store"
    assert dl.headers["content-type"].startswith("application/pdf")
    cd = dl.headers["content-disposition"]
    assert cd.startswith("attachment; filename=\"") and "filename*=UTF-8''" in cd
    assert cd.count('"') == 2 and "\r" not in cd and "\n" not in cd

    # withdrawn evidence stays downloadable and is marked
    w = await client.post(f"{base(ws)}/tasks/{tid}/evidence/{ev['id']}/withdraw", headers=ws.headers("ANALYST"), json={"reason": "Wrong"})
    assert w.status_code == 200 and w.json()["evidence"]["withdrawn_at"]
    assert (await client.get(f"{base(ws)}/tasks/{tid}/evidence/{ev['id']}/download", headers=ws.headers("AUDITOR"))).status_code == 200
    listing = await client.get(f"{base(ws)}/tasks/{tid}/evidence", headers=ws.headers("VIEWER"))
    assert any(e["withdrawn_at"] for e in listing.json())
    # someone else cannot withdraw
    other = await upload(client, ws, tid, content=PDF + b" other")
    wrong = await client.post(f"{base(ws)}/tasks/{tid}/evidence/{other.json()['evidence']['id']}/withdraw", headers=ws.headers("COMPLIANCE_OFFICER"), json={"reason": "no"})
    assert wrong.status_code == 403
    assert (await client.post(f"{base(ws)}/tasks/{tid}/evidence/{other.json()['evidence']['id']}/withdraw", headers=ws.headers("ANALYST"), json={"reason": ""})).status_code == 422
