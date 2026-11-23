"""Email a circular and assign it to a team member. Mail goes to a local fake mail server only."""
import base64
import email
from email import policy

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.tests.factories import make_user, make_workspace
from backend.app.tests.fake_smtp import FakeSMTP
from backend.app.tests.test_search_and_ask import make_real_doc

# A 1x1 PNG.
PNG = "data:image/png;base64," + base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
).decode()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mail(monkeypatch):
    s = FakeSMTP("ok").start()
    for k, v in dict(SMTP_HOST="127.0.0.1", SMTP_PORT=s.port, SMTP_FROM="alerts@regwatch.test", SMTP_USERNAME=None,
                     SMTP_PASSWORD=None, SMTP_TLS_MODE="none", APP_PUBLIC_URL="http://app.test").items():
        monkeypatch.setattr(settings, k, v)
    yield s
    s.stop()


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_email_needs_mail_set_up_but_the_file_always_works(client, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    user, token = await make_user()
    doc, _ = await make_real_doc(["Banks shall keep records."], reference="BRPD Circular No. 99")
    r = await client.post("/api/v1/share/email", json={"document_id": str(doc.id), "to": ["a@example.com"]}, headers=_auth(token))
    assert r.status_code == 409
    r = await client.post("/api/v1/share/email/file", json={"document_id": str(doc.id), "to": ["a@example.com"], "mind_map_png": PNG}, headers=_auth(token))
    assert r.status_code == 200
    msg = email.message_from_bytes(r.content, policy=policy.default)
    assert msg["To"] == "a@example.com"
    assert "BRPD Circular No. 99" in msg["Subject"]
    kinds = [p.get_content_type() for p in msg.walk()]
    assert "image/png" in kinds  # the mind map, inline


@pytest.mark.asyncio
async def test_email_is_sent_with_mind_map(client, mail):
    user, token = await make_user()
    doc, _ = await make_real_doc(["Text."], reference="DOS Circular No. 7")
    r = await client.post("/api/v1/share/email", json={"document_id": str(doc.id), "to": ["x@example.com", "y@example.com"], "note": "Please read", "mind_map_png": PNG}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 2
    _, rcpts, raw = mail.messages[-1]
    assert sorted(rcpts) == ["x@example.com", "y@example.com"]
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert "Please read" in msg.get_body(("plain",)).get_content()


@pytest.mark.asyncio
async def test_assign_only_inside_own_workspace_and_shows_for_both(client, mail):
    ws = await make_workspace({"COMPLIANCE_HEAD": None, "ANALYST": None})
    other = await make_workspace({"ANALYST": None})
    doc, _ = await make_real_doc(["Text."])
    head = ws.headers("COMPLIANCE_HEAD")
    analyst = ws.users["ANALYST"]

    team = (await client.get("/api/v1/share/team", headers=head)).json()
    assert str(analyst.id) in {m["user_id"] for m in team}
    assert str(other.users["ANALYST"].id) not in {m["user_id"] for m in team}

    r = await client.post("/api/v1/share/assign", json={"document_id": str(doc.id), "assignee_user_ids": [str(other.users["ANALYST"].id)]}, headers=head)
    assert r.status_code == 422

    r = await client.post("/api/v1/share/assign", json={"document_id": str(doc.id), "assignee_user_ids": [str(analyst.id)], "note": "Check ECL", "due_date": "2026-12-01"}, headers=head)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 1 and body["emailed"] == 1
    assert analyst.email in mail.messages[-1][1]

    mine = (await client.get("/api/v1/share/assignments", params={"scope": "mine"}, headers=ws.headers("ANALYST"))).json()
    assert [a["note"] for a in mine] == ["Check ECL"]
    a_id = mine[0]["id"]
    # Someone from another bank cannot see or change it.
    assert (await client.patch(f"/api/v1/share/assignments/{a_id}", json={"status": "DONE"}, headers=other.headers("ANALYST"))).status_code == 404
    done = await client.patch(f"/api/v1/share/assignments/{a_id}", json={"status": "DONE"}, headers=ws.headers("ANALYST"))
    assert done.json()["status"] == "DONE"
    by_me = (await client.get("/api/v1/share/assignments", params={"scope": "by_me"}, headers=head)).json()
    assert by_me[0]["status"] == "DONE"


@pytest.mark.asyncio
async def test_plans_limit_free_and_open_up_once_confirmed(client, monkeypatch):
    from backend.app.modules.plans import router as plans_router
    monkeypatch.setattr(plans_router, "ENFORCE_IN_TESTS", True)
    admin, admin_token = await make_user(is_superuser=True)
    user, token = await make_user()
    doc, _ = await make_real_doc(["Text."])

    me = (await client.get("/api/v1/plans/me", headers=_auth(token))).json()
    assert me["plan"] == "FREE" and me["questions_per_day"] == 0 and "email" in me["allows"]
    r = await client.post("/api/v1/share/email/file", json={"document_id": str(doc.id), "to": ["a@example.com"]}, headers=_auth(token))
    assert r.status_code == 200  # launch: every feature is free for everyone

    # Enterprise needs at least 20 seats and a name.
    r = await client.post("/api/v1/plans/request", json={"plan": "ENTERPRISE", "seats": 5, "organization_name": "ABC"}, headers=_auth(token))
    assert r.status_code == 422
    r = await client.post("/api/v1/plans/request", json={"plan": "PRO"}, headers=_auth(token))
    assert r.status_code == 201 and r.json()["pending_request"] == "PRO" and r.json()["plan"] == "FREE"

    reqs = (await client.get("/api/v1/plans/requests", headers=_auth(admin_token))).json()
    mine = next(x for x in reqs if x["requested_by"] == user.email)
    assert (await client.get("/api/v1/plans/requests", headers=_auth(token))).status_code == 403
    r = await client.post(f"/api/v1/plans/requests/{mine['id']}/activate", headers=_auth(admin_token))
    assert r.json()["status"] == "ACTIVE"
    assert (await client.get("/api/v1/plans/me", headers=_auth(token))).json()["plan"] == "PRO"
    r = await client.post("/api/v1/share/email/file", json={"document_id": str(doc.id), "to": ["a@example.com"]}, headers=_auth(token))
    assert r.status_code == 200
