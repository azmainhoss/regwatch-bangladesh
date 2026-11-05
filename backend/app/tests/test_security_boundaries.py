import time
from datetime import timedelta
import pytest
from httpx import ASGITransport, AsyncClient
import jwt
from backend.app.core.config import settings
from backend.app.core.security import ALGORITHM, create_access_token
from backend.app.core.storage import LocalStorageService
from backend.app.main import app


@pytest.mark.asyncio
async def test_password_length_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Passwords shorter than 8 characters MUST be rejected
        short_pass_resp = await client.post("/api/v1/auth/register", json={
            "email": "short_pass@test.bd",
            "password": "123",
            "full_name": "Test Short"
        })
        assert short_pass_resp.status_code == 422


@pytest.mark.asyncio
async def test_expired_token_rejection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generate an already-expired token (-10 minutes)
        expired_token = create_access_token(
            subject="00000000-0000-0000-0000-000000000000",
            expires_delta=timedelta(minutes=-10)
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401
        assert "Could not validate credentials" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tampered_jwt_signature_rejection():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Sign with wrong secret key
        tampered_token = jwt.encode(
            {"sub": "00000000-0000-0000-0000-000000000000", "exp": int(time.time()) + 3600},
            "completely-wrong-secret-key-12345",
            algorithm=ALGORITHM
        )
        headers = {"Authorization": f"Bearer {tampered_token}"}
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_storage_path_traversal_hard_block(tmp_path):
    storage = LocalStorageService(root_dir=str(tmp_path))
    with pytest.raises(PermissionError):
        storage.get_file_bytes("../../../etc/shadow")
    with pytest.raises(PermissionError):
        storage.get_file_bytes("/etc/passwd")

