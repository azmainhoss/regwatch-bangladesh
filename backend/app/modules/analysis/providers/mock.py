import json
import re
import time
from typing import Any, Dict, List, Optional

from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse, TokenUsage


_SENTENCE_LINE = re.compile(r"^\[(p\d+\.s\d+)\] (.*)$", re.MULTILINE)
_SENTENCE_TAG = re.compile(r"^\[p\d+\.s\d+\] ", re.MULTILINE)
_QUOTE_FIELDS = (("provisions", "verbatim_text"), ("obligations", "verbatim_quote"), ("relationships", "supporting_quote"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _ids_for_quote(quote: str, sentences: List[tuple]) -> List[str]:
    """Finds the sentence IDs that make up a canned quote, the way a model would pick them."""
    nq = _norm(quote)
    if not nq:
        return []
    inside = [i for i, (_sid, text) in enumerate(sentences) if len(_norm(text)) >= 8 and _norm(text) in nq]
    if inside:
        runs: List[List[int]] = []
        for i in inside:
            if runs and runs[-1][-1] + 1 == i:
                runs[-1].append(i)
            else:
                runs.append([i])
        best = max(runs, key=lambda r: sum(len(sentences[i][1]) for i in r))
        return [sentences[i][0] for i in best]
    for sid, text in sentences:
        if nq in _norm(text):
            return [sid]
    return []


def _quotes_to_ids(response: Dict[str, Any], sentences: List[tuple]) -> None:
    """Replaces typed quotes with quote_span_ids (prompt v2 answer shape)."""
    for section, field_name in _QUOTE_FIELDS:
        for item in response.get(section, []):
            quote = item.pop(field_name, "")
            item.pop("page_number", None)
            item["quote_span_ids"] = _ids_for_quote(quote, sentences)


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

        # Sentence-ID prompts (analysis v2) show "[p1.s3] text" lines. Detection below reads the
        # document text without the ID tags, so an ID like "p1.s105" can never look like content.
        sentences = _SENTENCE_LINE.findall(user_prompt)
        user_prompt = _SENTENCE_TAG.sub("", user_prompt)

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
        is_smespd = (
            "SMESPD" in user_prompt
            or "05" in user_prompt
            or "উদ্যোক্তা" in user_prompt
            or "UDYOG" in user_prompt
            or "উদ্যোগ" in user_prompt
        )

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
        elif is_smespd:
            response_dict = {
                "classification": {
                    "document_type": "CIRCULAR",
                    "institution": "Bangladesh Bank",
                    "department": "SMESPD",
                    "reference_number": "SMESPD Circular No. 05/2026",
                    "publication_date": "2026-09-13",
                    "subject": "নীতিমালা — উদ্যোক্তা উন্নয়ন কর্মসূচি (ব্যাংক ও আর্থিক প্রতিষ্ঠান সমূহের জন্য প্রশিক্ষণ নির্দেশিকা)",
                    "language": "bn",
                    "regulatory_topic": "SME & Youth Entrepreneurship Financing (UDYOG Programme)"
                },
                "executive_summary": {
                    "short_summary": "বাংলাদেশ ব্যাংক কর্তৃক উপজেলাভিত্তিক সম্ভাবনাময় তরুণ উদ্যোক্তা অনুসন্ধান, চিহ্নিতকরণ ও অর্থায়ন নিশ্চিতে 'উদ্যোগ (UDYOG)' শীর্ষক কর্মসূচি ও প্রশিক্ষণ নীতিমালা জারি করা হয়েছে।",
                    "detailed_summary": "তফসিলি ব্যাংকসমূহের মাধ্যমে উপজেলা পর্যায়ে তরুণ উদ্যোক্তাদের আবেদন গ্রহণ, বাছাই এবং সর্বোচ্চ ১০ লাখ টাকা পর্যন্ত ঋণ-অনুদানের সমন্বিত প্যাকেজ (৫০:৫০ অনুপাতে) প্রদানের নির্দেশ দেওয়া হয়েছে। বিতরণকৃত ঋণের বিপরীতে বাংলাদেশ ব্যাংকের সংশ্লিষ্ট স্কিম হতে পুনঃঅর্থায়ন সুবিধা প্রাপ্য হবে।",
                    "background": "ব্যাংক কোম্পানি আইন, ১৯৯১ এর ৪৫ ধারায় প্রদত্ত ক্ষমতাবলে এ নির্দেশনা জারি করা হয়েছে যা অবিলম্বে কার্যকর হবে।",
                    "purpose": "উপজেলা পর্যায়ে সম্ভাবনাময় তরুণ উদ্যোক্তাদের চিহ্নিত করে প্রশিক্ষণ প্রদান এবং সহজ শর্তে প্রাতিষ্ঠানিক অর্থায়ন নিশ্চিতকরণ।",
                    "key_changes": [
                        "প্রতিটি উপজেলায় তফসিলি ব্যাংকসমূহের মাধ্যমে সম্ভাবনাময় তরুণ উদ্যোক্তা অনুসন্ধান ও আবেদন গ্রহণ",
                        "ঋণ-অনুদান অনুপাত ৫০:৫০ (সর্বোচ্চ ১০ লাখ টাকা পর্যন্ত সমন্বিত অর্থায়ন প্যাকেজ)",
                        "বিতরণকৃত ঋণের বিপরীতে বাংলাদেশ ব্যাংকের স্কিম হতে পুনঃঅর্থায়ন সুবিধা প্রদান",
                        "জাতীয় পরিচয়পত্র, সিআইবি ও কেওয়াইসি যাচাই বাধ্যতামূলক; ঋণ খেলাপী ব্যক্তি অযোগ্য"
                    ],
                    "affected_stakeholders": ["Scheduled Commercial Banks", "Non-Bank Financial Institutions", "Youth Entrepreneurs"],
                    "important_dates": ["2026-09-13: Circular issue and immediate enforcement date"]
                },
                "provisions": [
                    {
                        "provision_number": "৪.১",
                        "parent_provision": "৪.",
                        "heading": "উদ্যোক্তা অনুসন্ধান ও আবেদন গ্রহণ পরিচালনা",
                        "verbatim_text": "উদ্যোক্তো অনুসন্ধোদনর কমযসূতচতর্ িফতসতল ব্াাংকসমূদহর মাধ্দম পতরচাতলি হদব। বযোাংদকর েোখোগুদলো স্থোনীয় পেথোদয় প্রিোর, \nউদ্যোক্তোগণ হদি আদব্ন িেণ, প্রকৃি উদে্াক্তা েনোক্তকরণ এবাং েোিোইকরদণ সভিয় িূভর্কো পোলন করদব;",
                        "page_number": 2,
                        "provision_type": "MANDATORY_REQUIREMENT",
                        "normalized_explanation": "তফসিলি ব্যাংকসমূহের স্থানীয় শাখা কর্তৃক উদ্যোক্তা অনুসন্ধান, প্রচার ও আবেদন গ্রহণ পরিচালনা বাধ্যতামূলক।"
                    },
                    {
                        "provision_number": "৭.১",
                        "parent_provision": "৭.",
                        "heading": "ঋণ সুবিধা ও পুনঃঅর্থায়ন প্রাপ্যতা",
                        "verbatim_text": "তিভসভল বযোাংকসর্ূে ভনবথোভিত উদ্যোক্তোদ্র অনুকূদল ঋণ প্র্োন করদব এবাং বযবসোদয়র ধ্রণ বো খোত অনুেোয়ী বোাংলোদ্ে \nবযোাংদকর সাংভিি পুনঃঅর্থোয়ন ভির্সমূহ গর্দক পুনঃ অর্থোয়ন সুভবধ্ো প্রোপয েদব;",
                        "page_number": 3,
                        "provision_type": "OPERATIONAL_MANDATE",
                        "normalized_explanation": "নির্বাচিত উদ্যোক্তাদের ঋণ প্রদান এবং বাংলাদেশ ব্যাংক থেকে পুনঃঅর্থায়ন প্রাপ্তির বিধান।"
                    },
                    {
                        "provision_number": "১১.১",
                        "parent_provision": "১১.",
                        "heading": "উপজেলা পর্যায়ে ব্যাংকের প্রচার দায়িত্ব",
                        "verbatim_text": "উদ্যোক্তো অনুসন্ধোন ও প্রিোর: কর্থসূভির আওতোিুক্ত উপদেলোয় অবভস্থত প্রভতভট তিভসভল বযোাংদকর েোখো স্থোনীয় পেথোদয় \nসম্ভোবনোর্য় তরুণ উদ্যোক্তো অনুসন্ধোন কর্থসূভির প্রিোর এবাং আদবেন গ্রহণ সাংিোন্ত কোেথির্ পভরিোলনো করদব।",
                        "page_number": 4,
                        "provision_type": "OPERATIONAL_MANDATE",
                        "normalized_explanation": "উপজেলা পর্যায়ে অবস্থিত ব্যাংক শাখা কর্তৃক তরুণ উদ্যোক্তা অনুসন্ধানের প্রচার পরিচালনা।"
                    },
                    {
                        "provision_number": "১৩.৩",
                        "parent_provision": "১৩.",
                        "heading": "উদ্যোক্তার বিস্তারিত তথ্য ও এনআইডি সংরক্ষণ",
                        "verbatim_text": "প্রভতভট বযোাংকদক তনবযাতচি উদ্যোক্তোর েোতীয় পভরিয়পত্র নম্বর, নোর্, বয়স, ভলি, ভিকোনো, উপদেলো, ভেযো/প্রভেযণ, বযবসোর \nধ্রণ, ভনেস্ব ভবভনদয়োগ, অনুদর্োভ্ত ঋণ ও অনু্োদনর পভরর্োণ, ঋদণর গর্য়ো্, ভবতরদণর তোভরখ, পুনঃ অর্থোয়ন, ঋণ",
                        "page_number": 5,
                        "provision_type": "RECORD_KEEPING",
                        "normalized_explanation": "নির্বাচিত উদ্যোক্তার জাতীয় পরিচয়পত্র নম্বর, বিতরণকৃত ঋণ ও পুনঃঅর্থায়ন সংক্রান্ত তথ্য সংরক্ষণ।"
                    },
                    {
                        "provision_number": "১৬",
                        "parent_provision": None,
                        "heading": "আইনি ভিত্তি ও অবিলম্বে কার্যকরের নির্দেশনা",
                        "verbatim_text": "ব্াাংক স্পকাম্পাতন আইন, ১৯৯১ এর ৪৫ ধারায় প্রেি যমিাবদল এ তনদেযশনা োতর করা হদলা র্া অতবলদম্ব কার্যকর হদব।",
                        "page_number": 5,
                        "provision_type": "LEGAL_AUTHORITY",
                        "normalized_explanation": "ব্যাংক কোম্পানি আইন, ১৯৯১ এর ৪৫ ধারায় প্রদত্ত ক্ষমতাবলে অবিলম্বে কার্যকর।"
                    }
                ],
                "obligations": [
                    {
                        "title": "তফসিলি ব্যাংক কর্তৃক উদ্যোক্তা অনুসন্ধান ও আবেদন গ্রহণ",
                        "obligation_type": "MANDATORY",
                        "requirement_description": "তফসিলি ব্যাংকসমূহকে তাদের স্থানীয় শাখার মাধ্যমে উপজেলা পর্যায়ে সম্ভাবনাময় তরুণ উদ্যোক্তা অনুসন্ধান, প্রচার এবং আবেদন গ্রহণ নিশ্চিত করতে হবে।",
                        "verbatim_quote": "উদ্যোক্তো অনুসন্ধোদনর কমযসূতচতর্ িফতসতল ব্াাংকসমূদহর মাধ্দম পতরচাতলি হদব। বযোাংদকর েোখোগুদলো স্থোনীয় পেথোদয় প্রিোর, \nউদ্যোক্তোগণ হদি আদব্ন িেণ, প্রকৃি উদে্াক্তা েনোক্তকরণ এবাং েোিোইকরদণ সভিয় িূভর্কো পোলন করদব;",
                        "page_number": 2,
                        "clause_reference": "৪.১",
                        "responsible_entity": "Scheduled Commercial Banks (Upazila Branches)",
                        "applicability_conditions": "All scheduled commercial banks operating in upazilas under UDYOG programme",
                        "effective_date": "2026-09-13",
                        "explicit_deadline": None,
                        "reporting_frequency": "CONTINUOUS",
                        "required_evidence": "Applicant intake register and local campaign records",
                        "consequence": "Regulatory action under Section 45 of the Bank Company Act, 1991"
                    },
                    {
                        "title": "নির্বাচিত উদ্যোক্তাদের অনুকূলে ঋণ বিতরণ ও পুনঃঅর্থায়ন আবেদন",
                        "obligation_type": "OPERATIONAL",
                        "requirement_description": "নির্বাচিত উদ্যোক্তাদের ব্যবসায়িক চাহিদা অনুযায়ী সর্বোচ্চ ১০ লাখ টাকা পর্যন্ত ঋণ-অনুদানের প্যাকেজ ৫০:৫০ অনুপাতে বিতরণ করতে হবে এবং বাংলাদেশ ব্যাংক হতে পুনঃঅর্থায়ন সুবিধা গ্রহণ করতে হবে।",
                        "verbatim_quote": "তিভসভল বযোাংকসর্ূে ভনবথোভিত উদ্যোক্তোদ্র অনুকূদল ঋণ প্র্োন করদব এবাং বযবসোদয়র ধ্রণ বো খোত অনুেোয়ী বোাংলোদ্ে \nবযোাংদকর সাংভিি পুনঃঅর্থোয়ন ভির্সমূহ গর্দক পুনঃ অর্থোয়ন সুভবধ্ো প্রোপয েদব;",
                        "page_number": 3,
                        "clause_reference": "৭.১",
                        "responsible_entity": "Scheduled Commercial Banks",
                        "applicability_conditions": "All candidate loan approvals under the programme",
                        "effective_date": "2026-09-13",
                        "explicit_deadline": None,
                        "reporting_frequency": "PER_DISBURSEMENT",
                        "required_evidence": "Loan sanction letter and refinance claim submission",
                        "consequence": "Loss of refinance eligibility"
                    },
                    {
                        "title": "উদ্যোক্তার এনআইডি ও ঋণ বিতরণের তথ্য সংরক্ষণ",
                        "obligation_type": "RECORD_KEEPING",
                        "requirement_description": "প্রতিটি ব্যাংককে নির্বাচিত উদ্যোক্তার জাতীয় পরিচয়পত্র নম্বর, বয়স, লিঙ্গ, ঠিকানা, উপজেলা, ব্যবসার ধরণ, নিজস্ব বিনিয়োগ, বিতরণকৃত ঋণ ও পরিশোধের শর্তাবলী সংক্রান্ত পূর্ণ তথ্য সংরক্ষণ করতে হবে।",
                        "verbatim_quote": "প্রভতভট বযোাংকদক তনবযাতচি উদ্যোক্তোর েোতীয় পভরিয়পত্র নম্বর, নোর্, বয়স, ভলি, ভিকোনো, উপদেলো, ভেযো/প্রভেযণ, বযবসোর \nধ্রণ, ভনেস্ব ভবভনদয়োগ, অনুদর্োভ্ত ঋণ ও অনু্োদনর পভরর্োণ, ঋদণর গর্য়ো্, ভবতরদণর তোভরখ, পুনঃ অর্থোয়ন, ঋণ",
                        "page_number": 5,
                        "clause_reference": "১৩.৩",
                        "responsible_entity": "Scheduled Commercial Banks",
                        "applicability_conditions": "All selected beneficiaries",
                        "effective_date": "2026-09-13",
                        "explicit_deadline": None,
                        "reporting_frequency": "MANDATORY_RECORD",
                        "required_evidence": "Beneficiary MIS database and verified NID copies",
                        "consequence": "Audit violation during Bangladesh Bank annual inspection"
                    }
                ],
                "applicability": {
                    "covered_entities": ["SCHEDULED_COMMERCIAL_BANK", "NON_BANK_FINANCIAL_INSTITUTION"],
                    "is_universal": True,
                    "exemptions": [],
                    "conditional_rules": "All branches operating in upazilas covered by the UDYOG programme"
                },
                "deadlines": {
                    "publication_date": "2026-09-13",
                    "effective_date": "2026-09-13",
                    "compliance_deadline": None,
                    "reporting_deadline": None,
                    "trigger_event": "Application intake and loan disbursement"
                },
                "relationships": [],
                "impact_assessment": {
                    "banking_operations": "উপজেলা পর্যায়ের শাখাগুলোতে প্রচার ও আবেদন ফরম বিতরণ ব্যবস্থা স্থাপন।",
                    "credit": "৫০:৫০ অনুপাতে সর্বোচ্চ ১০ লাখ টাকা পর্যন্ত ঋণ ও অনুদানের প্যাকেজ পরিচালনা।",
                    "compliance": "সিআইবি খেলাপী যাচাই, কেওয়াইসি এবং জাতীয় পরিচয়পত্র রেকর্ড সংরক্ষণ।",
                    "refinance": "বাংলাদেশ ব্যাংকের সংশ্লিষ্ট স্কিম হতে পুনঃঅর্থায়ন দাবি দাখিল।"
                }
            }
        else:
            # Generic valid fallback for any circular text
            first_line = user_prompt.splitlines()[0] if user_prompt else "Bangladesh Bank Circular"
            quote = user_prompt[:80] if len(user_prompt) >= 80 else user_prompt
            if sentences:
                quote = sentences[0][1]
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
            amending = next((text for _sid, text in sentences if re.search(r"\bamend", text, re.IGNORECASE)), None)
            if amending:
                response_dict["relationships"].append({
                    "relationship_type": "AMENDS",
                    "target_reference_hint": amending[:120],
                    "supporting_quote": amending,
                    "page_number": 1,
                    "confidence": 0.9,
                    "detection_method": "EXPLICIT_CITATION"
                })

        if sentences:
            _quotes_to_ids(response_dict, sentences)

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
