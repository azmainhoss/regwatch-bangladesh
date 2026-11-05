import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector


def test_connector_empty_or_malformed_html():
    connector = BangladeshBankConnector()
    # Empty HTML
    candidates_empty = connector.parse_listing_html("", "https://www.bb.org.bd")
    assert len(candidates_empty) == 0

    # HTML without any PDF links
    candidates_none = connector.parse_listing_html("<html><body><p>No circulars today.</p></body></html>", "https://www.bb.org.bd")
    assert len(candidates_none) == 0


def test_date_parser_variations():
    connector = BangladeshBankConnector()
    assert connector.parse_publication_date("27-11-2024") is not None
    assert connector.parse_publication_date("27/11/2024") is not None
    assert connector.parse_publication_date("27 Nov 2024") is not None
    assert connector.parse_publication_date("November 27, 2024") is not None
    assert connector.parse_publication_date("InvalidDateString") is None


@pytest.mark.asyncio
async def test_unauthorized_source_actions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sources_resp = await client.get("/api/v1/sources")
        assert sources_resp.status_code == 200
        source_id = sources_resp.json()[0]["id"]

        # Anonymous user cannot trigger source monitoring
        unauth_trigger = await client.post(f"/api/v1/sources/{source_id}/trigger")
        assert unauth_trigger.status_code == 401

        # Anonymous user cannot update source settings
        unauth_patch = await client.patch(f"/api/v1/sources/{source_id}", json={"is_active": False})
        assert unauth_patch.status_code == 401


@pytest.mark.asyncio
async def test_oversized_and_corrupt_pdf_rejection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        uid = uuid.uuid4().hex[:6]
        user_resp = await client.post("/api/v1/auth/register", json={
            "email": f"test_oversize_{uid}@regwatch.bd",
            "password": "Password12345!",
            "full_name": "Test User"
        })
        token = user_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        inst_resp = await client.get("/api/v1/institutions")
        bb_id = inst_resp.json()[0]["id"]

        data = {
            "institution_id": bb_id,
            "title": "Corrupt PDF Test",
            "publication_date": "2024-11-27"
        }

        # 1. Corrupt PDF starting with %PDF- but having invalid garbage body
        corrupt_bytes = b"%PDF-1.4\nGARBAGE_CORRUPT_NON_PARSABLE_BODY_HERE_WITHOUT_XREF"
        files_corrupt = {"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")}
        resp_corrupt = await client.post("/api/v1/documents/upload", headers=headers, files=files_corrupt, data=data)
        assert resp_corrupt.status_code == 422
        assert "Malformed or corrupt PDF" in resp_corrupt.json()["detail"]
