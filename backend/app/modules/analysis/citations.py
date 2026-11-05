import difflib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CitationValidationResult(BaseModel):
    is_verified: bool
    match_score: float
    match_method: str  # EXACT_SUBSTRING, WHITESPACE_NORMALIZED, HIGH_CONFIDENCE_FUZZY, NOT_FOUND
    page_number: int
    quoted_text: str
    issues: List[str] = Field(default_factory=list)


class ClaimValidationReport(BaseModel):
    total_claims: int
    verified_claims: int
    unverified_claims: int
    citation_coverage_score: float  # verified / total
    is_publication_eligible: bool
    unverified_excerpts: List[Dict[str, Any]] = Field(default_factory=list)


class CitationValidator:
    """
    Mandatory deterministic validation stage ensuring every AI statement,
    obligation, and provision is genuinely grounded in the official page text.
    Strictly forbids hallucinated or fabricated citations.
    """

    @classmethod
    def normalize_whitespace(cls, text: str) -> str:
        """Collapses all whitespace and removes trailing punctuation for clean comparison."""
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def validate_quote_against_page(
        cls,
        quote: str,
        page_text: str,
        page_number: int,
        fuzzy_threshold: float = 0.92
    ) -> CitationValidationResult:
        """
        Deterministically verifies if a cited quote is present in the specified page text.
        """
        clean_quote = quote.strip()
        if not clean_quote:
            return CitationValidationResult(
                is_verified=False,
                match_score=0.0,
                match_method="NOT_FOUND",
                page_number=page_number,
                quoted_text=quote,
                issues=["Cited quotation is empty"]
            )

        # 1. Exact Substring Match
        if clean_quote in page_text:
            return CitationValidationResult(
                is_verified=True,
                match_score=1.0,
                match_method="EXACT_SUBSTRING",
                page_number=page_number,
                quoted_text=clean_quote,
                issues=[]
            )

        # 2. Case-Insensitive Whitespace-Normalized Match
        norm_quote = cls.normalize_whitespace(clean_quote)
        norm_page = cls.normalize_whitespace(page_text)

        if norm_quote in norm_page:
            return CitationValidationResult(
                is_verified=True,
                match_score=0.98,
                match_method="WHITESPACE_NORMALIZED",
                page_number=page_number,
                quoted_text=clean_quote,
                issues=[]
            )

        # 3. Sliding Window Fuzzy Match
        # If quote is long, check if there is an excerpt on the page with >= fuzzy_threshold similarity
        quote_len = len(norm_quote)
        best_ratio = 0.0

        if quote_len >= 15 and len(norm_page) >= quote_len:
            # Check windows roughly the length of the quote
            step = max(5, quote_len // 4)
            for i in range(0, len(norm_page) - quote_len + 1, step):
                window = norm_page[i : i + quote_len]
                ratio = difflib.SequenceMatcher(None, norm_quote, window).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                if best_ratio >= fuzzy_threshold:
                    break

        if best_ratio >= fuzzy_threshold:
            return CitationValidationResult(
                is_verified=True,
                match_score=round(best_ratio, 4),
                match_method="HIGH_CONFIDENCE_FUZZY",
                page_number=page_number,
                quoted_text=clean_quote,
                issues=[f"Minor typographic or OCR character variance (match: {best_ratio:.2f})"]
            )

        # 4. Failed: Not Found
        return CitationValidationResult(
            is_verified=False,
            match_score=round(best_ratio, 4),
            match_method="NOT_FOUND",
            page_number=page_number,
            quoted_text=clean_quote,
            issues=[f"Quotation could not be located on page {page_number}. Best match was only {best_ratio:.2f}."]
        )

    @classmethod
    def validate_analysis_claims(
        cls,
        analysis_payload: Dict[str, Any],
        pages_by_number: Dict[int, str]
    ) -> ClaimValidationReport:
        """
        Validates all claims, provisions, obligations, and relationship quotes
        in an analysis payload against stored page texts.
        """
        total_claims = 0
        verified_claims = 0
        unverified_items: List[Dict[str, Any]] = []

        # Validate Provisions
        for prov in analysis_payload.get("provisions", []):
            total_claims += 1
            quote = prov.get("verbatim_text", "")
            p_no = prov.get("page_number", 1)
            page_text = pages_by_number.get(p_no, "")

            res = cls.validate_quote_against_page(quote, page_text, p_no)
            prov["verification_status"] = "VERIFIED" if res.is_verified else "UNVERIFIED"
            prov["citation_match_score"] = res.match_score
            if res.is_verified:
                verified_claims += 1
            else:
                unverified_items.append({
                    "item_type": "PROVISION",
                    "identifier": prov.get("provision_number"),
                    "page_number": p_no,
                    "quote": quote,
                    "issues": res.issues
                })

        # Validate Obligations
        for obl in analysis_payload.get("obligations", []):
            total_claims += 1
            quote = obl.get("verbatim_quote", "")
            p_no = obl.get("page_number", 1)
            page_text = pages_by_number.get(p_no, "")

            res = cls.validate_quote_against_page(quote, page_text, p_no)
            obl["verification_status"] = "VERIFIED" if res.is_verified else "UNVERIFIED"
            obl["citation_match_score"] = res.match_score
            if res.is_verified:
                verified_claims += 1
            else:
                unverified_items.append({
                    "item_type": "OBLIGATION",
                    "identifier": obl.get("title"),
                    "page_number": p_no,
                    "quote": quote,
                    "issues": res.issues
                })

        # Validate Relationships
        for rel in analysis_payload.get("relationships", []):
            total_claims += 1
            quote = rel.get("supporting_quote", "")
            p_no = rel.get("page_number", 1)
            page_text = pages_by_number.get(p_no, "")

            res = cls.validate_quote_against_page(quote, page_text, p_no)
            rel["verification_status"] = "VERIFIED" if res.is_verified else "UNVERIFIED"
            rel["citation_match_score"] = res.match_score
            if res.is_verified:
                verified_claims += 1
            else:
                unverified_items.append({
                    "item_type": "RELATIONSHIP",
                    "identifier": f"{rel.get('relationship_type')} -> {rel.get('target_reference_hint')}",
                    "page_number": p_no,
                    "quote": quote,
                    "issues": res.issues
                })

        coverage = round(verified_claims / max(total_claims, 1), 4)
        is_eligible = (coverage >= 0.95) and (len(unverified_items) == 0)

        return ClaimValidationReport(
            total_claims=total_claims,
            verified_claims=verified_claims,
            unverified_claims=total_claims - verified_claims,
            citation_coverage_score=coverage,
            is_publication_eligible=is_eligible,
            unverified_excerpts=unverified_items
        )
