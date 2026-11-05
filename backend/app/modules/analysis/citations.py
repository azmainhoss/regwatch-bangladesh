import difflib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Canonical Citation Verification States
STATE_VERIFIED_EXACT = "VERIFIED_EXACT"
STATE_VERIFIED_NORMALIZED = "VERIFIED_NORMALIZED"
STATE_CANDIDATE_FUZZY = "CANDIDATE_FUZZY"
STATE_UNVERIFIED = "UNVERIFIED"
STATE_WRONG_PAGE = "WRONG_PAGE"
STATE_SOURCE_MISSING = "SOURCE_MISSING"
STATE_HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class CitationValidationResult(BaseModel):
    status: str  # One of the canonical states above
    is_verified: bool  # True ONLY for EXACT, NORMALIZED, or HUMAN_CONFIRMED
    match_score: float
    match_method: str  # EXACT_SUBSTRING, WHITESPACE_NORMALIZED, SLIDING_WINDOW_FUZZY, CROSS_PAGE_MATCH, NOT_FOUND
    page_number: int
    actual_page_found: Optional[int] = None
    quoted_text: str
    normalization_ops: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class ClaimValidationReport(BaseModel):
    total_claims: int
    verified_claims: int
    verified_exact_count: int = 0
    verified_normalized_count: int = 0
    candidate_fuzzy_count: int = 0
    wrong_page_count: int = 0
    source_missing_count: int = 0
    unverified_claims: int = 0
    citation_coverage_score: float  # (exact + normalized) / total
    is_publication_eligible: bool
    unverified_excerpts: List[Dict[str, Any]] = Field(default_factory=list)


class CitationValidator:
    """
    Mandatory deterministic validation stage ensuring every AI statement,
    obligation, and provision is genuinely grounded in the official page text.
    Fuzzy matches are treated strictly as CANDIDATE_FUZZY and do NOT independently
    establish verified legal citations.
    """

    @classmethod
    def normalize_whitespace_and_case(cls, text: str) -> str:
        """Collapses all whitespace and converts to lower case."""
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def validate_quote_against_page(
        cls,
        quote: str,
        page_text: str,
        page_number: int,
        fuzzy_threshold: float = 0.85
    ) -> CitationValidationResult:
        """
        Validates whether a quote is present on the specified single page.
        """
        clean_quote = quote.strip()
        if not clean_quote:
            return CitationValidationResult(
                status=STATE_UNVERIFIED,
                is_verified=False,
                match_score=0.0,
                match_method="NOT_FOUND",
                page_number=page_number,
                quoted_text=quote,
                normalization_ops=[],
                issues=["Cited quotation is empty"]
            )

        # 1. Exact Substring Match
        if clean_quote in page_text:
            return CitationValidationResult(
                status=STATE_VERIFIED_EXACT,
                is_verified=True,
                match_score=1.0,
                match_method="EXACT_SUBSTRING",
                page_number=page_number,
                actual_page_found=page_number,
                quoted_text=clean_quote,
                normalization_ops=[],
                issues=[]
            )

        # 2. Case-Insensitive Whitespace-Normalized Match
        norm_quote = cls.normalize_whitespace_and_case(clean_quote)
        norm_page = cls.normalize_whitespace_and_case(page_text)

        if norm_quote in norm_page:
            return CitationValidationResult(
                status=STATE_VERIFIED_NORMALIZED,
                is_verified=True,
                match_score=0.98,
                match_method="WHITESPACE_NORMALIZED",
                page_number=page_number,
                actual_page_found=page_number,
                quoted_text=clean_quote,
                normalization_ops=["whitespace_collapsed", "case_folded"],
                issues=[]
            )

        # 3. Sliding Window Fuzzy Match
        # Fuzzy matching establishes CANDIDATE_FUZZY for human review, NOT independent verification
        quote_len = len(norm_quote)
        best_ratio = 0.0

        if quote_len >= 15 and len(norm_page) >= quote_len:
            step = max(5, quote_len // 4)
            for i in range(0, len(norm_page) - quote_len + 1, step):
                window = norm_page[i : i + quote_len]
                ratio = difflib.SequenceMatcher(None, norm_quote, window).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                if best_ratio >= 0.95:
                    break

        if best_ratio >= fuzzy_threshold:
            return CitationValidationResult(
                status=STATE_CANDIDATE_FUZZY,
                is_verified=False,  # MUST NOT count as verified without human review
                match_score=round(best_ratio, 4),
                match_method="SLIDING_WINDOW_FUZZY",
                page_number=page_number,
                actual_page_found=page_number,
                quoted_text=clean_quote,
                normalization_ops=["fuzzy_similarity_scan"],
                issues=[f"Fuzzy candidate on page {page_number} (similarity: {best_ratio:.2f}); requires human confirmation."]
            )

        # 4. Not Found on specified page
        return CitationValidationResult(
            status=STATE_UNVERIFIED,
            is_verified=False,
            match_score=round(best_ratio, 4),
            match_method="NOT_FOUND",
            page_number=page_number,
            quoted_text=clean_quote,
            normalization_ops=[],
            issues=[f"Quotation could not be located on page {page_number}. Best match: {best_ratio:.2f}."]
        )

    @classmethod
    def validate_quote_across_document(
        cls,
        quote: str,
        pages_by_number: Dict[int, str],
        cited_page_number: int,
        fuzzy_threshold: float = 0.85
    ) -> CitationValidationResult:
        """
        Validates quote against the cited page first; if missing, scans other document pages
        to detect WRONG_PAGE citations or SOURCE_MISSING states.
        """
        if cited_page_number not in pages_by_number:
            # Check if quote exists elsewhere in the document
            clean_quote = quote.strip()
            norm_quote = cls.normalize_whitespace_and_case(clean_quote)
            for p_num, p_text in pages_by_number.items():
                if clean_quote in p_text or norm_quote in cls.normalize_whitespace_and_case(p_text):
                    return CitationValidationResult(
                        status=STATE_WRONG_PAGE,
                        is_verified=False,
                        match_score=0.90,
                        match_method="CROSS_PAGE_MATCH",
                        page_number=cited_page_number,
                        actual_page_found=p_num,
                        quoted_text=clean_quote,
                        normalization_ops=[],
                        issues=[f"Quotation cited on non-existent page {cited_page_number}, but found on page {p_num}."]
                    )
            return CitationValidationResult(
                status=STATE_SOURCE_MISSING,
                is_verified=False,
                match_score=0.0,
                match_method="NOT_FOUND",
                page_number=cited_page_number,
                quoted_text=quote,
                normalization_ops=[],
                issues=[f"Page {cited_page_number} does not exist in the document."]
            )

        target_page_text = pages_by_number[cited_page_number]
        page_res = cls.validate_quote_against_page(
            quote=quote,
            page_text=target_page_text,
            page_number=cited_page_number,
            fuzzy_threshold=fuzzy_threshold
        )

        if page_res.is_verified:
            return page_res

        # If not verified on cited page, check if it actually exists on another page
        clean_quote = quote.strip()
        norm_quote = cls.normalize_whitespace_and_case(clean_quote)
        for other_p_num, other_p_text in pages_by_number.items():
            if other_p_num == cited_page_number:
                continue
            if clean_quote in other_p_text or norm_quote in cls.normalize_whitespace_and_case(other_p_text):
                return CitationValidationResult(
                    status=STATE_WRONG_PAGE,
                    is_verified=False,
                    match_score=0.90,
                    match_method="CROSS_PAGE_MATCH",
                    page_number=cited_page_number,
                    actual_page_found=other_p_num,
                    quoted_text=clean_quote,
                    normalization_ops=[],
                    issues=[f"Quotation cited on page {cited_page_number} actually exists on page {other_p_num}."]
                )

        return page_res

    @classmethod
    def validate_analysis_claims(
        cls,
        analysis_payload: Dict[str, Any],
        pages_by_number: Dict[int, str]
    ) -> ClaimValidationReport:
        """
        Validates all provisions, obligations, and relationships against stored page texts.
        Enforces strict zero-tolerance publication gates.
        """
        total_claims = 0
        exact_count = 0
        normalized_count = 0
        fuzzy_count = 0
        wrong_page_count = 0
        missing_count = 0
        unverified_count = 0
        unverified_items: List[Dict[str, Any]] = []

        # 1. Validate Provisions
        for prov in analysis_payload.get("provisions", []):
            total_claims += 1
            quote = prov.get("verbatim_text", "")
            p_no = prov.get("page_number", 1)

            res = cls.validate_quote_across_document(quote, pages_by_number, p_no)
            prov["verification_status"] = res.status
            prov["citation_match_score"] = res.match_score
            prov["actual_page_found"] = res.actual_page_found

            if res.status == STATE_VERIFIED_EXACT:
                exact_count += 1
            elif res.status == STATE_VERIFIED_NORMALIZED:
                normalized_count += 1
            elif res.status == STATE_CANDIDATE_FUZZY:
                fuzzy_count += 1
                unverified_items.append({
                    "item_type": "PROVISION",
                    "identifier": prov.get("provision_number"),
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            elif res.status == STATE_WRONG_PAGE:
                wrong_page_count += 1
                unverified_items.append({
                    "item_type": "PROVISION",
                    "identifier": prov.get("provision_number"),
                    "page_number": p_no,
                    "actual_page": res.actual_page_found,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            else:
                unverified_count += 1
                unverified_items.append({
                    "item_type": "PROVISION",
                    "identifier": prov.get("provision_number"),
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })

        # 2. Validate Obligations
        for obl in analysis_payload.get("obligations", []):
            total_claims += 1
            quote = obl.get("verbatim_quote", "")
            p_no = obl.get("page_number", 1)

            res = cls.validate_quote_across_document(quote, pages_by_number, p_no)
            obl["verification_status"] = res.status
            obl["citation_match_score"] = res.match_score
            obl["actual_page_found"] = res.actual_page_found

            if res.status == STATE_VERIFIED_EXACT:
                exact_count += 1
            elif res.status == STATE_VERIFIED_NORMALIZED:
                normalized_count += 1
            elif res.status == STATE_CANDIDATE_FUZZY:
                fuzzy_count += 1
                unverified_items.append({
                    "item_type": "OBLIGATION",
                    "identifier": obl.get("title"),
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            elif res.status == STATE_WRONG_PAGE:
                wrong_page_count += 1
                unverified_items.append({
                    "item_type": "OBLIGATION",
                    "identifier": obl.get("title"),
                    "page_number": p_no,
                    "actual_page": res.actual_page_found,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            else:
                unverified_count += 1
                unverified_items.append({
                    "item_type": "OBLIGATION",
                    "identifier": obl.get("title"),
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })

        # 3. Validate Relationships
        for rel in analysis_payload.get("relationships", []):
            total_claims += 1
            quote = rel.get("supporting_quote", "")
            p_no = rel.get("page_number", 1)

            res = cls.validate_quote_across_document(quote, pages_by_number, p_no)
            rel["verification_status"] = res.status
            rel["citation_match_score"] = res.match_score
            rel["actual_page_found"] = res.actual_page_found

            if res.status == STATE_VERIFIED_EXACT:
                exact_count += 1
            elif res.status == STATE_VERIFIED_NORMALIZED:
                normalized_count += 1
            elif res.status == STATE_CANDIDATE_FUZZY:
                fuzzy_count += 1
                unverified_items.append({
                    "item_type": "RELATIONSHIP",
                    "identifier": f"{rel.get('relationship_type')} -> {rel.get('target_reference_hint')}",
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            elif res.status == STATE_WRONG_PAGE:
                wrong_page_count += 1
                unverified_items.append({
                    "item_type": "RELATIONSHIP",
                    "identifier": f"{rel.get('relationship_type')} -> {rel.get('target_reference_hint')}",
                    "page_number": p_no,
                    "actual_page": res.actual_page_found,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })
            else:
                unverified_count += 1
                unverified_items.append({
                    "item_type": "RELATIONSHIP",
                    "identifier": f"{rel.get('relationship_type')} -> {rel.get('target_reference_hint')}",
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": res.issues
                })

        verified_total = exact_count + normalized_count
        coverage = round(verified_total / max(total_claims, 1), 4)

        # STRICT PUBLICATION GATE:
        # Any UNVERIFIED, WRONG_PAGE, or CANDIDATE_FUZZY on an obligation immediately blocks auto-publication
        has_blocking_items = len(unverified_items) > 0
        is_eligible = (coverage >= 0.95) and not has_blocking_items

        return ClaimValidationReport(
            total_claims=total_claims,
            verified_claims=verified_total,
            verified_exact_count=exact_count,
            verified_normalized_count=normalized_count,
            candidate_fuzzy_count=fuzzy_count,
            wrong_page_count=wrong_page_count,
            source_missing_count=missing_count,
            unverified_claims=unverified_count,
            citation_coverage_score=coverage,
            is_publication_eligible=is_eligible,
            unverified_excerpts=unverified_items
        )
