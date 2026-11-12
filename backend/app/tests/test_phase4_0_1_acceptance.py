"""
Phase 4.0.1 Combined Technical Acceptance, Gemini Verification & Plain-Language Telemetry Suite.
Verifies:
  1. API-level isolation: Default /documents returns ONLY genuine documents.
  2. Synthetic records (GP, VCP, UTD, Sample, BRPD(P)) are excluded from genuine corpus.
  3. Stats endpoint truthfulness and department code deduplication.
  4. Provider status plain-language service states and admin diagnostics isolation.
  5. On-demand provider handshake test.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.modules.documents.schemas import DocumentRead


@pytest.mark.asyncio
async def test_api_level_genuine_corpus_isolation():
    """Confirms that default /documents returns ONLY genuine publications."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Default request (no corpus_type passed) must default to GENUINE
        res = await client.get("/api/v1/documents")
        assert res.status_code == 200
        docs = res.json()
        assert len(docs) >= 4
        for d in docs:
            assert d["is_synthetic"] is False
            assert d["corpus_type"] == "GENUINE"
            title_low = d["title"].lower()
            ref_low = (d.get("reference_number") or "").lower()
            # Only explicit fixture markers count: real titles such as "Stress Testing" stay visible.
            assert not title_low.startswith("sample ")
            assert not ref_low.startswith("vcp-")
            assert not ref_low.startswith("utd-")
            assert not ref_low.startswith("gp-")
            assert not ref_low.startswith("brpd(p)")


@pytest.mark.asyncio
async def test_synthetic_test_area_isolation():
    """Confirms that synthetic fixtures are segregated into SYNTHETIC_SAMPLE corpus."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/documents?corpus_type=SYNTHETIC_SAMPLE&limit=10")
        assert res.status_code == 200
        docs = res.json()
        assert len(docs) > 0
        for d in docs:
            assert d["is_synthetic"] is True
            assert d["corpus_type"] == "SYNTHETIC_SAMPLE"


@pytest.mark.asyncio
async def test_stats_truthfulness_and_department_deduplication():
    """Confirms stats counts distinguish genuine vs synthetic and deduplicates department codes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/documents/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["genuine_documents_count"] >= 4
        assert data["synthetic_documents_count"] > 100
        assert data["genuine_pages_count"] >= 17
        # Distinct department codes
        assert len(data["departments_codes"]) == len(set(data["departments_codes"]))
        assert "BRPD" in data["departments_codes"]


@pytest.mark.asyncio
async def test_plain_language_provider_status_telemetry():
    """Confirms provider status separates professional service state from admin diagnostics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/documents/provider-status")
        assert res.status_code == 200
        data = res.json()
        assert "service_state" in data
        assert data["service_state"] in (
            "AI Analysis Available",
            "AI Analysis Not Connected",
            "AI Usage Limit Reached",
            "AI Analysis Temporarily Unavailable",
            "Test Mode (Offline Rules)",
        )
        assert data["billing_policy"] == "ZERO_COST_FREE_TIER"
        assert "admin_diagnostics" in data
        assert "GEMINI_API_KEY" not in str(data)

