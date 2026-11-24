"""Phase 1 analysis upload (analysis/upload_router.py): machine token only, one circular at a time, same checks."""
import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.documents.models import Document
from backend.app.tests.factories import make_document, make_user

TOKEN = "t" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", SecretStr(TOKEN))


async def shared_doc(pages: int = 1):
    """A Bangladesh Bank circular in the shared library (the factory makes synthetic ones)."""
    doc, version, rows = await make_document(pages=pages)
    async with AsyncSessionLocal() as db:
        row = await db.get(Document, doc.id)
        row.is_synthetic_fixture = False
        await db.commit()
    return doc, version, rows


def answer(sentence_id: str = "p1.s1") -> dict:
    return {
        "classification": {"document_type": "CIRCULAR", "institution": "Bangladesh Bank", "department": None,
                           "reference_number": None, "publication_date": "2026-01-01", "subject": "Liquidity",
                           "language": "en", "regulatory_topic": "Liquidity"},
        "executive_summary": {"summary_points": [{"text": "Banks must keep a liquidity ratio.", "evidence_ids": [sentence_id]}],
                              "key_changes": []},
        "provisions": [],
        "obligations": [{"title": "Maintain the liquidity ratio", "obligation_type": "MANDATORY",
                         "requirement_description": "Banks shall maintain the liquidity ratio.",
                         "quote_span_ids": [sentence_id], "responsible_entity": None, "who_ids": [],
                         "explicit_deadline": None, "deadline_text": None, "deadline_ids": [],
                         "effective_date": None, "effective_date_ids": [], "reporting_frequency": "EVENT_DRIVEN",
                         "consequence": None, "consequence_ids": [], "clause_reference": None}],
        "applicability": {"covered": [], "exemptions": []},
        "deadlines": {"effective_date": None, "compliance_deadline": None, "reporting_deadline": None},
        "relationships": [],
    }


@pytest.mark.asyncio
async def test_routes_do_not_exist_without_a_token(client, monkeypatch):
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", None)
    assert (await client.get("/api/v1/analysis-upload/pending", headers=AUTH)).status_code == 404
    monkeypatch.setattr(settings, "ANALYSIS_UPLOAD_TOKEN", SecretStr("short"))  # too short counts as not set
    assert (await client.get("/api/v1/analysis-upload/pending", headers=AUTH)).status_code == 404


@pytest.mark.asyncio
async def test_wrong_token_and_user_logins_are_refused(client, token):
    assert (await client.get("/api/v1/analysis-upload/pending")).status_code == 401
    assert (await client.get("/api/v1/analysis-upload/pending", headers={"Authorization": "Bearer nope"})).status_code == 401
    _admin, admin_jwt = await make_user(is_superuser=True)
    assert (await client.get("/api/v1/analysis-upload/pending",
                             headers={"Authorization": f"Bearer {admin_jwt}"})).status_code == 401


@pytest.mark.asyncio
async def test_pending_text_and_upload_one_circular(client, token):
    doc, _version, _rows = await shared_doc()
    pending = (await client.get("/api/v1/analysis-upload/pending?limit=200", headers=AUTH)).json()["circulars"]
    assert str(doc.id) in [c["document_id"] for c in pending]

    text_res = await client.get(f"/api/v1/analysis-upload/circulars/{doc.id}/text", headers=AUTH)
    assert text_res.status_code == 200 and "[p1.s1]" in text_res.json()["text"]

    bad = await client.post(f"/api/v1/analysis-upload/circulars/{doc.id}/analysis", headers=AUTH, content=b"{not json")
    assert bad.status_code == 422
    unknown = await client.post(f"/api/v1/analysis-upload/circulars/{doc.id}/analysis", headers=AUTH,
                                content=json.dumps(answer("p9.s9")))
    assert unknown.status_code == 422 and any("p9.s9" in p for p in unknown.json()["detail"]["problems"])

    ok = await client.post(f"/api/v1/analysis-upload/circulars/{doc.id}/analysis", headers=AUTH,
                           content=json.dumps(answer()))
    assert ok.status_code == 200, ok.text
    assert sum(ok.json()["points"].values()) >= 1

    again = await client.post(f"/api/v1/analysis-upload/circulars/{doc.id}/analysis", headers=AUTH,
                              content=json.dumps(answer()))
    assert again.status_code == 409
    pending = (await client.get("/api/v1/analysis-upload/pending?limit=200", headers=AUTH)).json()["circulars"]
    assert str(doc.id) not in [c["document_id"] for c in pending]


@pytest.mark.asyncio
async def test_private_or_missing_circulars_are_not_offered(client, token):
    doc, _v, _r = await make_document()  # synthetic fixture: not part of the shared library
    assert (await client.get(f"/api/v1/analysis-upload/circulars/{doc.id}/text", headers=AUTH)).status_code == 404


@pytest.mark.asyncio
async def test_admin_status_needs_a_superuser(client, token):
    _u, user_jwt = await make_user()
    assert (await client.get("/api/v1/analysis-upload/admin-status",
                             headers={"Authorization": f"Bearer {user_jwt}"})).status_code == 403
    _a, admin_jwt = await make_user(is_superuser=True)
    res = await client.get("/api/v1/analysis-upload/admin-status", headers={"Authorization": f"Bearer {admin_jwt}"})
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True and "stale" in body and "recent_circulars_waiting" in body


@pytest.mark.asyncio
async def test_production_never_writes_mock_analyses(monkeypatch):
    """Phase 1 server: no model, so nothing is analysed by itself and a manual run is refused."""
    from backend.app.modules.analysis.auto import auto_analysis_enabled
    from backend.app.modules.analysis.service import AnalysisService

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ANALYSIS_PROVIDER", "mock")
    monkeypatch.setattr(settings, "ANALYSIS_AUTO_ENABLED", True)
    assert auto_analysis_enabled() is False
    doc, _v, _p = await shared_doc()
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="No analysis model"):
            await AnalysisService.analyze_document_version(db, doc.id)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ANALYSIS_AUTO_ENABLED", False)
    assert auto_analysis_enabled() is False
