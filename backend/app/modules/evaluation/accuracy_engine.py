"""
Accuracy & Quality Engine for RegWatch Bangladesh.
Implements the 3 independent quality dimensions defined in Phase 3.9:
  Dimension A: Citation Coverage
  Dimension B: Extraction Completeness (Precision, Recall, F1)
  Dimension C: Interpretation Accuracy
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CitationCoverageMetrics(BaseModel):
    total_claims: int
    verified_claims: int
    exact_match_claims: int
    normalized_match_claims: int
    fuzzy_candidate_claims: int
    wrong_page_claims: int
    unverified_claims: int
    coverage_score: float  # (exact + normalized) / total_claims
    is_eligible_for_publication: bool


class ExtractionCompletenessMetrics(BaseModel):
    ground_truth_total: int
    extracted_total: int
    matched_count: int
    unmatched_ground_truth: int
    extra_extracted_count: int
    precision: float
    recall: float
    f1_score: float


class InterpretationAccuracyMetrics(BaseModel):
    evaluated_provisions_count: int
    modality_correct: int
    modality_accuracy: float
    responsible_entity_correct: int
    responsible_entity_accuracy: float
    financial_thresholds_correct: int
    financial_thresholds_accuracy: float
    deadlines_correct: int
    deadlines_accuracy: float
    overall_interpretation_accuracy: float


class MultiDimensionalQualityReport(BaseModel):
    document_title: str
    reference_number: str
    page_count: int
    evaluator_mode: str  # MOCK_HEURISTIC, LIVE_GEMINI_EVALUATION
    dimension_a_citation_coverage: CitationCoverageMetrics
    dimension_b_extraction_completeness: ExtractionCompletenessMetrics
    dimension_c_interpretation_accuracy: InterpretationAccuracyMetrics
    operational_reliance_grade: str  # RELIABLE, CONDITIONAL_REVIEW, NOT_RELIABLE
    known_limitations: List[str]


def compute_citation_coverage(claims: List[Dict[str, Any]]) -> CitationCoverageMetrics:
    """Calculates Dimension A: Citation Coverage."""
    total = len(claims)
    if total == 0:
        return CitationCoverageMetrics(
            total_claims=0,
            verified_claims=0,
            exact_match_claims=0,
            normalized_match_claims=0,
            fuzzy_candidate_claims=0,
            wrong_page_claims=0,
            unverified_claims=0,
            coverage_score=0.0,
            is_eligible_for_publication=False
        )

    exact = 0
    normalized = 0
    fuzzy = 0
    wrong_page = 0
    unverified = 0

    for c in claims:
        status = c.get("verification_status", "UNVERIFIED")
        if status in ("VERIFIED_EXACT", "VERIFIED"):
            exact += 1
        elif status == "VERIFIED_NORMALIZED":
            normalized += 1
        elif status == "CANDIDATE_FUZZY":
            fuzzy += 1
        elif status == "WRONG_PAGE":
            wrong_page += 1
        else:
            unverified += 1

    verified_total = exact + normalized
    coverage = round(verified_total / max(total, 1), 4)
    # Publication eligibility requires 100% verified exact/normalized and 0 blocking issues
    is_eligible = (coverage >= 1.0) and (fuzzy == 0) and (wrong_page == 0) and (unverified == 0)

    return CitationCoverageMetrics(
        total_claims=total,
        verified_claims=verified_total,
        exact_match_claims=exact,
        normalized_match_claims=normalized,
        fuzzy_candidate_claims=fuzzy,
        wrong_page_claims=wrong_page,
        unverified_claims=unverified,
        coverage_score=coverage,
        is_eligible_for_publication=is_eligible
    )


def compute_extraction_completeness(
    ground_truth_clauses: List[str],
    extracted_clauses: List[str]
) -> ExtractionCompletenessMetrics:
    """Calculates Dimension B: Extraction Completeness (Precision, Recall, F1)."""
    gt_set = set(c.strip().lower() for c in ground_truth_clauses if c)
    ext_set = set(c.strip().lower() for c in extracted_clauses if c)

    matched = gt_set.intersection(ext_set)
    matched_count = len(matched)
    gt_total = len(gt_set)
    ext_total = len(ext_set)

    precision = round(matched_count / max(ext_total, 1), 4) if ext_total > 0 else 0.0
    recall = round(matched_count / max(gt_total, 1), 4) if gt_total > 0 else 0.0

    if precision + recall > 0:
        f1 = round(2 * (precision * recall) / (precision + recall), 4)
    else:
        f1 = 0.0

    return ExtractionCompletenessMetrics(
        ground_truth_total=gt_total,
        extracted_total=ext_total,
        matched_count=matched_count,
        unmatched_ground_truth=gt_total - matched_count,
        extra_extracted_count=ext_total - matched_count,
        precision=precision,
        recall=recall,
        f1_score=f1
    )


def compute_interpretation_accuracy(
    evaluations: List[Dict[str, bool]]
) -> InterpretationAccuracyMetrics:
    """Calculates Dimension C: Interpretation Accuracy."""
    total = len(evaluations)
    if total == 0:
        return InterpretationAccuracyMetrics(
            evaluated_provisions_count=0,
            modality_correct=0,
            modality_accuracy=0.0,
            responsible_entity_correct=0,
            responsible_entity_accuracy=0.0,
            financial_thresholds_correct=0,
            financial_thresholds_accuracy=0.0,
            deadlines_correct=0,
            deadlines_accuracy=0.0,
            overall_interpretation_accuracy=0.0
        )

    mod_correct = sum(1 for e in evaluations if e.get("modality_correct", False))
    entity_correct = sum(1 for e in evaluations if e.get("responsible_entity_correct", False))
    fin_correct = sum(1 for e in evaluations if e.get("financial_thresholds_correct", False))
    dl_correct = sum(1 for e in evaluations if e.get("deadlines_correct", False))

    mod_acc = round(mod_correct / total, 4)
    ent_acc = round(entity_correct / total, 4)
    fin_acc = round(fin_correct / total, 4)
    dl_acc = round(dl_correct / total, 4)

    overall = round((mod_acc + ent_acc + fin_acc + dl_acc) / 4.0, 4)

    return InterpretationAccuracyMetrics(
        evaluated_provisions_count=total,
        modality_correct=mod_correct,
        modality_accuracy=mod_acc,
        responsible_entity_correct=entity_correct,
        responsible_entity_accuracy=ent_acc,
        financial_thresholds_correct=fin_correct,
        financial_thresholds_accuracy=fin_acc,
        deadlines_correct=dl_correct,
        deadlines_accuracy=dl_acc,
        overall_interpretation_accuracy=overall
    )

