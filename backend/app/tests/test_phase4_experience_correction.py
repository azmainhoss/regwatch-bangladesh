import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from backend.app.main import app
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector


@pytest.mark.asyncio
async def test_bangladesh_bank_table_parsing_high_fidelity():
    """
    Validates Phase 4: Bangladesh Bank HTML table row parser extracts
    real dates, references, and PDF download links.
    """
    sample_html = """
    <table>
      <tr>
        <th>Date</th><th>Title</th><th>English</th><th>Bangla</th>
      </tr>
      <tr>
        <td>05/11/26</td>
        <td>BRPD-1 Circular Letter No. 37: Pre-Finance Scheme to support the closed industry and service sectors.</td>
        <td>Not Available</td>
        <td><a href="https://www.bb.org.bd/mediaroom/circulars/brpd/nov052026brpd-1l37.pdf" target="_blank">Download</a></td>
      </tr>
      <tr>
        <td>04/11/26</td>
        <td>FEPD-2 Circular No. 10: Foreign Currency custodial account facilities and secure transport guidelines for licensed Money Changers</td>
        <td><a href="https://www.bb.org.bd/mediaroom/circulars/fepd-2/nov042026fepd-210e.pdf" target="_blank">Download</a></td>
        <td>Not Available</td>
      </tr>
    </table>
    """
    connector = BangladeshBankConnector()
    candidates = connector.parse_listing_html(sample_html, "https://www.bb.org.bd/en/index.php/mediaroom/circular")

    assert len(candidates) == 2

    # Candidate 1: BRPD-1
    c1 = candidates[0]
    assert c1.reference_number == "BRPD-1 Circular Letter No. 37"
    assert c1.department_code == "BRPD"
    assert str(c1.publication_date) == "2026-11-05"
    assert c1.file_url == "https://www.bb.org.bd/mediaroom/circulars/brpd/nov052026brpd-1l37.pdf"
    assert c1.metadata.get("language") == "Bangla"

    # Candidate 2: FEPD-2
    c2 = candidates[1]
    assert c2.reference_number == "FEPD-2 Circular No. 10"
    assert c2.department_code == "FEPD"
    assert str(c2.publication_date) == "2026-11-04"
    assert c2.file_url == "https://www.bb.org.bd/mediaroom/circulars/fepd-2/nov042026fepd-210e.pdf"
    assert c2.metadata.get("language") == "English"


@pytest.mark.asyncio
async def test_genuine_documents_honest_publication_status():
    """
    Validates Phase 5: Genuine Bangladesh Bank circulars are honestly categorized
    and unreviewed machine extractions (like SMESPD) remain PUBLISHED_MACHINE_PROCESSED
    without false claims of human review.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/documents?corpus_type=GENUINE")
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) >= 4

        # SMESPD Circular No. 05/2026 must be honestly marked as machine processed/verified
        smespd = next((d for d in docs if "05/2026" in (d.get("reference_number") or "")), None)
        if smespd:
            assert smespd["publication_status"] in ("PUBLISHED_MACHINE_PROCESSED", "PUBLISHED_MACHINE_VERIFIED")

        # All documents must carry valid production publication statuses
        for d in docs:
            assert d["publication_status"] in (
                "PUBLISHED_MACHINE_PROCESSED",
                "PUBLISHED_MACHINE_VERIFIED",
                "PUBLISHED_HUMAN_REVIEWED",
                "EXTRACTED",
                "AWAITING_REVIEW"
            )


@pytest.mark.asyncio
async def test_authenticated_regulatory_qa():
    """
    Validates Phase 6: Grounded Regulatory Q&A executes with a verified
    banking professional token (CCO account) and returns grounded citations.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Log in as Chief Compliance Officer
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "cco@abcbank.bd",
            "password": "CCOPassword123!"
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get SMESPD circular ID
        docs_res = await client.get("/api/v1/documents?corpus_type=GENUINE")
        docs = docs_res.json()
        smespd_doc = next(d for d in docs if "SMESPD" in (d.get("reference_number") or ""))

        # 3. Query the assistant
        qa_res = await client.post("/api/v1/research/query", headers=headers, json={
            "query": "What are the eligibility criteria for trainees in entrepreneurship development program?",
            "document_id": smespd_doc["id"]
        })
        assert qa_res.status_code == 200
        data = qa_res.json()
        assert data["is_grounded"] is True
        assert len(data["answer"]) > 10
        assert len(data["citations"]) > 0
        assert any(c["page_number"] > 0 for c in data["citations"])


@pytest.mark.asyncio
async def test_unauthenticated_qa_rejected():
    """
    Validates Phase 3 & 6: Unauthenticated research query is strictly rejected with 401.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/research/query", json={
            "query": "What are the capital requirements?"
        })
        assert res.status_code == 401
