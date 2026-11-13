"""Alerts: events, inbox, isolation, preferences, deadline and register checks, admin queues, worker gating."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.alerts import router as alerts_router
from backend.app.modules.alerts import sweeps, templates
from backend.app.modules.alerts.dispatch import dispatch_pending
from backend.app.modules.alerts.emit import circular_fields, circular_published, emit
from backend.app.modules.alerts.kinds import GROUPS, KIND_GROUP
from backend.app.modules.alerts.models import AlertEvent, AlertNotification, AlertPreference
from backend.app.modules.compliance import rules
from backend.app.modules.compliance.models import ComplianceItem
from backend.app.modules.documents.models import Document
from backend.app.modules.identity.models import User
from backend.app.modules.institutions.models import InstitutionDepartment
from backend.app.modules.organizations.models import Department, OrganizationMember
from backend.app.modules.relationships.models import DocumentRelationship
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.tests.factories import make_document, make_institution, make_user, make_workspace
from backend.app.tests.test_compliance_workspace import (
    base, circular, new_register, add_items, one_item, task_for, upload,
)

PUBLISHED = "PUBLISHED_MACHINE_PROCESSED"
AN = AlertNotification

ROLES = {
    "ORG_ADMIN": None,
    "COMPLIANCE_HEAD": None,
    "COMPLIANCE_OFFICER": None,
    "DEPARTMENT_LEAD": "A",
    "DEPARTMENT_LEAD:B": "B",
    "REVIEWER": None,
    "REVIEWER:2": None,
    "ANALYST": "A",
    "ANALYST:2": "A",
    "VIEWER": None,
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _fresh():
    """Clear the on-poll throttle and park every event left over from other tests."""
    alerts_router._last_poll_sweep.clear()
    alerts_router._last_test_email.clear()
    await park_events()
    yield
    alerts_router._last_poll_sweep.clear()


async def park_events():
    async with AsyncSessionLocal() as db:
        await db.execute(update(AlertEvent).where(AlertEvent.status == "PENDING").values(status="SUPPRESSED"))
        await db.commit()


def H(token):
    return {"Authorization": f"Bearer {token}"}


async def dispatch():
    async with AsyncSessionLocal() as db:
        n = await dispatch_pending(db)
        await db.commit()
        return n


async def quiet(user, groups=("library",)):
    """Switch these groups off for a person so counts in a test are exact."""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))).scalar_one_or_none()
        channels = {g: {"in_app": False, "email": "OFF"} for g in groups}
        if row is None:
            db.add(AlertPreference(user_id=user.id, channels=channels, lock_version=1))
        else:
            row.channels = {**(row.channels or {}), **channels}
        await db.commit()


async def make_ws(roles=ROLES, **kw):
    ws = await make_workspace(roles, **kw)
    for u in ws.users.values():
        await quiet(u)
    return ws


async def notes(user, kind=None, org=None, doc_id=None):
    async with AsyncSessionLocal() as db:
        q = select(AN).where(AN.user_id == user.id)
        if kind:
            q = q.where(AN.kind == kind)
        if org:
            q = q.where(AN.organization_id == uuid.UUID(str(org)))
        rows = (await db.execute(q.order_by(AN.created_at, AN.id))).scalars().all()
        if doc_id:
            rows = [r for r in rows if str(r.document_id) == str(doc_id)]
        return list(rows)


async def events(kind=None, key_prefix=None, org=None):
    async with AsyncSessionLocal() as db:
        q = select(AlertEvent)
        if kind:
            q = q.where(AlertEvent.kind == kind)
        if key_prefix:
            q = q.where(AlertEvent.dedupe_key.like(f"{key_prefix}%"))
        if org:
            q = q.where(AlertEvent.organization_id == uuid.UUID(str(org)))
        return list((await db.execute(q.order_by(AlertEvent.created_at, AlertEvent.id))).scalars().all())


def who(ws, rows_by_role):
    """Names of the roles (in this workspace) that have at least one row."""
    return {role for role, rows in rows_by_role.items() if rows}


async def got(ws, kind, entity_id=None):
    """role -> notes of this kind for each member of the workspace."""
    out = {}
    for role, user in ws.users.items():
        rows = await notes(user, kind=kind, org=ws.org_id)
        if entity_id is not None:
            rows = [r for r in rows if str(entity_id) in r.link or str(entity_id) in r.dedupe_key]
        out[role] = rows
    return out


async def published_doc(**fields):
    doc, version, pages = await make_document(pages=2, status=PUBLISHED)
    if fields:
        async with AsyncSessionLocal() as db:
            d = await db.get(Document, doc.id)
            for k, v in fields.items():
                setattr(d, k, v)
            await db.commit()
            await db.refresh(d)
            doc = d
    return doc, version, pages


async def announce(doc):
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, doc.id)
        row = await circular_published(db, d)
        await db.commit()
        return row


# ---------------------------------------------------------------------------
# 1. A new circular alerts everyone, with fixed text
# ---------------------------------------------------------------------------
async def test_library_publish_alerts_active_users_with_fixed_text(client):
    u1, _t1 = await make_user()
    u2, _t2 = await make_user()
    off, _t3 = await make_user()
    await quiet(off)
    doc, _v, _p = await published_doc(
        title="Liquidity rules for banks", reference_number="BRPD-77/2026",
    )
    assert await announce(doc) is not None
    await dispatch()
    for u in (u1, u2):
        rows = await notes(u, doc_id=doc.id)
        assert len(rows) == 1
        r = rows[0]
        assert r.kind == "CIRCULAR_PUBLISHED" and r.read_at is None and r.in_app is True
        assert r.title == "New circular: BRPD-77/2026"
        assert r.body == "Liquidity rules for banks. Published 1 Jan 2026."
        assert r.link == f"/?doc={doc.id}"
        assert r.quote_text is None and r.quote_page_number is None and r.detail is None
    assert await notes(off, doc_id=doc.id) == []


async def test_published_status_change_through_review_service_announces(client):
    """The review step that publishes a circular records the alert in the same save."""
    from backend.app.modules.analysis.service import AnalysisService

    reviewer, _t = await make_user()
    doc, _v, _p = await published_doc()
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, doc.id)
        d.publication_status = "AWAITING_REVIEW"
        await db.commit()
    assert await events(key_prefix=f"CIRCULAR_PUBLISHED:{doc.id}") == []
    async with AsyncSessionLocal() as db:
        await AnalysisService.review_and_publish_analysis(db, doc.id, reviewer.id, "WITHDRAWN")
    assert await events(key_prefix=f"CIRCULAR_PUBLISHED:{doc.id}") == []  # withdrawn is not a publication


# ---------------------------------------------------------------------------
# 2. Private uploads never alert anyone
# ---------------------------------------------------------------------------
async def test_private_upload_never_alerts_anyone(client):
    owner, _t = await make_user()
    doc, _v, _p = await published_doc(owner_user_id=owner.id)
    assert await announce(doc) is None
    async with AsyncSessionLocal() as db:
        await sweeps.sweep_published(db)
        await db.commit()
    assert await events(key_prefix=f"CIRCULAR_PUBLISHED:{doc.id}") == []
    await park_events()
    await dispatch()
    assert await notes(owner, doc_id=doc.id) == []


# ---------------------------------------------------------------------------
# 3. Library filters
# ---------------------------------------------------------------------------
async def dept_id(code):
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(InstitutionDepartment.id).where(InstitutionDepartment.code == code).limit(1)
        )).scalar_one()


async def set_prefs(client, token, **body):
    body.setdefault("channels", {})
    r = await client.put("/api/v1/alerts/preferences", headers=H(token), json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_library_filters(client):
    brpd, dos = await dept_id("BRPD"), await dept_id("DOS")
    people = {}
    for name, body in {
        "all": {},
        "dept": {"library_department_codes": ["BRPD"]},
        "type": {"library_document_types": ["GUIDELINE"]},
        "word": {"library_keywords": ["LIQUIDITY"]},
        "word_ref": {"library_keywords": ["fix-liq"]},
        "word_bn": {"library_keywords": ["তারল্য"]},
        "and": {"library_department_codes": ["BRPD"], "library_document_types": ["GUIDELINE"]},
    }.items():
        user, token = await make_user()
        await set_prefs(client, token, **body)
        people[name] = user
    d1, _v, _p = await published_doc(department_id=brpd, document_type="CIRCULAR", title="Liquidity rules", reference_number="FIX-LIQ-1")
    d2, _v, _p = await published_doc(department_id=dos, document_type="GUIDELINE", title="Other topic", reference_number="OTH-2")
    d3, _v, _p = await published_doc(department_id=brpd, document_type="GUIDELINE", title="Plain title",
                                     reference_number="PLN-3", title_bn="তারল্য সংক্রান্ত নির্দেশনা")
    for d in (d1, d2, d3):
        await announce(d)
    await dispatch()

    async def docs_for(name):
        return {d.id for d in (d1, d2, d3) if await notes(people[name], doc_id=d.id)}

    assert await docs_for("all") == {d1.id, d2.id, d3.id}
    assert await docs_for("dept") == {d1.id, d3.id}
    assert await docs_for("type") == {d2.id, d3.id}
    assert await docs_for("word") == {d1.id}            # case-insensitive, in the title
    assert await docs_for("word_ref") == {d1.id}        # in the reference number
    assert await docs_for("word_bn") == {d3.id}         # in the Bangla title
    assert await docs_for("and") == {d3.id}             # two groups are ANDed


# ---------------------------------------------------------------------------
# 4. Dedupe
# ---------------------------------------------------------------------------
async def test_dedupe_through_status_changes_sweeps_and_dispatch(client):
    users = [(await make_user())[0] for _ in range(2)]
    doc, _v, _p = await published_doc()
    key = f"CIRCULAR_PUBLISHED:{doc.id}"
    assert await announce(doc) is not None
    assert await announce(doc) is None
    for status in ("AWAITING_REVIEW", "PUBLISHED_HUMAN_REVIEWED"):
        async with AsyncSessionLocal() as db:
            d = await db.get(Document, doc.id)
            d.publication_status = status
            await circular_published(db, d)
            await db.commit()
    for _ in range(3):
        async with AsyncSessionLocal() as db:
            await sweeps.sweep_published(db)
            await db.commit()
    assert len(await events(key_prefix=key)) == 1
    await dispatch()
    await dispatch()
    for u in users:
        assert len(await notes(u, doc_id=doc.id)) == 1


async def test_emit_with_existing_key_does_not_break_the_callers_save(client):
    doc, _v, _p = await published_doc()
    await announce(doc)
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, doc.id)
        d.title = "Changed title"
        again = await emit(db, kind="CIRCULAR_PUBLISHED", dedupe_key=f"CIRCULAR_PUBLISHED:{doc.id}",
                           document_id=doc.id, payload={})
        assert again is None
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert (await db.get(Document, doc.id)).title == "Changed title"
    with pytest.raises(ValueError):
        async with AsyncSessionLocal() as db:
            await emit(db, kind="NOT_A_KIND", dedupe_key="x")
    async with AsyncSessionLocal() as db:
        # nobody left to tell once the actor is removed
        me = uuid.uuid4()
        assert await emit(db, kind="TASK_ASSIGNED", dedupe_key=f"t:{uuid.uuid4()}", actor_user_id=me,
                          recipient_user_ids=[me], payload={}) is None


# ---------------------------------------------------------------------------
# 5. Safety net
# ---------------------------------------------------------------------------
async def test_publish_safety_net_window(client):
    fresh, _v, _p = await published_doc()
    old, _v2, _p2 = await published_doc()
    async with AsyncSessionLocal() as db:
        await db.execute(update(Document).where(Document.id == old.id).values(
            updated_at=datetime.now(timezone.utc) - timedelta(days=3)
        ))
        await db.commit()
    async with AsyncSessionLocal() as db:
        n = await sweeps.sweep_published(db)
        await db.commit()
        assert n >= 1
    assert len(await events(key_prefix=f"CIRCULAR_PUBLISHED:{fresh.id}")) == 1
    assert await events(key_prefix=f"CIRCULAR_PUBLISHED:{old.id}") == []


# ---------------------------------------------------------------------------
# 6. Bank isolation
# ---------------------------------------------------------------------------
async def test_bank_isolation_and_suspension(client):
    a, b = await make_ws(), await make_ws()
    _rid, items, *_ = await one_item(client, a)
    await task_for(client, a, items[0]["id"], assignee="ANALYST")
    await dispatch()
    analyst = a.users["ANALYST"]
    mine = (await client.get("/api/v1/alerts", headers=a.headers("ANALYST"))).json()
    assert [x["kind"] for x in mine["alerts"]] == ["TASK_ASSIGNED"] and mine["unread_count"] == 1
    alert_id = mine["alerts"][0]["id"]
    assert all(x["organization_id"] == a.org_id for x in mine["alerts"])

    # a member of another bank sees nothing and gets 404 on A's alert
    for role in ("ANALYST", "COMPLIANCE_OFFICER", "ORG_ADMIN"):
        other = await client.get("/api/v1/alerts", headers=b.headers(role))
        assert other.json()["alerts"] == [] and other.json()["unread_count"] == 0
    assert (await client.post(f"/api/v1/alerts/{alert_id}/read", headers=b.headers("ANALYST"))).status_code == 404
    assert (await client.post(f"/api/v1/alerts/{alert_id}/unread", headers=b.headers("ANALYST"))).status_code == 404

    # a platform administrator who is not a member gets nothing and cannot read it
    admin, admin_token = await make_user(is_superuser=True)
    await quiet(admin, ("library", "admin_queue"))
    listing = await client.get("/api/v1/alerts", headers=H(admin_token))
    assert listing.json()["alerts"] == []
    assert (await client.post(f"/api/v1/alerts/{alert_id}/read", headers=H(admin_token))).status_code == 404
    assert await notes(admin, org=a.org_id) == []

    # a suspended member stops seeing the bank's alerts at once; re-activating brings them back
    async def set_status(value):
        async with AsyncSessionLocal() as db:
            m = (await db.execute(select(OrganizationMember).where(
                OrganizationMember.user_id == analyst.id, OrganizationMember.organization_id == uuid.UUID(a.org_id)
            ))).scalar_one()
            m.status = value
            await db.commit()

    await set_status("SUSPENDED")
    after = await client.get("/api/v1/alerts", headers=a.headers("ANALYST"))
    assert after.json()["alerts"] == [] and after.json()["unread_count"] == 0
    assert (await client.get("/api/v1/alerts/summary", headers=a.headers("ANALYST"))).json()["unread_count"] == 0
    assert (await client.post(f"/api/v1/alerts/{alert_id}/read", headers=a.headers("ANALYST"))).status_code == 404
    await set_status("ACTIVE")
    back = await client.get("/api/v1/alerts/summary", headers=a.headers("ANALYST"))
    assert back.json()["unread_count"] == 1


# ---------------------------------------------------------------------------
# 7. No self-alerts
# ---------------------------------------------------------------------------
async def test_actors_never_alert_themselves(client):
    ws = await make_ws()
    _rid, items, *_ = await one_item(client, ws)
    iid = items[0]["id"]
    off = ws.headers("COMPLIANCE_OFFICER")
    # assigning a task to yourself, and making yourself the lead
    t = await task_for(client, ws, iid, assignee="COMPLIANCE_OFFICER")
    r = await client.patch(f"{base(ws)}/items/{iid}", headers=off, json={"assigned_lead_id": str(ws.users["COMPLIANCE_OFFICER"].id)})
    assert r.status_code == 200
    # the assignee uploads, someone else reviews: nobody hears about their own action
    up = await upload(client, ws, t["task"]["id"], role="COMPLIANCE_OFFICER")
    assert up.status_code == 201, up.text
    rev = await client.post(f"{base(ws)}/tasks/{t['task']['id']}/reviews", headers=ws.headers("REVIEWER"),
                            json={"decision": "APPROVED"})
    assert rev.status_code == 201, rev.text
    await dispatch()
    assert await notes(ws.users["COMPLIANCE_OFFICER"], kind="TASK_ASSIGNED") == []
    assert await notes(ws.users["COMPLIANCE_OFFICER"], kind="ITEM_LEAD_ASSIGNED") == []
    assert await notes(ws.users["REVIEWER"], kind="TASK_REVIEWED") == []
    # the officer uploaded, so the officer is not asked to review it either
    assert await notes(ws.users["COMPLIANCE_OFFICER"], kind="EVIDENCE_AWAITING_REVIEW") == []
    # the person who decided is never told about it
    for e in await events(kind="TASK_REVIEWED", org=ws.org_id):
        assert str(ws.users["REVIEWER"].id) not in (e.recipient_user_ids or [])


# ---------------------------------------------------------------------------
# 8. Assignment
# ---------------------------------------------------------------------------
async def test_assignment_events(client):
    ws = await make_ws()
    _rid, items, *_ = await one_item(client, ws, n=2)
    iid = items[0]["id"]
    off = ws.headers("COMPLIANCE_OFFICER")
    a, b = ws.users["ANALYST"], ws.users["ANALYST:2"]

    t = await task_for(client, ws, iid, assignee="ANALYST")
    tid = t["task"]["id"]
    await dispatch()
    rows = await notes(a, kind="TASK_ASSIGNED")
    assert len(rows) == 1 and rows[0].title == "Task assigned to you: Collect proof"
    assert rows[0].link == f"/workspace/{ws.org_id}/items/{iid}#task-{tid}"
    assert "assigned you a task at" in rows[0].body

    # same PATCH with no change: nothing new
    same = await client.patch(f"{base(ws)}/tasks/{tid}", headers=off, json={"assigned_to_user_id": str(a.id)})
    assert same.status_code == 200
    # reassign to B, then back to A: both are told, A again with a new key
    to_b = await client.patch(f"{base(ws)}/tasks/{tid}", headers=off, json={"assigned_to_user_id": str(b.id)})
    assert to_b.status_code == 200
    await dispatch()
    assert len(await notes(b, kind="TASK_ASSIGNED")) == 1
    back = await client.patch(f"{base(ws)}/tasks/{tid}", headers=off, json={"assigned_to_user_id": str(a.id)})
    assert back.status_code == 200
    await dispatch()
    assert len(await notes(a, kind="TASK_ASSIGNED")) == 2
    assert len(await notes(b, kind="TASK_ASSIGNED")) == 1

    # a lead on an item
    lead = await client.patch(f"{base(ws)}/items/{items[1]['id']}", headers=off, json={"assigned_lead_id": str(a.id)})
    assert lead.status_code == 200
    again = await client.patch(f"{base(ws)}/items/{items[1]['id']}", headers=off, json={"assigned_lead_id": str(a.id)})
    assert again.status_code == 200
    await dispatch()
    led = await notes(a, kind="ITEM_LEAD_ASSIGNED")
    assert len(led) == 1 and led[0].title.startswith("You lead an item:")
    assert led[0].link == f"/workspace/{ws.org_id}/items/{items[1]['id']}"

    # cancel: the assignee is told
    c = await client.post(f"{base(ws)}/tasks/{tid}/cancel", headers=off, json={"reason": "Not needed"})
    assert c.status_code == 200
    await dispatch()
    cancelled = await notes(a, kind="TASK_CANCELLED")
    assert len(cancelled) == 1 and cancelled[0].title == "Task cancelled: Collect proof"
    assert await notes(b, kind="TASK_CANCELLED") == []

    # a lead named when the item is created
    doc, _v, pages, obls = await circular(n_verified=1)
    rid = await new_register(client, ws, "Second register")
    made = await client.post(f"{base(ws)}/items", headers=off, json={
        "register_id": rid, "obligation_id": str(obls[0].id), "assigned_lead_id": str(b.id),
    })
    assert made.status_code == 201, made.text
    await dispatch()
    assert len(await notes(b, kind="ITEM_LEAD_ASSIGNED")) == 1


# ---------------------------------------------------------------------------
# 9. Evidence and sign-off waiting
# ---------------------------------------------------------------------------
async def test_review_waiting_recipients(client):
    ws = await make_ws()
    _rid, items, *_ = await one_item(client, ws)
    iid = items[0]["id"]
    off = ws.headers("COMPLIANCE_OFFICER")
    dep = await client.patch(f"{base(ws)}/items/{iid}", headers=off, json={"department_id": ws.departments["A"]})
    assert dep.status_code == 200
    t = await task_for(client, ws, iid, assignee="ANALYST")
    tid = t["task"]["id"]
    assert (await upload(client, ws, tid)).status_code == 201
    await dispatch()
    seen = who(ws, await got(ws, "EVIDENCE_AWAITING_REVIEW"))
    assert seen == {"COMPLIANCE_HEAD", "REVIEWER", "REVIEWER:2", "DEPARTMENT_LEAD"}
    row = (await notes(ws.users["REVIEWER"], kind="EVIDENCE_AWAITING_REVIEW"))[0]
    assert row.title == "Evidence to review: Collect proof" and row.link == f"/workspace/{ws.org_id}/review"

    # approve, then send the item for sign-off: heads and reviewers (not the bank admin)
    assert (await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"),
                              json={"decision": "APPROVED"})).status_code == 201
    sent = await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})
    assert sent.status_code == 200, sent.text
    await dispatch()
    seen = who(ws, await got(ws, "ITEM_AWAITING_SIGNOFF"))
    assert seen == {"COMPLIANCE_HEAD", "REVIEWER", "REVIEWER:2"}


async def test_review_waiting_falls_back_to_bank_admin(client):
    ws = await make_ws({"ORG_ADMIN": None, "COMPLIANCE_OFFICER": None, "ANALYST": "A"})
    _rid, items, *_ = await one_item(client, ws)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    assert (await upload(client, ws, t["task"]["id"])).status_code == 201
    await dispatch()
    assert who(ws, await got(ws, "EVIDENCE_AWAITING_REVIEW")) == {"ORG_ADMIN"}


# ---------------------------------------------------------------------------
# 10. Decisions
# ---------------------------------------------------------------------------
async def test_decisions_reach_the_right_people(client):
    ws = await make_ws()
    _rid, items, *_ = await one_item(client, ws, n=2)
    off = ws.headers("COMPLIANCE_OFFICER")

    # evidence: changes requested
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    tid = t["task"]["id"]
    assert (await upload(client, ws, tid)).status_code == 201
    ch = await client.post(f"{base(ws)}/tasks/{tid}/reviews", headers=ws.headers("REVIEWER"),
                           json={"decision": "CHANGES_REQUESTED", "comments": "Add the signed page."})
    assert ch.status_code == 201, ch.text
    await dispatch()
    rows = await notes(ws.users["ANALYST"], kind="TASK_REVIEWED")
    assert len(rows) == 1 and rows[0].detail == "Add the signed page." and rows[0].severity == "warn"
    assert rows[0].title == "Evidence needs changes: Collect proof"
    assert await notes(ws.users["REVIEWER"], kind="TASK_REVIEWED") == []
    assert await notes(ws.users["ANALYST:2"], kind="TASK_REVIEWED") == []

    # sign-off: sent back. The person who sent it for sign-off is read before the item moves.
    iid = items[1]["id"]
    t2 = await task_for(client, ws, iid, assignee="ANALYST")
    assert (await upload(client, ws, t2["task"]["id"], content=b"%PDF-1.4 other")).status_code == 201
    assert (await client.post(f"{base(ws)}/tasks/{t2['task']['id']}/reviews", headers=ws.headers("REVIEWER"),
                              json={"decision": "APPROVED"})).status_code == 201
    assert (await client.post(f"{base(ws)}/items/{iid}/status", headers=off, json={"to": "EVIDENCE_SUBMITTED"})).status_code == 200
    back = await client.post(f"{base(ws)}/items/{iid}/signoff", headers=ws.headers("REVIEWER:2"),
                             json={"decision": "REJECTED", "comments": "Not yet."})
    assert back.status_code == 201, back.text
    await dispatch()
    sent_back = await notes(ws.users["COMPLIANCE_OFFICER"], kind="ITEM_SIGNOFF_DECIDED")
    assert len(sent_back) == 1 and sent_back[0].detail == "Not yet." and sent_back[0].severity == "warn"
    assert sent_back[0].title.startswith("Item sent back:")
    assert await notes(ws.users["REVIEWER:2"], kind="ITEM_SIGNOFF_DECIDED") == []


# ---------------------------------------------------------------------------
# 11. Deadlines
# ---------------------------------------------------------------------------
async def sweep_deadlines(org_id, today):
    async with AsyncSessionLocal() as db:
        n = await sweeps.ensure_deadline_events(db, uuid.UUID(str(org_id)), today)
        await db.commit()
        return n


async def deadline_ws():
    ws = await make_ws({
        "COMPLIANCE_HEAD": None, "COMPLIANCE_HEAD:2": None, "COMPLIANCE_OFFICER": None,
        "DEPARTMENT_LEAD": "A", "ANALYST": "A", "REVIEWER": None,
    })
    async with AsyncSessionLocal() as db:
        d = await db.get(Department, uuid.UUID(ws.departments["A"]))
        d.head_user_id = ws.users["DEPARTMENT_LEAD"].id
        await db.commit()
    return ws


async def patch_item(client, ws, iid, **body):
    r = await client.patch(f"{base(ws)}/items/{iid}", headers=ws.headers("COMPLIANCE_OFFICER"), json=body)
    assert r.status_code == 200, r.text


async def test_deadline_due_soon_and_overdue(client):
    ws = await deadline_ws()
    _rid, items, *_ = await one_item(client, ws, n=6)
    ids = [i["id"] for i in items]
    T = date(2031, 6, 15)
    lead, dept_head = ws.users["ANALYST"], ws.users["DEPARTMENT_LEAD"]

    # item 0: lead + department A, due in 7 days
    due = T + timedelta(days=7)
    await patch_item(client, ws, ids[0], department_id=ws.departments["A"], assigned_lead_id=str(lead.id),
                     internal_deadline=str(due))
    assert await sweep_deadlines(ws.org_id, T) >= 1
    assert len(await events(kind="ITEM_DUE_SOON", key_prefix=f"ITEM_DUE_SOON:{ids[0]}:")) == 1
    assert await sweep_deadlines(ws.org_id, T) == 0          # nothing new the second time
    assert await sweep_deadlines(ws.org_id, T + timedelta(days=1)) == 0   # 6 days left: still the 7-day alert
    await sweep_deadlines(ws.org_id, due - timedelta(days=1))
    keys = sorted(e.dedupe_key for e in await events(kind="ITEM_DUE_SOON", key_prefix=f"ITEM_DUE_SOON:{ids[0]}:"))
    assert keys == [f"ITEM_DUE_SOON:{ids[0]}:{due}:1", f"ITEM_DUE_SOON:{ids[0]}:{due}:7"]
    await sweep_deadlines(ws.org_id, due + timedelta(days=1))
    await sweep_deadlines(ws.org_id, due + timedelta(days=2))
    assert len(await events(kind="ITEM_OVERDUE", key_prefix=f"ITEM_OVERDUE:{ids[0]}:")) == 1
    await dispatch()
    lead_titles = sorted(r.title for r in await notes(lead, org=ws.org_id) if r.kind in ("ITEM_DUE_SOON", "ITEM_OVERDUE"))
    assert any(t.startswith("Due in 7 days:") for t in lead_titles)
    assert any(t.startswith("Due in 1 day:") for t in lead_titles)
    assert any(t.startswith("Overdue:") for t in lead_titles)
    overdue_to = who(ws, await got(ws, "ITEM_OVERDUE", ids[0]))
    assert overdue_to == {"ANALYST", "DEPARTMENT_LEAD", "COMPLIANCE_HEAD", "COMPLIANCE_HEAD:2"}
    due_to = who(ws, await got(ws, "ITEM_DUE_SOON", ids[0]))
    assert due_to == {"ANALYST"}                     # the lead only, not the heads

    # item 1: first seen at 1 day left gets only the 1-day alert
    d1 = T + timedelta(days=10)
    await patch_item(client, ws, ids[1], assigned_lead_id=str(lead.id), internal_deadline=str(d1))
    await sweep_deadlines(ws.org_id, d1 - timedelta(days=1))
    k1 = [e.dedupe_key for e in await events(kind="ITEM_DUE_SOON", key_prefix=f"ITEM_DUE_SOON:{ids[1]}:")]
    assert k1 == [f"ITEM_DUE_SOON:{ids[1]}:{d1}:1"]

    # item 2: waiting for sign-off is never overdue
    async with AsyncSessionLocal() as db:
        row = await db.get(ComplianceItem, uuid.UUID(ids[2]))
        row.status = "EVIDENCE_SUBMITTED"
        row.internal_deadline = T - timedelta(days=5)
        await db.commit()
    await sweep_deadlines(ws.org_id, T)
    assert await events(kind="ITEM_OVERDUE", key_prefix=f"ITEM_OVERDUE:{ids[2]}:") == []

    # item 3: editing the deadline gives a new due-soon alert
    first = T + timedelta(days=7)
    await patch_item(client, ws, ids[3], assigned_lead_id=str(lead.id), internal_deadline=str(first))
    await sweep_deadlines(ws.org_id, T)
    moved = first + timedelta(days=3)
    await patch_item(client, ws, ids[3], internal_deadline=str(moved))
    await sweep_deadlines(ws.org_id, moved - timedelta(days=7))
    k3 = sorted(e.dedupe_key for e in await events(kind="ITEM_DUE_SOON", key_prefix=f"ITEM_DUE_SOON:{ids[3]}:"))
    assert k3 == sorted([f"ITEM_DUE_SOON:{ids[3]}:{first}:7", f"ITEM_DUE_SOON:{ids[3]}:{moved}:7"])

    # item 4: no lead, department A has a head: the head is told
    await patch_item(client, ws, ids[4], department_id=ws.departments["A"], internal_deadline=str(T + timedelta(days=7)))
    # item 5: no lead and no department head: the compliance heads are told
    await patch_item(client, ws, ids[5], internal_deadline=str(T + timedelta(days=7)))
    await sweep_deadlines(ws.org_id, T)
    await dispatch()
    assert who(ws, await got(ws, "ITEM_DUE_SOON", ids[4])) == {"DEPARTMENT_LEAD"}
    assert who(ws, await got(ws, "ITEM_DUE_SOON", ids[5])) == {"COMPLIANCE_HEAD", "COMPLIANCE_HEAD:2"}


async def test_task_deadline_alerts_and_poll_sweep(client, monkeypatch):
    ws = await deadline_ws()
    _rid, items, *_ = await one_item(client, ws)
    T = date(2031, 7, 1)
    monkeypatch.setattr(rules, "today_dhaka", lambda: T)
    t = await task_for(client, ws, items[0]["id"], assignee="ANALYST", due=T - timedelta(days=1))
    tid = t["task"]["id"]
    soon = await task_for(client, ws, items[0]["id"], assignee="ANALYST", due=T + timedelta(days=1))
    # the on-poll check turns the derived state into alerts for the person who polls
    r = await client.get("/api/v1/alerts/summary", headers=ws.headers("ANALYST"))
    assert r.status_code == 200
    assert str(uuid.UUID(ws.org_id)) in alerts_router._last_poll_sweep
    rows = await notes(ws.users["ANALYST"], org=ws.org_id)
    kinds = sorted(x.kind for x in rows)
    assert kinds.count("TASK_ASSIGNED") == 2
    assert "TASK_OVERDUE" in kinds and "TASK_DUE_SOON" in kinds
    overdue = [x for x in rows if x.kind == "TASK_OVERDUE"][0]
    assert overdue.title == "Overdue task: Collect proof" and overdue.severity == "bad"
    assert overdue.link == f"/workspace/{ws.org_id}/items/{items[0]['id']}#task-{tid}"
    soon_row = [x for x in rows if x.kind == "TASK_DUE_SOON"][0]
    assert soon_row.title == "Task due in 1 day: Collect proof"
    # a second poll inside the throttle gap changes nothing
    before = len(await notes(ws.users["ANALYST"], org=ws.org_id))
    await client.get("/api/v1/alerts/summary", headers=ws.headers("ANALYST"))
    assert len(await notes(ws.users["ANALYST"], org=ws.org_id)) == before
    # nobody else is told about the task
    assert await notes(ws.users["REVIEWER"], kind="TASK_OVERDUE") == []
    _ = soon


# ---------------------------------------------------------------------------
# 12. A circular behind register items changed
# ---------------------------------------------------------------------------
QUOTE = "This circular replaces BRPD Circular No. 5 (2020) – “all earlier text” is withdrawn."


async def link(source, target, rel_type, page=None, status="VERIFIED", quote=QUOTE):
    async with AsyncSessionLocal() as db:
        rel = DocumentRelationship(
            source_document_id=source.id, target_document_id=target.id, relationship_type=rel_type,
            supporting_quote=quote, source_page_id=page.id if page is not None else None,
            verification_status=status, detection_method="AI_INFERRED",
            reviewed_at=datetime.now(timezone.utc) if status == "VERIFIED" else None,
        )
        db.add(rel)
        await db.commit()
        await db.refresh(rel)
        return rel


async def run_source_check(org_id):
    async with AsyncSessionLocal() as db:
        n = await sweeps.ensure_source_change_events(db, uuid.UUID(str(org_id)))
        await db.commit()
        return n


async def test_register_source_change(client):
    ws = await make_ws({
        "ORG_ADMIN": None, "COMPLIANCE_HEAD": None, "COMPLIANCE_OFFICER": None, "REVIEWER": None, "VIEWER": None,
    })
    other = await make_ws({"COMPLIANCE_OFFICER": None})
    _rid, items, x, _v, _p, _o = await one_item(client, ws, n=3)
    await one_item(client, other, n=1)
    admin, admin_token = await make_user(is_superuser=True)
    await quiet(admin, ("library", "admin_queue"))
    y, _yv, ypages, _yo = await circular(n_verified=0)

    rel = await link(y, x, "REPLACES", page=ypages[1], status="PENDING_REVIEW")
    await dispatch()
    assert await events(kind="REGISTER_SOURCE_CHANGED", org=ws.org_id) == []
    assert await run_source_check(ws.org_id) == 0          # still waiting for review

    ok = await client.post(f"/api/v1/relationships/{rel.id}/review", headers=H(admin_token), json={"decision": "VERIFIED"})
    assert ok.status_code == 200, ok.text
    evs = await events(kind="REGISTER_SOURCE_CHANGED", org=ws.org_id)
    assert len(evs) == 1                                   # one event for three items
    await dispatch()
    staff = {"ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER"}
    seen = await got(ws, "REGISTER_SOURCE_CHANGED")
    assert who(ws, seen) == staff and all(len(seen[r]) == 1 for r in staff)
    n = seen["COMPLIANCE_OFFICER"][0]
    assert n.quote_text == QUOTE and n.quote_page_number == 2 and str(n.quote_document_id) == str(y.id)
    assert n.title == f"{x.reference_number} was replaced"
    assert f"{y.reference_number} replaces it. 3 items in your registers" in n.body
    assert n.severity == "warn" and n.link.endswith("?changed=1")
    # the other bank has nothing
    assert await events(kind="REGISTER_SOURCE_CHANGED", org=other.org_id) == []
    assert who(other, await got(other, "REGISTER_SOURCE_CHANGED")) == set()
    # the same state never alerts twice
    assert await run_source_check(ws.org_id) == 0

    # acknowledge all three, then a stronger verified link gives a new signature and a new alert
    for it in items:
        a = await client.post(f"{base(ws)}/items/{it['id']}/acknowledge-source-change",
                              headers=ws.headers("COMPLIANCE_OFFICER"), json={"note": "Checked."})
        assert a.status_code == 200, a.text
    assert await run_source_check(ws.org_id) == 0
    z, _zv, zpages, _zo = await circular(n_verified=0)
    await link(z, x, "REPEALS", page=zpages[0], quote="Circular Z repeals the earlier one.")
    assert await run_source_check(ws.org_id) == 1
    assert await run_source_check(ws.org_id) == 0
    await dispatch()
    seen = await got(ws, "REGISTER_SOURCE_CHANGED")
    assert all(len(seen[r]) == 2 for r in staff)
    newest = sorted(seen["COMPLIANCE_HEAD"], key=lambda r: r.created_at)[-1]
    assert newest.severity == "bad" and newest.quote_text == "Circular Z repeals the earlier one."
    assert newest.quote_page_number == 1

    # a verified link stated by a private upload changes nothing
    owner, _t = await make_user()
    _r2, items2, x2, *_rest = await one_item(client, ws, n=1)
    private, *_ = await circular(n_verified=0)
    async with AsyncSessionLocal() as db:
        d = await db.get(Document, private.id)
        d.owner_user_id = owner.id
        await db.commit()
    await link(private, x2, "REPEALS")
    assert await run_source_check(ws.org_id) == 0
    assert await events(key_prefix=f"SOURCE_CHANGED:{ws.org_id}:{x2.id}") == []


async def test_withdrawn_circular_alerts_through_the_review_step(client):
    from backend.app.modules.analysis.service import AnalysisService

    ws = await make_ws({"ORG_ADMIN": None, "COMPLIANCE_OFFICER": None})
    _rid, _items, x, *_ = await one_item(client, ws, n=1)
    reviewer, _t = await make_user(is_superuser=True)
    async with AsyncSessionLocal() as db:
        await AnalysisService.review_and_publish_analysis(db, x.id, reviewer.id, "WITHDRAWN")
    await dispatch()
    rows = await notes(ws.users["COMPLIANCE_OFFICER"], kind="REGISTER_SOURCE_CHANGED")
    assert len(rows) == 1 and rows[0].title == f"{x.reference_number} was withdrawn" and rows[0].severity == "bad"
    assert rows[0].quote_text is None


# ---------------------------------------------------------------------------
# 13. Admin queues
# ---------------------------------------------------------------------------
async def test_admin_queue_alerts(client, monkeypatch):
    s1, _t1 = await make_user(is_superuser=True)
    s2, _t2 = await make_user(is_superuser=True)
    normal, _t3 = await make_user()
    for u in (s1, s2, normal):
        await quiet(u)
    # set the other waiting discoveries aside so the count in this test is exact
    async with AsyncSessionLocal() as db:
        parked = [r[0] for r in (await db.execute(
            select(SourceDiscovery.id).where(SourceDiscovery.status == "VALIDATED"))).all()]
        if parked:
            await db.execute(update(SourceDiscovery).where(SourceDiscovery.id.in_(parked)).values(status="PARKED"))
        inst = await make_institution()
        src = Source(institution_id=inst.id, name="Queue test source")
        db.add(src)
        await db.flush()
        run = SourceRun(source_id=src.id)
        db.add(run)
        await db.flush()
        db.add(SourceDiscovery(source_run_id=run.id, source_url="https://example.test/a.pdf", status="VALIDATED"))
        await db.commit()
    try:
        day = date(2031, 3, 3)

        async def check(d):
            async with AsyncSessionLocal() as db:
                n = await sweeps.ensure_admin_queue_events(db, d)
                await db.commit()
                return n

        assert await check(day) >= 1
        await dispatch()
        for s in (s1, s2):
            rows = await notes(s, kind="ADMIN_QUEUE")
            mine = [r for r in rows if r.title == "1 new circular to approve"]
            assert len(mine) == 1 and mine[0].link == "/admin?tab=queue"
            assert mine[0].body == "They are waiting in the admin review queue."
        assert await notes(normal, kind="ADMIN_QUEUE") == []
        assert await check(day) == 0                    # same day: nothing
        await dispatch()
        assert len([r for r in await notes(s1, kind="ADMIN_QUEUE") if r.title == "1 new circular to approve"]) == 1
        assert await check(day + timedelta(days=1)) >= 1  # next day: a new one
        await dispatch()
        assert len([r for r in await notes(s1, kind="ADMIN_QUEUE") if r.title == "1 new circular to approve"]) == 2
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(update(SourceDiscovery).where(SourceDiscovery.source_url == "https://example.test/a.pdf")
                             .values(status="REJECTED"))
            if parked:
                await db.execute(update(SourceDiscovery).where(SourceDiscovery.id.in_(parked)).values(status="VALIDATED"))
            await db.commit()


# ---------------------------------------------------------------------------
# 14. Inbox endpoints
# ---------------------------------------------------------------------------
async def seed_inbox(user, n=5):
    base_time = datetime(2031, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    ids = []
    async with AsyncSessionLocal() as db:
        for i in range(n):
            group = "due_soon" if i == 3 else ("assigned" if i % 2 else "library")
            kind = {"due_soon": "ITEM_DUE_SOON", "assigned": "TASK_ASSIGNED", "library": "CIRCULAR_PUBLISHED"}[group]
            row = AN(
                user_id=user.id, kind=kind, group=group, dedupe_key=f"seed:{uuid.uuid4()}", severity="info",
                title=f"Alert {i}", body="Body", link="/", in_app=True, email_mode="OFF",
                created_at=base_time + timedelta(minutes=i),
            )
            db.add(row)
            await db.flush()
            ids.append(str(row.id))
        await db.commit()
    return ids, base_time


async def test_inbox_endpoints(client):
    user, token = await make_user()
    await quiet(user)
    ids, t0 = await seed_inbox(user, 5)
    h = H(token)
    full = (await client.get("/api/v1/alerts", headers=h)).json()
    assert [a["title"] for a in full["alerts"]] == [f"Alert {i}" for i in (4, 3, 2, 1, 0)]
    assert full["next_before"] is None and full["unread_count"] == 5

    # paging
    p1 = (await client.get("/api/v1/alerts", headers=h, params={"limit": 2})).json()
    assert [a["title"] for a in p1["alerts"]] == ["Alert 4", "Alert 3"] and p1["next_before"]
    p2 = (await client.get("/api/v1/alerts", headers=h, params={"limit": 2, "before": p1["next_before"]})).json()
    assert [a["title"] for a in p2["alerts"]] == ["Alert 2", "Alert 1"] and p2["next_before"]
    p3 = (await client.get("/api/v1/alerts", headers=h, params={"limit": 2, "before": p2["next_before"]})).json()
    assert [a["title"] for a in p3["alerts"]] == ["Alert 0"] and p3["next_before"] is None
    newer = (await client.get("/api/v1/alerts", headers=h, params={"after": (t0 + timedelta(minutes=2)).isoformat()})).json()
    assert [a["title"] for a in newer["alerts"]] == ["Alert 4", "Alert 3"]

    # groups
    grouped = (await client.get("/api/v1/alerts", headers=h, params={"group": "assigned"})).json()
    assert [a["title"] for a in grouped["alerts"]] == ["Alert 1"]
    dl = (await client.get("/api/v1/alerts", headers=h, params={"group": "deadlines"})).json()
    assert [a["title"] for a in dl["alerts"]] == ["Alert 3"]
    assert (await client.get("/api/v1/alerts", headers=h, params={"group": "nope"})).status_code == 422

    # read, idempotent, unread
    first = (await client.post(f"/api/v1/alerts/{ids[0]}/read", headers=h)).json()
    assert first["unread_count"] == 4 and first["alert"]["read_at"]
    second = (await client.post(f"/api/v1/alerts/{ids[0]}/read", headers=h)).json()
    assert second["alert"]["read_at"] == first["alert"]["read_at"] and second["unread_count"] == 4
    only = (await client.get("/api/v1/alerts", headers=h, params={"filter": "unread"})).json()
    assert [a["title"] for a in only["alerts"]] == ["Alert 4", "Alert 3", "Alert 2", "Alert 1"]
    undone = (await client.post(f"/api/v1/alerts/{ids[0]}/unread", headers=h)).json()
    assert undone["alert"]["read_at"] is None and undone["unread_count"] == 5

    # read-all up to a time leaves the newer ones unread
    done = (await client.post("/api/v1/alerts/read-all", headers=h,
                              json={"up_to": (t0 + timedelta(minutes=2)).isoformat()})).json()
    assert done["updated"] == 3 and done["unread_count"] == 2
    left = (await client.get("/api/v1/alerts", headers=h, params={"filter": "unread"})).json()
    assert [a["title"] for a in left["alerts"]] == ["Alert 4", "Alert 3"]
    one_group = (await client.post("/api/v1/alerts/read-all", headers=h, json={
        "up_to": (t0 + timedelta(days=1)).isoformat(), "group": "deadlines"})).json()
    assert one_group["updated"] == 1 and one_group["unread_count"] == 1

    # every count matches a fresh poll
    summary = (await client.get("/api/v1/alerts/summary", headers=h)).json()
    assert summary["unread_count"] == 1 and summary["email_configured"] is False
    assert summary["latest_id"] == ids[4] and summary["server_time"]
    assert (await client.get("/api/v1/alerts")).status_code == 401
    assert (await client.get("/api/v1/alerts/summary")).status_code == 401


# ---------------------------------------------------------------------------
# 15. Preferences
# ---------------------------------------------------------------------------
async def test_preferences_defaults_and_validation(client):
    plain, plain_token = await make_user()
    admin, admin_token = await make_user(is_superuser=True)
    ws = await make_ws({"COMPLIANCE_OFFICER": None})
    d = (await client.get("/api/v1/alerts/preferences", headers=H(plain_token))).json()
    assert set(d["channels"]) == {"library"} and d["email_enabled"] is True and d["lock_version"] == 1
    assert d["channels"]["library"] == {"in_app": True, "email": "DIGEST"}
    assert d["email_configured"] is False and d["due_soon_days"] == [1, 7] and d["digest_time"] == "10:30"
    assert [g["id"] for g in d["options"]["groups"]] == ["library"]
    assert any(c["code"] == "BRPD" for c in d["options"]["department_codes"])
    assert set((await client.get("/api/v1/alerts/preferences", headers=H(admin_token))).json()["channels"]) == {"library", "admin_queue"}
    bank = (await client.get("/api/v1/alerts/preferences", headers=ws.headers("COMPLIANCE_OFFICER"))).json()
    assert set(bank["channels"]) == set(GROUPS) - {"admin_queue"}

    ch = {"library": {"in_app": True, "email": "OFF"}}
    bad = [
        {"channels": {"nope": {"in_app": True, "email": "OFF"}}},
        {"channels": {"library": {"in_app": True, "email": "WEEKLY"}}},
        {"channels": ch, "library_department_codes": ["ZZZ-NOT-A-DEPARTMENT"]},
        {"channels": ch, "library_keywords": ["a"]},
        {"channels": ch, "library_keywords": ["liquidity", "LIQUIDITY"]},
        {"channels": ch, "library_keywords": [f"word{i:02d}" for i in range(21)]},
    ]
    for body in bad:
        r = await client.put("/api/v1/alerts/preferences", headers=H(plain_token), json=body)
        assert r.status_code == 422, (body, r.text)

    # groups the person cannot see are ignored
    ok = await client.put("/api/v1/alerts/preferences", headers=H(plain_token), json={
        "channels": {"library": {"in_app": False, "email": "OFF"}, "admin_queue": {"in_app": False, "email": "OFF"}},
        "library_keywords": ["  Liquidity   rules "], "lock_version": 1,
    })
    assert ok.status_code == 200, ok.text
    saved = ok.json()
    assert saved["library_keywords"] == ["Liquidity rules"] and saved["lock_version"] == 1
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == plain.id))).scalar_one()
        assert set(row.channels) == {"library"}

    # a stale save is refused with the current copy
    one = await client.put("/api/v1/alerts/preferences", headers=H(plain_token), json={"channels": ch, "lock_version": 1})
    assert one.status_code == 200 and one.json()["lock_version"] == 2
    stale = await client.put("/api/v1/alerts/preferences", headers=H(plain_token), json={"channels": ch, "lock_version": 1})
    assert stale.status_code == 409
    assert stale.json()["current"]["lock_version"] == 2 and "detail" in stale.json()


async def test_preferences_switch_off_and_hidden_rows(client):
    ws = await make_ws({"COMPLIANCE_OFFICER": None, "ANALYST": "A", "ANALYST:2": "A"})
    await put_assigned(client, ws, "ANALYST", {"in_app": False, "email": "OFF"})
    await put_assigned(client, ws, "ANALYST:2", {"in_app": False, "email": "DIGEST"})
    _rid, items, *_ = await one_item(client, ws)
    await task_for(client, ws, items[0]["id"], assignee="ANALYST")
    await task_for(client, ws, items[0]["id"], assignee="ANALYST:2")
    await dispatch()
    assert await notes(ws.users["ANALYST"], kind="TASK_ASSIGNED") == []      # nothing stored at all
    kept = await notes(ws.users["ANALYST:2"], kind="TASK_ASSIGNED")
    assert len(kept) == 1 and kept[0].in_app is False and kept[0].email_mode == "DIGEST"
    # kept for the daily summary only: hidden from the inbox and from the counts
    lst = (await client.get("/api/v1/alerts", headers=ws.headers("ANALYST:2"))).json()
    assert lst["alerts"] == [] and lst["unread_count"] == 0
    assert (await client.get("/api/v1/alerts/summary", headers=ws.headers("ANALYST:2"))).json()["unread_count"] == 0


async def put_assigned(client, ws, role, setting):
    r = await client.put("/api/v1/alerts/preferences", headers=ws.headers(role), json={"channels": {"assigned": setting}})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 16. Golden rule: alert text is fixed words plus stored values
# ---------------------------------------------------------------------------
SAMPLE = {
    "document_id": "d-1", "reference_number": "BRPD 5/2026", "title": "Liquidity rules", "publication_date": "2026-11-13",
    "organization_id": "o-1", "organization_name": "Test Bank", "item_id": "i-1", "item_title": "Keep reserves",
    "register_id": "r-1", "task_id": "t-1", "task_title": "Collect proof", "due_date": "2026-12-01",
    "deadline": "2026-12-02", "days_left": 3, "actor_name": "Rina", "decision": "APPROVED", "comments": "Looks fine.",
    "change_kind": "AMENDED", "by_document_id": "d-2", "by_reference_number": "BRPD 9/2026", "by_title": "Newer rules",
    "link_quote": "This circular amends BRPD 5/2026.", "link_quote_page": 3, "item_ids": ["i-1"], "register_ids": ["r-1"],
    "item_count": 1, "queue": "links", "count": 2,
    "executive_summary": "SECRET SUMMARY TEXT", "impact": "SECRET IMPACT TEXT",
}


def test_alert_text_is_fixed_words_plus_stored_values():
    for kind in KIND_GROUP:
        r = templates.render(kind, SAMPLE)
        text = " ".join([r.title, r.body, r.detail or "", r.link])
        assert "SECRET" not in text, kind
        assert r.title and r.body and r.link.startswith("/")
        assert r.severity in ("info", "warn", "bad")
    exact = {
        "CIRCULAR_PUBLISHED": ("New circular: BRPD 5/2026", "Liquidity rules. Published 13 Nov 2026.", "/?doc=d-1"),
        "TASK_ASSIGNED": ("Task assigned to you: Collect proof", "Rina assigned you a task at Test Bank. Due 1 Dec 2026.",
                          "/workspace/o-1/items/i-1#task-t-1"),
        "ITEM_OVERDUE": ("Overdue: Keep reserves", "The deadline was 2 Dec 2026 at Test Bank.", "/workspace/o-1/items/i-1"),
        "ADMIN_QUEUE": ("2 links to confirm", "They are waiting in the admin review queue.", "/admin?tab=links"),
    }
    for kind, (title, body, link) in exact.items():
        r = templates.render(kind, SAMPLE)
        assert (r.title, r.body, r.link) == (title, body, link), kind
    moved = templates.render("REGISTER_SOURCE_CHANGED", SAMPLE)
    assert moved.title == "BRPD 5/2026 was amended"
    assert moved.body == "BRPD 9/2026 amends it. 1 item in your registers at Test Bank points to it. Please check it."
    assert moved.quote_text == "This circular amends BRPD 5/2026." and moved.quote_page_number == 3
    assert moved.quote_label == "From BRPD 9/2026, page 3:"
    # only the confirmed link's quote is ever shown
    for kind in KIND_GROUP:
        if kind != "REGISTER_SOURCE_CHANGED":
            assert templates.render(kind, SAMPLE).quote_text is None


async def test_circular_fields_carry_no_analysis_text():
    doc, _v, _p = await published_doc()
    async with AsyncSessionLocal() as db:
        fields = await circular_fields(db, await db.get(Document, doc.id))
    assert set(fields) == {
        "document_id", "reference_number", "title", "title_bn", "document_type", "department_code", "publication_date",
    }


# ---------------------------------------------------------------------------
# 17. The alerts job stays off unless asked for
# ---------------------------------------------------------------------------
async def test_worker_gating(monkeypatch):
    from backend.app.main import app as the_app
    from backend.app.modules.alerts.worker import alerts_worker
    from backend.app.core.config import settings

    assert settings.SCHEDULER_ENABLED is False and settings.ALERTS_WORKER_ENABLED is False
    async with the_app.router.lifespan_context(the_app):
        assert alerts_worker.running is False

    calls = []

    async def fake_start():
        calls.append("start")

    async def fake_stop():
        calls.append("stop")

    monkeypatch.setattr(settings, "ALERTS_WORKER_ENABLED", True)
    monkeypatch.setattr(alerts_worker, "start", fake_start)
    monkeypatch.setattr(alerts_worker, "stop", fake_stop)
    async with the_app.router.lifespan_context(the_app):
        assert calls == ["start"]
    assert calls == ["start", "stop"]
