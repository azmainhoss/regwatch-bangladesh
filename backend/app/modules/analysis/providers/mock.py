import json
import re
import time
from typing import Any, Dict, List, Optional

from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage


class MockAIProvider(BaseAIProvider):
    """
    Deterministic mock provider for testing, local offline verification,
    and CI environments without external API keys.
    Extracts authentic quotes directly from the provided prompt text.
    """

    def __init__(self, model_name: str = "mock-regulatory-v1"):
        super().__init__(model_name=model_name)
        self.simulate_failure: bool = False
        self.simulate_invalid_json: bool = False

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0
    ) -> LLMResponse:
        start_time = time.time()

        if self.simulate_failure:
            return LLMResponse(
                raw_content="",
                parsed_json=None,
                token_usage=TokenUsage(),
                model_name=self.model_name,
                latency_ms=10,
                success=False,
                error="Simulated provider failure: API connection refused."
            )

        if self.simulate_invalid_json:
            return LLMResponse(
                raw_content="INVALID JSON {not_json: true,",
                parsed_json=None,
                token_usage=TokenUsage(prompt_tokens=100, completion_tokens=10, total_tokens=110),
                model_name=self.model_name,
                latency_ms=10,
                success=False,
                error="JSONDecodeError: Expecting property name enclosed in double quotes"
            )

        # Check if query is about an unrelated non-banking domain
        unrelated_domains = ["aerospace", "orbital", "satellite", "astronomy", "medical", "surgical", "rocket"]
        if any(w in user_prompt.lower() for w in unrelated_domains):
            return LLMResponse(
                raw_content="I could not verify this from the available regulatory documents.",
                parsed_json={"answer": "I could not verify this from the available regulatory documents."},
                token_usage=TokenUsage(prompt_tokens=50, completion_tokens=15, total_tokens=65),
                model_name=self.model_name,
                latency_ms=5,
                success=True,
                error=None
            )

        # Detect document reference number from user prompt
        ref_match = re.search(r"BRPD Circular No\.\s*(\d+)", user_prompt, re.IGNORECASE)
        ref_no = f"BRPD Circular No. {ref_match.group(1)}" if ref_match else "Regulatory Circular"

        # Check for specific circular context
        is_ifrs9 = "IFRS 9" in user_prompt or "15" in ref_no
        is_ubo = "Beneficial Ownership" in user_prompt or "16" in ref_no

        if is_ifrs9:
            response_dict = {
                "classification": {
                    "document_type": "CIRCULAR",
                    "institution": "Bangladesh Bank",
                    "department": "BRPD",
                    "reference_number": "BRPD Circular No. 15",
                    "publication_date": "2024-11-27",
                    "subject": "Master Policy on Loan Classification and Provisioning Alignment with IFRS 9",
                    "language": "en",
                    "regulatory_topic": "Credit Risk & Prudential Provisioning"
                },
                "executive_summary": {
                    "short_summary": "Bangladesh Bank introduces a master policy aligning loan classification and general provisioning standards with IFRS 9.",
                    "detailed_summary": "The circular establishes a mandatory three-stage credit facility classification framework for all scheduled commercial banks. Stage 1 requires 1.00% general provision, Stage 2 requires 5.00% provision, and Stage 3 requires specific provisioning for non-performing loans.",
                    "background": "Issued under powers conferred by the Bank Company Act, 1991 to strengthen risk management in the banking sector.",
                    "purpose": "Harmonization of credit risk measurement with international accounting standard IFRS 9.",
                    "key_changes": [
                        "Introduction of mandatory 3-stage credit classification framework",
                        "Mandatory general provision of 5.00% on Stage 2 underperforming loans",
                        "Ban on interest reversal into income without prior written approval from Bangladesh Bank"
                    ],
                    "affected_stakeholders": ["Scheduled Commercial Banks", "Borrowers", "Statutory Auditors"],
                    "important_dates": ["2024-12-31: Initial readiness report deadline", "2025-01-01: Effective enforcement date"]
                },
                "provisions": [
                    {
                        "provision_number": "1.",
                        "parent_provision": None,
                        "heading": "Mandatory Staging Framework",
                        "verbatim_text": "All scheduled commercial banks must classify their credit facilities into three distinct stages:",
                        "page_number": 1,
                        "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "Mandates 3-stage loan classification for all scheduled banks."
                    },
                    {
                        "provision_number": "1.1",
                        "parent_provision": "1.",
                        "heading": "Stage 1 Performing",
                        "verbatim_text": "1.1 Stage 1 (Performing): Loans with no significant increase in credit risk. General provision: 1.00%.",
                        "page_number": 1,
                        "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "Stage 1 requires 1% general provision."
                    },
                    {
                        "provision_number": "1.2",
                        "parent_provision": "1.",
                        "heading": "Stage 2 Underperforming",
                        "verbatim_text": "1.2 Stage 2 (Underperforming): Significant increase in credit risk (overdue 30-89 days). Provision: 5.00%.",
                        "page_number": 1,
                        "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "Stage 2 loans overdue 30-89 days require 5% general provision."
                    },
                    {
                        "provision_number": "2.",
                        "parent_provision": None,
                        "heading": "Effective Date & Compliance Timeline",
                        "verbatim_text": "All banks must submit an initial readiness report to BRPD within 31 December 2024.",
                        "page_number": 1,
                        "provision_type": "EFFECTIVE_DATE",
                        "normalized_explanation": "Enforceable from Jan 1, 2025 with readiness report due Dec 31, 2024."
                    },
                    {
                        "provision_number": "3.",
                        "parent_provision": None,
                        "heading": "Penal Sanctions",
                        "verbatim_text": "Failure to comply with these provisions will attract penal actions under Section 109(7) of the Bank Company Act, 1991.",
                        "page_number": 1,
                        "provision_type": "SANCTION",
                        "normalized_explanation": "Penal consequences under Bank Company Act Section 109(7)."
                    }
                ],
                "obligations": [
                    {
                        "title": "Maintain 5.00% General Provision on Stage 2 Loans",
                        "obligation_type": "MANDATORY",
                        "requirement_description": "Scheduled commercial banks must maintain 5.00% general provisioning on credit facilities categorized under Stage 2 (overdue 30-89 days).",
                        "verbatim_quote": "1.2 Stage 2 (Underperforming): Significant increase in credit risk (overdue 30-89 days). Provision: 5.00%.",
                        "page_number": 1,
                        "clause_reference": "1.2",
                        "responsible_entity": "Scheduled Commercial Banks",
                        "applicability_conditions": "All credit facilities with significant increase in credit risk overdue 30 to 89 days",
                        "effective_date": "2025-01-01",
                        "explicit_deadline": None,
                        "reporting_frequency": "QUARTERLY",
                        "required_evidence": "Quarterly CL-1/CL-2 regulatory reporting submission to BRPD and statutory audit confirmation",
                        "consequence": "Penal sanctions under Section 109(7) of Bank Company Act, 1991"
                    },
                    {
                        "title": "Submit Initial IFRS 9 Readiness Report",
                        "obligation_type": "REPORTING",
                        "requirement_description": "Submit comprehensive readiness report outlining IT readiness and model calibration to BRPD.",
                        "verbatim_quote": "All banks must submit an initial readiness report to BRPD within 31 December 2024.",
                        "page_number": 1,
                        "clause_reference": "2.",
                        "responsible_entity": "Scheduled Commercial Banks",
                        "applicability_conditions": "All scheduled commercial banks",
                        "effective_date": "2024-11-27",
                        "explicit_deadline": "2024-12-31",
                        "reporting_frequency": "ONE_TIME",
                        "required_evidence": "Board-approved IFRS 9 transition readiness report",
                        "consequence": "Supervisory warning and inspection scrutiny"
                    }
                ],
                "applicability": {
                    "covered_entities": ["SCHEDULED_COMMERCIAL_BANK"],
                    "is_universal": True,
                    "exemptions": ["Islamic Banks are covered under separate shariah-compliant guidelines"],
                    "conditional_rules": "Applies to all loan portfolios exceeding initial recognition"
                },
                "deadlines": {
                    "publication_date": "2024-11-27",
                    "effective_date": "2025-01-01",
                    "compliance_deadline": "2024-12-31",
                    "reporting_deadline": "2024-12-31",
                    "trigger_event": "Circular publication on Bangladesh Bank website"
                },
                "relationships": [
                    {
                        "relationship_type": "AMENDS",
                        "target_reference_hint": "BRPD Circular No. 14 dated 23 September 2012",
                        "supporting_quote": "Please refer to BRPD Circular No. 14 dated 23 September 2012 and subsequent instructions issued on loan classification and provisioning standards for scheduled commercial banks.",
                        "page_number": 1,
                        "confidence": 0.98,
                        "detection_method": "EXPLICIT_CITATION"
                    }
                ],
                "impact_assessment": {
                    "banking_operations": "Requires core banking system loan staging automation.",
                    "credit": "Increased provisioning buffer required for Stage 2 loans.",
                    "compliance": "Mandatory tracking of 30-day delinquency triggers.",
                    "risk_management": "Model calibration for Significant Increase in Credit Risk (SICR)."
                }
            }
        else:
            # Generic valid fallback for any circular text
            first_line = user_prompt.splitlines()[0] if user_prompt else "Bangladesh Bank Circular"
            quote = user_prompt[:80] if len(user_prompt) >= 80 else user_prompt
            response_dict = {
                "classification": {
                    "document_type": "CIRCULAR",
                    "institution": "Bangladesh Bank",
                    "department": "BRPD",
                    "reference_number": ref_no,
                    "publication_date": "2024-12-01",
                    "subject": "Regulatory Directive",
                    "language": "en",
                    "regulatory_topic": "Banking Regulation"
                },
                "executive_summary": {
                    "short_summary": "Official circular issued by Bangladesh Bank.",
                    "detailed_summary": "Instructs financial institutions on mandatory compliance procedures.",
                    "background": "Legal regulatory directive.",
                    "purpose": "Prudential governance.",
                    "key_changes": ["Mandatory regulatory adherence"],
                    "affected_stakeholders": ["Commercial Banks"],
                    "important_dates": []
                },
                "provisions": [
                    {
                        "provision_number": "1.",
                        "parent_provision": None,
                        "heading": "General Instruction",
                        "verbatim_text": quote,
                        "page_number": 1,
                        "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "General compliance directive."
                    }
                ],
                "obligations": [
                    {
                        "title": "Regulatory Compliance Instruction",
                        "obligation_type": "MANDATORY",
                        "requirement_description": "Banks must comply with regulatory requirements set forth by Bangladesh Bank.",
                        "verbatim_quote": quote,
                        "page_number": 1,
                        "clause_reference": "1.",
                        "responsible_entity": "Scheduled Commercial Banks",
                        "applicability_conditions": "All operating institutions",
                        "effective_date": "2024-12-01",
                        "explicit_deadline": None,
                        "reporting_frequency": "ONE_TIME",
                        "required_evidence": "Compliance confirmation letter",
                        "consequence": None
                    }
                ],
                "applicability": {
                    "covered_entities": ["SCHEDULED_COMMERCIAL_BANK"],
                    "is_universal": True,
                    "exemptions": [],
                    "conditional_rules": None
                },
                "deadlines": {
                    "publication_date": "2024-12-01",
                    "effective_date": "2024-12-01",
                    "compliance_deadline": None,
                    "reporting_deadline": None,
                    "trigger_event": None
                },
                "relationships": [],
                "impact_assessment": {
                    "compliance": "Requires policy review and operational adherence."
                }
            }

        elapsed_ms = int((time.time() - start_time) * 1000)
        json_str = json.dumps(response_dict)

        return LLMResponse(
            raw_content=json_str,
            parsed_json=response_dict,
            token_usage=TokenUsage(
                prompt_tokens=450,
                completion_tokens=320,
                total_tokens=770,
                estimated_cost_usd=0.00015
            ),
            model_name=self.model_name,
            latency_ms=elapsed_ms,
            success=True,
            error=None
        )
