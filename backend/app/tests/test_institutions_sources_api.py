import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app


@pytest.mark.asyncio
async def test_institutions_and_sources_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List institutions (already seeded with BB)
        resp = await client.get("/api/v1/institutions")
        assert resp.status_code == 200
        inst_list = resp.json()
        assert len(inst_list) >= 1
        bb = next((i for i in inst_list if i["code"] == "BB"), None)
        assert bb is not None
        assert "departments" in bb
        assert len(bb["departments"]) >= 6

        # 2. Create another institution (e.g. BSEC or test code)
        import uuid
        test_code = f"T_{uuid.uuid4().hex[:4].upper()}"
        nbr_payload = {
            "code": test_code,
            "name": "Bangladesh Securities and Exchange Commission",
            "name_bn": "বাংলাদেশ সিকিউরিটিজ অ্যান্ড এক্সচেঞ্জ কমিশন",
            "website_url": "https://sec.gov.bd",
            "is_active": True
        }
        create_resp = await client.post("/api/v1/institutions", json=nbr_payload)
        assert create_resp.status_code == 201
        nbr_data = create_resp.json()
        assert nbr_data["code"] == test_code

        # 3. Add department to NBR
        dept_payload = {
            "code": "CUSTOMS",
            "name": "Customs & Modernization",
            "name_bn": "শুল্ক আধুনিকায়ন"
        }
        dept_resp = await client.post(f"/api/v1/institutions/{nbr_data['id']}/departments", json=dept_payload)
        assert dept_resp.status_code == 201
        assert dept_resp.json()["code"] == "CUSTOMS"

        # 4. Sources API
        sources_resp = await client.get("/api/v1/sources")
        assert sources_resp.status_code == 200
        sources = sources_resp.json()
        assert len(sources) >= 1
