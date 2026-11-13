import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app


@pytest.mark.asyncio
async def test_strict_multi_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create User A (Org A Admin)
        uid_a = uuid.uuid4().hex[:6]
        user_a_resp = await client.post("/api/v1/auth/register", json={
            "email": f"admin_a_{uid_a}@bankalpha.bd",
            "password": "Password123Alpha!",
            "full_name": "Alpha Bank CCO"
        })
        assert user_a_resp.status_code == 201
        token_a = user_a_resp.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # 2. Create User B (Org B Admin)
        uid_b = uuid.uuid4().hex[:6]
        user_b_resp = await client.post("/api/v1/auth/register", json={
            "email": f"admin_b_{uid_b}@bankbeta.bd",
            "password": "Password123Beta!",
            "full_name": "Beta Bank CCO"
        })
        assert user_b_resp.status_code == 201
        token_b = user_b_resp.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 3. User A creates Organization A ("Bank Alpha PLC")
        org_a_resp = await client.post(
            "/api/v1/organizations",
            headers=headers_a,
            json={"name": f"Bank Alpha PLC {uid_a}", "entity_type": "COMMERCIAL_BANK"}
        )
        assert org_a_resp.status_code == 201
        org_a_id = org_a_resp.json()["id"]

        # 4. User B creates Organization B ("Bank Beta PLC")
        org_b_resp = await client.post(
            "/api/v1/organizations",
            headers=headers_b,
            json={"name": f"Bank Beta PLC {uid_b}", "entity_type": "COMMERCIAL_BANK"}
        )
        assert org_b_resp.status_code == 201
        org_b_id = org_b_resp.json()["id"]

        # 5. User A creates a Compliance Register in Org A
        reg_a_resp = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/registers",
            headers=headers_a,
            json={"title": "Alpha BRPD 2024 Audit Register", "description": "Confidential Alpha Register"}
        )
        assert reg_a_resp.status_code == 201
        reg_a_id = reg_a_resp.json()["id"]

        # 6. ATTACK 1: User B attempts to access Org A's registers
        breach_1 = await client.get(
            f"/api/v1/organizations/{org_a_id}/compliance/registers",
            headers=headers_b
        )
        assert breach_1.status_code == 403
        assert "Cross-tenant access forbidden" in breach_1.json()["detail"]

        # 7. User A creates a Compliance Item & Task in Org A
        from backend.app.tests.factories import make_obligation, make_user
        dummy_ob_id = str((await make_obligation(verified=True, doc_status="PUBLISHED_MACHINE_PROCESSED")).id)
        item_a_resp = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/items",
            headers=headers_a,
            json={
                "register_id": reg_a_id,
                "obligation_id": dummy_ob_id,
                "internal_code": "ALPHA-CR-01",
                "status": "IN_PROGRESS"
            }
        )
        assert item_a_resp.status_code == 201
        item_a_id = item_a_resp.json()["id"]

        task_a_resp = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks",
            headers=headers_a,
            json={
                "compliance_item_id": item_a_id,
                "title": "Alpha Bank Internal Credit Policy Review",
                "due_date": "2026-12-31",
                "priority": "HIGH"
            }
        )
        assert task_a_resp.status_code == 201
        task_a_id = task_a_resp.json()["task"]["id"]

        # 8. User A uploads confidential Evidence to Task A in Org A
        evidence_content = b"%PDF-1.4 CONFIDENTIAL INTERNAL AUDIT REPORT OF BANK ALPHA"
        files = {"file": ("alpha_audit_report.pdf", evidence_content, "application/pdf")}
        data = {"notes": "Strictly confidential board review notes"}
        evidence_resp = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/evidence",
            headers=headers_a,
            files=files,
            data=data
        )
        assert evidence_resp.status_code == 201
        evidence_a_id = evidence_resp.json()["evidence"]["id"]

        # 9. ATTACK 2: User B attempts to view evidence list for Task A
        breach_2 = await client.get(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/evidence",
            headers=headers_b
        )
        assert breach_2.status_code == 403

        # 10. ATTACK 3: User B attempts to download User A's raw evidence file
        breach_3 = await client.get(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/evidence/{evidence_a_id}/download",
            headers=headers_b
        )
        assert breach_3.status_code == 403

        # 11. ATTACK 4: ID Substitution attack - User B puts their own org_b_id in path with Task A's ID
        breach_4 = await client.get(
            f"/api/v1/organizations/{org_b_id}/compliance/tasks/{task_a_id}/evidence",
            headers=headers_b
        )
        assert breach_4.status_code == 404
        assert "Task not found in this organization" in breach_4.json()["detail"]

        # 12. User A downloads their own evidence successfully
        legit_download = await client.get(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/evidence/{evidence_a_id}/download",
            headers=headers_a
        )
        assert legit_download.status_code == 200
        assert legit_download.content == evidence_content

        # 13. The uploader cannot approve their own evidence; a second member (REVIEWER) does
        self_review = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/reviews",
            headers=headers_a,
            json={"decision": "APPROVED", "comments": "Approving my own upload."}
        )
        assert self_review.status_code == 403
        reviewer, reviewer_token = await make_user()
        add_reviewer = await client.post(
            f"/api/v1/organizations/{org_a_id}/members",
            headers=headers_a,
            json={"user_id": str(reviewer.id), "role": "REVIEWER"}
        )
        assert add_reviewer.status_code == 201
        review_resp = await client.post(
            f"/api/v1/organizations/{org_a_id}/compliance/tasks/{task_a_id}/reviews",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"decision": "APPROVED", "comments": "Board committee approved policy alignment."}
        )
        assert review_resp.status_code == 201
        assert review_resp.json()["review"]["decision"] == "APPROVED"

