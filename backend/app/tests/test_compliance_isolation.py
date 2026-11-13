"""One bank never sees another bank's workspace data (cross-organization isolation)."""
import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.compliance.models import TaskEvidence
from backend.app.modules.organizations.models import OrganizationMember
from backend.app.tests.factories import make_document, make_user, make_workspace
from backend.app.tests.test_compliance_workspace import PDF, add_obligation, base, upload

PUBLISHED = "PUBLISHED_MACHINE_PROCESSED"
ROLES = {"ORG_ADMIN": None, "COMPLIANCE_OFFICER": "A", "ANALYST": "A", "REVIEWER": None}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def fill(client, ws, doc, obl):
    """A register, an item, a task and an evidence file in one bank."""
    h = ws.headers("COMPLIANCE_OFFICER")
    reg = (await client.post(f"{base(ws)}/registers", headers=h, json={"title": "Register"})).json()["id"]
    item = (await client.post(f"{base(ws)}/items", headers=h, json={"register_id": reg, "obligation_id": str(obl.id)})).json()
    task = (await client.post(f"{base(ws)}/tasks", headers=h, json={
        "compliance_item_id": item["id"], "title": "Task", "due_date": str(date.today() + timedelta(days=9)),
        "assigned_to_user_id": str(ws.users["ANALYST"].id)})).json()["task"]
    ev = (await upload(client, ws, task["id"])).json()["evidence"]
    return {"register": reg, "item": item["id"], "task": task["id"], "evidence": ev["id"],
            "department": ws.departments["A"], "member": ws.members["ANALYST"], "user": str(ws.users["ANALYST"].id)}


@pytest.fixture
async def banks(client):
    doc, version, pages = await make_document(pages=1, status=PUBLISHED)
    obl = await add_obligation(version.id, pages[0].id, "Banks shall keep records of everything.")
    a = await make_workspace(ROLES)
    b = await make_workspace(ROLES)
    da = await fill(client, a, doc, obl)
    db_ = await fill(client, b, doc, obl)
    sup, sup_token = await make_user(is_superuser=True)
    return {"a": a, "b": b, "da": da, "db": db_, "doc": doc, "sup": sup, "sup_token": sup_token, "obl": obl}


def routes(ws, ids, doc):
    """(method, path, json) for every workspace route, filled with one bank's ids."""
    o = f"/api/v1/organizations/{ws.org_id}"
    c = f"{o}/compliance"
    nid = str(uuid.uuid4())
    return [
        ("GET", f"{o}/me", None),
        ("GET", f"{o}/members", None),
        ("POST", f"{o}/members/by-email", {"email": "x@example.test", "role": "VIEWER"}),
        ("PATCH", f"{o}/members/{ids['member']}", {"role": "VIEWER"}),
        ("GET", f"{o}/departments", None),
        ("POST", f"{o}/departments", {"name": "Intruder dept"}),
        ("PATCH", f"{o}/departments/{ids['department']}", {"name": "Hacked"}),
        ("DELETE", f"{o}/departments/{ids['department']}", None),
        ("GET", f"{c}/registers", None),
        ("POST", f"{c}/registers", {"title": "x"}),
        ("GET", f"{c}/registers/{ids['register']}", None),
        ("PATCH", f"{c}/registers/{ids['register']}", {"title": "x"}),
        ("POST", f"{c}/registers/from-document", {"document_id": str(doc.id)}),
        ("POST", f"{c}/registers/{ids['register']}/items/from-document", {"document_id": str(doc.id)}),
        ("GET", f"{c}/documents/{doc.id}/addable-obligations", None),
        ("GET", f"{c}/items", None),
        ("GET", f"{c}/items/{ids['item']}", None),
        ("PATCH", f"{c}/items/{ids['item']}", {"notes": "x"}),
        ("POST", f"{c}/items/{ids['item']}/status", {"to": "IN_PROGRESS"}),
        ("POST", f"{c}/items/{ids['item']}/signoff", {"decision": "APPROVED", "comments": "x"}),
        ("POST", f"{c}/items/{ids['item']}/acknowledge-source-change", {"note": "x"}),
        ("POST", f"{c}/items/{ids['item']}/reopen", {"reason": "x"}),
        ("GET", f"{c}/tasks", None),
        ("POST", f"{c}/tasks", {"compliance_item_id": ids["item"], "title": "x", "due_date": "2030-01-01"}),
        ("PATCH", f"{c}/tasks/{ids['task']}", {"title": "x"}),
        ("POST", f"{c}/tasks/{ids['task']}/cancel", {"reason": "x"}),
        ("GET", f"{c}/tasks/{ids['task']}/evidence", None),
        ("GET", f"{c}/tasks/{ids['task']}/evidence/{ids['evidence']}/download", None),
        ("POST", f"{c}/tasks/{ids['task']}/evidence/{ids['evidence']}/withdraw", {"reason": "x"}),
        ("POST", f"{c}/tasks/{ids['task']}/reviews", {"decision": "APPROVED", "comments": "x"}),
        ("GET", f"{c}/audit", None),
        ("GET", f"{c}/report", None),
    ]


async def call(client, headers, method, path, body):
    return await client.request(method, path, headers=headers, json=body)


@pytest.mark.asyncio
async def test_other_bank_gets_403_on_every_route(client, banks):
    a, b = banks["a"], banks["b"]
    for method, path, body in routes(a, banks["da"], banks["doc"]):
        r = await call(client, b.headers("ORG_ADMIN"), method, path, body)
        assert r.status_code == 403, (method, path, r.status_code)
        assert "Cross-tenant access forbidden" in r.json()["detail"]
    # nothing was changed in bank A
    assert (await client.get(f"{base(a)}/registers/{banks['da']['register']}", headers=a.headers("ORG_ADMIN"))).json()["title"] == "Register"
    assert len((await client.get(f"/api/v1/organizations/{a.org_id}/departments", headers=a.headers("ORG_ADMIN"))).json()) == 2


@pytest.mark.asyncio
async def test_own_routes_with_other_banks_ids_never_show_their_data(client, banks):
    a, b = banks["a"], banks["b"]
    o = f"/api/v1/organizations/{b.org_id}"
    c = f"{o}/compliance"
    ids = banks["da"]  # bank A's ids, used against bank B's paths
    h = b.headers("ORG_ADMIN")
    cases = [
        ("GET", f"{c}/registers/{ids['register']}", None),
        ("PATCH", f"{c}/registers/{ids['register']}", {"title": "x"}),
        ("POST", f"{c}/registers/{ids['register']}/items/from-document", {"document_id": str(banks['doc'].id)}),
        ("GET", f"{c}/items/{ids['item']}", None),
        ("PATCH", f"{c}/items/{ids['item']}", {"notes": "x"}),
        ("POST", f"{c}/items/{ids['item']}/status", {"to": "IN_PROGRESS"}),
        ("POST", f"{c}/items/{ids['item']}/signoff", {"decision": "APPROVED", "comments": "x"}),
        ("POST", f"{c}/items/{ids['item']}/acknowledge-source-change", {"note": "x"}),
        ("POST", f"{c}/items/{ids['item']}/reopen", {"reason": "x"}),
        ("PATCH", f"{c}/tasks/{ids['task']}", {"title": "x"}),
        ("POST", f"{c}/tasks/{ids['task']}/cancel", {"reason": "x"}),
        ("GET", f"{c}/tasks/{ids['task']}/evidence", None),
        ("GET", f"{c}/tasks/{ids['task']}/evidence/{ids['evidence']}/download", None),
        ("POST", f"{c}/tasks/{ids['task']}/evidence/{ids['evidence']}/withdraw", {"reason": "x"}),
        ("POST", f"{c}/tasks/{ids['task']}/reviews", {"decision": "APPROVED", "comments": "x"}),
        ("PATCH", f"{o}/departments/{ids['department']}", {"name": "x"}),
        ("DELETE", f"{o}/departments/{ids['department']}", None),
        ("PATCH", f"{o}/members/{ids['member']}", {"role": "VIEWER"}),
        ("GET", f"{c}/report", None),
    ]
    for method, path, body in cases:
        r = await call(client, h, method, path, body)
        if path.endswith("/report"):
            r = await client.get(f"{c}/report", headers=h, params={"register_id": ids["register"]})
        assert r.status_code == 404, (method, path, r.status_code, r.text)
        assert str(ids["item"]) not in r.text or "not found" in r.text.lower()
    # A's users and departments cannot be used as B's lead, assignee, head or department
    item_b = banks["db"]["item"]
    for body in ({"assigned_lead_id": ids["user"]}, {"department_id": ids["department"]}):
        r = await client.patch(f"{c}/items/{item_b}", headers=h, json=body)
        assert r.status_code == 400, body
    t = await client.post(f"{c}/tasks", headers=h, json={"compliance_item_id": item_b, "title": "x", "due_date": "2030-01-01", "assigned_to_user_id": ids["user"]})
    assert t.status_code == 400
    t2 = await client.post(f"{c}/tasks", headers=h, json={"compliance_item_id": ids["item"], "title": "x", "due_date": "2030-01-01"})
    assert t2.status_code == 400
    d = await client.patch(f"{o}/departments/{banks['db']['department']}", headers=h, json={"head_user_id": ids["user"]})
    assert d.status_code == 400
    m = await client.patch(f"{o}/members/{banks['db']['member']}", headers=h, json={"department_id": ids["department"]})
    assert m.status_code == 400
    r = await client.post(f"{c}/registers/{banks['db']['register']}/items/from-document", headers=h, json={"document_id": str(banks["doc"].id)})
    assert r.status_code == 201  # a shared circular is fine; the register is B's own
    # the filters on lists never pull in A's records either
    lst = await client.get(f"{c}/items", headers=h, params={"register_id": ids["register"]})
    assert lst.status_code == 200 and lst.json()["items"] == []
    lst = await client.get(f"{c}/tasks", headers=h, params={"item_id": ids["item"]})
    assert lst.json()["tasks"] == []
    # a user from A who is not in B cannot be added to B's audit filters to reveal anything
    log = await client.get(f"{c}/audit", headers=h, params={"entity_id": ids["item"]})
    assert log.status_code == 200 and log.json()["events"] == []


@pytest.mark.asyncio
async def test_superuser_who_is_not_a_member_is_locked_out(client, banks):
    a = banks["a"]
    h = {"Authorization": f"Bearer {banks['sup_token']}"}
    for method, path, body in routes(a, banks["da"], banks["doc"]):
        r = await call(client, h, method, path, body)
        assert r.status_code == 403, (method, path, r.status_code)
    mine = await client.get("/api/v1/organizations/mine", headers=h)
    assert mine.status_code == 200 and mine.json() == []


@pytest.mark.asyncio
async def test_suspended_member_is_locked_out(client, banks):
    a = banks["a"]
    r = await client.patch(f"/api/v1/organizations/{a.org_id}/members/{a.members['REVIEWER']}", headers=a.headers("ORG_ADMIN"), json={"status": "SUSPENDED"})
    assert r.status_code == 200 and r.json()["status"] == "SUSPENDED"
    for method, path, body in routes(a, banks["da"], banks["doc"]):
        res = await call(client, a.headers("REVIEWER"), method, path, body)
        assert res.status_code == 403, (method, path)
    mine = await client.get("/api/v1/organizations/mine", headers=a.headers("REVIEWER"))
    assert mine.json() == []


@pytest.mark.asyncio
async def test_lists_only_contain_own_rows(client, banks):
    a, b = banks["a"], banks["b"]
    for ws, other in ((a, b), (b, a)):
        h = ws.headers("ORG_ADMIN")
        for path, key in (("items", "items"), ("tasks", "tasks")):
            rows = (await client.get(f"{base(ws)}/{path}", headers=h)).json()[key]
            assert rows and all(r["organization_id"] == ws.org_id for r in rows)
        regs = (await client.get(f"{base(ws)}/registers", headers=h, params={"include_archived": "true"})).json()
        assert regs and all(r["organization_id"] == ws.org_id for r in regs)
        assert all(d["organization_id"] == ws.org_id for d in (await client.get(f"/api/v1/organizations/{ws.org_id}/departments", headers=h)).json())
        assert all(m["organization_id"] == ws.org_id for m in (await client.get(f"/api/v1/organizations/{ws.org_id}/members", headers=h)).json())
        rep = (await client.get(f"{base(ws)}/report", headers=h)).json()
        assert rep["organization"]["id"] == ws.org_id and all(i["organization_id"] == ws.org_id for i in rep["items"])
        log = (await client.get(f"{base(ws)}/audit", headers=h, params={"limit": 500})).json()["events"]
        assert log
        mine = (await client.get("/api/v1/organizations/mine", headers=h)).json()
        assert [o["id"] for o in mine] == [ws.org_id]
        assert other.org_id not in str(mine)


@pytest.mark.asyncio
async def test_same_file_is_stored_per_bank_and_downloads_stay_separate(client, banks):
    a, b = banks["a"], banks["b"]
    async with AsyncSessionLocal() as db:
        ev_a = await db.get(TaskEvidence, uuid.UUID(banks["da"]["evidence"]))
        ev_b = await db.get(TaskEvidence, uuid.UUID(banks["db"]["evidence"]))
    pa, pb = ev_a.storage_path.replace("\\", "/"), ev_b.storage_path.replace("\\", "/")
    assert f"evidence/{a.org_id}/" in pa and f"evidence/{b.org_id}/" in pb
    assert pa != pb and ev_a.file_sha256 == ev_b.file_sha256

    for ws, ids in ((a, banks["da"]), (b, banks["db"])):
        r = await client.get(f"{base(ws)}/tasks/{ids['task']}/evidence/{ids['evidence']}/download", headers=ws.headers("ORG_ADMIN"))
        assert r.status_code == 200 and r.content == PDF
    # B's path with A's evidence id (and A's task id) finds nothing
    for tid in (banks["db"]["task"], banks["da"]["task"]):
        r = await client.get(f"{base(b)}/tasks/{tid}/evidence/{banks['da']['evidence']}/download", headers=b.headers("ORG_ADMIN"))
        assert r.status_code == 404
    # and B's own task with A's evidence id
    r = await client.get(f"{base(b)}/tasks/{banks['db']['task']}/evidence/{banks['da']['evidence']}/download", headers=b.headers("ORG_ADMIN"))
    assert r.status_code == 404
