import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.core.logging import logger
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage
from backend.app.modules.analysis.prompts import (
    ANALYSIS_RESPONSE_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_REGULATORY_PROMPT,
    USER_ANALYSIS_PROMPT_TEMPLATE,
)
from backend.app.modules.analysis.citations import CitationValidator, ClaimValidationReport
from backend.app.modules.analysis.sentences import SentenceIndex, apply_quote_ids


class PipelineExecutionResult(BaseModel):
    success: bool
    model_name: str
    prompt_version: str
    structured_payload: Dict[str, Any]
    raw_model_response: str
    token_usage: TokenUsage
    latency_ms: int
    validation_report: ClaimValidationReport
    publication_status: str  # PUBLISHED_MACHINE_VERIFIED, or FAILED (the real status is derived from the claims)
    error: Optional[str] = None


class RegulatoryIntelligencePipeline:
    """
    Multi-stage end-to-end regulatory document analysis pipeline:
    1. Formats page text with page-level boundaries.
    2. Runs Analysis provider inference for structured intelligence.
    3. Runs mandatory deterministic citation verification.
    4. Reports the quote coverage figure. Publication is decided per point, later (claims/).
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
        # `force_human_review` is applied to the claims by the analysis service, not here.
        start_time = time.time()

        # Step 1: split every page into sentences with stable IDs (p3.s12) and show the model
        # the text with those IDs. The model answers with IDs; code copies the exact text.
        sentence_index = SentenceIndex.build(pages)
        pages_by_number: Dict[int, str] = dict(sentence_index.pages)

        user_prompt = USER_ANALYSIS_PROMPT_TEMPLATE.format(
            document_pages_text=sentence_index.render_for_prompt()
        )

        logger.info(f"Running regulatory intelligence pipeline for document with {len(pages)} pages using {self.provider.model_name}")

        # Step 2: Call AI Provider. Any failure here ends the run as FAILED, never as grounded.
        try:
            llm_response: LLMResponse = await self.provider.generate_structured_json(
                system_prompt=SYSTEM_REGULATORY_PROMPT,
                user_prompt=user_prompt,
                json_schema=ANALYSIS_RESPONSE_SCHEMA,
                temperature=0.0
            )
        except Exception as e:
            logger.error(f"Analysis provider raised during analysis: {e}")
            llm_response = LLMResponse(
                raw_content="",
                parsed_json=None,
                model_name=self.provider.model_name,
                success=False,
                error=f"Analysis provider error: {e}",
            )

        elapsed_ms = int((time.time() - start_time) * 1000)

        usable = llm_response.success and isinstance(llm_response.parsed_json, dict) and bool(llm_response.parsed_json)
        if not usable:
            error = llm_response.error
            if llm_response.success and not error:
                error = "Analysis provider returned an answer that is not a JSON object."
            logger.error(f"Analysis provider pipeline step failed: {error}")
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
                error=error or "Empty structured output from provider."
            )

        payload = llm_response.parsed_json

        # Step 2b: turn quote_span_ids into exact quotes. Unknown IDs drop the quote and
        # flag the item for a person; no text is ever made up.
        quote_problems = apply_quote_ids(payload, sentence_index)

        # Step 3: Mandatory Deterministic Citation Verification (Stage 9)
        validation_report: ClaimValidationReport = CitationValidator.validate_analysis_claims(
            analysis_payload=payload,
            pages_by_number=pages_by_number
        )

        # Step 4: nothing is held back here any more. Each point is checked and shown or hidden
        # on its own after the analysis is saved (claims/checks.py and claims/status.py). The
        # coverage number above is only kept as a summary figure.
        publication_status = "PUBLISHED_MACHINE_VERIFIED"

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
