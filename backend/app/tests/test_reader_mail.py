"""Owner-approved reader emails (2026-11-25): password reset, one-click unsubscribe, sender and headers."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.alerts import brand, mailer, reader_mail

API = "/api/v1"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _register(client, password="Sunrise#2026"):
    email = f"mail_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/quick-register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return email, r.json()["user"]["id"]


@pytest.mark.asyncio
async def test_reset_request_answers_the_same_for_unknown_emails(client):
    email, _ = await _register(client)
    a = await client.post(f"{API}/auth/password-reset/request", json={"email": email})
    b = await client.post(f"{API}/auth/password-reset/request", json={"email": "nobody_" + email})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()


@pytest.mark.asyncio
async def test_reset_link_sets_a_new_password_once(client):
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.identity.models import User

    email, uid = await _register(client)
    async with AsyncSessionLocal() as db:
        token = reader_mail.reset_token(await db.get(User, uid))
    ok = await client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "NewPass#2026"})
    assert ok.status_code == 200, ok.text
    assert (await client.post(f"{API}/auth/login", json={"email": email, "password": "NewPass#2026"})).status_code == 200
    assert (await client.post(f"{API}/auth/login", json={"email": email, "password": "Sunrise#2026"})).status_code == 401
    # The same link cannot be used twice (the password it was signed with has changed).
    again = await client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "password": "Other#2026x"})
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_tampered_reset_token_is_refused(client):
    _, uid = await _register(client)
    bad = f"{uid}.9999999999.not-a-real-signature"
    assert (await client.post(f"{API}/auth/password-reset/confirm", json={"token": bad, "password": "NewPass#2026"})).status_code == 400


@pytest.mark.asyncio
async def test_one_click_unsubscribe_turns_the_digest_off(client):
    from sqlalchemy import select

    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.alerts import prefs
    from backend.app.modules.alerts.models import AlertPreference

    _, uid = await _register(client)
    token = reader_mail.unsubscribe_token(uid)
    assert (await client.post(f"{API}/email/unsubscribe/{token}x")).status_code == 400
    r = await client.post(f"{API}/email/unsubscribe/{token}")
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as db:
        pref = (await db.execute(select(AlertPreference).where(AlertPreference.user_id == uid))).scalar_one()
        assert prefs.channel_for(pref, "library")[1] == "OFF"
        # Other alerts are untouched.
        assert prefs.channel_for(pref, "assigned")[1] == "INSTANT"


def test_digest_message_has_sender_and_one_click_header():
    msg = mailer.build_message("a@b.test", "Subject", "text", "<p>x</p>", sender_pair=brand.INSIGHTS_FROM,
                               unsubscribe_post_url="https://amarcircular.com/api/v1/email/unsubscribe/abc.def")
    assert "insights@amarcircular.com" in msg["From"]
    assert msg["List-Unsubscribe"] == "<https://amarcircular.com/api/v1/email/unsubscribe/abc.def>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_senders_by_kind(monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "SMTP_FROM", "insights@amarcircular.com")
    monkeypatch.setattr(settings, "SMTP_ALERTS_FROM", "alerts@amarcircular.com")
    assert reader_mail.sender_for("DIGEST") == brand.INSIGHTS_FROM
    assert reader_mail.sender_for("WELCOME") == brand.INSIGHTS_FROM
    assert reader_mail.sender_for("RESET") == brand.ALERTS_FROM
    assert reader_mail.sender_for("INSTANT") == brand.ALERTS_FROM
    monkeypatch.setattr(settings, "SMTP_ALERTS_FROM", None)
    assert reader_mail.sender_for("RESET") == ("Amar Circular Alerts", "insights@amarcircular.com")
