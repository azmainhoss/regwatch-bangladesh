import pytest
from datetime import date, datetime, timezone
from uuid import uuid4

import backend.app.database.models
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.analysis.service import AnalysisService
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.institutions.models import Institution


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


async def _create_test_hierarchy(db, coverage=1.0, claim_status="VERIFIED_EXACT", citation_score=1.0, page_id=None):
    """Helper to set up test document hierarchy."""
    inst = Institution(
        id=uuid4(),
        name=f"Gate Test Inst {uuid4().hex[:6]}",
        code=f"GTI_{uuid4().hex[:6]}"
    )
    db.add(inst)
    await db.flush()

    doc = Document(
        id=uuid4(),
        institution_id=inst.id,
        title=f"Gate Policy {uuid4().hex[:6]}",
        reference_number=f"GP-{uuid4().hex[:4]}",
        publication_date=date(2026, 1, 1),
        document_type="CIRCULAR",
        publication_status="DRAFT"
    )
    db.add(doc)
    await db.flush()

    ver = DocumentVersion(
        id=uuid4(),
        document_id=doc.id,
        version_number=1,
        file_sha256=f"hash_{uuid4().hex}",
        storage_path="originals/test_gate.pdf",
        page_count=2,
        file_size_bytes=1024
    )
    db.add(ver)
    doc.current_version_id = ver.id
    await db.flush()

    page = DocumentPage(
        id=uuid4(),
        document_version_id=ver.id,
        page_number=1,
        raw_text="Sample text for verification."
    )
    db.add(page)
    await db.flush()

    target_page_id = page.id if page_id is None else page_id

    analysis = DocumentAnalysis(
        id=uuid4(),
        document_version_id=ver.id,
        model_name="mock-regulatory-v1",
        prompt_version="v1.0.0",
        executive_summary="Summary for gate test.",
        structured_payload={},
        citation_coverage_score=coverage,
        publication_decision="AWAITING_REVIEW"
    )
    db.add(analysis)
    await db.flush()

    claim = AnalysisClaim(
        id=uuid4(),
        analysis_id=analysis.id,
        claim_type="PROVISION_ASSERTION",
        statement="Mandatory reserve ratio requirement of 4%.",
        verification_status=claim_status
    )
    db.add(claim)
    await db.flush()

    citation = ClaimCitation(
        id=uuid4(),
        claim_id=claim.id,
        page_id=target_page_id,
        quoted_text="Mandatory reserve ratio requirement of 4%.",
        match_score=citation_score
    )
    db.add(citation)
    await db.commit()

    return doc, analysis, claim, citation, inst


@pytest.mark.asyncio
async def test_publication_blocked_by_partial_citation_coverage(db_session):
    """Partial citation coverage (e.g. 60.0%) must strictly block publication."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(db_session, coverage=0.60)
    try:
        with pytest.raises(ValueError, match="Publication blocked: Citation coverage is 60.0%"):
            await AnalysisService.review_and_publish_analysis(
                db=db_session,
                document_id=doc.id,
                reviewer_id=uuid4(),
                decision="PUBLISHED_HUMAN_REVIEWED",
                review_notes="Senior Officer verified partial items"
            )
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_blocked_by_candidate_fuzzy_citation(db_session):
    """Fuzzy candidate citations (CANDIDATE_FUZZY) must not count as verified and must block publication."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=1.0, claim_status="CANDIDATE_FUZZY"
    )
    try:
        with pytest.raises(ValueError, match="Publication blocked by claim-level validation.*CANDIDATE_FUZZY"):
            await AnalysisService.review_and_publish_analysis(
                db=db_session,
                document_id=doc.id,
                reviewer_id=uuid4(),
                decision="PUBLISHED_HUMAN_REVIEWED",
                review_notes="Reviewed with fuzzy candidate"
            )
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_blocked_by_wrong_page_citation(db_session):
    """Wrong page citations (WRONG_PAGE) must block publication."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=1.0, claim_status="WRONG_PAGE"
    )
    try:
        with pytest.raises(ValueError, match="Publication blocked by claim-level validation.*WRONG_PAGE"):
            await AnalysisService.review_and_publish_analysis(
                db=db_session,
                document_id=doc.id,
                reviewer_id=uuid4(),
                decision="PUBLISHED_HUMAN_REVIEWED",
                review_notes="Reviewed with wrong page"
            )
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_blocked_by_insufficient_match_score(db_session):
    """Citations with match_score below 0.85 must block publication."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=1.0, claim_status="VERIFIED_EXACT", citation_score=0.50
    )
    try:
        with pytest.raises(ValueError, match="Publication blocked: Citation has insufficient match score"):
            await AnalysisService.review_and_publish_analysis(
                db=db_session,
                document_id=doc.id,
                reviewer_id=uuid4(),
                decision="PUBLISHED_HUMAN_REVIEWED",
                review_notes="Reviewed with weak citation match score"
            )
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_blocked_by_incomplete_human_review(db_session):
    """Missing or empty review notes must block auditable human review publication."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=1.0, claim_status="VERIFIED_EXACT", citation_score=1.0
    )
    try:
        with pytest.raises(ValueError, match="Publication requires non-empty review_notes"):
            await AnalysisService.review_and_publish_analysis(
                db=db_session,
                document_id=doc.id,
                reviewer_id=uuid4(),
                decision="PUBLISHED_HUMAN_REVIEWED",
                review_notes="   "  # Empty whitespace
            )
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_publication_succeeds_when_all_claim_level_invariants_met(db_session):
    """Publication must succeed when coverage is 100%, claims are exact, and review is auditable."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=1.0, claim_status="VERIFIED_EXACT", citation_score=1.0
    )
    try:
        reviewer = uuid4()
        updated_doc = await AnalysisService.review_and_publish_analysis(
            db=db_session,
            document_id=doc.id,
            reviewer_id=reviewer,
            decision="PUBLISHED_HUMAN_REVIEWED",
            review_notes="Audited by Senior Compliance Officer against Page 1 source text."
        )
        assert updated_doc.publication_status == "PUBLISHED_HUMAN_REVIEWED"
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()


@pytest.mark.asyncio
async def test_needs_revision_state_preserves_distinction(db_session):
    """Setting decision to NEEDS_REVISION preserves review queue status without publication restrictions."""
    doc, analysis, claim, citation, inst = await _create_test_hierarchy(
        db_session, coverage=0.50, claim_status="UNVERIFIED"
    )
    try:
        updated_doc = await AnalysisService.review_and_publish_analysis(
            db=db_session,
            document_id=doc.id,
            reviewer_id=uuid4(),
            decision="NEEDS_REVISION",
            review_notes="Sent back to queue for further extraction verification"
        )
        assert updated_doc.publication_status == "NEEDS_REVISION"
    finally:
        await db_session.delete(doc)
        await db_session.delete(inst)
        await db_session.commit()
