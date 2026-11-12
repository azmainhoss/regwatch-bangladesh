"""Quotes by sentence ID (DECISIONS.md 7), the Gemini and OpenAI-compatible providers, the
factory and provider health. No network: every HTTP call goes to an httpx.MockTransport."""
import json
from typing import Any, Dict, List, Optional

import httpx
import pytest

from backend.app.core.config import settings
from backend.app.modules.analysis.citations import STATE_UNVERIFIED, STATE_VERIFIED_EXACT, CitationValidator
from backend.app.modules.analysis.pipeline import RegulatoryIntelligencePipeline
from backend.app.modules.analysis.prompts import ANALYSIS_RESPONSE_SCHEMA, PROMPT_VERSION
from backend.app.modules.analysis.providers import health
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse
from backend.app.modules.analysis.providers.factory import get_active_provider_info, get_ai_provider
from backend.app.modules.analysis.providers.gemini import GeminiAIProvider
from backend.app.modules.analysis.providers.mock import MockAIProvider
from backend.app.modules.analysis.providers.openai_compat import OpenAICompatibleProvider
from backend.app.modules.analysis.sentences import SentenceIndex, apply_quote_ids, split_sentences


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------
def test_split_english_keeps_abbreviations_numbers_and_list_markers():
    text = (
        "Please refer to BRPD Circular No. 14 dated 23 September 2012. "
        "Banks must keep a general provision of 1.00% on Stage 1 loans. "
        "Is this clear? Yes!\n"
        "1. Stage 1 loans are performing.\n"
        "(a) Report to the Dept. of Offsite Supervision, i.e. DOS, by 31 Dec. 2024."
    )
    assert split_sentences(text) == [
        "Please refer to BRPD Circular No. 14 dated 23 September 2012.",
        "Banks must keep a general provision of 1.00% on Stage 1 loans.",
        "Is this clear?",
        "Yes!",
        "1. Stage 1 loans are performing.",
        "(a) Report to the Dept. of Offsite Supervision, i.e. DOS, by 31 Dec. 2024.",
    ]


def test_split_bangla_full_stop_and_blank_lines():
    text = (
        "সকল তফসিলি ব্যাংককে এ নির্দেশনা মানতে হবে। এটি অবিলম্বে কার্যকর হবে।\n\n"
        "বিষয়: উদ্যোক্তা উন্নয়ন কর্মসূচি\n"
        "ক) প্রতিটি শাখা আবেদন গ্রহণ করবে;\n"
        "খ) তথ্য সংরক্ষণ করবে।"
    )
    assert split_sentences(text) == [
        "সকল তফসিলি ব্যাংককে এ নির্দেশনা মানতে হবে।",
        "এটি অবিলম্বে কার্যকর হবে।",
        "বিষয়: উদ্যোক্তা উন্নয়ন কর্মসূচি",
        "ক) প্রতিটি শাখা আবেদন গ্রহণ করবে;",
        "খ) তথ্য সংরক্ষণ করবে।",
    ]


def test_split_is_stable_and_spans_are_exact():
    text = "First rule applies.  Second   rule\napplies too।Third."
    index = SentenceIndex.build([{"page_number": 2, "raw_text": text}])
    again = SentenceIndex.build([{"page_number": 2, "raw_text": text}])
    assert list(index.sentences) == list(again.sentences) == ["p2.s1", "p2.s2", "p2.s3"]
    for s in index.sentences.values():
        assert text[s.start:s.end] == s.text
    assert index.sentences["p2.s2"].text == "Second   rule\napplies too।"


# ---------------------------------------------------------------------------
# IDs -> quotes
# ---------------------------------------------------------------------------
PAGES = [
    {"page_number": 1, "raw_text": "BANGLADESH BANK\n\nAll banks must classify loans into three stages. "
                                   "Stage 2 needs a 5.00% provision. This circular takes effect at once."},
    {"page_number": 2, "raw_text": "Please refer to BRPD Circular No. 14 dated 23 September 2012. "
                                   "Failure to comply will attract penal action."},
]


def test_render_for_prompt_shows_ids():
    rendered = SentenceIndex.build(PAGES).render_for_prompt()
    assert "--- START PAGE 1 ---" in rendered
    assert "[p1.s2] All banks must classify loans into three stages." in rendered
    assert "[p2.s1] Please refer to BRPD Circular No. 14 dated 23 September 2012." in rendered


def test_resolve_contiguous_ids_copies_exact_page_text():
    index = SentenceIndex.build(PAGES)
    span = index.resolve(["p1.s3", "p1.s2"])  # order does not matter
    assert span.ok
    assert span.quote == "All banks must classify loans into three stages. Stage 2 needs a 5.00% provision."
    assert span.page_number == 1
    assert span.sentence_ids == ["p1.s2", "p1.s3"]
    res = CitationValidator.validate_quote_against_page(span.quote, PAGES[0]["raw_text"], 1)
    assert res.status == STATE_VERIFIED_EXACT


def test_resolve_gapped_and_cross_page_ids_validate_exact():
    index = SentenceIndex.build(PAGES)
    payload = {"obligations": [{"title": "Classify", "quote_span_ids": ["p1.s2", "p1.s4", "p2.s2"]}]}
    problems = apply_quote_ids(payload, index)
    assert problems == []
    obl = payload["obligations"][0]
    assert len(obl["quote_fragments"]) == 3
    assert obl["page_number"] == 1
    report = CitationValidator.validate_analysis_claims(payload, index.pages)
    assert obl["verification_status"] == STATE_VERIFIED_EXACT
    assert report.is_publication_eligible is True


def test_unknown_ids_drop_the_quote_and_flag_review():
    index = SentenceIndex.build(PAGES)
    payload = {
        "provisions": [{
            "provision_number": "1",
            "quote_span_ids": ["p1.s2", "p9.s1"],
            "verbatim_text": "A quote the model typed itself, which must be ignored.",
        }],
        "obligations": [{"title": "No ids at all"}],
    }
    problems = apply_quote_ids(payload, index)
    prov, obl = payload["provisions"][0], payload["obligations"][0]
    assert prov["verbatim_text"] == ""
    assert prov["needs_human_review"] is True
    assert prov["unknown_quote_ids"] == ["p9.s1"]
    assert obl["verbatim_quote"] == "" and obl["needs_human_review"] is True
    assert len(problems) == 2

    report = CitationValidator.validate_analysis_claims(payload, index.pages)
    assert prov["verification_status"] == STATE_UNVERIFIED
    assert report.is_publication_eligible is False
    assert "Unknown sentence IDs" in report.unverified_excerpts[0]["issues"][0]


def test_sentences_map_to_line_boxes():
    lines = [
        {"text": "All banks must classify", "box_2d": [100, 50, 120, 900]},
        {"text": "loans into three stages. Stage 2", "box_2d": [121, 50, 140, 900]},
        {"text": "needs a 5.00% provision.", "box_2d": [141, 50, 160, 600]},
    ]
    text = "\n".join(l["text"] for l in lines)
    index = SentenceIndex.build([{"page_number": 3, "cleaned_text": text, "line_boxes": lines}])
    assert index.sentences["p3.s1"].line_indexes == [0, 1]
    assert index.sentences["p3.s2"].line_indexes == [1, 2]
    span = index.resolve(["p3.s2"])
    assert [b["line_index"] for b in span.boxes] == [1, 2]
    assert span.boxes[0] == {"page_number": 3, "line_index": 1, "box_2d": [121, 50, 140, 900]}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class _ScriptedProvider(BaseAIProvider):
    def __init__(self, answer: Any = None, raise_error: Optional[Exception] = None):
        super().__init__(model_name="scripted")
        self.answer = answer
        self.raise_error = raise_error
        self.calls: List[Dict[str, Any]] = []

    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        self.calls.append({"user_prompt": user_prompt, "json_schema": json_schema})
        if self.raise_error:
            raise self.raise_error
        return LLMResponse(raw_content=json.dumps(self.answer), parsed_json=self.answer, model_name=self.model_name)


def _answer(prov_ids, obl_ids):
    return {
        "classification": {"document_type": "CIRCULAR", "subject": "Loans", "language": "en"},
        "executive_summary": {"short_summary": "s", "detailed_summary": "d", "key_changes": []},
        "provisions": [{"provision_number": "1", "quote_span_ids": prov_ids, "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "x", "verbatim_text": "invented text"}],
        "obligations": [{"title": "Provision 5%", "obligation_type": "MANDATORY", "requirement_description": "r",
                         "quote_span_ids": obl_ids}],
        "relationships": [],
        "impact_assessment": {},
    }


@pytest.mark.asyncio
async def test_pipeline_quotes_from_ids_are_verified_exact():
    provider = _ScriptedProvider(_answer(["p1.s2"], ["p1.s3"]))
    res = await RegulatoryIntelligencePipeline(provider).execute_document_analysis(pages=PAGES)
    assert res.success and res.prompt_version == PROMPT_VERSION == "v2"
    assert "[p1.s2]" in provider.calls[0]["user_prompt"]
    assert provider.calls[0]["json_schema"] is ANALYSIS_RESPONSE_SCHEMA
    prov = res.structured_payload["provisions"][0]
    assert prov["verbatim_text"] == "All banks must classify loans into three stages."
    assert prov["verification_status"] == STATE_VERIFIED_EXACT
    assert res.validation_report.verified_exact_count == 2
    assert res.publication_status == "PUBLISHED_MACHINE_VERIFIED"


@pytest.mark.asyncio
async def test_pipeline_unknown_ids_go_to_review():
    provider = _ScriptedProvider(_answer(["p1.s2"], ["p1.s99"]))
    res = await RegulatoryIntelligencePipeline(provider).execute_document_analysis(pages=PAGES)
    assert res.success
    assert res.publication_status == "AWAITING_REVIEW"
    assert res.structured_payload["obligations"][0]["needs_human_review"] is True


@pytest.mark.asyncio
async def test_pipeline_provider_failure_ends_failed():
    raised = await RegulatoryIntelligencePipeline(_ScriptedProvider(raise_error=RuntimeError("boom"))) \
        .execute_document_analysis(pages=PAGES)
    assert raised.success is False and raised.publication_status == "FAILED"
    assert "boom" in raised.error

    not_object = await RegulatoryIntelligencePipeline(_ScriptedProvider(answer=["not", "an", "object"])) \
        .execute_document_analysis(pages=PAGES)
    assert not_object.success is False and not_object.publication_status == "FAILED"


@pytest.mark.asyncio
async def test_mock_provider_answers_with_ids():
    res = await RegulatoryIntelligencePipeline(MockAIProvider()).execute_document_analysis(pages=PAGES)
    prov = res.structured_payload["provisions"][0]
    assert prov["quote_span_ids"] == ["p1.s1"]
    assert prov["verification_status"] == STATE_VERIFIED_EXACT


# ---------------------------------------------------------------------------
# Gemini provider: schema and backoff
# ---------------------------------------------------------------------------
def _gemini_ok(payload: Dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
    })


class _Recorder:
    def __init__(self, replies: List[httpx.Response]):
        self.replies = list(replies)
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.replies.pop(0)


def _sleeper():
    waits: List[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    return waits, sleep


@pytest.mark.asyncio
async def test_gemini_backs_off_on_429_and_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "AI_RETRY_BASE_SECONDS", 5.0)
    monkeypatch.setattr(settings, "AI_RETRY_MAX_SECONDS", 120.0)
    rec = _Recorder([httpx.Response(429), httpx.Response(503), _gemini_ok({"ok": True})])
    waits, sleep = _sleeper()
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key="k", client=client, sleep=sleep)
        res = await provider.generate_structured_json("sys", "user", json_schema=ANALYSIS_RESPONSE_SCHEMA)
    assert res.success and res.parsed_json == {"ok": True}
    assert waits == [5.0, 10.0]
    assert len(rec.requests) == 3
    body = json.loads(rec.requests[0].content)
    schema = body["generationConfig"]["responseSchema"]
    assert schema["type"] == "OBJECT"
    assert schema["properties"]["provisions"]["items"]["properties"]["quote_span_ids"]["type"] == "ARRAY"
    assert rec.requests[0].headers["x-goog-api-key"] == "k"


@pytest.mark.asyncio
async def test_gemini_backoff_is_capped_then_fails_clearly(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 4)
    monkeypatch.setattr(settings, "AI_RETRY_BASE_SECONDS", 10.0)
    monkeypatch.setattr(settings, "AI_RETRY_MAX_SECONDS", 25.0)
    rec = _Recorder([httpx.Response(503)] * 4 + [httpx.Response(503, headers={"Retry-After": "7"})])
    waits, sleep = _sleeper()
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        provider = GeminiAIProvider(model_name="gemini-3.5-flash", api_key="k", client=client, sleep=sleep)
        res = await provider.generate_structured_json("sys", "user")
    assert res.success is False
    assert "HTTP 503" in res.error and "5 attempts" in res.error
    assert waits == [10.0, 20.0, 25.0, 25.0]
    body = json.loads(rec.requests[0].content)
    assert "responseSchema" not in body["generationConfig"]  # no schema asked for, none sent


@pytest.mark.asyncio
async def test_gemini_honours_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 2)
    rec = _Recorder([httpx.Response(429, headers={"Retry-After": "3"}), _gemini_ok({"a": 1})])
    waits, sleep = _sleeper()
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        res = await GeminiAIProvider(model_name="m", api_key="k", client=client, sleep=sleep) \
            .generate_structured_json("s", "u")
    assert res.success and waits == [3.0]


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------
def _chat_ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    })


@pytest.mark.asyncio
async def test_openai_compat_request_and_parse(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "AI_RETRY_BASE_SECONDS", 2.0)
    rec = _Recorder([httpx.Response(429), _chat_ok('```json\n{"answer": "ok"}\n```')])
    waits, sleep = _sleeper()
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        provider = OpenAICompatibleProvider(
            model_name="some/model", base_url="https://llm.example/v1/", api_key="secret",
            response_format="json_object", client=client, sleep=sleep,
        )
        res = await provider.generate_structured_json("sys", "user", json_schema=ANALYSIS_RESPONSE_SCHEMA)
    assert res.success and res.parsed_json == {"answer": "ok"}
    assert res.token_usage.total_tokens == 10
    assert waits == [2.0]
    req = rec.requests[-1]
    assert str(req.url) == "https://llm.example/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer secret"
    body = json.loads(req.content)
    assert body["model"] == "some/model"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_compat_json_schema_mode_and_errors():
    rec = _Recorder([httpx.Response(400, text="bad key=secret")])
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        provider = OpenAICompatibleProvider(
            model_name="m", base_url="http://localhost:8080/v1", api_key="secret",
            response_format="json_schema", client=client,
        )
        res = await provider.generate_structured_json("s", "u", json_schema=ANALYSIS_RESPONSE_SCHEMA)
    assert res.success is False
    assert "secret" not in res.error and "[REDACTED]" in res.error
    rf = json.loads(rec.requests[0].content)["response_format"]
    assert rf["type"] == "json_schema"
    schema = rf["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["classification"]["properties"]["department"]["type"] == ["string", "null"]


@pytest.mark.asyncio
async def test_openai_compat_needs_base_url_and_model():
    res = await OpenAICompatibleProvider(model_name="", base_url="").generate_structured_json("s", "u")
    assert res.success is False and "OPENAI_COMPAT_BASE_URL" in res.error


# ---------------------------------------------------------------------------
# Factory and health
# ---------------------------------------------------------------------------
def test_factory_chooses_by_config(monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "mock")
    assert isinstance(get_ai_provider(), MockAIProvider)

    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(settings, "ANALYSIS_MODEL", None)
    gem = get_ai_provider()
    assert isinstance(gem, GeminiAIProvider) and gem.model_name == settings.GEMINI_ANALYSIS_DEFAULT_MODEL
    monkeypatch.setattr(settings, "ANALYSIS_MODEL", "gemini-3.5-flash-lite")
    assert get_ai_provider().model_name == "gemini-3.5-flash-lite"

    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "openai_compat")
    monkeypatch.setattr(settings, "OPENAI_COMPAT_BASE_URL", "https://llm.example/v1")
    monkeypatch.setattr(settings, "ANALYSIS_MODEL", "some/model")
    oa = get_ai_provider()
    assert isinstance(oa, OpenAICompatibleProvider)
    assert oa.model_name == "some/model" and oa.base_url == "https://llm.example/v1"
    assert isinstance(get_ai_provider("openai-compatible"), OpenAICompatibleProvider)

    monkeypatch.setattr(settings, "OPENAI_COMPAT_BASE_URL", None)
    with pytest.raises(ValueError, match="OPENAI_COMPAT_BASE_URL"):
        get_ai_provider()
    with pytest.raises(ValueError, match="Unknown AI provider"):
        get_ai_provider("no-such-provider")


@pytest.mark.asyncio
async def test_health_is_not_prefilled_and_follows_real_calls(monkeypatch):
    health.reset_health()
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(settings, "ANALYSIS_MODEL", "gemini-3.5-flash")

    info = get_active_provider_info()
    assert info["status"] == "NOT_TESTED"
    assert info["is_available"] is False
    assert info["admin_diagnostics"]["last_latency_ms"] is None
    assert "CONNECTED_TESTED" not in json.dumps(info)

    rec = _Recorder([_gemini_ok({"status": "healthy"})])
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        res = await GeminiAIProvider(api_key="k", client=client).generate_structured_json("s", "u")
    assert res.success
    info = get_active_provider_info()
    assert info["status"] == "CONNECTED_TESTED" and info["is_available"] is True
    assert info["last_checked_at"] is not None

    rec = _Recorder([httpx.Response(401)])
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        await GeminiAIProvider(api_key="k", client=client).generate_structured_json("s", "u")
    assert get_active_provider_info()["status"] == "AUTH_FAILED"
    health.reset_health()
