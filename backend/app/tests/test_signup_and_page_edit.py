"""Sign-up rules and the admin page-correction screen's backend. No test here touches the network."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.documents.models import DocumentPage
from backend.app.tests.factories import make_document, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _email() -> str:
    return f"signup_{uuid.uuid4().hex[:8]}@regwatch.bd"


@pytest.mark.asyncio
async def test_register_ignores_admin_flags_and_signs_in(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": _email(), "password": "Password123!", "full_name": "Sam Sign",
        "is_superuser": True, "is_active": False,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["is_superuser"] is False
    assert body["user"]["is_active"] is True
    me = await client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200 and me.json()["full_name"] == "Sam Sign"


@pytest.mark.asyncio
async def test_register_duplicate_email_is_a_clear_400(client):
    email = _email()
    payload = {"email": email, "password": "Password123!", "full_name": "First"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    dup = await client.post("/api/v1/auth/register", json={**payload, "email": email.upper()})
    assert dup.status_code == 400
    assert "already exists" in dup.json()["detail"]


@pytest.mark.asyncio
async def test_register_rejects_short_password_and_blank_name(client):
    short = await client.post("/api/v1/auth/register", json={
        "email": _email(), "password": "short", "full_name": "Pat"})
    assert short.status_code == 422
    blank = await client.post("/api/v1/auth/register", json={
        "email": _email(), "password": "Password123!", "full_name": "   "})
    assert blank.status_code == 422


@pytest.mark.asyncio
async def test_page_correction_is_admin_only_and_returns_the_page(client):
    _admin, admin_token = await make_user(is_superuser=True)
    _user, user_token = await make_user(is_superuser=False)
    doc, version, _ = await make_document()
    url = f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct"
    body = {"corrected_text": "  Typed by a person  ", "correction_notes": "Page was blank"}

    assert (await client.post(url, json=body)).status_code in (401, 403)
    assert (await client.post(url, headers=_auth(user_token), json=body)).status_code == 403

    ok = await client.post(url, headers=_auth(admin_token), json=body)
    assert ok.status_code == 200
    page = ok.json()["page"]
    assert page["human_corrected_text"] == "Typed by a person"
    assert page["is_human_corrected"] is True
    assert page["quality_status"] == "SUCCESS_NORMALIZED"

    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(DocumentPage).where(
            DocumentPage.document_version_id == version.id, DocumentPage.page_number == 1))).scalar_one()
        assert row.human_corrected_text == "Typed by a person"


@pytest.mark.asyncio
async def test_page_correction_fixes_a_page_waiting_to_be_read(client):
    _admin, admin_token = await make_user(is_superuser=True)
    doc, version, _ = await make_document()
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(DocumentPage).where(
            DocumentPage.document_version_id == version.id, DocumentPage.page_number == 1))).scalar_one()
        row.raw_text = ""
        row.cleaned_text = ""
        row.quality_status = "PENDING_VISION"
        row.vision_error = "timeout"
        await db.commit()

    resp = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        headers=_auth(admin_token), json={"corrected_text": "Typed text", "correction_notes": "Scanned page"},
    )
    assert resp.status_code == 200
    page = resp.json()["page"]
    assert page["quality_status"] == "SUCCESS_NORMALIZED" and page["vision_error"] is None


@pytest.mark.asyncio
async def test_page_correction_rejects_empty_text(client):
    _admin, admin_token = await make_user(is_superuser=True)
    doc, version, _ = await make_document()
    resp = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        headers=_auth(admin_token), json={"corrected_text": "   ", "correction_notes": "x"},
    )
    assert resp.status_code == 422
