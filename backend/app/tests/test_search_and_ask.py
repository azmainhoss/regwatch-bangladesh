"""Search across circulars, asking across circulars, and the page-correction audit trail.

Nothing here touches the network. The answer service is the built-in offline one or a stub.
"""
import re
import uuid
from datetime import date
from typing import List, Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.providers.base import LLMResponse
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion, PageCorrection
from backend.app.modules.documents.search import make_snippet, query_terms
from backend.app.tests.factories import make_institution, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tok() -> str:
    return "zq" + uuid.uuid4().hex[:10]


async def make_real_doc(
    texts: List[str],
    title: Optional[str] = None,
    reference: Optional[str] = None,
    owner_id=None,
    published: date = date(2025, 3, 1),
    doc_type: str = "CIRCULAR",
    status: str = "PUBLISHED_MACHINE_PROCESSED",
    version_status: str = "CURRENT",
    synthetic: bool = False,
):
    """A genuine (not sample) circular with one page per text."""
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc = Document(
            institution_id=inst.id,
            title=title or f"Liquidity rules {uuid.uuid4().hex[:6]}",
            reference_number=reference or f"BRPD-{uuid.uuid4().hex[:6]}",
            publication_date=published,
            document_type=doc_type,
            publication_status=status,
            is_synthetic_fixture=synthetic,
            owner_user_id=owner_id,
        )
        db.add(doc)
        await db.flush()
        version = DocumentVersion(
            document_id=doc.id, version_number=1, file_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            file_size_bytes=10, storage_path="originals/none.pdf", page_count=len(texts), status=version_status,
        )
        db.add(version)
        await db.flush()
        doc.current_version_id = version.id
        for n, text in enumerate(texts, start=1):
            db.add(DocumentPage(document_version_id=version.id, page_number=n, raw_text=text, cleaned_text=text))
        await db.commit()
        await db.refresh(doc)
        await db.refresh(version)
        return doc, version


async def search(client, token: Optional[str] = None, **params):
    headers = _auth(token) if token else {}
    resp = await client.get("/api/v1/documents/search", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- search

@pytest.mark.asyncio
async def test_search_finds_page_text_title_and_reference_with_exact_snippets(client):
    tok = _tok()
    page1 = f"Introduction. Banks shall keep the {tok} reserve at the level set below. " + "Filler words. " * 30
    page2 = "Nothing relevant on this page."
    page3 = ("Lead in text. " * 20) + f"The {tok.upper()} reserve is reviewed every quarter by the Board."
    doc, version = await make_real_doc([page1, page2, page3], title=f"Reserve circular {tok}", reference=f"REF-{tok}")

    body = await search(client, q=tok)
    hit = next(r for r in body["results"] if r["document_id"] == str(doc.id))
    assert hit["title_match"] is True
    assert hit["matching_pages"] == 2
    assert [s["page_number"] for s in hit["snippets"]] == [1, 3]
    pages = {1: page1, 3: page3}
    for snip in hit["snippets"]:
        assert snip["text"] in pages[snip["page_number"]]          # exact substring of the stored page
        assert len(snip["text"]) <= 200
        assert snip["version_id"] == str(version.id)
        assert snip["matches"], "the matched word must be marked"
        for start, end in snip["matches"]:
            assert snip["text"][start:end].lower() == tok
    # By reference number alone, and by a title word alone.
    assert any(r["document_id"] == str(doc.id) for r in (await search(client, q=f"REF-{tok}"))["results"])
    assert body["total"] >= 1 and body["terms"] == [tok]


@pytest.mark.asyncio
async def test_search_matches_bangla_text(client):
    tok = _tok()
    bangla = f"ব্যাংকসমূহ ঋণ শ্রেণিবিন্যাস সংক্রান্ত নির্দেশনা {tok} মেনে চলবে।"
    doc, _ = await make_real_doc([bangla])
    for word in ("শ্রেণিবিন্যাস", "ঋণ"):
        body = await search(client, q=f"{word} {tok}")
        hit = next(r for r in body["results"] if r["document_id"] == str(doc.id))
        snip = hit["snippets"][0]
        assert snip["text"] in bangla
        marked = [snip["text"][s:e] for s, e in snip["matches"]]
        assert word in marked


@pytest.mark.asyncio
async def test_search_all_words_must_appear_and_wildcards_are_literal(client):
    tok = _tok()
    doc, _ = await make_real_doc([f"The {tok} capital rule applies."])
    assert (await search(client, q=f"{tok} capital"))["total"] == 1
    assert (await search(client, q=f"{tok} nonexistentword"))["total"] == 0
    assert (await search(client, q="%"))["total"] == 0   # no words, nothing to match
    pct = await search(client, q=f"{tok}%")
    assert [r["document_id"] for r in pct["results"]] == [str(doc.id)]
    assert (await search(client, q=""))["results"] == []
    assert (await search(client, q="   "))["total"] == 0


@pytest.mark.asyncio
async def test_search_route_is_not_shadowed_and_limits_are_checked(client):
    assert (await client.get("/api/v1/documents/search?q=abc")).status_code == 200
    assert (await client.get("/api/v1/documents/search?q=abc&limit=500")).status_code == 422


@pytest.mark.asyncio
async def test_search_skips_private_documents_of_other_users(client):
    tok = _tok()
    owner_a, token_a = await make_user()
    _b, token_b = await make_user()
    _admin, token_admin = await make_user(is_superuser=True)
    secret = f"Our internal {tok} limit is confidential."
    doc, _ = await make_real_doc([secret], owner_id=owner_a.id, title=f"Private memo {tok}")

    def ids(body):
        return [r["document_id"] for r in body["results"]]

    assert str(doc.id) in ids(await search(client, token_a, q=tok))
    assert str(doc.id) not in ids(await search(client, token_b, q=tok))
    assert str(doc.id) not in ids(await search(client, token_b, q="confidential"))
    assert str(doc.id) not in ids(await search(client, token_admin, q=tok))   # admins get no exception
    assert (await search(client, None, q=tok))["total"] == 0                  # signed out
    # A shared circular is found by everyone.
    shared_tok = _tok()
    shared, _ = await make_real_doc([f"Public {shared_tok} rule."])
    for t in (None, token_a, token_b):
        assert str(shared.id) in ids(await search(client, t, q=shared_tok))


@pytest.mark.asyncio
async def test_search_hides_synthetic_fixtures_and_superseded_files(client):
    tok = _tok()
    fixture, _ = await make_real_doc([f"Fixture text {tok}."], synthetic=True)
    sample, _ = await make_real_doc([f"Sample text {tok}."], title=f"Sample circular {tok}")
    old, _ = await make_real_doc([f"Old file text {tok}."], version_status="SUPERSEDED", title="Plain title")
    live, _ = await make_real_doc([f"Current text {tok}."])
    body = await search(client, q=tok)
    found = {r["document_id"] for r in body["results"]}
    assert str(live.id) in found
    assert not ({str(fixture.id), str(sample.id), str(old.id)} & found)


@pytest.mark.asyncio
async def test_search_filters(client):
    tok = _tok()
    a, _ = await make_real_doc([f"{tok} text"], reference=f"BRPD-{tok}", published=date(2023, 5, 1), status="PUBLISHED_HUMAN_REVIEWED")
    b, _ = await make_real_doc([f"{tok} text"], reference=f"DOS-{tok}", published=date(2025, 5, 1), doc_type="GUIDELINE")

    def ids(body):
        return {r["document_id"] for r in body["results"]}

    assert ids(await search(client, q=tok)) == {str(a.id), str(b.id)}
    assert ids(await search(client, q=tok, department="BRPD")) == {str(a.id)}
    assert ids(await search(client, q=tok, department="dos")) == {str(b.id)}
    assert ids(await search(client, q=tok, year_from=2024)) == {str(b.id)}
    assert ids(await search(client, q=tok, year_to=2023)) == {str(a.id)}
    assert ids(await search(client, q=tok, doc_type="GUIDELINE")) == {str(b.id)}
    assert ids(await search(client, q=tok, status="PUBLISHED_HUMAN_REVIEWED")) == {str(a.id)}
    assert ids(await search(client, q=tok, status="PUBLISHED")) == {str(a.id), str(b.id)}
    # Newest first, and paging works.
    first = await search(client, q=tok, limit=1)
    assert first["total"] == 2 and [r["document_id"] for r in first["results"]] == [str(b.id)]
    second = await search(client, q=tok, limit=1, offset=1)
    assert [r["document_id"] for r in second["results"]] == [str(a.id)]


@pytest.mark.asyncio
async def test_search_returns_at_most_three_snippets_per_document(client):
    tok = _tok()
    doc, _ = await make_real_doc([f"Page {n} mentions {tok}." for n in range(1, 7)])
    hit = next(r for r in (await search(client, q=tok))["results"] if r["document_id"] == str(doc.id))
    assert hit["matching_pages"] == 6
    assert [s["page_number"] for s in hit["snippets"]] == [1, 2, 3]


def test_snippet_is_always_an_exact_piece_of_the_text():
    text = ("Alpha beta gamma. " * 40) + "The capital adequacy ratio must stay above ten percent. " + ("Delta epsilon. " * 40)
    snip = make_snippet(text, ["capital", "adequacy"])
    assert snip["text"] in text and len(snip["text"]) <= 200
    assert snip["starts_mid_text"] and snip["ends_mid_text"]
    marked = [snip["text"][s:e].lower() for s, e in snip["matches"]]
    assert "capital" in marked and "adequacy" in marked
    assert query_terms("Capital capital  adequacy, ঋণ-শ্রেণি") == ["Capital", "adequacy", "ঋণ", "শ্রেণি"]


# ---------------------------------------------------------------- ask

class _Stub:
    def __init__(self, parsed, success=True):
        self.parsed, self.success = parsed, success
        self.prompt = ""

    async def generate_structured_json(self, system_prompt, user_prompt, **kwargs):
        self.prompt = user_prompt
        return LLMResponse(raw_content="", parsed_json=self.parsed, model_name="stub", success=self.success)


async def ask(client, token, query, **extra):
    resp = await client.post("/api/v1/research/query", json={"query": query, **extra}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_ask_across_circulars_cites_exact_page_text(client):
    tok = _tok()
    _u, token = await make_user()
    page = f"Preamble line.\nBanks must submit the {tok} report within ten days. Late reports attract a fine.\nSigned."
    doc, version = await make_real_doc(["Unrelated page.", page], title=f"Reporting circular {tok}")
    # More circulars, so this is a real search across documents and no document_id is passed.
    for _ in range(3):
        await make_real_doc([f"Another circular about {tok}-other things only."])

    body = await ask(client, token, f"Who must submit the {tok} report?")
    assert body["is_grounded"] is True and body["answer"]
    cite = next(c for c in body["citations"] if c["document_id"] == str(doc.id))
    assert cite["page_number"] == 2
    assert cite["verbatim_excerpt"] in page                      # copied from the stored page
    assert tok in cite["verbatim_excerpt"]
    assert cite["version_id"] == str(version.id)
    assert cite["document_title"] == f"Reporting circular {tok}" and cite["reference_number"]
    assert cite["sentence_ids"] and all(re.match(r"^p2\.s\d+$", s) for s in cite["sentence_ids"])


@pytest.mark.asyncio
async def test_ask_never_uses_another_users_private_circular(client):
    tok = _tok()
    owner, token_owner = await make_user()
    _other, token_other = await make_user()
    doc, _ = await make_real_doc([f"Private rule about {tok} for our staff only."], owner_id=owner.id)
    mine = await ask(client, token_owner, f"{tok}?")
    assert any(c["document_id"] == str(doc.id) for c in mine["citations"])
    theirs = await ask(client, token_other, f"{tok}?")
    assert not any(c["document_id"] == str(doc.id) for c in theirs["citations"])
    assert theirs["is_grounded"] is False and theirs["citations"] == []


@pytest.mark.asyncio
async def test_ask_requires_sign_in(client):
    resp = await client.post("/api/v1/research/query", json={"query": "What is the reserve rule?"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ask_quotes_come_from_ids_never_from_the_model(client, monkeypatch):
    tok = _tok()
    _u, token = await make_user()
    page = f"The {tok} limit is five percent. A second sentence follows here."
    doc, _ = await make_real_doc([page])
    stub = _Stub({
        "answer": "The limit is five percent.",
        "verbatim_excerpt": "A quote the model invented",
        "sources": [{"quote_span_ids": ["D1.p1.s1"], "verbatim_excerpt": "Typed by the model"}],
    })
    monkeypatch.setattr("backend.app.modules.research.service.get_answer_provider", lambda *a, **k: stub)
    body = await ask(client, token, f"What is the {tok} limit?")
    assert "D1.p1.s1" in stub.prompt and "[D1." in stub.prompt
    assert body["is_grounded"] is True
    assert [c["verbatim_excerpt"] for c in body["citations"]] == [f"The {tok} limit is five percent."]
    assert "invented" not in str(body) and "Typed by the model" not in str(body)


@pytest.mark.asyncio
async def test_ask_without_a_real_source_shows_no_answer(client, monkeypatch):
    tok = _tok()
    _u, token = await make_user()
    await make_real_doc([f"The {tok} limit is five percent."])
    cases = [
        {"answer": "It is five percent.", "sources": []},                                   # no sources
        {"answer": "It is five percent.", "sources": [{"quote_span_ids": ["D1.p9.s99"]}]},   # unknown sentence
        {"answer": "It is five percent.", "sources": [{"quote_span_ids": ["D7.p1.s1"]}]},    # unknown circular
        {"answer": "It is five percent.", "sources": [{"quote_span_ids": ["D1.p1.s1", "D1.p1.s50"]}]},  # one bad ID
        {"answer": "It is five percent.", "sources": [{"verbatim_excerpt": f"The {tok} limit is five percent."}]},  # typed quote only
        {"answer": "I could not verify this from the available regulatory documents.", "sources": [{"quote_span_ids": ["D1.p1.s1"]}]},
        {"answer": "", "sources": [{"quote_span_ids": ["D1.p1.s1"]}]},
    ]
    for parsed in cases:
        monkeypatch.setattr("backend.app.modules.research.service.get_answer_provider", lambda *a, _p=parsed, **k: _Stub(_p))
        body = await ask(client, token, f"What is the {tok} limit?")
        assert body["is_grounded"] is False, parsed
        assert body["citations"] == [], parsed
        assert body["answer"] == "I could not verify this from the available regulatory documents.", parsed


@pytest.mark.asyncio
async def test_ask_finds_nothing_for_unrelated_questions(client):
    _u, token = await make_user()
    body = await ask(client, token, f"What does {_tok()} say about orbital rockets?")
    assert body["is_grounded"] is False and body["citations"] == []


# ---------------------------------------------------------------- page corrections

@pytest.mark.asyncio
async def test_page_correction_keeps_who_when_why_and_a_history(client):
    admin, admin_token = await make_user(is_superuser=True)
    doc, version = await make_real_doc(["Original text of page one."])
    url = f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct"

    first = await client.post(url, headers=_auth(admin_token), json={"corrected_text": "First fix", "correction_notes": "  Wrong digit  "})
    assert first.status_code == 200
    page = first.json()["page"]
    assert page["correction_reason"] == "Wrong digit"
    assert page["corrected_by_name"] == "Test User"
    assert page["corrected_at"]

    second = await client.post(url, headers=_auth(admin_token), json={"corrected_text": "Second fix", "correction_notes": "Missing line"})
    assert second.json()["page"]["correction_reason"] == "Missing line"

    # The page list returns the latest one.
    pages = (await client.get(f"/api/v1/documents/{doc.id}/versions/{version.id}/pages")).json()
    assert pages[0]["correction_reason"] == "Missing line" and pages[0]["corrected_by_name"] == "Test User"

    # Both corrections are kept, with the text before and after each.
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PageCorrection).where(PageCorrection.document_version_id == version.id).order_by(PageCorrection.created_at)
        )).scalars().all()
    assert [r.reason for r in rows] == ["Wrong digit", "Missing line"]
    assert [r.corrected_text for r in rows] == ["First fix", "Second fix"]
    assert [r.previous_text for r in rows] == ["Original text of page one.", "First fix"]
    assert all(str(r.corrected_by_user_id) == str(admin.id) for r in rows)


@pytest.mark.asyncio
async def test_page_correction_without_a_reason_still_records_who_and_when(client):
    _admin, admin_token = await make_user(is_superuser=True)
    doc, version = await make_real_doc(["Text."])
    resp = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        headers=_auth(admin_token), json={"corrected_text": "New text"},
    )
    page = resp.json()["page"]
    assert page["correction_reason"] is None and page["corrected_by_name"] and page["corrected_at"]


@pytest.mark.asyncio
async def test_refused_corrections_leave_no_history(client):
    _user, user_token = await make_user()
    doc, version = await make_real_doc(["Text."])
    resp = await client.post(
        f"/api/v1/documents/{doc.id}/versions/{version.id}/pages/1/correct",
        headers=_auth(user_token), json={"corrected_text": "Nope", "correction_notes": "x"},
    )
    assert resp.status_code == 403
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(PageCorrection).where(PageCorrection.document_version_id == version.id))).first() is None
