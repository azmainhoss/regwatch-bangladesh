"""
Ground Truth Annotations for Bangladesh Bank BRPD Circular No. 15 (2024).
Official Title: Master Policy on Loan Classification and Provisioning Alignment with IFRS 9
Total Pages: 2 (Page 1: Policy Directive; Page 2: Annexure A Required Provisioning Schedule Table).
Certified Human Verification: Gold Human Ground Truth.
"""

from typing import List
from pydantic import BaseModel, Field


class BRPDAnnotation(BaseModel):
    clause_number: str
    page_number: int
    heading_en: str
    category: str
    modality: str
    responsible_entity: str
    verbatim_text: str
    normalized_interpretation: str
    financial_thresholds: List[str] = Field(default_factory=list)
    deadlines: List[str] = Field(default_factory=list)
    statutory_references: List[str] = Field(default_factory=list)


BRPD15_GROUND_TRUTH: List[BRPDAnnotation] = [
    BRPDAnnotation(
        clause_number="REF-PREAMBLE",
        page_number=1,
        heading_en="Preamble and Reference to Prior Circular",
        category="RELATIONSHIP_REFERENCE",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="Please refer to BRPD Circular No. 14 dated 23 September 2012 and subsequent instructions issued on loan classification and provisioning standards for scheduled commercial banks.",
        normalized_interpretation="Amends and updates regulatory framework originally established by BRPD Circular No. 14 of 2012.",
        statutory_references=["BRPD Circular No. 14 dated 23 September 2012"]
    ),
    BRPDAnnotation(
        clause_number="1.1",
        page_number=1,
        heading_en="Stage 1 Performing Loans",
        category="MANDATORY_OBLIGATION",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="Stage 1 (Performing): Loans with no significant increase in credit risk. General provision: 1.00%.",
        normalized_interpretation="Mandates 1.00% general provisioning rate for credit facilities demonstrating no significant increase in credit risk.",
        financial_thresholds=["1.00% general provision"]
    ),
    BRPDAnnotation(
        clause_number="1.2",
        page_number=1,
        heading_en="Stage 2 Underperforming Loans",
        category="MANDATORY_OBLIGATION",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="Stage 2 (Underperforming): Significant increase in credit risk (overdue 30-89 days). Provision: 5.00%.",
        normalized_interpretation="Mandates 5.00% provision for credit facilities overdue between 30 and 89 days.",
        financial_thresholds=["5.00% provision", "30-89 days overdue threshold"]
    ),
    BRPDAnnotation(
        clause_number="1.3",
        page_number=1,
        heading_en="Stage 3 Non-Performing Loans",
        category="MANDATORY_OBLIGATION",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="Stage 3 (Non-Performing): Overdue for 90 days or more. Must maintain specific provision.",
        normalized_interpretation="Classifies loans overdue for 90 days or more as Stage 3 / Non-Performing, requiring specific provisioning per schedule.",
        financial_thresholds=["90 days overdue threshold"]
    ),
    BRPDAnnotation(
        clause_number="2.1",
        page_number=1,
        heading_en="Enforceability & Effective Date",
        category="DEADLINE",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="The amended provisions shall come into force with effect from 01 January 2025.",
        normalized_interpretation="Sets effective enforcement date to January 1, 2025.",
        deadlines=["01 January 2025"]
    ),
    BRPDAnnotation(
        clause_number="2.2",
        page_number=1,
        heading_en="Readiness Report Submission Deadline",
        category="REPORTING_REQUIREMENT",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="All banks must submit an initial readiness report to BRPD within 31 December 2024.",
        normalized_interpretation="Requires banks to submit an initial compliance readiness report to BRPD by December 31, 2024.",
        deadlines=["31 December 2024"]
    ),
    BRPDAnnotation(
        clause_number="3.",
        page_number=1,
        heading_en="Penal Sanctions",
        category="STATUTORY_AUTHORITY",
        modality="PROHIBITIVE",
        responsible_entity="Bangladesh Bank",
        verbatim_text="Failure to comply with these provisions will attract penal actions under Section 109(7) of the Bank Company Act, 1991.",
        normalized_interpretation="Enforces sanctions and penalties under Section 109(7) of Bank Company Act, 1991 for non-compliance.",
        statutory_references=["Section 109(7), Bank Company Act, 1991"]
    ),
    BRPDAnnotation(
        clause_number="TABLE-1",
        page_number=2,
        heading_en="Annexure A: Minimum Regulatory Provisioning Schedule",
        category="FINANCIAL_THRESHOLD",
        modality="MANDATORY",
        responsible_entity="Scheduled Commercial Banks",
        verbatim_text="Standard (Continuous): 1.00% | Special Mention Account (30-89 days): 5.00% | Sub-Standard (90-179 days): 20.00% | Doubtful (180-269 days): 50.00% | Bad or Loss (270 days or more): 100.00%",
        normalized_interpretation="Mandatory tiered provisioning schedule ranging from 1.0% to 100.0% depending on overdue duration.",
        financial_thresholds=["1.00%", "5.00%", "20.00%", "50.00%", "100.00%"]
    ),
]

