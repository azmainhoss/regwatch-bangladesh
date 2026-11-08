import uuid
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app


@pytest.mark.asyncio
async def test_document_ingestion_and_provenance():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register an authorized ingestion user
        unique_id = uuid.uuid4().hex[:6]
        user_resp = await client.post("/api/v1/auth/register", json={
            "email": f"ingest_admin_{unique_id}@regwatch.bd",
            "password": "SecurePassword123!",
            "full_name": "Ingestion Operator"
        })
        assert user_resp.status_code == 201
        token = user_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Get BB institution ID
        inst_resp = await client.get("/api/v1/institutions")
        bb = next(i for i in inst_resp.json() if i["code"] == "BB")
        bb_id = bb["id"]
        brpd_dept = next(d for d in bb["departments"] if d["code"] == "BRPD")
        brpd_id = brpd_dept["id"]

        pdf_path = Path("backend/app/tests/fixtures/corpus/bb_brpd_2024_15.pdf")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # 2. Test: Unauthenticated upload MUST be rejected with 401
        files = {"file": ("bb_brpd_2024_15.pdf", pdf_bytes, "application/pdf")}
        data = {
            "institution_id": bb_id,
            "department_id": brpd_id,
            "reference_number": f"BRPD Circular No. 15/{unique_id}",
            "title": "Master Policy on Loan Classification and Provisioning Alignment with IFRS 9",
            "document_type": "CIRCULAR",
            "publication_date": "2024-11-27",
            "effective_date": "2025-01-01",
            "source_url": "https://www.bb.org.bd/mediaroom/circulars/brpd/nov272024brpd15e.pdf"
        }
        unauth_resp = await client.post("/api/v1/documents/upload", files=files, data=data)
        assert unauth_resp.status_code == 401

        # 3. Test: Non-PDF file upload MUST be rejected with 400
        fake_files = {"file": ("malicious.pdf", b"NOT A REAL PDF FILE HEADER", "application/pdf")}
        bad_format_resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=fake_files, data=data)
        assert bad_format_resp.status_code == 400
        assert "PDF header signature" in bad_format_resp.json()["detail"]

        # 4. Authenticated Upload: BRPD Circular 15
        upload_resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files, data=data)
        assert upload_resp.status_code == 201
        res = upload_resp.json()
        doc = res["document"]
        version = res["version"]
        assert doc["title"] == "Master Policy on Loan Classification and Provisioning Alignment with IFRS 9"
        assert doc["publication_status"] in ["EXTRACTED", "AWAITING_REVIEW", "PUBLISHED_MACHINE_PROCESSED"]
        assert res["pages_extracted"] == 2
        assert len(version["file_sha256"]) == 64
        assert version["version_number"] == 1

        doc_id = doc["id"]
        version_id = version["id"]

        # 5. Page-level extraction verification
        pages_resp = await client.get(f"/api/v1/documents/{doc_id}/versions/{version_id}/pages")
        assert pages_resp.status_code == 200
        pages = pages_resp.json()
        assert len(pages) == 2
        assert pages[0]["page_number"] == 1
        assert "BANGLADESH BANK" in pages[0]["raw_text"]
        assert "IFRS 9" in pages[0]["raw_text"]

        assert pages[1]["page_number"] == 2
        assert "Annexure: Reporting Template" in pages[1]["raw_text"]

        # 6. Stream original PDF
        pdf_stream_resp = await client.get(f"/api/v1/documents/{doc_id}/pdf")
        assert pdf_stream_resp.status_code == 200
        assert pdf_stream_resp.headers["Content-Type"] == "application/pdf"
        assert pdf_stream_resp.headers["X-SHA256-Checksum"] == version["file_sha256"]
        assert len(pdf_stream_resp.content) == len(pdf_bytes)

        # 7. Upload duplicate file -> verify idempotency / deduplication
        files_dup = {"file": ("bb_brpd_2024_15_duplicate.pdf", pdf_bytes, "application/pdf")}
        dup_resp = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files_dup, data=data)
        assert dup_resp.status_code == 201
        dup_res = dup_resp.json()
        assert dup_res["version"]["id"] == version_id
        assert dup_res["version"]["file_sha256"] == version["file_sha256"]

        # 8. Upload second document: BRPD Circular 16
        pdf_path_16 = Path("backend/app/tests/fixtures/corpus/bb_brpd_2024_16.pdf")
        with open(pdf_path_16, "rb") as f2:
            pdf_bytes_16 = f2.read()

        files_16 = {"file": ("bb_brpd_2024_16.pdf", pdf_bytes_16, "application/pdf")}
        data_16 = {
            "institution_id": bb_id,
            "department_id": brpd_id,
            "reference_number": f"BRPD Circular No. 16/{unique_id}",
            "title": "Guidelines on Ultimate Beneficial Ownership (UBO) Disclosure",
            "document_type": "GUIDELINE",
            "publication_date": "2024-12-01",
            "source_url": "https://www.bb.org.bd/mediaroom/circulars/brpd/dec012024brpd16e.pdf"
        }
        upload_resp_16 = await client.post("/api/v1/documents/upload", headers=auth_headers, files=files_16, data=data_16)
        assert upload_resp_16.status_code == 201

        # 9. Filter and search documents
        list_search = await client.get("/api/v1/documents?search=IFRS")
        assert list_search.status_code == 200
        docs_found = list_search.json()
        assert len(docs_found) >= 1
        assert any("IFRS" in d["title"] for d in docs_found)
