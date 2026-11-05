import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.core.logging import logger
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage
from backend.app.modules.analysis.prompts import PROMPT_VERSION, SYSTEM_REGULATORY_PROMPT, USER_ANALYSIS_PROMPT_TEMPLATE
from backend.app.modules.analysis.citations import CitationValidator, ClaimValidationReport


class PipelineExecutionResult(BaseModel):
    success: bool
    model_name: str
    prompt_version: str
    structured_payload: Dict[str, Any]
    raw_model_response: str
    token_usage: TokenUsage
    latency_ms: int
    validation_report: ClaimValidationReport
    publication_status: str  # PUBLISHED_MACHINE_PROCESSED or AWAITING_REVIEW or FAILED
    error: Optional[str] = None


class RegulatoryIntelligencePipeline:
    """
    Multi-stage end-to-end regulatory document analysis pipeline:
    1. Formats page text with page-level boundaries.
    2. Runs AI provider inference for structured intelligence.
    3. Runs mandatory deterministic citation verification.
    4. Evaluates risk-based publication eligibility.
    """

    def __init__(self, provider: BaseAIProvider):
        self.provider = provider
        self.prompt_version = PROMPT_VERSION

    async def execute_document_analysis(
        self,
        pages: List[Dict[str, Any]],
        document_title: str = "",
        reference_hint: Optional[str] = None,
        force_human_review: bool = False
    ) -> PipelineExecutionResult:
        start_time = time.time()
        
        # Build text input with explicit page markers
        pages_by_number: Dict[int, str] = {}
        formatted_pages_list: List[str] = []

        for p in sorted(pages, key=lambda x: x.get("page_number", 1)):
            p_no = p.get("page_number", 1)
            raw_text = p.get("cleaned_text") or p.get("raw_text", "")
            pages_by_number[p_no] = raw_text
            formatted_pages_list.append(f"--- START PAGE {p_no} ---\n{raw_text}\n--- END PAGE {p_no} ---")

        full_document_context = "\n\n".join(formatted_pages_list)

        user_prompt = USER_ANALYSIS_PROMPT_TEMPLATE.format(
            document_pages_text=full_document_context
        )

        logger.info(f"Running regulatory intelligence pipeline for document with {len(pages)} pages using {self.provider.model_name}")

        # Step 2: Call AI Provider
        llm_response: LLMResponse = await self.provider.generate_structured_json(
            system_prompt=SYSTEM_REGULATORY_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        if not llm_response.success or not llm_response.parsed_json:
            logger.error(f"AI provider pipeline step failed: {llm_response.error}")
            empty_report = ClaimValidationReport(
                total_claims=0,
                verified_claims=0,
                unverified_claims=0,
                citation_coverage_score=0.0,
                is_publication_eligible=False,
                unverified_excerpts=[]
            )
            return PipelineExecutionResult(
                success=False,
                model_name=self.provider.model_name,
                prompt_version=self.prompt_version,
                structured_payload={},
                raw_model_response=llm_response.raw_content,
                token_usage=llm_response.token_usage,
                latency_ms=elapsed_ms,
                validation_report=empty_report,
                publication_status="FAILED",
                error=llm_response.error or "Empty structured output from provider."
            )

        payload = llm_response.parsed_json

        # Step 3: Mandatory Deterministic Citation Verification (Stage 9)
        validation_report: ClaimValidationReport = CitationValidator.validate_analysis_claims(
            analysis_payload=payload,
            pages_by_number=pages_by_number
        )

        # Step 4: Risk-based Publication Eligibility
        # A document requires human review if:
        # - Any unverified claims
        # - Citation coverage < 95%
        # - Contains AMENDS / REPEALS / SUPERSEDES relationships
        # - Explicitly requested via force_human_review
        has_amendment = any(
            rel.get("relationship_type") in ("AMENDS", "REPEALS", "SUPERSEDES")
            for rel in payload.get("relationships", [])
        )

        if force_human_review or not validation_report.is_publication_eligible or has_amendment:
            publication_status = "AWAITING_REVIEW"
        else:
            publication_status = "PUBLISHED_MACHINE_PROCESSED"

        logger.info(
            f"Pipeline completed in {elapsed_ms}ms. "
            f"Claims: {validation_report.verified_claims}/{validation_report.total_claims} verified "
            f"({validation_report.citation_coverage_score * 100:.1f}%). "
            f"Status: {publication_status}"
        )

        return PipelineExecutionResult(
            success=True,
            model_name=self.provider.model_name,
            prompt_version=self.prompt_version,
            structured_payload=payload,
            raw_model_response=llm_response.raw_content,
            token_usage=llm_response.token_usage,
            latency_ms=elapsed_ms,
            validation_report=validation_report,
            publication_status=publication_status,
            error=None
        )
