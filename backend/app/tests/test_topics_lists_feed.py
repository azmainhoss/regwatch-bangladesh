"""Subject categories, saved lists (Favourites, Read later, own lists), the home feed and stronger search.

Nothing here touches the network: the classifier's reply parser is tested on its own.
"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.library.feed import period_start
from backend.app.modules.topics.classify import parse_reply
from backend.app.modules.topics.models import DocumentTopic
from backend.app.modules.topics.taxonomy import topics_for, words_for
from backend.app.tests.factories import make_user, signed_in_reader
from backend.app.tests.test_search_and_ask import make_real_doc


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await signed_in_reader(ac)
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_short_forms_expand_both_ways():
    assert "expected credit loss" in words_for("ECL")
    assert "ECL" in words_for("Expected Credit Loss")
    assert words_for("the") == []
    assert topics_for("ecl") == ["ECL"]
    assert "PROVISION" in topics_for("provisioning")


def test_reply_parser_keeps_known_codes_only():
    got = parse_reply('{"results":[{"n":1,"topics":["ECL","provision","MADE_UP"]},{"n":2,"topics":["OTHER","AML"]},{"n":9,"topics":["AML"]}]}', 2)
    assert got == {1: ["ECL", "PROVISION"], 2: ["AML"]}
    assert parse_reply("not json", 2) == {}
    assert parse_reply('{"results":[{"n":1,"topics":[]}]}', 1) == {1: ["OTHER"]}


def test_period_starts():
    thu = date(2026, 11, 19)  # a Thursday
    assert period_start("today", thu) == thu
    assert period_start("week", thu) == date(2026, 11, 15)  # Sunday
    assert period_start("week", date(2026, 11, 15)) == date(2026, 11, 15)
    assert period_start("month", thu) == date(2026, 11, 1)
    assert period_start(None, thu) is None


@pytest.mark.asyncio
async def test_search_finds_ecl_by_spelled_out_name_and_by_category(client):
    tok = "zq" + uuid.uuid4().hex[:8]
    spelled, _ = await make_real_doc([f"Banks shall measure expected credit loss {tok} on every loan."])
    tagged, _ = await make_real_doc([f"Rules on staging {tok}."])
    async with AsyncSessionLocal() as db:
        db.add(DocumentTopic(document_id=tagged.id, topic="ECL"))
        await db.commit()
    r = await client.get("/api/v1/documents/search", params={"q": f"ECL {tok}"})
    ids = {h["document_id"] for h in r.json()["results"]}
    assert str(spelled.id) in ids and str(tagged.id) in ids
    # A short form never matches inside another word.
    inside, _ = await make_real_doc([f"Declaration form {tok}."])
    r = await client.get("/api/v1/documents/search", params={"q": f"ECL {tok}"})
    assert str(inside.id) not in {h["document_id"] for h in r.json()["results"]}
    # Words may sit on different pages of one circular.
    split, _ = await make_real_doc([f"Part one {tok}.", "Part two talks about provisioning."])
    r = await client.get("/api/v1/documents/search", params={"q": f"{tok} provision"})
    assert str(split.id) in {h["document_id"] for h in r.json()["results"]}


@pytest.mark.asyncio
async def test_lists_and_feed(client):
    user, token = await make_user()
    other, other_token = await make_user()
    today = date.today()
    recent, _ = await make_real_doc(["Recent page."], published=today)
    old, _ = await make_real_doc(["Old page."], published=today - timedelta(days=400))
    async with AsyncSessionLocal() as db:
        db.add(DocumentTopic(document_id=old.id, topic="AML"))
        await db.commit()

    lists = (await client.get("/api/v1/me/lists", headers=_auth(token))).json()
    kinds = [l["kind"] for l in lists]
    assert kinds[:2] == ["FAVOURITES", "READ_LATER"]
    later = next(l for l in lists if l["kind"] == "READ_LATER")

    r = await client.put(f"/api/v1/me/lists/{later['id']}/items/{old.id}", headers=_auth(token))
    assert r.status_code == 200
    assert str(old.id) in next(l for l in r.json() if l["kind"] == "READ_LATER")["document_ids"]
    # Someone else cannot touch my list.
    r = await client.put(f"/api/v1/me/lists/{later['id']}/items/{recent.id}", headers=_auth(other_token))
    assert r.status_code == 404

    r = await client.post("/api/v1/me/lists", json={"name": "Board pack"}, headers=_auth(token))
    assert any(l["name"] == "Board pack" and l["kind"] == "CUSTOM" for l in r.json())

    counts = (await client.get("/api/v1/feed/counts", headers=_auth(token))).json()
    assert counts["read_later"] == 1
    assert counts["today"] >= 1 and counts["month"] >= counts["week"] >= counts["today"]

    saved = (await client.get("/api/v1/feed", params={"saved": "READ_LATER"}, headers=_auth(token))).json()
    assert [d["id"] for d in saved["items"]] == [str(old.id)]
    assert saved["items"][0]["topics"] == ["AML"]

    today_feed = (await client.get("/api/v1/feed", params={"period": "today", "limit": 100})).json()
    ids = {d["id"] for d in today_feed["items"]}
    assert str(recent.id) in ids and str(old.id) not in ids

    by_topic = (await client.get("/api/v1/feed", params={"topic": "AML", "limit": 100})).json()
    assert str(old.id) in {d["id"] for d in by_topic["items"]}

    r = await client.delete(f"/api/v1/me/lists/{later['id']}/items/{old.id}", headers=_auth(token))
    assert next(l for l in r.json() if l["kind"] == "READ_LATER")["document_ids"] == []
    # Built-in lists cannot be deleted.
    assert (await client.delete(f"/api/v1/me/lists/{later['id']}", headers=_auth(token))).status_code == 422
