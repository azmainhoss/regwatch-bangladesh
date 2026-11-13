"""Private uploads: only the uploader can see them; only superusers add to the shared library."""
import json
import uuid

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.providers.base import LLMResponse
from backend.app.modules.research.service import ResearchService
from backend.app.tests.factories import make_document, make_institution, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_pdf(text_body: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text_body)
    data = doc.tobytes()
    doc.close()
    return data


async def _upload(client, token, institution_id, title, body, visibility=None, reference=None):
    data = {
        "institution_id": str(institution_id),
        "title": title,
        "publication_date": "2026-03-01",
        "reference_number": reference or f"PRIV-{uuid.uuid4().hex[:6]}",
    }
    if visibility is not None:
        data["visibility"] = visibility
    return await client.post(
        "/api/v1/documents/upload",
        data=data,
        files={"file": ("circular.pdf", _make_pdf(body), "application/pdf")},
        headers=_auth(token),
    )


class _EchoProvider:
    """Stands in for the AI provider; the research service still returns the citations it searched."""

    async def generate_structured_json(self, **kwargs):
        return LLMResponse(raw_content="", model_name="x", success=False, error="offline")


@pytest.mark.asyncio
async def test_private_upload_is_only_visible_to_its_owner(client, monkeypatch):
    inst = await make_institution()
    user_a, token_a = await make_user()
    _user_b, token_b = await make_user()
    _admin, token_admin = await make_user(is_superuser=True)
    secret = f"zq{uuid.uuid4().hex[:10]}"
    title = f"Private memo {secret}"

    resp = await _upload(client, token_a, inst.id, title, f"Banks must file the {secret} return monthly.")
    assert resp.status_code == 201, resp.text
    doc = resp.json()["document"]
    doc_id, version_id = doc["id"], doc["current_version_id"]
    assert doc["owner_user_id"] == str(user_a.id)
    assert doc["is_private"] is True

    # Owner sees it everywhere.
    listed = await client.get("/api/v1/documents", params={"search": secret, "corpus_type": "ALL"}, headers=_auth(token_a))
    assert [d["id"] for d in listed.json()] == [doc_id]
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=_auth(token_a))).status_code == 200
    pages = await client.get(f"/api/v1/documents/{doc_id}/versions/{version_id}/pages", headers=_auth(token_a))
    assert pages.status_code == 200 and pages.json()

    # Another user, a superuser and an anonymous caller all get nothing / 404.
    for headers in (_auth(token_b), _auth(token_admin), {}):
        listed = await client.get("/api/v1/documents", params={"search": secret, "corpus_type": "ALL"}, headers=headers)
        assert listed.status_code == 200 and listed.json() == []
        for path in (
            f"/api/v1/documents/{doc_id}",
            f"/api/v1/documents/{doc_id}/versions/{version_id}/pages",
            f"/api/v1/documents/{doc_id}/versions/{version_id}/tables",
            f"/api/v1/documents/{doc_id}/versions/{version_id}/report",
            f"/api/v1/documents/{doc_id}/pdf",
            f"/api/v1/documents/{doc_id}/analysis",
            f"/api/v1/documents/{doc_id}/provisions",
            f"/api/v1/documents/{doc_id}/obligations",
            f"/api/v1/documents/{doc_id}/relationships",
        ):
            assert (await client.get(path, headers=headers)).status_code == 404, path

    # Stats count it for the owner only.
    stats_a = (await client.get("/api/v1/documents/stats", headers=_auth(token_a))).json()
    stats_b = (await client.get("/api/v1/documents/stats", headers=_auth(token_b))).json()
    assert stats_a["total_documents"] == stats_b["total_documents"] + 1

    # Research: the owner's question can cite it, other users' questions cannot.
    monkeypatch.setattr("backend.app.modules.research.service.get_answer_provider", lambda *a, **k: _EchoProvider())
    question = {"query": f"What is the {secret} return?"}
    res_a = await client.post("/api/v1/research/query", json=question, headers=_auth(token_a))
    assert any(c["document_title"] == title for c in res_a.json()["citations"])
    res_b = await client.post("/api/v1/research/query", json=question, headers=_auth(token_b))
    assert res_b.status_code == 200
    assert not any(c["document_title"] == title for c in res_b.json()["citations"])
    scoped = await client.post("/api/v1/research/query", json={**question, "document_id": doc_id}, headers=_auth(token_b))
    assert scoped.json()["citations"] == []

    # A superuser cannot even see another user's private circular, so publishing it is a 404.
    publish = await client.post(
        f"/api/v1/documents/{doc_id}/publish",
        json={"decision": "PUBLISHED_HUMAN_REVIEWED", "review_notes": "ok"},
        headers=_auth(token_admin),
    )
    assert publish.status_code == 404


@pytest.mark.asyncio
async def test_non_superuser_cannot_upload_to_shared_library(client):
    inst = await make_institution()
    _user, token = await make_user()
    resp = await _upload(client, token, inst.id, "Attempted shared upload", "Shared attempt body", visibility="shared")
    assert resp.status_code == 403
    bad = await _upload(client, token, inst.id, "Bad visibility", "Bad visibility body", visibility="public")
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_superuser_shared_upload_is_visible_to_everyone(client):
    inst = await make_institution()
    _admin, token_admin = await make_user(is_superuser=True)
    _user, token_user = await make_user()
    marker = f"sh{uuid.uuid4().hex[:10]}"

    resp = await _upload(client, token_admin, inst.id, f"Shared circular {marker}", f"Shared {marker} rule")
    assert resp.status_code == 201, resp.text
    doc = resp.json()["document"]
    assert doc["owner_user_id"] is None and doc["is_private"] is False

    for headers in (_auth(token_user), {}):
        got = await client.get(f"/api/v1/documents/{doc['id']}", headers=headers)
        assert got.status_code == 200
        listed = await client.get("/api/v1/documents", params={"search": marker, "corpus_type": "ALL"}, headers=headers)
        assert [d["id"] for d in listed.json()] == [doc["id"]]

    # Superusers can still choose a private upload.
    private = await _upload(client, token_admin, inst.id, f"Admin private {marker}", f"Admin private {marker} note", visibility="private")
    assert private.status_code == 201
    assert private.json()["document"]["is_private"] is True
    publish_own = await client.post(
        f"/api/v1/documents/{private.json()['document']['id']}/publish",
        json={"decision": "PUBLISHED_HUMAN_REVIEWED", "review_notes": "ok"},
        headers=_auth(token_admin),
    )
    assert publish_own.status_code == 400
    other = await client.get(f"/api/v1/documents/{private.json()['document']['id']}", headers=_auth(token_user))
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_same_file_private_and_shared_stay_separate(client):
    """A private upload of a file already in the shared library gets its own private copy, and vice versa."""
    inst = await make_institution()
    _admin, token_admin = await make_user(is_superuser=True)
    user_a, token_a = await make_user()
    _user_b, token_b = await make_user()
    body = f"Identical circular body {uuid.uuid4().hex}"
    pdf = _make_pdf(body)

    async def post(token, title, visibility=None):
        data = {"institution_id": str(inst.id), "title": title, "publication_date": "2026-03-01", "reference_number": "SAME-REF-1"}
        if visibility:
            data["visibility"] = visibility
        return await client.post(
            "/api/v1/documents/upload", data=data,
            files={"file": ("c.pdf", pdf, "application/pdf")}, headers=_auth(token),
        )

    private_a = (await post(token_a, "A's copy")).json()["document"]
    shared = (await post(token_admin, "Shared copy")).json()["document"]
    private_b = (await post(token_b, "B's copy")).json()["document"]
    again_a = (await post(token_a, "A's copy again")).json()["document"]

    assert shared["owner_user_id"] is None
    assert private_a["owner_user_id"] == str(user_a.id)
    assert len({private_a["id"], shared["id"], private_b["id"]}) == 3
    # Re-uploading the same file inside the same scope reuses the existing document.
    assert again_a["id"] == private_a["id"]


@pytest.mark.asyncio
async def test_research_service_without_user_only_searches_shared(monkeypatch):
    secret = f"rs{uuid.uuid4().hex[:10]}"
    owner, _ = await make_user()
    doc, _version, _pages = await make_document()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE document_pages SET cleaned_text = :t WHERE document_version_id = :v"),
            {"t": f"The {secret} limit applies.", "v": str(doc.current_version_id)},
        )
        await db.execute(
            text("UPDATE documents SET owner_user_id = :o WHERE id = :d"),
            {"o": str(owner.id), "d": str(doc.id)},
        )
        await db.commit()
    monkeypatch.setattr("backend.app.modules.research.service.get_answer_provider", lambda *a, **k: _EchoProvider())
    async with AsyncSessionLocal() as db:
        anonymous = await ResearchService.query_regulatory_knowledge(db=db, query=f"What is the {secret} limit?")
        as_owner = await ResearchService.query_regulatory_knowledge(db=db, query=f"What is the {secret} limit?", user=owner)
    assert not any(c.reference_number == doc.reference_number for c in anonymous.citations)
    assert any(c.reference_number == doc.reference_number for c in as_owner.citations)


@pytest.mark.asyncio
async def test_pages_endpoint_tolerates_json_stored_as_text(client):
    """Seed imports used to store page tables/layout as JSON text; the pages endpoint must still answer."""
    doc, version, _pages = await make_document(pages=1)
    tables_text = json.dumps([{"table_index": 1, "headers": ["a"], "rows": [["1"]]}])
    layout_text = json.dumps({"clauses": [], "subject": None, "annexures": []})
    async with AsyncSessionLocal() as db:
        # Store each value as a JSON string, the way the old seed import did.
        await db.execute(
            text("UPDATE document_pages SET extracted_tables = :t, layout_hierarchy = :l, has_tables = 1 WHERE document_version_id = :v"),
            {"t": json.dumps(tables_text), "l": json.dumps(layout_text), "v": str(version.id)},
        )
        await db.commit()

    resp = await client.get(f"/api/v1/documents/{doc.id}/versions/{version.id}/pages")
    assert resp.status_code == 200, resp.text
    page = resp.json()[0]
    assert isinstance(page["extracted_tables"], list) and page["extracted_tables"][0]["table_index"] == 1
    assert page["layout_hierarchy"] == {"clauses": [], "subject": None, "annexures": []}

    tables = await client.get(f"/api/v1/documents/{doc.id}/versions/{version.id}/tables")
    assert tables.status_code == 200 and tables.json()[0]["page_number"] == 1


def test_seed_import_decodes_json_text_columns():
    from backend.scripts.import_seed_data import _decode_json_value

    assert _decode_json_value('[{"a": 1}]') == [{"a": 1}]
    assert _decode_json_value("{}") == {}
    assert _decode_json_value([1]) == [1]
