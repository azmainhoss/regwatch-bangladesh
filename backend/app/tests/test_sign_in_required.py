"""Launch rule: nobody reads circulars without signing in. Health and sign-in stay open."""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.tests.factories import make_user


@pytest.mark.asyncio
async def test_reads_need_a_signed_in_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for path in ("/api/v1/sources", "/api/v1/summary"):
            r = await ac.get(path)
            assert r.status_code == 401, (path, r.status_code)
        # The public dashboard lists are open to visitors (opening a circular still needs Register now).
        for path in ("/api/v1/feed", "/api/v1/feed/counts", "/api/v1/institutions", "/api/v1/documents"):
            r = await ac.get(path)
            assert r.status_code == 200, (path, r.status_code)

        assert (await ac.get("/api/v1/health")).status_code == 200
        bad_login = await ac.post("/api/v1/auth/login", data={"username": "nobody@example.test", "password": "x"})
        assert bad_login.status_code != 404  # the sign-in route itself is reachable

        _user, token = await make_user()
        signed_in = {"Authorization": f"Bearer {token}"}
        for path in ("/api/v1/documents", "/api/v1/feed", "/api/v1/institutions"):
            r = await ac.get(path, headers=signed_in)
            assert r.status_code == 200, (path, r.status_code)
