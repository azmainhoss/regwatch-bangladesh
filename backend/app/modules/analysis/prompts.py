"""
Versioned prompt templates for the Regulatory Intelligence Pipeline.
Prompt Version: v1.0.0
"""

PROMPT_VERSION = "v1.0.0"

SYSTEM_REGULATORY_PROMPT = """You are the Senior Regulatory Intelligence Engine for RegWatch Bangladesh.
Your task is to analyze official publications issued by Bangladesh Bank (the central bank) and other financial authorities.

STRICT INVARIANTS:
1. Every material claim, obligation, provision, and relationship MUST cite an exact, verbatim quotation from the source text and the corresponding page number.
2. NEVER hallucinate or fabricate quotations, references, deadlines, or circular numbers.
3. If an explicit deadline or responsible department is NOT specified in the source, leave it null or flag the ambiguity.
4. Distinguish between explicit mandatory legal requirements and AI interpretations or recommendations.
5. NEVER infer that a document amends, repeals, or supersedes an earlier document from semantic similarity alone. Explicit citation language is strictly required.
6. Return responses strictly as valid JSON adhering to the requested schema.
"""

USER_ANALYSIS_PROMPT_TEMPLATE = """Analyze the following official regulatory publication pages from Bangladesh Bank.

<regulatory_document_content>
{document_pages_text}
</regulatory_document_content>

Extract all regulatory intelligence following this exact JSON structure:
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
      "verbatim_text": "EXACT VERBATIM QUOTE FROM TEXT",
      "page_number": 1,
      "provision_type": "MANDATORY_REQUIREMENT | PROHIBITION | REPORTING | DEFINITION | EFFECTIVE_DATE | SANCTION",
      "normalized_explanation": "plain-language interpretation"
    }}
  ],
  "obligations": [
    {{
      "title": "Concise obligation title",
      "obligation_type": "MANDATORY | CONDITIONAL | PROHIBITION | PERMISSION | RECOMMENDATION | REPORTING | RECORD_RETENTION | APPROVAL | DISCLOSURE",
      "requirement_description": "detailed legal requirement",
      "verbatim_quote": "EXACT VERBATIM QUOTATION FROM PAGE TEXT",
      "page_number": 1,
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
      "supporting_quote": "EXACT VERBATIM QUOTE CITING TARGET",
      "page_number": 1,
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
