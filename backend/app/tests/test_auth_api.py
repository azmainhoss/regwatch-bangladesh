import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app


@pytest.mark.asyncio
async def test_health_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

        # DB Health check
        db_resp = await client.get("/api/v1/health/db")
        assert db_resp.status_code == 200
        db_data = db_resp.json()
        assert db_data["status"] == "healthy"
        assert db_data["database"] == "connected"


@pytest.mark.asyncio
async def test_auth_workflow():
    import uuid
    test_email = f"officer_{uuid.uuid4().hex[:6]}@testbank.bd"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a new user
        reg_payload = {
            "email": test_email,
            "password": "SecurePassword123!",
            "full_name": "Tariqul Islam",
            "phone_number": "+8801711112233"
        }
        reg_resp = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_resp.status_code == 201
        reg_data = reg_resp.json()
        assert "access_token" in reg_data
        assert reg_data["user"]["email"] == test_email

        token = reg_data["access_token"]

        # 2. Get current user profile with token
        headers = {"Authorization": f"Bearer {token}"}
        me_resp = await client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["full_name"] == "Tariqul Islam"

        # 3. Login with credentials
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "SecurePassword123!"}
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()

        # 4. Invalid login rejected
        bad_login = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "WrongPassword!"}
        )
        assert bad_login.status_code == 401
