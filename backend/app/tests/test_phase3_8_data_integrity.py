import pytest
from datetime import date, datetime, timezone
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from backend.app.database.session import AsyncSessionLocal
from backend.app.main import app
from backend.app.modules.analysis.models import DocumentAnalysis
from backend.app.modules.analysis.service import AnalysisService
from backend.app.modules.documents.models import Document, DocumentVersion
from backend.app.modules.documents.schemas import DocumentRead
from backend.app.modules.institutions.models import Institution


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_document_read_computed_corpus_type():
    """Verify that DocumentRead properly computes is_synthetic and corpus_type."""
    doc_id = uuid4()
    inst_id = uuid4()
    now = datetime.now(timezone.utc)

    sample_doc = Document(
        id=doc_id,
        institution_id=inst_id,
        title="Sample Test Circular on Liquidity Support",
        reference_number="SAMPLE-01",
        publication_date=date(2024, 1, 1),
        document_type="CIRCULAR",
        publication_status="DRAFT",
        created_at=now,
        updated_at=now
    )
    read_sample = DocumentRead.model_validate(sample_doc)
    assert read_sample.is_synthetic is True
    assert read_sample.corpus_type == "SYNTHETIC_SAMPLE"

    official_doc = Document(
        id=uuid4(),
        institution_id=inst_id,
        title="SMESPD Circular No. 05/2026: Financial Assistance for Young Entrepreneurs",
        reference_number="SMESPD-05/2026",
        publication_date=date(2026, 3, 1),
        document_type="CIRCULAR",
        publication_status="PUBLISHED_HUMAN_REVIEWED",
        created_at=now,
        updated_at=now
    )
    read_official = DocumentRead.model_validate(official_doc)
    assert read_official.is_synthetic is False
    assert read_official.corpus_type == "GENUINE"


@pytest.mark.asyncio
async def test_publication_blocked_when_citation_coverage_is_zero(db_session):
    """Verify that human review publication is blocked when citation coverage score is 0.0."""
    inst = Institution(
        id=uuid4(),
        name="Test Regulatory Bank",
        code=f"TRB_{uuid4().hex[:6]}",
        website_url="https://trb.example.gov.bd"
    )
    db_session.add(inst)
    await db_session.flush()

    doc = Document(
        id=uuid4(),
        institution_id=inst.id,
        title="Unverified Test Directive",
        reference_number=f"UTD-{uuid4().hex[:4]}",
        publication_date=date(2026, 1, 1),
        document_type="CIRCULAR",
        publication_status="DRAFT"
    )
    db_session.add(doc)
    await db_session.flush()

    version = DocumentVersion(
        id=uuid4(),
        document_id=doc.id,
        version_number=1,
        file_sha256="dummy_sha256_hash",
        storage_path="originals/dummy.pdf",
        page_count=5,
        file_size_bytes=1024
    )
    db_session.add(version)
    doc.current_version_id = version.id
    await db_session.flush()

    # Analysis with 0.0% verified citation coverage
    analysis = DocumentAnalysis(
        id=uuid4(),
        document_version_id=version.id,
        model_name="mock-regulatory-v1",
        prompt_version="v1.0.0",
        executive_summary="Unverified summary.",
        structured_payload={},
        citation_coverage_score=0.0,
        publication_decision="AWAITING_REVIEW"
    )
    db_session.add(analysis)
    await db_session.commit()

    # Attempting to publish without citation verification must raise ValueError
    with pytest.raises(ValueError, match="Publication blocked: Citation coverage is 0.0%"):
        await AnalysisService.review_and_publish_analysis(
            db=db_session,
            document_id=doc.id,
            reviewer_id=uuid4(),
            decision="PUBLISHED_HUMAN_REVIEWED",
            review_notes="Attempted invalid publication"
        )


@pytest.mark.asyncio
async def test_publication_allowed_when_citations_verified(db_session):
    """Verify that human review publication succeeds when citation coverage score > 0."""
    inst = Institution(
        id=uuid4(),
        name="Verified Regulatory Bank",
        code=f"VRB_{uuid4().hex[:6]}",
        website_url="https://vrb.example.gov.bd"
    )
    db_session.add(inst)
    await db_session.flush()

    doc = Document(
        id=uuid4(),
        institution_id=inst.id,
        title="Verified Citation Policy",
        reference_number=f"VCP-{uuid4().hex[:4]}",
        publication_date=date(2026, 1, 1),
        document_type="CIRCULAR",
        publication_status="DRAFT"
    )
    db_session.add(doc)
    await db_session.flush()

    version = DocumentVersion(
        id=uuid4(),
        document_id=doc.id,
        version_number=1,
        file_sha256="dummy_verified_sha256",
        storage_path="originals/dummy_verified.pdf",
        page_count=5,
        file_size_bytes=2048
    )
    db_session.add(version)
    doc.current_version_id = version.id
    await db_session.flush()

    analysis = DocumentAnalysis(
        id=uuid4(),
        document_version_id=version.id,
        model_name="mock-regulatory-v1",
        prompt_version="v1.0.0",
        executive_summary="Verified summary.",
        structured_payload={},
        citation_coverage_score=1.0,
        publication_decision="AWAITING_REVIEW"
    )
    db_session.add(analysis)
    await db_session.commit()

    # Publishing with 1.0 citation score must succeed
    reviewer_id = uuid4()
    updated_doc = await AnalysisService.review_and_publish_analysis(
        db=db_session,
        document_id=doc.id,
        reviewer_id=reviewer_id,
        decision="PUBLISHED_HUMAN_REVIEWED",
        review_notes="Verified by senior compliance officer"
    )

    assert updated_doc.publication_status == "PUBLISHED_HUMAN_REVIEWED"


@pytest.mark.asyncio
async def test_document_stats_endpoint_truthfulness():
    """Verify that GET /api/v1/documents/stats returns truthful live data."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/documents/stats")
        assert response.status_code == 200
        data = response.json()

        assert "total_documents" in data
        assert "genuine_documents_count" in data
        assert "synthetic_documents_count" in data
        assert "genuine_pages_count" in data
        assert data["primary_authority"] == "Bangladesh Bank"
        assert data["source_monitoring_status"] == "IMPERVA_TSPD_CAPTCHA"
        assert "Imperva WAF anti-bot challenge" in data["source_monitoring_message"]
        assert data["genuine_documents_count"] >= 4
        assert data["synthetic_documents_count"] >= 35


@pytest.mark.asyncio
async def test_documents_list_corpus_filtering():
    """Verify that /api/v1/documents correctly filters by corpus_type."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Genuine only
        resp_genuine = await client.get("/api/v1/documents?corpus_type=GENUINE")
        assert resp_genuine.status_code == 200
        docs_genuine = resp_genuine.json()
        assert len(docs_genuine) > 0
        for d in docs_genuine:
            assert d["is_synthetic"] is False
            assert d["corpus_type"] == "GENUINE"

        # 2. Synthetic only
        resp_synth = await client.get("/api/v1/documents?corpus_type=SYNTHETIC_SAMPLE")
        assert resp_synth.status_code == 200
        docs_synth = resp_synth.json()
        assert len(docs_synth) > 0
        for d in docs_synth:
            assert d["is_synthetic"] is True
            assert d["corpus_type"] == "SYNTHETIC_SAMPLE"
