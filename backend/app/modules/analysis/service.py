import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.logging import logger
from backend.app.core.storage import storage_service
from backend.app.modules.analysis.leases import AnalysisLeaseManager
from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.analysis.pipeline import RegulatoryIntelligencePipeline, PipelineExecutionResult
from backend.app.modules.analysis.providers.factory import get_ai_provider
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.page_router import has_word_boxes, text_layer_lines_by_page
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.provisions.models import Provision
from backend.app.modules.relationships.models import DocumentRelationship


class AnalysisService:
    @staticmethod
    async def _fill_text_layer_word_boxes(version: DocumentVersion) -> int:
        """Adds line and word boxes from the stored PDF to text-layer pages that lack word boxes.

        Pages read from their image keep their own boxes. Returns how many pages were filled.
        Any problem (missing file, unreadable PDF) leaves the pages as they were.
        """
        missing = [p for p in version.pages if (p.raw_text or p.cleaned_text) and not has_word_boxes(p.line_boxes)]
        if not missing or not version.storage_path:
            return 0
        try:
            pdf_bytes = storage_service.get_file_bytes(version.storage_path)
            by_page = await asyncio.to_thread(text_layer_lines_by_page, pdf_bytes)
        except Exception as e:
            logger.info(f"Word boxes not added for version {version.id}: {e}")
            return 0
        filled = 0
        for page in missing:
            lines = by_page.get(page.page_number)
            if lines:
                page.line_boxes = lines
                filled += 1
        return filled

    @staticmethod
    async def analyze_document_version(
        db: AsyncSession,
        document_id: UUID,
        version_id: Optional[UUID] = None,
        provider_name: Optional[str] = None,
        force_human_review: bool = False
    ) -> DocumentAnalysis:
        """
        Executes end-to-end regulatory intelligence extraction on a document version.
        Saves provisions, obligations, relationships, and claims transactionally.
        """
        doc = await db.get(Document, document_id)
        if not doc:
            raise ValueError("Document not found.")

        target_version_id = version_id or doc.current_version_id
        if not target_version_id:
            raise ValueError("Document has no version to analyze.")

        version_query = await db.execute(
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.pages))
            .where(DocumentVersion.id == target_version_id)
        )
        version = version_query.scalar_one_or_none()
        if not version or not version.pages:
            raise ValueError("Document version or its pages are missing.")

        # Check for active concurrent processing (prevent duplicate pipeline runs)
        now = datetime.now(timezone.utc)
        updated_at = doc.updated_at
        if updated_at and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        if doc.publication_status == "ANALYZING" and updated_at and (now - updated_at).total_seconds() < 300:
            raise ValueError(f"Document analysis already in progress (started at {updated_at}).")

        # Acquire durable database-backed lease across all workers/processes.
        # The lease is the concurrency guard; the document status is left alone
        # until a new analysis has been produced and saved.
        worker_id = f"worker-{os.getpid()}-{uuid4().hex[:6]}"
        lease_token = await AnalysisLeaseManager.acquire_lease(db, doc.id, worker_id)
        await db.commit()
        prior_status = doc.publication_status
        doc_id = doc.id

        async def _fail(reason: str) -> None:
            # Discard anything half-written, keep the previous results and status,
            # and record the failure on the lease (the record of this analysis run).
            await db.rollback()
            try:
                await AnalysisLeaseManager.release_lease(db, doc_id, lease_token, status="FAILED")
                await db.commit()
            except Exception as lease_err:
                await db.rollback()
                logger.error(f"Could not record failed analysis run for document {doc_id}: {lease_err}")
            logger.error(f"Analysis failed for document {doc_id}; previous results kept. Reason: {reason}")

        # English text-layer pages read before word boxes were stored get them now, so their
        # quotes can be marked on the page image word for word.
        await AnalysisService._fill_text_layer_word_boxes(version)

        # Prepare page dictionary for pipeline
        pages_payload = [
            {
                "page_number": p.page_number,
                "raw_text": p.cleaned_text or p.raw_text,
                "cleaned_text": p.cleaned_text or p.raw_text,
                "has_tables": p.has_tables,
                "line_boxes": p.line_boxes,
            }
            for p in version.pages
        ]

        try:
            provider = get_ai_provider(provider_name)
            pipeline = RegulatoryIntelligencePipeline(provider)

            result: PipelineExecutionResult = await pipeline.execute_document_analysis(
                pages=pages_payload,
                document_title=doc.title,
                reference_hint=doc.reference_number,
                force_human_review=force_human_review
            )
        except Exception as e:
            await _fail(str(e))
            raise RuntimeError(f"AI analysis pipeline failed: {e}") from e

        if not result.success:
            await _fail(str(result.error))
            raise RuntimeError(f"AI analysis pipeline failed: {result.error}")

        try:
            analysis = await AnalysisService._replace_analysis_results(
                db=db,
                doc=doc,
                version=version,
                result=result,
                prior_status=prior_status,
                lease_token=lease_token,
            )
        except Exception as e:
            await _fail(str(e))
            raise

        logger.info(f"Analysis saved successfully for doc '{doc.title}'. Published status: {doc.publication_status}")
        return analysis

    @staticmethod
    async def _replace_analysis_results(
        db: AsyncSession,
        doc: Document,
        version: DocumentVersion,
        result: PipelineExecutionResult,
        prior_status: Optional[str],
        lease_token: str,
    ) -> DocumentAnalysis:
        """Swaps the old provisions/obligations/relationships for the new ones in a single commit."""
        await db.execute(delete(Obligation).where(Obligation.document_version_id == version.id))
        await db.execute(delete(Provision).where(Provision.document_version_id == version.id))
        await db.execute(delete(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id))
        await db.flush()

        # A document a person already reviewed and published must go back to review
        # when its analysis changes, rather than silently showing unreviewed content.
        needs_re_review = prior_status == "PUBLISHED_HUMAN_REVIEWED"

        payload = result.structured_payload
        exec_summary = payload.get("executive_summary", {})

        # Map page numbers to DocumentPage IDs
        page_id_map = {p.page_number: p.id for p in version.pages}
        default_page_id = version.pages[0].id if version.pages else None

        # 1. Create DocumentAnalysis record
        analysis = DocumentAnalysis(
            document_version_id=version.id,
            executive_summary=exec_summary.get("short_summary", "Summary pending"),
            purpose=exec_summary.get("purpose"),
            background=exec_summary.get("background"),
            key_changes=exec_summary.get("key_changes", []),
            impact_summary=payload.get("impact_assessment", {}),
            model_name=result.model_name,
            prompt_version=result.prompt_version,
            structured_payload=payload,
            citation_coverage_score=result.validation_report.citation_coverage_score,
            raw_model_response=result.raw_model_response,
            validation_errors=[item for item in result.validation_report.unverified_excerpts],
            tokens_used=result.token_usage.total_tokens,
            estimated_cost_usd=result.token_usage.estimated_cost_usd,
            processing_time_ms=result.latency_ms,
            publication_decision="AWAITING_REVIEW" if (needs_re_review or result.publication_status == "AWAITING_REVIEW") else "APPROVED"
        )
        db.add(analysis)
        await db.flush()

        # 2. Persist Provisions
        provision_map: Dict[str, Provision] = {}
        for prov_idx, prov_data in enumerate(payload.get("provisions", [])):
            p_no = prov_data.get("page_number", 1)
            target_page_id = page_id_map.get(p_no, default_page_id)
            prov_record = Provision(
                document_version_id=version.id,
                page_id=target_page_id,
                provision_number=prov_data.get("provision_number"),
                heading=prov_data.get("heading"),
                verbatim_text=prov_data.get("verbatim_text", ""),
                quote_span_ids=prov_data.get("quote_span_ids") or [],
                quote_boxes=prov_data.get("quote_boxes") or [],
                order_index=prov_idx + 1
            )
            db.add(prov_record)
            await db.flush()
            if prov_data.get("provision_number"):
                provision_map[prov_data["provision_number"]] = prov_record

        # 3. Persist Obligations
        for obl_data in payload.get("obligations", []):
            p_no = obl_data.get("page_number", 1)
            target_page_id = page_id_map.get(p_no, default_page_id)
            clause_ref = obl_data.get("clause_reference")
            prov = provision_map.get(clause_ref) if clause_ref else None

            # Parse explicit deadline if present
            explicit_date = None
            if obl_data.get("explicit_deadline"):
                try:
                    explicit_date = datetime.strptime(obl_data["explicit_deadline"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    explicit_date = None

            obl_record = Obligation(
                document_version_id=version.id,
                provision_id=prov.id if prov else None,
                page_id=target_page_id,
                obligation_type=obl_data.get("obligation_type", "MANDATORY"),
                title=obl_data.get("title", "Regulatory Obligation"),
                requirement_description=obl_data.get("requirement_description", ""),
                supporting_text=obl_data.get("verbatim_quote", ""),
                quote_span_ids=obl_data.get("quote_span_ids") or [],
                quote_boxes=obl_data.get("quote_boxes") or [],
                applicability_summary=obl_data.get("responsible_entity", "Scheduled Commercial Banks"),
                explicit_deadline=explicit_date,
                deadline_description=obl_data.get("explicit_deadline"),
                frequency=obl_data.get("reporting_frequency", "ONE_TIME"),
                verification_status="VERIFIED" if obl_data.get("verification_status") in ("VERIFIED", "VERIFIED_EXACT", "VERIFIED_NORMALIZED") else "PENDING_REVIEW"
            )
            db.add(obl_record)

        # 4. Persist Relationships
        for rel_data in payload.get("relationships", []):
            p_no = rel_data.get("page_number", 1)
            target_page_id = page_id_map.get(p_no, default_page_id)
            rel_record = DocumentRelationship(
                source_document_id=doc.id,
                target_document_id=None,  # Linked later if target exists
                target_reference_hint=rel_data.get("target_reference_hint"),
                relationship_type=rel_data.get("relationship_type", "REFERENCES"),
                source_page_id=target_page_id,
                supporting_quote=rel_data.get("supporting_quote", ""),
                quote_span_ids=rel_data.get("quote_span_ids") or [],
                quote_boxes=rel_data.get("quote_boxes") or [],
                confidence=float(rel_data.get("confidence", 0.9)),
                detection_method="AI_INFERRED",
                verification_status="VERIFIED" if rel_data.get("verification_status") in ("VERIFIED", "VERIFIED_EXACT", "VERIFIED_NORMALIZED") else "PENDING_REVIEW"
            )
            db.add(rel_record)

        # 5. Persist Claims & Citations
        for prov_data in payload.get("provisions", []):
            claim = AnalysisClaim(
                analysis_id=analysis.id,
                claim_type="PROVISION_ASSERTION",
                statement=prov_data.get("normalized_explanation") or prov_data.get("heading") or "Provision claim",
                verification_status=prov_data.get("verification_status", "UNVERIFIED")
            )
            db.add(claim)
            await db.flush()

            p_no = prov_data.get("page_number", 1)
            target_page_id = page_id_map.get(p_no, default_page_id)
            citation = ClaimCitation(
                claim_id=claim.id,
                page_id=target_page_id,
                quoted_text=prov_data.get("verbatim_text", ""),
                quote_span_ids=prov_data.get("quote_span_ids") or [],
                quote_boxes=prov_data.get("quote_boxes") or [],
                match_score=float(prov_data.get("citation_match_score", 1.0))
            )
            db.add(citation)

        # Update Document publication status and release durable lease
        doc.publication_status = "AWAITING_REVIEW" if needs_re_review else result.publication_status
        await AnalysisLeaseManager.release_lease(db, doc.id, lease_token, status="RELEASED")
        await db.commit()
        await db.refresh(analysis)
        return analysis

    ALLOWED_REVIEW_DECISIONS = {
        "PUBLISHED_HUMAN_REVIEWED",
        "REJECTED",
        "NEEDS_REVISION",
        "CORRECTED",
        "WITHDRAWN",
        "SUPERSEDED"
    }

    @staticmethod
    async def review_and_publish_analysis(
        db: AsyncSession,
        document_id: UUID,
        reviewer_id: UUID,
        decision: str,
        review_notes: Optional[str] = None
    ) -> Document:
        """
        Records human editor review decision, audits the decision,
        validates state machine transitions, and updates the document's publication status.
        """
        if decision not in AnalysisService.ALLOWED_REVIEW_DECISIONS:
            raise ValueError(
                f"Invalid review decision '{decision}'. Allowed: {sorted(list(AnalysisService.ALLOWED_REVIEW_DECISIONS))}"
            )

        doc = await db.get(Document, document_id)
        if not doc or not doc.current_version_id:
            raise ValueError("Document or active version not found.")

        # State transition validation
        current_status = doc.publication_status
        if current_status == "EXTRACTION_FAILED" and decision in ("PUBLISHED_HUMAN_REVIEWED", "CORRECTED"):
            raise ValueError("Cannot publish a document whose extraction has failed. Please re-extract or correct the document first.")

        if current_status == "WITHDRAWN" and decision == "PUBLISHED_HUMAN_REVIEWED":
            raise ValueError("Cannot publish a document that has been marked as WITHDRAWN.")

        if current_status == "SUPERSEDED" and decision == "PUBLISHED_HUMAN_REVIEWED":
            raise ValueError("Cannot publish a document that has been marked as SUPERSEDED.")

        # Find latest analysis
        query = select(DocumentAnalysis).where(
            DocumentAnalysis.document_version_id == doc.current_version_id
        ).order_by(DocumentAnalysis.created_at.desc()).limit(1)
        analysis = (await db.execute(query)).scalars().first()

        # Phase 3.9 Strengthened Claim-Level Publication Gates
        if decision == "PUBLISHED_HUMAN_REVIEWED":
            # 1. Auditable human approval validation
            if not reviewer_id:
                raise ValueError("Publication requires an explicit reviewer_id for compliance auditability.")
            if not review_notes or not review_notes.strip():
                raise ValueError("Publication requires non-empty review_notes documenting the human compliance verification.")

            if analysis is None:
                raise ValueError(
                    "Publication blocked: this document version has no analysis. Run the analysis and verify it before publishing."
                )

            if analysis:
                # 2. Strict citation coverage threshold (must be 100% verified, partial coverage disallowed)
                if analysis.citation_coverage_score < 1.0:
                    raise ValueError(
                        f"Publication blocked: Citation coverage is {analysis.citation_coverage_score * 100:.1f}%. "
                        f"A mandatory citation validation failure prevents publication. Every regulatory claim must "
                        f"have verified page-level provenance (100.0% coverage required)."
                    )

                # 3. Claim-level citation verification
                claims_query = select(AnalysisClaim).options(
                    selectinload(AnalysisClaim.citations)
                ).where(AnalysisClaim.analysis_id == analysis.id)
                claims = (await db.execute(claims_query)).scalars().all()

                for claim in claims:
                    if claim.verification_status in ("UNVERIFIED", "CANDIDATE_FUZZY", "WRONG_PAGE", "SOURCE_MISSING"):
                        raise ValueError(
                            f"Publication blocked by claim-level validation: Claim '{claim.statement[:50]}' "
                            f"has status '{claim.verification_status}'. Candidate fuzzy, wrong page, or unverified claims "
                            f"cannot be published without verified source grounding."
                        )
                    for citation in claim.citations:
                        if citation.match_score < 0.85:
                            raise ValueError(
                                f"Publication blocked: Citation has insufficient match score ({citation.match_score:.2f} < 0.85)."
                            )
                        if not citation.page_id:
                            raise ValueError("Publication blocked: Citation is missing a valid page reference.")

        if analysis:
            analysis.publication_decision = decision
            analysis.reviewed_by = reviewer_id
            analysis.reviewed_at = datetime.now(timezone.utc)
            analysis.review_notes = review_notes

        doc.publication_status = decision
        await db.commit()
        await db.refresh(doc)
        return doc
