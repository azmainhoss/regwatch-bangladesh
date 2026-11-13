"""Regression tests for the phase 0 security and data-safety fixes. No test here touches the network."""
import uuid
from datetime import date

import httpx
import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.models import DocumentAnalysis
from backend.app.modules.analysis.pipeline import RegulatoryIntelligencePipeline
from backend.app.modules.analysis.providers.base import LLMResponse
from backend.app.modules.analysis.service import AnalysisService
from backend.app.modules.documents.models import Document, DocumentPage
from backend.app.modules.documents.service import document_ingestion_service
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.organizations.models import Organization, OrganizationMember
from backend.app.modules.provisions.models import Provision
from backend.app.modules.research.service import ResearchService
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.models import Source, SourceDiscovery, SourceRun
from backend.app.modules.sources.schemas import SourceCreate, SourceUpdate
from backend.app.modules.sources.service import source_monitoring_service
from backend.app.modules.sources.url_policy import DisallowedSourceURL, validate_source_url
from backend.app.tests.factories import make_document, make_institution, make_user

BB_LIST_URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="ignore")
        self.headers = headers or {}


async def _make_source(institution_id) -> Source:
    async with AsyncSessionLocal() as db:
        src = Source(institution_id=institution_id, name=f"Test source {uuid.uuid4().hex[:6]}", base_url=BB_LIST_URL)
        db.add(src)
        await db.commit()
        await db.refresh(src)
        return src


async def _add_discovery(source_id, file_url: str, status: str = "VALIDATED") -> SourceDiscovery:
    async with AsyncSessionLocal() as db:
        run = SourceRun(source_id=source_id, run_type="TEST", status="COMPLETED")
        db.add(run)
        await db.flush()
        disc = SourceDiscovery(
            source_run_id=run.id,
            source_url=BB_LIST_URL,
            file_url=file_url,
            title=f"Fixture circular {uuid.uuid4().hex[:6]}",
            reference_number=f"FIX-{uuid.uuid4().hex[:6]}",
            publication_date=date(2026, 2, 1),
            status=status,
        )
        db.add(disc)
        await db.commit()
        await db.refresh(disc)
        return disc


# ---------------------------------------------------------------------------
# Source URL allow-list (SSRF)
# ---------------------------------------------------------------------------
def test_source_base_url_must_be_bangladesh_bank_https():
    assert validate_source_url("https://www.bb.org.bd/x") == "https://www.bb.org.bd/x"
    assert validate_source_url("https://bb.org.bd/x") == "https://bb.org.bd/x"
    for bad in [
        "https://example.com/x",
        "http://www.bb.org.bd/x",
        "https://www.bb.org.bd.evil.com/x",
        "https://169.254.169.254/latest/meta-data",
        "https://user:pw@www.bb.org.bd/x",
        "file:///etc/passwd",
        "https://www.bb.org.bd:8443/x",
    ]:
        with pytest.raises(DisallowedSourceURL):
            validate_source_url(bad)

    with pytest.raises(ValidationError):
        SourceCreate(institution_id=uuid.uuid4(), name="x", base_url="https://example.com/feed")
    with pytest.raises(ValidationError):
        SourceUpdate(base_url="http://169.254.169.254/")
    assert SourceUpdate(base_url=BB_LIST_URL).base_url == BB_LIST_URL


def test_connector_refuses_foreign_base_url():
    with pytest.raises(DisallowedSourceURL):
        BangladeshBankConnector(base_url="https://example.com/")


@pytest.mark.asyncio
async def test_connector_does_not_follow_redirect_to_other_host(monkeypatch):
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)
        return _FakeResponse(302, b"", headers={"location": "https://evil.example.com/steal.pdf"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    content, challenge = await BangladeshBankConnector().download_document(
        "https://www.bb.org.bd/mediaroom/circulars/brpd/a.pdf", backoff_base_seconds=0
    )
    assert content is None
    assert challenge.challenge_type == "DISALLOWED_URL"
    assert calls == ["https://www.bb.org.bd/mediaroom/circulars/brpd/a.pdf"]

    # A link found on a listing page that points elsewhere is never fetched
    calls.clear()
    content, challenge = await BangladeshBankConnector().download_document("https://example.com/a.pdf")
    assert content is None and challenge.challenge_type == "DISALLOWED_URL"
    assert calls == []


@pytest.mark.asyncio
async def test_api_rejects_source_with_foreign_base_url(client):
    _admin, token = await make_user(is_superuser=True)
    inst = await make_institution()
    resp = await client.post(
        "/api/v1/sources",
        headers=_auth(token),
        json={"institution_id": str(inst.id), "name": "Evil", "base_url": "https://example.com/feed"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Admin-only actions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_admin_cannot_create_or_trigger_sources(client):
    _user, token = await make_user(is_superuser=False)
    inst = await make_institution()
    src = await _make_source(inst.id)

    create = await client.post(
        "/api/v1/sources",
        headers=_auth(token),
        json={"institution_id": str(inst.id), "name": "Mine", "base_url": BB_LIST_URL},
    )
    assert create.status_code == 403
    for path in [f"/api/v1/sources/{src.id}/trigger", f"/api/v1/sources/{src.id}/discover"]:
        assert (await client.post(path, headers=_auth(token))).status_code == 403
    backfill = await client.post(f"/api/v1/sources/{src.id}/backfill", headers=_auth(token), json={})
    assert backfill.status_code == 403
    patch = await client.patch(f"/api/v1/sources/{src.id}", headers=_auth(token), json={"is_active": False})
    assert patch.status_code == 403

    inst_create = await client.post(
        "/api/v1/institutions", headers=_auth(token), json={"code": "ZZ1", "name": "Nope"}
    )
    assert inst_create.status_code == 403
    assert (await client.post("/api/v1/documents/provider-test", headers=_auth(token))).status_code == 403


@pytest.mark.asyncio
async def test_registered_user_is_not_admin(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"new_{uuid.uuid4().hex[:6]}@regwatch.bd",
        "password": "Password123!",
        "full_name": "New Person",
    })
    assert resp.status_code == 201
    assert resp.json()["user"]["is_superuser"] is False


@pytest.mark.asyncio
async def test_org_admin_of_any_org_cannot_publish(client):
    user, token = await make_user(is_superuser=False)
    async with AsyncSessionLocal() as db:
        org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
        db.add(org)
        await db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="ORG_ADMIN", status="ACTIVE"))
        await db.commit()
    doc, _version, _pages = await make_document()
    resp = await client.post(
        f"/api/v1/documents/{doc.id}/publish",
        headers=_auth(token),
        json={"decision": "WITHDRAWN", "review_notes": "trying"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_compliance_head_cannot_grant_org_admin(client):
    head, head_token = await make_user()
    target, _ = await make_user()
    async with AsyncSessionLocal() as db:
        org = Organization(name=f"Org {uuid.uuid4().hex[:6]}")
        db.add(org)
        await db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=head.id, role="COMPLIANCE_HEAD", status="ACTIVE"))
        await db.commit()
        org_id = org.id
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=_auth(head_token),
        json={"user_id": str(target.id), "role": "ORG_ADMIN"},
    )
    assert resp.status_code == 403
    ok = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=_auth(head_token),
        json={"user_id": str(target.id), "role": "ANALYST"},
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_compliance_task_cannot_be_assigned_outside_org(client):
    admin, token = await make_user()
    outsider, _ = await make_user()
    org_resp = await client.post("/api/v1/organizations", headers=_auth(token), json={"name": "Alpha"})
    org_id = org_resp.json()["id"]
    reg = await client.post(f"/api/v1/organizations/{org_id}/compliance/registers", headers=_auth(token), json={"title": "R"})
    from backend.app.tests.factories import make_obligation
    obl = await make_obligation(verified=True, doc_status="PUBLISHED_MACHINE_PROCESSED")
    bad_lead = await client.post(
        f"/api/v1/organizations/{org_id}/compliance/items",
        headers=_auth(token),
        json={"register_id": reg.json()["id"], "obligation_id": str(obl.id), "assigned_lead_id": str(outsider.id)},
    )
    assert bad_lead.status_code == 400
    item = await client.post(
        f"/api/v1/organizations/{org_id}/compliance/items",
        headers=_auth(token),
        json={"register_id": reg.json()["id"], "obligation_id": str(obl.id)},
    )
    assert item.status_code == 201
    task = await client.post(
        f"/api/v1/organizations/{org_id}/compliance/tasks",
        headers=_auth(token),
        json={"compliance_item_id": item.json()["id"], "title": "T", "due_date": "2026-12-31",
              "assigned_to_user_id": str(outsider.id)},
    )
    assert task.status_code == 400


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_page_correction_with_mismatched_document_is_refused(client):
    _admin, admin_token = await make_user(is_superuser=True)
    _user, user_token = await make_user(is_superuser=False)
    doc_a, version_a, _ = await make_document()
    doc_b, _version_b, _ = await make_document()

    payload = {"corrected_text": "tampered"}
    mismatched = await client.post(
        f"/api/v1/documents/{doc_b.id}/versions/{version_a.id}/pages/1/correct",
        headers=_auth(admin_token), json=payload,
    )
    assert mismatched.status_code == 404

    not_admin = await client.post(
        f"/api/v1/documents/{doc_a.id}/versions/{version_a.id}/pages/1/correct",
        headers=_auth(user_token), json=payload,
    )
    assert not_admin.status_code == 403

    ok = await client.post(
        f"/api/v1/documents/{doc_a.id}/versions/{version_a.id}/pages/1/correct",
        headers=_auth(admin_token), json={"corrected_text": "Corrected page text"},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_reextraction_keeps_page_ids_and_human_corrections(client):
    _admin, admin_token = await make_user(is_superuser=True)
    inst = await make_institution()
    async with AsyncSessionLocal() as db:
        doc, version, _count = await document_ingestion_service.ingest_document(
            db=db, pdf_bytes=_make_pdf(f"Banks shall report liquidity {uuid.uuid4().hex}"),
            institution_id=inst.id, title="Liquidity reporting", publication_date=date(2026, 3, 1),
        )
        doc_id, version_id = doc.id, version.id
        page_ids_before = [p.id for p in (await db.execute(
            select(DocumentPage).where(DocumentPage.document_version_id == version_id)
        )).scalars().all()]

    corrected = await client.post(
        f"/api/v1/documents/{doc_id}/versions/{version_id}/pages/1/correct",
        headers=_auth(admin_token), json={"corrected_text": "Human corrected text"},
    )
    assert corrected.status_code == 200

    resp = await client.post(f"/api/v1/documents/{doc_id}/extract", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["human_corrections_preserved"] == 1

    async with AsyncSessionLocal() as db:
        pages = (await db.execute(
            select(DocumentPage).where(DocumentPage.document_version_id == version_id)
        )).scalars().all()
        assert [p.id for p in pages] == page_ids_before
        assert pages[0].cleaned_text == "Human corrected text"
        assert pages[0].is_human_corrected is True


@pytest.mark.asyncio
async def test_real_titles_containing_test_are_not_hidden(client):
    from backend.app.modules.documents.synthetic import is_synthetic_document
    assert is_synthetic_document("Guidelines on Stress Testing for Banks", "DOS Circular No. 3") is False
    assert is_synthetic_document("Latest instructions on CRR", "BRPD Circular No. 9") is False
    assert is_synthetic_document("Sample Regulatory Circular", None) is True
    assert is_synthetic_document("Anything", "GP-1234") is True
    assert is_synthetic_document("Anything", None, flag=True) is True

    inst = await make_institution()
    ref = f"DOS Circular No. {uuid.uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        db.add(Document(institution_id=inst.id, title="Guidelines on Stress Testing for Banks",
                        reference_number=ref, publication_date=date(2026, 4, 1),
                        publication_status="PUBLISHED_MACHINE_PROCESSED"))
        await db.commit()
    resp = await client.get("/api/v1/documents", params={"search": ref, "corpus_type": "GENUINE"})
    assert resp.status_code == 200
    assert [d["reference_number"] for d in resp.json()] == [ref]


@pytest.mark.asyncio
async def test_failed_ingest_leaves_no_orphan_document(monkeypatch):
    inst = await make_institution()
    title = f"Will fail {uuid.uuid4().hex[:6]}"

    def boom(**kwargs):
        raise RuntimeError("extraction exploded")

    from backend.app.modules.extraction.service import extraction_service
    monkeypatch.setattr(extraction_service, "extract_document_pages", boom)
    async with AsyncSessionLocal() as db:
        with pytest.raises(RuntimeError):
            await document_ingestion_service.ingest_document(
                db=db, pdf_bytes=_make_pdf("x"), institution_id=inst.id, title=title,
                publication_date=date(2026, 1, 1),
            )
    async with AsyncSessionLocal() as db:
        left = (await db.execute(select(Document).where(Document.title == title))).scalars().all()
        assert left == []


# ---------------------------------------------------------------------------
# Backfill / approve
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill_downloads_ingests_and_counts_duplicates(monkeypatch):
    inst = await make_institution()
    src = await _make_source(inst.id)
    other_src = await _make_source(inst.id)
    pdf = _make_pdf(f"BRPD circular body {uuid.uuid4().hex}")
    d1 = await _add_discovery(src.id, "https://www.bb.org.bd/mediaroom/circulars/brpd/one.pdf")
    d2 = await _add_discovery(src.id, "https://www.bb.org.bd/mediaroom/circulars/brpd/same-file.pdf")
    foreign = await _add_discovery(other_src.id, "https://www.bb.org.bd/mediaroom/circulars/brpd/other.pdf")

    async def fake_get(self, url, **kwargs):
        return _FakeResponse(200, pdf)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    async with AsyncSessionLocal() as db:
        result = await source_monitoring_service.execute_backfill_batch(db=db, source_id=src.id, batch_size=10)

    assert result["attempted"] == 2
    assert result["successful"] == 1
    assert result["duplicates"] == 1
    assert result["failed"] == 0

    async with AsyncSessionLocal() as db:
        statuses = {d.id: d.status for d in (await db.execute(
            select(SourceDiscovery).where(SourceDiscovery.id.in_([d1.id, d2.id, foreign.id]))
        )).scalars().all()}
    assert sorted([statuses[d1.id], statuses[d2.id]]) == ["DUPLICATE", "INGESTED"]
    # Discoveries of another source are untouched by this source's backfill
    assert statuses[foreign.id] == "VALIDATED"


@pytest.mark.asyncio
async def test_approve_refuses_already_handled_discoveries(client):
    _admin, token = await make_user(is_superuser=True)
    inst = await make_institution()
    src = await _make_source(inst.id)
    for status in ("REJECTED", "INGESTED", "DOWNLOADED"):
        disc = await _add_discovery(src.id, f"https://www.bb.org.bd/{uuid.uuid4().hex}.pdf", status=status)
        resp = await client.post(f"/api/v1/sources/discoveries/{disc.id}/approve", headers=_auth(token))
        assert resp.status_code == 409, status
    missing = await client.post(f"/api/v1/sources/discoveries/{uuid.uuid4()}/approve", headers=_auth(token))
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
async def _seed_old_results(version, page) -> None:
    async with AsyncSessionLocal() as db:
        prov = Provision(document_version_id=version.id, page_id=page.id, verbatim_text="Old provision", order_index=1)
        db.add(prov)
        await db.flush()
        db.add(Obligation(
            document_version_id=version.id, provision_id=prov.id, page_id=page.id, obligation_type="MANDATORY",
            title="Old obligation", requirement_description="old", supporting_text="old", applicability_summary="all",
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_failed_reanalysis_keeps_previous_results(monkeypatch):
    doc, version, pages = await make_document(status="PUBLISHED_HUMAN_REVIEWED")
    await _seed_old_results(version, pages[0])

    async def failing_analysis(self, **kwargs):
        raise RuntimeError("provider timed out")

    monkeypatch.setattr(RegulatoryIntelligencePipeline, "execute_document_analysis", failing_analysis)

    async with AsyncSessionLocal() as db:
        with pytest.raises(RuntimeError):
            await AnalysisService.analyze_document_version(db=db, document_id=doc.id, provider_name="mock")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc.id)
        assert refreshed.publication_status == "PUBLISHED_HUMAN_REVIEWED"
        provs = (await db.execute(select(Provision).where(Provision.document_version_id == version.id))).scalars().all()
        obls = (await db.execute(select(Obligation).where(Obligation.document_version_id == version.id))).scalars().all()
        assert [p.verbatim_text for p in provs] == ["Old provision"]
        assert [o.title for o in obls] == ["Old obligation"]
        from backend.app.modules.analysis.models import AnalysisLease
        lease = (await db.execute(select(AnalysisLease).where(AnalysisLease.document_id == doc.id))).scalars().first()
        assert lease is not None and lease.status == "FAILED"


@pytest.mark.asyncio
async def test_successful_reanalysis_sends_reviewed_document_back_to_review():
    doc, version, pages = await make_document(status="PUBLISHED_HUMAN_REVIEWED")
    await _seed_old_results(version, pages[0])

    async with AsyncSessionLocal() as db:
        analysis = await AnalysisService.analyze_document_version(db=db, document_id=doc.id, provider_name="mock")
        assert analysis.publication_decision == "AWAITING_REVIEW"

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Document, doc.id)
        assert refreshed.publication_status == "AWAITING_REVIEW"
        provs = (await db.execute(select(Provision).where(Provision.document_version_id == version.id))).scalars().all()
        assert "Old provision" not in [p.verbatim_text for p in provs]


@pytest.mark.asyncio
async def test_publish_refused_without_analysis(client):
    _admin, token = await make_user(is_superuser=True)
    doc, _version, _pages = await make_document(status="AWAITING_REVIEW")
    resp = await client.post(
        f"/api/v1/documents/{doc.id}/publish",
        headers=_auth(token),
        json={"decision": "PUBLISHED_HUMAN_REVIEWED", "review_notes": "Looks fine"},
    )
    assert resp.status_code == 400
    assert "no analysis" in resp.json()["detail"]
    async with AsyncSessionLocal() as db:
        assert (await db.get(Document, doc.id)).publication_status == "AWAITING_REVIEW"
        assert (await db.execute(select(DocumentAnalysis).where(
            DocumentAnalysis.document_version_id == doc.current_version_id))).first() is None


# ---------------------------------------------------------------------------
# Research assistant
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_research_not_grounded_when_ai_fails(monkeypatch):
    token = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        inst = await make_institution()
        # Push the target document past the first 25 documents to prove all documents are searched
        for _ in range(26):
            db.add(Document(institution_id=inst.id, title="Filler", reference_number=f"F-{uuid.uuid4().hex[:6]}",
                            publication_date=date(2020, 1, 1)))
        await db.commit()
    doc, _version, _pages = await make_document()
    async with AsyncSessionLocal() as db:
        page = (await db.execute(select(DocumentPage).where(DocumentPage.document_version_id == doc.current_version_id))).scalars().first()
        page.cleaned_text = f"The {token} reserve requirement applies to all banks."
        await db.commit()

    class FailingProvider:
        async def generate_structured_json(self, **kwargs):
            return LLMResponse(raw_content="partial junk", model_name="x", success=False, error="timeout")

    monkeypatch.setattr("backend.app.modules.research.service.get_answer_provider", lambda *a, **k: FailingProvider())
    async with AsyncSessionLocal() as db:
        resp = await ResearchService.query_regulatory_knowledge(db=db, query=f"What is the {token} requirement?")
    assert resp.is_grounded is False
    assert resp.answer == "I could not verify this from the available regulatory documents."
    assert any(c.reference_number == doc.reference_number for c in resp.citations)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def test_production_requires_private_secret_key(monkeypatch):
    from backend.app.core.config import LEGACY_DEFAULT_SECRET_KEY, Settings
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ENVIRONMENT="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=LEGACY_DEFAULT_SECRET_KEY)
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    assert Settings(_env_file=None, ENVIRONMENT="production").SECRET_KEY == "x" * 48
    dev = Settings(_env_file=None, ENVIRONMENT="development")
    assert dev.SECRET_KEY


def test_allowed_origins_from_comma_list(monkeypatch):
    from backend.app.core.config import Settings
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com, https://admin.example.com")
    assert Settings(_env_file=None).ALLOWED_ORIGINS == ["https://app.example.com", "https://admin.example.com"]
