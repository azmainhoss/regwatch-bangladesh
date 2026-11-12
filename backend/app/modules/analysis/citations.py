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


def safe_int_page(val: Any) -> int:
    """Coerces strings like '1-2', 'Page 1', etc., or unexpected values to a valid integer."""
    if isinstance(val, int):
        return max(1, val)
    if isinstance(val, str):
        m = re.search(r'\d+', val)
        if m:
            try:
                return max(1, int(m.group()))
            except (ValueError, TypeError):
                pass
    return 1


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
        cited_page_number = safe_int_page(cited_page_number)
        if not (quote or "").strip():
            # An empty quote is never grounded (and "" would otherwise "match" every page).
            return cls.validate_quote_against_page("", "", cited_page_number)
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
    def validate_item_quote(
        cls,
        quote: str,
        cited_page_number: int,
        pages_by_number: Dict[int, str],
        fragments: Optional[List[Dict[str, Any]]] = None,
    ) -> CitationValidationResult:
        """Checks one item's quote. A quote copied from sentence IDs may be made of several
        pieces (sentences that are not next to each other); each piece is checked on its own page
        and the weakest result is kept."""
        if not fragments or len(fragments) <= 1:
            single = fragments[0] if fragments else None
            if single:
                return cls.validate_quote_across_document(
                    single.get("text", ""), pages_by_number, single.get("page_number", cited_page_number)
                )
            return cls.validate_quote_across_document(quote, pages_by_number, cited_page_number)

        rank = {
            STATE_VERIFIED_EXACT: 0,
            STATE_VERIFIED_NORMALIZED: 1,
            STATE_CANDIDATE_FUZZY: 2,
            STATE_WRONG_PAGE: 3,
            STATE_UNVERIFIED: 4,
            STATE_SOURCE_MISSING: 5,
        }
        worst: Optional[CitationValidationResult] = None
        for frag in fragments:
            res = cls.validate_quote_across_document(
                frag.get("text", ""), pages_by_number, frag.get("page_number", cited_page_number)
            )
            if worst is None or rank.get(res.status, 9) > rank.get(worst.status, 9):
                worst = res
        return worst.model_copy(update={"quoted_text": quote, "page_number": safe_int_page(cited_page_number)})

    # (payload section, item type label, quote field, identifier)
    _SECTIONS = (
        ("provisions", "PROVISION", "verbatim_text", lambda i: i.get("provision_number")),
        ("obligations", "OBLIGATION", "verbatim_quote", lambda i: i.get("title")),
        ("relationships", "RELATIONSHIP", "supporting_quote",
         lambda i: f"{i.get('relationship_type')} -> {i.get('target_reference_hint')}"),
    )

    @classmethod
    def validate_analysis_claims(
        cls,
        analysis_payload: Dict[str, Any],
        pages_by_number: Dict[int, str]
    ) -> ClaimValidationReport:
        """
        Validates all provisions, obligations, and relationships against stored page texts.
        Enforces strict zero-tolerance publication gates. An item whose quote could not be built
        from its sentence IDs has an empty quote, so it always comes out UNVERIFIED.
        """
        total_claims = 0
        exact_count = 0
        normalized_count = 0
        fuzzy_count = 0
        wrong_page_count = 0
        missing_count = 0
        unverified_count = 0
        unverified_items: List[Dict[str, Any]] = []

        for section, item_type, quote_field, ident in cls._SECTIONS:
            for item in analysis_payload.get(section, []) or []:
                if not isinstance(item, dict):
                    continue
                total_claims += 1
                quote = item.get(quote_field, "") or ""
                p_no = safe_int_page(item.get("page_number", 1))
                item["page_number"] = p_no

                res = cls.validate_item_quote(quote, p_no, pages_by_number, item.get("quote_fragments"))
                item["verification_status"] = res.status
                item["citation_match_score"] = res.match_score
                item["actual_page_found"] = res.actual_page_found

                issues = list(res.issues)
                if item.get("quote_error"):
                    issues.insert(0, item["quote_error"])

                entry = {
                    "item_type": item_type,
                    "identifier": ident(item),
                    "page_number": p_no,
                    "quote": quote,
                    "status": res.status,
                    "issues": issues,
                }
                if res.status == STATE_VERIFIED_EXACT:
                    exact_count += 1
                elif res.status == STATE_VERIFIED_NORMALIZED:
                    normalized_count += 1
                elif res.status == STATE_CANDIDATE_FUZZY:
                    fuzzy_count += 1
                    unverified_items.append(entry)
                elif res.status == STATE_WRONG_PAGE:
                    wrong_page_count += 1
                    entry["actual_page"] = res.actual_page_found
                    unverified_items.append(entry)
                elif res.status == STATE_SOURCE_MISSING:
                    missing_count += 1
                    unverified_count += 1
                    unverified_items.append(entry)
                else:
                    unverified_count += 1
                    unverified_items.append(entry)

        verified_total = exact_count + normalized_count
        coverage = round(verified_total / max(total_claims, 1), 4)

        # STRICT PUBLICATION GATE:
        # Any UNVERIFIED, WRONG_PAGE, CANDIDATE_FUZZY or SOURCE_MISSING item blocks auto-publication,
        # and so does an analysis with no grounded items at all.
        has_blocking_items = len(unverified_items) > 0
        is_eligible = total_claims > 0 and (coverage >= 0.95) and not has_blocking_items

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
