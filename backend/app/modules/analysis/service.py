import asyncio
import hashlib
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
from backend.app.modules.analysis import prompts as _prompts
from backend.app.modules.analysis.models import AnalysisClaim, ClaimCitation, DocumentAnalysis
from backend.app.modules.analysis.pipeline import RegulatoryIntelligencePipeline, PipelineExecutionResult
from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims import decide as claim_decide
from backend.app.modules.claims import checks as claim_checks
from backend.app.modules.claims import reading as claim_reading
from backend.app.modules.claims import status as claim_status
from backend.app.modules.claims.build import build_claims, save_claims
from backend.app.modules.analysis.providers.factory import get_ai_provider
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.extraction.page_router import has_word_boxes, text_layer_lines_by_page
from backend.app.modules.obligations.models import Obligation
from backend.app.modules.provisions.models import Provision
from backend.app.modules.relationships.linking import link_relationship_targets
from backend.app.modules.relationships.models import DocumentRelationship


async def _announce_circular(db, doc) -> None:
    """Records a new-circular alert in this transaction. Never raises."""
    try:
        from backend.app.modules.alerts.emit import circular_published
        await circular_published(db, doc)
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)


async def _announce_library_change(db, doc_ids) -> None:
    """After a commit: check the banks that use these circulars. Never raises."""
    try:
        from backend.app.modules.alerts.sweeps import library_changed
        await library_changed(db, doc_ids)
    except Exception as exc:
        logger.warning("Alert not recorded: %s", type(exc).__name__)



def input_fingerprint(model_name: str, pages: List[Dict[str, Any]]) -> str:
    """Hash of what the model would be sent: same model + same prompt version + same page texts = same fingerprint."""
    h = hashlib.sha256((model_name or "").encode("utf-8"))
    h.update(f"\n#prompt {_prompts.PROMPT_VERSION}\n".encode("utf-8"))
    for p in sorted(pages, key=lambda x: x["page_number"]):
        h.update(f"\n#page {p['page_number']}\n".encode("utf-8"))
        h.update((p.get("cleaned_text") or "").encode("utf-8"))
    return h.hexdigest()


def pages_payload_for(version: DocumentVersion) -> List[Dict[str, Any]]:
    return [
        {
            "page_number": p.page_number,
            "raw_text": p.cleaned_text or p.raw_text,
            "cleaned_text": p.cleaned_text or p.raw_text,
            "has_tables": p.has_tables,
            "line_boxes": p.line_boxes,
        }
        for p in version.pages
    ]


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
        force_human_review: bool = False,
        provider: Optional[Any] = None,
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
        waiting = [p for p in version.pages if p.quality_status == "PENDING_VISION" and not p.is_human_corrected]
        if waiting:
            # Never analyse empty Bangla or scanned pages: wait until every page has been read.
            raise ValueError(f"Pages are still being read ({len(waiting)} waiting).")
        unread = [p for p in version.pages
                  if p.quality_status in ("NEEDS_HUMAN_REVIEW", "READ_FAILED") and not p.is_human_corrected]
        if unread:
            # A page whose reading failed or whose text is damaged may hold duties the analysis cannot see.
            # Never publish such a circular by itself: every point waits for a person.
            force_human_review = True
            logger.info(f"Document {document_id}: {len(unread)} page(s) not read cleanly; held for a person.")

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
        lease_token = await AnalysisLeaseManager.acquire_lease(db, doc.id, worker_id, lease_duration_seconds=900)
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
        pages_payload = pages_payload_for(version)

        try:
            # A ready-made provider (e.g. answers written outside the app, scripts/manual_analysis.py)
            # goes through exactly the same checks as a live model.
            provider = provider or get_ai_provider(provider_name)
            pipeline = RegulatoryIntelligencePipeline(provider)

            result: PipelineExecutionResult = await pipeline.execute_document_analysis(
                pages=pages_payload,
                document_title=doc.title,
                reference_hint=doc.reference_number,
                force_human_review=force_human_review
            )
        except Exception as e:
            await _fail(str(e))
            raise RuntimeError(f"Analysis pipeline failed: {e}") from e
        try:
            result.structured_payload["input_sha256"] = input_fingerprint(provider.model_name, pages_payload)
        except Exception:
            pass

        if not result.success:
            await _fail(str(result.error))
            raise RuntimeError(f"Analysis pipeline failed: {result.error}")

        try:
            analysis = await AnalysisService._replace_analysis_results(
                db=db,
                doc=doc,
                version=version,
                result=result,
                prior_status=prior_status,
                lease_token=lease_token,
                pages_payload=pages_payload,
                force_human_review=force_human_review,
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
        pages_payload: Optional[List[Dict[str, Any]]] = None,
        force_human_review: bool = False,
    ) -> DocumentAnalysis:
        """Swaps the old provisions/obligations/relationships for the new ones, builds and checks one claim
        per shown item, and sets each row and the circular's status from the claims, in a single commit."""
        await db.execute(delete(Obligation).where(Obligation.document_version_id == version.id))
        await db.execute(delete(Provision).where(Provision.document_version_id == version.id))
        await db.execute(delete(DocumentRelationship).where(DocumentRelationship.source_document_id == doc.id))
        await db.flush()

        payload = result.structured_payload
        index = SentenceIndex.build(pages_payload if pages_payload is not None else pages_payload_for(version))

        # Map page numbers to DocumentPage IDs
        page_id_map = {p.page_number: p.id for p in version.pages}
        default_page_id = version.pages[0].id if version.pages else None

        # 1. Create DocumentAnalysis record. Its summary text is filled in below from the points that are shown.
        analysis = DocumentAnalysis(
            document_version_id=version.id,
            executive_summary="",
            purpose=None,
            background=None,
            key_changes=[],
            impact_summary={},
            model_name=result.model_name,
            prompt_version=result.prompt_version,
            structured_payload=payload,
            citation_coverage_score=result.validation_report.citation_coverage_score,
            raw_model_response=result.raw_model_response,
            validation_errors=[item for item in result.validation_report.unverified_excerpts],
            tokens_used=result.token_usage.total_tokens,
            estimated_cost_usd=result.token_usage.estimated_cost_usd,
            processing_time_ms=result.latency_ms,
            publication_decision="AWAITING_REVIEW",
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

        # 3. Persist Obligations. Their status follows their claim (claims/status.py::sync_rows).
        obligation_rows: List[Obligation] = []
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
                obligation_type=obl_data.get("obligation_type") or "MANDATORY",
                title=obl_data.get("title") or "Regulatory Obligation",
                requirement_description=obl_data.get("requirement_description") or "",
                supporting_text=obl_data.get("verbatim_quote") or "",
                quote_span_ids=obl_data.get("quote_span_ids") or [],
                quote_boxes=obl_data.get("quote_boxes") or [],
                applicability_summary=obl_data.get("responsible_entity") or "",
                explicit_deadline=explicit_date,
                deadline_description=obl_data.get("explicit_deadline"),
                frequency=obl_data.get("reporting_frequency") or "ONE_TIME",
                verification_status="PENDING_REVIEW",
            )
            db.add(obl_record)
            obligation_rows.append(obl_record)

        # 4. Persist Relationships. A change-the-law link is not VERIFIED until a person confirms it.
        relationship_rows: List[DocumentRelationship] = []
        for rel_data in payload.get("relationships", []):
            p_no = rel_data.get("page_number", 1)
            target_page_id = page_id_map.get(p_no, default_page_id)
            hint = rel_data.get("target_reference_hint")
            rel_record = DocumentRelationship(
                source_document_id=doc.id,
                target_document_id=None,  # Filled in by link_relationship_targets once the cited circular is found
                target_reference_hint=str(hint)[:255] if hint else None,
                relationship_type=rel_data.get("relationship_type") or "REFERENCES",
                source_page_id=target_page_id,
                supporting_quote=rel_data.get("supporting_quote") or "",
                quote_span_ids=rel_data.get("quote_span_ids") or [],
                quote_boxes=rel_data.get("quote_boxes") or [],
                confidence=float(rel_data.get("confidence") or 0.9),
                detection_method="AI_INFERRED",
                verification_status="PENDING_REVIEW",
            )
            db.add(rel_record)
            relationship_rows.append(rel_record)
        await db.flush()

        # 5. Claims: build one per shown item, keep a person's earlier decisions, check, route, save.
        drafts = build_claims(payload, index, doc)
        for d in drafts:
            if d.kind == "OBLIGATION" and d.source_index is not None and d.source_index < len(obligation_rows):
                d.obligation_id = obligation_rows[d.source_index].id
            elif d.kind == "LINK" and d.source_index is not None and d.source_index < len(relationship_rows):
                d.relationship_id = relationship_rows[d.source_index].id
        await claim_status.carry_over(db, version.id, analysis.id, drafts)
        reading = await claim_reading.ensure_reading_checks(db, drafts, index, version.pages)
        await claim_checks.run_code_checks(db, drafts, index, doc, version.pages, reading)
        for d in drafts:
            claim_status.route(d, doc, force_review=force_human_review)
        claim_rows = await save_claims(db, analysis, drafts, index, page_id_map)
        await claim_status.sync_rows(db, claim_rows)

        analysis.executive_summary = claim_status.shown_text_for_summary(claim_rows)
        analysis.key_changes = [
            (c.fields or {}).get("text")
            for c in sorted(claim_rows, key=lambda c: c.order_index or 0)
            if c.kind == "KEY_CHANGE" and claim_status.is_shown(c) and (c.fields or {}).get("text")
        ]

        # Update the circular's status from its claims and release the durable lease.
        claim_status.apply_document_status(doc, claim_rows)
        analysis.publication_decision = "AWAITING_REVIEW" if doc.publication_status == "AWAITING_REVIEW" else "APPROVED"
        # An archive circular analysed on request never sends a "new circular" alert, now or when a person
        # later releases it. It is marked so a later decision knows it came from the archive.
        if prior_status == "EXTRACTED":
            claim_decide.mark_archive_run(db, doc)
        elif not await claim_decide.was_archive_circular(db, doc):
            await _announce_circular(db, doc)
        await AnalysisLeaseManager.release_lease(db, doc.id, lease_token, status="RELEASED")
        await db.commit()
        # Fill in which stored circular each cited reference names (never guessed; see relationships/linking.py).
        try:
            await link_relationship_targets(db, doc.id)
        except Exception as link_err:
            await db.rollback()
            logger.warning(f"Could not link relationship targets for document {doc.id}: {link_err}")
        try:
            rel_targets = (await db.execute(
                select(DocumentRelationship.target_document_id).where(
                    DocumentRelationship.source_document_id == doc.id,
                    DocumentRelationship.target_document_id.is_not(None),
                )
            )).scalars().all()
        except Exception:
            rel_targets = []
        await _announce_library_change(db, [doc.id, *rel_targets])
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
        await _announce_circular(db, doc)
        await db.commit()
        if decision in ("WITHDRAWN", "SUPERSEDED"):
            await _announce_library_change(db, [doc.id])
        await db.refresh(doc)
        return doc
