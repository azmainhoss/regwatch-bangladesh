"""A re-uploaded PDF that reads the same keeps its analysis; a changed one waits for a new analysis (owner, 2026-11-28)."""
import uuid

import pytest
from sqlalchemy import select

from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.analysis.carry_version import carry_unchanged_analyses, page_similarity
from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.tests.factories import make_document

LONG = ("Authorized Dealers are advised to establish a dedicated cell for centralized monitoring and verification of "
        "prices relating to trade transactions including imports exports services and other cross border transactions. ") * 3


async def _analysed_doc_with_new_version(new_text: str):
    doc, v1, pages = await make_document(pages=1)
    async with AsyncSessionLocal() as db:
        p1 = await db.get(DocumentPage, pages[0].id)
        p1.cleaned_text = p1.raw_text = "Date: 26/11/2026 " + LONG
        a = DocumentAnalysis(document_version_id=v1.id, executive_summary="x", model_name="m", prompt_version="p")
        db.add(a)
        await db.flush()
        claim = AnalysisClaim(analysis_id=a.id, claim_type="SUMMARY_STATEMENT", statement="s", kind="SUMMARY_POINT",
                              check_status="PASSED", fields={"text": "s"})
        db.add(claim)
        await db.flush()
        db.add(ClaimCitation(claim_id=claim.id, page_id=p1.id, quoted_text="q"))
        v2 = DocumentVersion(document_id=doc.id, version_number=2, file_sha256=uuid.uuid4().hex * 2, file_size_bytes=1,
                             storage_path="originals/none2.pdf", page_count=1)
        db.add(v2)
        await db.flush()
        p2 = DocumentPage(document_version_id=v2.id, page_number=1, raw_text=new_text, cleaned_text=new_text)
        db.add(p2)
        d = await db.get(Document, doc.id)
        d.current_version_id = v2.id
        d.publication_status = "EXTRACTED"
        await db.commit()
        return doc.id, a.id, v2.id, p2.id, claim.id


def test_word_similarity_ignores_line_wrapping():
    assert page_similarity("a b\nc d", "a b c\nd") == 1.0


@pytest.mark.asyncio
async def test_same_text_keeps_analysis():
    doc_id, aid, v2, p2, cid = await _analysed_doc_with_new_version("Date: November 26, 2026 " + LONG)
    async with AsyncSessionLocal() as db:
        assert await carry_unchanged_analyses(db) >= 1
    async with AsyncSessionLocal() as db:
        assert (await db.get(DocumentAnalysis, aid)).document_version_id == v2
        cit = (await db.execute(select(ClaimCitation).where(ClaimCitation.claim_id == cid))).scalars().one()
        assert cit.page_id == p2
        assert (await db.get(Document, doc_id)).publication_status == "PUBLISHED_MACHINE_VERIFIED"


@pytest.mark.asyncio
async def test_changed_text_waits_for_new_analysis():
    doc_id, aid, v2, p2, cid = await _analysed_doc_with_new_version("A completely different instruction on loan classification.")
    async with AsyncSessionLocal() as db:
        await carry_unchanged_analyses(db)
    async with AsyncSessionLocal() as db:
        assert (await db.get(DocumentAnalysis, aid)).document_version_id != v2
        assert (await db.get(Document, doc_id)).publication_status == "EXTRACTED"
