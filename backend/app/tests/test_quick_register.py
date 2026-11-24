"""'Register now' on the public site: no password, five details, signed in at once."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app

API = "/api/v1"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _details(email: str, phone: str = "+880 1711-000000", password: str = "Sunrise#2026") -> dict:
    return {"full_name": "Rahim Uddin", "email": email, "phone_number": phone,
            "company": "Example Bank PLC", "designation": "Compliance Officer", "password": password}


@pytest.mark.asyncio
async def test_register_signs_in_at_once_and_the_password_works_next_time(client):
    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/quick-register", json=_details(email))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == email and not body["user"]["is_superuser"]
    assert body["expires_in_seconds"] == 30 * 24 * 3600
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["phone_number"] == "+880 1711-000000"
    ok = await client.post(f"{API}/auth/login", json={"email": email, "password": "Sunrise#2026"})
    assert ok.status_code == 200 and ok.json()["expires_in_seconds"] == 30 * 24 * 3600
    bad = await client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_same_email_cannot_register_twice_and_is_told_to_sign_in(client):
    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    assert (await client.post(f"{API}/auth/quick-register", json=_details(email))).status_code == 200
    again = await client.post(f"{API}/auth/quick-register", json=_details(email, password="Another#2026"))
    assert again.status_code == 409 and "sign in" in again.json()["detail"].lower()
    # The first password still works; the second attempt changed nothing.
    assert (await client.post(f"{API}/auth/login", json={"email": email, "password": "Sunrise#2026"})).status_code == 200


@pytest.mark.asyncio
async def test_password_accounts_cannot_be_taken_over_by_quick_register(client):
    email = f"pw_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/register", json={"email": email, "password": "Password123!", "full_name": "P"})
    assert r.status_code == 201, r.text
    q = await client.post(f"{API}/auth/quick-register", json=_details(email))
    assert q.status_code == 409 and "sign in" in q.json()["detail"].lower()


@pytest.mark.asyncio
async def test_email_and_password_are_required_the_rest_is_optional(client):
    d = _details(f"lead_{uuid.uuid4().hex[:8]}@example.com")
    for field in ("email", "password"):
        partial = {k: v for k, v in d.items() if k != field}
        assert (await client.post(f"{API}/auth/quick-register", json=partial)).status_code == 422, field
    assert (await client.post(f"{API}/auth/quick-register", json={**d, "phone_number": "abc"})).status_code == 422
    assert (await client.post(f"{API}/auth/quick-register", json={**d, "password": "short"})).status_code == 422
    # Step 1 of the 3-step sign-up: email and password alone make the account.
    step1 = await client.post(f"{API}/auth/quick-register", json={"email": d["email"], "password": d["password"]})
    assert step1.status_code == 200, step1.text


@pytest.mark.asyncio
async def test_steps_two_and_three_fill_in_the_profile(client):
    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/quick-register", json={"email": email, "password": "Sunrise#2026"})
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    s2 = await client.patch(f"{API}/auth/me/profile", json={"full_name": "Rahim Uddin", "phone_number": "+880 1711-000000"}, headers=auth)
    assert s2.status_code == 200, s2.text
    assert s2.json()["full_name"] == "Rahim Uddin" and s2.json()["phone_number"] == "+880 1711-000000"
    s3 = await client.patch(f"{API}/auth/me/profile", json={"company": "Example Bank PLC", "designation": "Compliance Officer"}, headers=auth)
    assert s3.status_code == 200, s3.text
    assert (await client.patch(f"{API}/auth/me/profile", json={"phone_number": "abc"}, headers=auth)).status_code == 422
    assert (await client.patch(f"{API}/auth/me/profile", json={"full_name": "X"})).status_code == 401


@pytest.mark.asyncio
async def test_visitors_see_the_dashboard_lists_and_can_open_shared_circulars(client):
    for path in ("/feed?limit=5", "/feed/counts", "/feed/topics", "/institutions"):
        r = await client.get(f"{API}{path}")
        assert r.status_code == 200, (path, r.text)
    # Visitors may open shared circulars (the site counts 3 free ones); an unknown id is simply not found.
    any_id = "00000000-0000-0000-0000-000000000001"
    assert (await client.get(f"{API}/documents/{any_id}")).status_code == 404
    # The admin progress page still needs an administrator.
    assert (await client.get(f"{API}/summary")).status_code == 401


@pytest.mark.asyncio
async def test_admin_sees_signups_with_all_details_and_others_cannot(client):
    from backend.app.tests.factories import make_user

    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    lead = await client.post(f"{API}/auth/quick-register", json=_details(email))
    lead_token = lead.json()["access_token"]
    assert (await client.get(f"{API}/auth/admin/signups")).status_code == 401
    assert (await client.get(f"{API}/auth/admin/signups", headers={"Authorization": f"Bearer {lead_token}"})).status_code == 403

    admin, tok = await make_user(is_superuser=True)
    admin_email = admin.email
    rows = (await client.get(f"{API}/auth/admin/signups", headers={"Authorization": f"Bearer {tok}"})).json()
    mine = [r for r in rows if r["email"] == email]
    assert len(mine) == 1
    assert mine[0]["company"] == "Example Bank PLC" and mine[0]["designation"] == "Compliance Officer"
    assert mine[0]["phone_number"] == "+880 1711-000000" and mine[0]["registered_at"]
    assert all(r["email"] != admin_email for r in rows)  # password accounts are not sign-ups


@pytest.mark.asyncio
async def test_ask_without_an_answer_service_is_not_a_server_error(client, monkeypatch):
    from backend.app.modules.research import service as research_service

    def boom():
        raise ValueError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(research_service, "get_answer_provider", boom)
    r = await client.post(f"{API}/auth/quick-register", json=_details(f"lead_{uuid.uuid4().hex[:8]}@example.com"))
    tok = r.json()["access_token"]
    res = await client.post(f"{API}/research/query", json={"query": "What is the provision rate for SMA loans?"},
                            headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code != 500, res.text
