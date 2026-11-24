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


def _details(email: str, phone: str = "+880 1711-000000") -> dict:
    return {"full_name": "Rahim Uddin", "email": email, "phone_number": phone,
            "company": "Example Bank PLC", "designation": "Compliance Officer"}


@pytest.mark.asyncio
async def test_new_visitor_is_signed_in_at_once_and_cannot_use_a_password(client):
    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/quick-register", json=_details(email))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == email and not body["user"]["is_superuser"]
    assert body["expires_in_seconds"] == 30 * 24 * 3600
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["phone_number"] == "+880 1711-000000"
    # The account has no known password.
    bad = await client.post(f"{API}/auth/login", json={"email": email, "password": "Password123!"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_same_email_gets_back_in_only_with_the_same_phone(client):
    email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
    assert (await client.post(f"{API}/auth/quick-register", json=_details(email))).status_code == 200
    again = await client.post(f"{API}/auth/quick-register", json=_details(email, phone="01711000000"))
    assert again.status_code == 409  # 01711000000 lacks the 880 prefix: different digits
    same = await client.post(f"{API}/auth/quick-register", json=_details(email, phone="+8801711000000"))
    assert same.status_code == 200, same.text


@pytest.mark.asyncio
async def test_password_accounts_cannot_be_taken_over_by_quick_register(client):
    email = f"pw_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/register", json={"email": email, "password": "Password123!", "full_name": "P"})
    assert r.status_code == 201, r.text
    q = await client.post(f"{API}/auth/quick-register", json=_details(email))
    assert q.status_code == 409 and "sign in" in q.json()["detail"].lower()


@pytest.mark.asyncio
async def test_all_five_details_are_required(client):
    d = _details(f"lead_{uuid.uuid4().hex[:8]}@example.com")
    for field in ("full_name", "email", "phone_number", "company", "designation"):
        partial = {k: v for k, v in d.items() if k != field}
        assert (await client.post(f"{API}/auth/quick-register", json=partial)).status_code == 422, field
    assert (await client.post(f"{API}/auth/quick-register", json={**d, "phone_number": "abc"})).status_code == 422


@pytest.mark.asyncio
async def test_visitors_see_the_dashboard_lists_but_not_a_circular(client):
    for path in ("/feed?limit=5", "/feed/counts", "/feed/topics", "/institutions"):
        r = await client.get(f"{API}{path}")
        assert r.status_code == 200, (path, r.text)
    # Opening a circular, its pages or its PDF still needs an account.
    any_id = "00000000-0000-0000-0000-000000000001"
    assert (await client.get(f"{API}/documents/{any_id}")).status_code == 401
    assert (await client.get(f"{API}/documents/{any_id}/pdf")).status_code == 401


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
