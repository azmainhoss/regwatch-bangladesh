"""
Versioned prompt templates and the response schema for the Regulatory Intelligence Pipeline.

v2: quotes are picked by sentence ID (DECISIONS.md 7). The document is shown with an ID such as
[p3.s12] before every sentence, and the model answers with `quote_span_ids` instead of typing
a quote. Code copies the exact text for those IDs.
"""
from typing import Any, Dict

PROMPT_VERSION = "v2"

SYSTEM_REGULATORY_PROMPT = """You are the Senior Regulatory Intelligence Engine for RegWatch Bangladesh.
Your task is to analyze official publications issued by Bangladesh Bank (the central bank) and other financial authorities.

STRICT INVARIANTS:
1. Every provision, obligation and relationship MUST point to its source by sentence ID. The document is given
   with an ID in square brackets before each sentence, for example [p3.s12] = page 3, sentence 12.
   Put the IDs of the sentence(s) that state the item in "quote_span_ids". Never type or paraphrase a quote yourself.
2. Use only IDs that appear in the document. NEVER invent IDs, quotations, references, deadlines, or circular numbers.
3. If an explicit deadline or responsible department is NOT specified in the source, leave it null or flag the ambiguity.
4. Distinguish between explicit mandatory legal requirements and AI interpretations or recommendations.
5. NEVER infer that a document amends, repeals, or supersedes an earlier document from semantic similarity alone. Explicit citation language is strictly required.
6. Return responses strictly as valid JSON adhering to the requested schema.
"""

USER_ANALYSIS_PROMPT_TEMPLATE = """Analyze the following official regulatory publication pages from Bangladesh Bank.
Each sentence starts with its ID in square brackets, e.g. [p1.s4].

<regulatory_document_content>
{document_pages_text}
</regulatory_document_content>

Extract all regulatory intelligence following this exact JSON structure.
For "quote_span_ids", list the IDs (e.g. ["p1.s4", "p1.s5"]) of the sentence(s) that support the item, in reading order.
Pick the fewest sentences that fully state the item.
{{
  "classification": {{
    "document_type": "CIRCULAR | CIRCULAR_LETTER | GUIDELINE | NOTIFICATION | POLICY | DIRECTIVE | INSTRUCTION | NOTICE | ORDER",
    "institution": "Bangladesh Bank",
    "department": "string or null",
    "reference_number": "string or null",
    "publication_date": "YYYY-MM-DD",
    "subject": "string",
    "language": "en | bn | mixed",
    "regulatory_topic": "string"
  }},
  "executive_summary": {{
    "short_summary": "1-2 sentence overview",
    "detailed_summary": "comprehensive multi-paragraph summary",
    "background": "regulatory context and statutory powers",
    "purpose": "core regulatory objective",
    "key_changes": ["list of explicit amendments or new rules"],
    "affected_stakeholders": ["list of affected entities"],
    "important_dates": ["list of key dates and milestones"]
  }},
  "provisions": [
    {{
      "provision_number": "string (e.g. '1.', '1.1', '2(a)')",
      "parent_provision": "string or null",
      "heading": "string or null",
      "quote_span_ids": ["p1.s3"],
      "provision_type": "MANDATORY_REQUIREMENT | PROHIBITION | REPORTING | DEFINITION | EFFECTIVE_DATE | SANCTION",
      "normalized_explanation": "plain-language interpretation"
    }}
  ],
  "obligations": [
    {{
      "title": "Concise obligation title",
      "obligation_type": "MANDATORY | CONDITIONAL | PROHIBITION | PERMISSION | RECOMMENDATION | REPORTING | RECORD_RETENTION | APPROVAL | DISCLOSURE",
      "requirement_description": "detailed legal requirement",
      "quote_span_ids": ["p1.s5", "p1.s6"],
      "clause_reference": "clause number if available",
      "responsible_entity": "Scheduled Commercial Banks | NBFIs | etc.",
      "applicability_conditions": "conditions under which obligation triggers",
      "effective_date": "YYYY-MM-DD or null",
      "explicit_deadline": "YYYY-MM-DD or null",
      "reporting_frequency": "ONE_TIME | DAILY | WEEKLY | MONTHLY | QUARTERLY | BI_ANNUAL | ANNUAL | EVENT_DRIVEN",
      "required_evidence": "audit proof or submission required",
      "consequence": "explicit penalty or sanction if stated in source"
    }}
  ],
  "applicability": {{
    "covered_entities": ["SCHEDULED_COMMERCIAL_BANK", "ISLAMIC_BANK", "NBFI", "PAYMENT_SERVICE_PROVIDER"],
    "is_universal": true,
    "exemptions": ["list of explicit exemptions"],
    "conditional_rules": "string or null"
  }},
  "deadlines": {{
    "publication_date": "YYYY-MM-DD",
    "effective_date": "YYYY-MM-DD or null",
    "compliance_deadline": "YYYY-MM-DD or null",
    "reporting_deadline": "YYYY-MM-DD or null",
    "trigger_event": "string or null"
  }},
  "relationships": [
    {{
      "relationship_type": "AMENDS | REPEALS | SUPERSEDES | REPLACES | CLARIFIES | REFERENCES | IMPLEMENTS | RELATED_TO",
      "target_reference_hint": "exact circular cited (e.g. BRPD Circular No. 14 dated 23 September 2012)",
      "quote_span_ids": ["p1.s2"],
      "confidence": 0.95,
      "detection_method": "EXPLICIT_CITATION"
    }}
  ],
  "impact_assessment": {{
    "banking_operations": "string or null",
    "credit": "string or null",
    "compliance": "string or null",
    "risk_management": "string or null",
    "technology": "string or null"
  }}
}}
"""


def _s(nullable: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": "string"}
    if nullable:
        out["nullable"] = True
    return out


def _str_list() -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_IDS = {"type": "array", "items": {"type": "string"}}

# The expected answer, as a provider-neutral JSON schema (single types, `nullable` flags).
# Providers convert it to their own dialect (Gemini responseSchema, OpenAI json_schema).
ANALYSIS_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "object",
            "properties": {
                "document_type": _s(),
                "institution": _s(),
                "department": _s(True),
                "reference_number": _s(True),
                "publication_date": _s(True),
                "subject": _s(),
                "language": _s(),
                "regulatory_topic": _s(True),
            },
            "required": ["document_type", "subject", "language"],
        },
        "executive_summary": {
            "type": "object",
            "properties": {
                "short_summary": _s(),
                "detailed_summary": _s(),
                "background": _s(True),
                "purpose": _s(True),
                "key_changes": _str_list(),
                "affected_stakeholders": _str_list(),
                "important_dates": _str_list(),
            },
            "required": ["short_summary", "detailed_summary", "key_changes"],
        },
        "provisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "provision_number": _s(True),
                    "parent_provision": _s(True),
                    "heading": _s(True),
                    "quote_span_ids": _IDS,
                    "provision_type": _s(),
                    "normalized_explanation": _s(),
                },
                "required": ["quote_span_ids", "provision_type", "normalized_explanation"],
            },
        },
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": _s(),
                    "obligation_type": _s(),
                    "requirement_description": _s(),
                    "quote_span_ids": _IDS,
                    "clause_reference": _s(True),
                    "responsible_entity": _s(True),
                    "applicability_conditions": _s(True),
                    "effective_date": _s(True),
                    "explicit_deadline": _s(True),
                    "reporting_frequency": _s(True),
                    "required_evidence": _s(True),
                    "consequence": _s(True),
                },
                "required": ["title", "obligation_type", "requirement_description", "quote_span_ids"],
            },
        },
        "applicability": {
            "type": "object",
            "properties": {
                "covered_entities": _str_list(),
                "is_universal": {"type": "boolean"},
                "exemptions": _str_list(),
                "conditional_rules": _s(True),
            },
        },
        "deadlines": {
            "type": "object",
            "properties": {
                "publication_date": _s(True),
                "effective_date": _s(True),
                "compliance_deadline": _s(True),
                "reporting_deadline": _s(True),
                "trigger_event": _s(True),
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relationship_type": _s(),
                    "target_reference_hint": _s(True),
                    "quote_span_ids": _IDS,
                    "confidence": {"type": "number"},
                    "detection_method": _s(True),
                },
                "required": ["relationship_type", "quote_span_ids"],
            },
        },
        "impact_assessment": {
            "type": "object",
            "properties": {
                "banking_operations": _s(True),
                "credit": _s(True),
                "compliance": _s(True),
                "risk_management": _s(True),
                "technology": _s(True),
            },
        },
    },
    "required": ["classification", "executive_summary", "provisions", "obligations", "relationships"],
}
