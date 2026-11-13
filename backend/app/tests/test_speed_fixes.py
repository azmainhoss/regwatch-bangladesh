"""Tests for the 13 Nov speed fixes: quick connection check and background analysis. No network."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.modules.analysis import jobs
from backend.app.modules.analysis.providers import factory
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage
from backend.app.modules.analysis.providers import health
from backend.app.tests.factories import make_document, make_user


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class _BusyProvider(BaseAIProvider):
    def __init__(self):
        super().__init__(model_name="probe-model")

    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        health.record_call("gemini", self.model_name, False, 900, 503, "overloaded")
        return LLMResponse(raw_content="", parsed_json=None, token_usage=TokenUsage(), model_name=self.model_name,
                           latency_ms=900, success=False, error="Gemini is overloaded (HTTP 503)")


class _OkProvider(_BusyProvider):
    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        health.record_call("gemini", self.model_name, True, 1200, 200)
        return LLMResponse(raw_content="{}", parsed_json={"status": "ok"}, token_usage=TokenUsage(),
                           model_name=self.model_name, latency_ms=1200, success=True, error=None)


@pytest.mark.asyncio
async def test_probe_uses_one_try_short_timeout_and_cheap_model(monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    p = factory.get_probe_provider()
    assert p.model_name == settings.PROBE_GEMINI_MODEL
    assert p._max_retries == 0
    assert p._timeout == settings.PROBE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_probe_busy_answers_plainly(client, monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(factory, "get_probe_provider", lambda: _BusyProvider())
    _, token = await make_user(is_superuser=True)
    res = (await client.post("/api/v1/documents/provider-test", headers=_auth(token))).json()
    tr = res["test_result"]
    assert tr["success"] is False and tr["busy"] is True
    assert "busy" in tr["message"].lower()
    assert "503" not in tr["message"] and "HTTP" not in tr["message"]
    # Recorded as the health of the configured model, not the probe model.
    assert res["status"] == health.TEMPORARILY_UNAVAILABLE


@pytest.mark.asyncio
async def test_probe_success_marks_configured_model_connected(client, monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(factory, "get_probe_provider", lambda: _OkProvider())
    _, token = await make_user(is_superuser=True)
    res = (await client.post("/api/v1/documents/provider-test", headers=_auth(token))).json()
    assert res["test_result"]["success"] is True
    assert res["is_available"] is True
    assert "1.2 s" in res["test_result"]["message"]


@pytest.mark.asyncio
async def test_analysis_runs_in_background_then_skips_unchanged(client):
    _, token = await make_user(is_superuser=True)
    doc, _v, _p = await make_document(pages=2)
    first = await client.post(f"/api/v1/documents/{doc.id}/analyze", json={"provider": "mock"}, headers=_auth(token))
    assert first.status_code == 202
    assert first.json()["state"] == jobs.RUNNING
    await jobs.wait(doc.id)
    st = (await client.get(f"/api/v1/documents/{doc.id}/analysis-status", headers=_auth(token))).json()
    assert st["state"] == jobs.DONE
    assert (await client.get(f"/api/v1/documents/{doc.id}/analysis")).status_code == 200

    # Same pages, same model: not sent again.
    again = await client.post(f"/api/v1/documents/{doc.id}/analyze", json={"provider": "mock"}, headers=_auth(token))
    assert again.json()["state"] == jobs.UNCHANGED

    # Forced: runs again.
    forced = await client.post(f"/api/v1/documents/{doc.id}/analyze", json={"provider": "mock", "force": True},
                               headers=_auth(token))
    assert forced.json()["state"] == jobs.RUNNING
    await jobs.wait(doc.id)


@pytest.mark.asyncio
async def test_failed_analysis_reports_plain_reason(client, monkeypatch):
    from backend.app.modules.analysis import service as svc

    async def boom(**kwargs):
        raise RuntimeError("AI analysis pipeline failed: Gemini rate limit or quota reached (HTTP 429)")

    monkeypatch.setattr(svc.AnalysisService, "analyze_document_version", staticmethod(boom))
    _, token = await make_user(is_superuser=True)
    doc, _v, _p = await make_document(pages=1)
    await client.post(f"/api/v1/documents/{doc.id}/analyze", json={"provider": "mock"}, headers=_auth(token))
    await jobs.wait(doc.id)
    st = (await client.get(f"/api/v1/documents/{doc.id}/analysis-status", headers=_auth(token))).json()
    assert st["state"] == jobs.FAILED
    assert "limit" in st["message"]
    assert "429" not in st["message"]


@pytest.mark.asyncio
async def test_status_needs_admin(client):
    _, token = await make_user(is_superuser=False)
    assert (await client.get(f"/api/v1/documents/{uuid.uuid4()}/analysis-status", headers=_auth(token))).status_code == 403


# --------------------------------------------------------------------------- Ask: small prompt, instant matches
def test_prompt_keeps_only_matching_sentences_and_neighbours():
    from backend.app.modules.analysis.sentences import SentenceIndex
    from backend.app.modules.research.service import _pick_sentence_ids

    filler = " ".join(f"Filler sentence number {i} about nothing." for i in range(200))
    text = filler + " Banks must keep a cash reserve ratio of four percent. " + filler
    index = SentenceIndex.build([{"page_number": 1, "cleaned_text": text}])
    chosen = _pick_sentence_ids(index, [1], ["cash", "reserve"], 5000)
    chosen_text = " ".join(index.sentences[s].text for s in chosen)
    assert "cash reserve ratio" in chosen_text
    assert len(chosen) <= 3  # the hit plus one neighbour each side
    assert len(chosen_text) < len(text) / 20


def test_prompt_falls_back_to_page_start_when_nothing_matches():
    from backend.app.modules.analysis.sentences import SentenceIndex
    from backend.app.modules.research.service import FALLBACK_CHARS_PER_PAGE, _pick_sentence_ids

    text = " ".join(f"Sentence {i} of the page." for i in range(500))
    index = SentenceIndex.build([{"page_number": 1, "cleaned_text": text}])
    chosen = _pick_sentence_ids(index, [1], ["nomatchword"], 5000)
    assert chosen
    assert sum(len(index.sentences[s].text) for s in chosen) <= FALLBACK_CHARS_PER_PAGE + 40


@pytest.mark.asyncio
async def test_matches_endpoint_returns_exact_lines_without_a_model_call(client, monkeypatch):
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.documents.models import DocumentPage
    from backend.app.modules.research import service as research_service
    from sqlalchemy import select

    def no_model(*a, **k):
        raise AssertionError("matches must not call the model")

    monkeypatch.setattr(research_service, "get_answer_provider", no_model)
    _, token = await make_user(is_superuser=False)
    doc, version, _ = await make_document(pages=1, status="PUBLISHED_MACHINE_PROCESSED")
    line = "Every scheduled bank shall report its liquidity coverage ratio monthly."
    async with AsyncSessionLocal() as db:
        page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == version.id))).scalars().first()
        page.cleaned_text = page.raw_text = "Intro text here. " + line + " Closing words."
        await db.commit()
    res = await client.post("/api/v1/research/matches", json={"query": "liquidity coverage ratio", "document_id": str(doc.id)},
                            headers=_auth(token))
    assert res.status_code == 200
    matches = res.json()["matches"]
    assert matches and matches[0]["verbatim_excerpt"] == line
    assert matches[0]["page_number"] == 1


# --------------------------------------------------------------------------- page reading: a few pages at once
@pytest.mark.asyncio
async def test_vision_job_reads_pages_in_parallel(monkeypatch):
    import asyncio
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.extraction.vision import VisionResult
    from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages
    from backend.app.tests.test_page_reading import _ingest, _pages, bangla_pdf

    monkeypatch.setattr(settings, "VISION_CALLS_PER_KEY", 3)
    _doc_id, version_id = await _ingest(bangla_pdf(pages=3))
    in_flight = {"now": 0, "max": 0}

    async def reader(png):
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.05)
        in_flight["now"] -= 1
        return VisionResult(success=True, text="পৃষ্ঠা", line_boxes=[])

    async with AsyncSessionLocal() as db:
        summary = await process_pending_vision_pages(db, reader=reader, version_id=version_id)
    assert summary["read"] == 3
    assert in_flight["max"] == 3
    assert all(p.quality_status == "SUCCESS_VISION" for p in await _pages(version_id))


def test_gemini_keys_rotation_list(monkeypatch):
    from backend.app.modules.extraction.vision import gemini_keys

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k1")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", "k2, k1 ,k3,")
    assert gemini_keys() == ["k1", "k2", "k3"]


# --------------------------------------------------------------------------- free quota: never blame the page
@pytest.mark.asyncio
async def test_busy_or_out_of_quota_never_counts_as_a_failed_try():
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.extraction.vision import VisionResult
    from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages
    from backend.app.tests.test_page_reading import _ingest, _pages, bangla_pdf

    _doc_id, version_id = await _ingest(bangla_pdf(pages=1))

    async def busy(png):
        return VisionResult(success=False, error="daily limit reached", transient=True, quota_exhausted=True)

    for _ in range(8):
        async with AsyncSessionLocal() as db:
            summary = await process_pending_vision_pages(db, reader=busy, version_id=version_id)
        assert summary["waiting_busy"] == 1
    page = (await _pages(version_id))[0]
    assert page.quality_status == "PENDING_VISION"
    assert (page.vision_attempts or 0) == 0


@pytest.mark.asyncio
async def test_daily_quota_reply_rests_that_key(monkeypatch):
    import httpx
    from backend.app.modules.extraction import vision

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key-a")
    monkeypatch.setattr(settings, "GEMINI_EXTRA_API_KEYS", "key-b")
    vision._exhausted_until.clear()

    def handler(request):
        return httpx.Response(429, json={"error": {"message": "Quota exceeded for metric GenerateRequestsPerDayPerProjectPerModel"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await vision.read_page_image(b"\x89PNG", api_key="key-a", client=client)
    assert res.quota_exhausted and res.transient and not res.success
    assert vision.available_gemini_keys() == ["key-b"]
    vision._exhausted_until.clear()


# --------------------------------------------------------------------------- step 1: no analysis on unread pages
@pytest.mark.asyncio
async def test_analysis_waits_for_unread_pages(client):
    from backend.app.tests.test_page_reading import _ingest, bangla_pdf

    _, token = await make_user(is_superuser=True)
    doc_id, _version_id = await _ingest(bangla_pdf(pages=2))
    res = await client.post(f"/api/v1/documents/{doc_id}/analyze", json={"provider": "mock"}, headers=_auth(token))
    assert res.status_code == 202
    body = res.json()
    assert body["state"] == jobs.WAITING_FOR_PAGES
    assert "still being read" in body["message"]

    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.analysis.service import AnalysisService
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="still being read"):
            await AnalysisService.analyze_document_version(db=db, document_id=doc_id, provider_name="mock")


@pytest.mark.asyncio
async def test_live_circular_is_analysed_once_pages_are_read_but_archive_is_not(monkeypatch):
    from sqlalchemy import select
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.analysis import auto
    from backend.app.modules.analysis.models import DocumentAnalysis
    from backend.app.modules.documents.models import Document
    from backend.app.modules.extraction.vision import VisionResult
    from backend.app.modules.extraction.vision_jobs import process_pending_vision_pages
    from backend.app.tests.test_page_reading import _ingest, bangla_pdf

    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "mock")
    auto._last_try.clear()
    live_id, live_v = await _ingest(bangla_pdf(pages=1))
    arch_id, arch_v = await _ingest(bangla_pdf(pages=1), title="Archive circular for auto test")
    async with AsyncSessionLocal() as db:
        (await db.get(Document, live_id)).publication_status = "PUBLISHED_MACHINE_PROCESSED"
        (await db.get(Document, arch_id)).publication_status = "EXTRACTED"
        await db.commit()

    async def reader(png):
        return VisionResult(success=True, text="ব্যাংকসমূহকে প্রতি মাসে প্রতিবেদন দাখিল করতে হবে।", line_boxes=[])

    async with AsyncSessionLocal() as db:
        ready_before = await auto.ready_live_circulars(db, limit=50)
    assert live_id not in ready_before  # pages not read yet

    for v in (live_v, arch_v):
        async with AsyncSessionLocal() as db:
            await process_pending_vision_pages(db, reader=reader, version_id=v)
    async with AsyncSessionLocal() as db:
        ready = await auto.ready_live_circulars(db, limit=50)
    assert live_id in ready and arch_id not in ready

    async def only_live(db, limit=3):
        return [live_id]
    monkeypatch.setattr(auto, "ready_live_circulars", only_live)
    assert await auto.analyze_ready_live_circulars(AsyncSessionLocal) == 1
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, live_id)
        found = (await db.execute(select(DocumentAnalysis).where(DocumentAnalysis.document_version_id == doc.current_version_id))).scalars().first()
    assert found is not None


@pytest.mark.asyncio
async def test_reading_status_says_what_is_waiting(client, monkeypatch):
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.documents.models import Document
    from backend.app.tests.test_page_reading import _ingest, bangla_pdf

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(settings, "VISION_WORKER_ENABLED", True)
    doc_id, _v = await _ingest(bangla_pdf(pages=2))
    async with AsyncSessionLocal() as db:
        (await db.get(Document, doc_id)).publication_status = "EXTRACTED"
        await db.commit()
    r = (await client.get(f"/api/v1/documents/{doc_id}/reading-status")).json()
    assert r["pages_total"] == 2 and r["pages_waiting"] == 2
    assert r["state"] in ("READING", "QUEUED") and r["minutes_left"] >= 1
    assert r["analysis_after"] == "LATER"
