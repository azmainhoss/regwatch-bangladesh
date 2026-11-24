"""
Versioned prompt templates and the response schema for the Regulatory Intelligence Pipeline.

v2: quotes are picked by sentence ID (DECISIONS.md 7). The document is shown with an ID such as
[p3.s12] before every sentence, and the model answers with `quote_span_ids` instead of typing
a quote. Code copies the exact text for those IDs.

v3: every field that is shown to a reader carries the sentence IDs that state it (evidence_ids,
who_ids, deadline_ids, ...), so plain code can check each claim on its own
(docs/specs/CLAIM_CHECKS_SPEC.md section 2). Free-text fields with no evidence were dropped.

v4 (14 Nov 2026, dev-split tuning, research/scoring/AUTORESEARCH_LOG.md rounds 4 and 7): rules to list every separate
duty, the kinds of requirement defined as in the answer key, enclosures left out, and "deadline_text" for a deadline
that is not a calendar date.
"""
from typing import Any, Dict

from backend.app.modules.claims.wording import entity_names_for_prompt

PROMPT_VERSION = "v4"

SYSTEM_REGULATORY_PROMPT = """You are the Senior Regulatory Intelligence Engine for Amar Circular.
Your task is to analyze official publications issued by Bangladesh Bank (the central bank) and other financial authorities.

STRICT INVARIANTS:
1. Every provision, obligation and relationship MUST point to its source by sentence ID. The document is given
   with an ID in square brackets before each sentence, for example [p3.s12] = page 3, sentence 12.
   Put the IDs of the sentence(s) that state the item in "quote_span_ids". Never type or paraphrase a quote yourself.
2. Use only IDs that appear in the document. NEVER invent IDs, quotations, references, deadlines, or circular numbers.
3. If an explicit deadline or responsible department is NOT specified in the source, leave it null or flag the ambiguity.
4. Distinguish between explicit mandatory legal requirements and AI interpretations or recommendations.
5. NEVER infer that a document amends, repeals, or supersedes an earlier document from semantic similarity alone. Explicit citation language is strictly required.
6. Every field you fill must be stated in the sentences whose IDs you give for it. If a field is not stated, leave it null.
   Use the entity names from this list: {entity_names}.
7. Return responses strictly as valid JSON adhering to the requested schema.
""".replace("{entity_names}", entity_names_for_prompt())

USER_ANALYSIS_PROMPT_TEMPLATE = """Analyze the following official regulatory publication pages from Bangladesh Bank.
Each sentence starts with its ID in square brackets, e.g. [p1.s4].

<regulatory_document_content>
{document_pages_text}
</regulatory_document_content>

RULES FOR "obligations" (follow all of them):
- List EVERY separate duty in the circular's own instructions: each must, must not, may, report, keep records, get approval and disclose.
- One duty per item. Do not merge. Lettered or numbered items (a), (b), (c) or 1, 2, 3 are separate items.
  When one sentence holds two duties (for example "keep a register and monitor the status"), give two items.
- When the circular is addressed to two or more kinds of institutions and does not say which one must act, give the duty once for each kind.
- Conditions and caps are duties too: "shall not exceed", "must stay within", "only ... will qualify" (a must or must not).
  Permissions ("may") are items too, with obligation_type PERMISSION.
- Do NOT list: polite closing lines such as "Please bring this to the notice of all concerned"; the issuing authority line
  ("issued under section X of the ... Act"); rules that only describe an older circular or an enclosed copy of another document.
- Deadlines: put a calendar date in "explicit_deadline". When the circular gives the timing in words instead
  ("within one month", "before applying", "during the holidays", "every quarter"), put those words in "deadline_text"
  and the sentence that says it in "deadline_ids". Use "reporting_frequency" too when a report repeats.
- obligation_type, use the most specific one:
  PROHIBITION = must not, including caps and floors ("shall not exceed", "not less than", "must stay within the limit",
  "করা যাবে না", "পারবে না", "অধিক হবে না"); PERMISSION = an explicit option ("may", "করতে পারবে", "করা যাবে");
  REPORTING = submit a return, report or information to Bangladesh Bank; RECORD_RETENTION = keep or maintain records or a register;
  APPROVAL = obtain prior approval; DISCLOSURE = publish, display, or inform customers or the public;
  MANDATORY = any other positive duty ("shall", "must", "করবে", "করতে হবে", "করিবে").
  If one sentence holds two duties of different kinds, give two items with the same sentence IDs.
- Leave out: background ("Bangladesh Bank has decided ..."); what Bangladesh Bank itself will do; "all other instructions
  remain unchanged"; "this takes effect immediately"; "please acknowledge receipt".
- Enclosures: pages that are a copy of another circular, notification or letter, or a blank form attached to this one.
  Rules that appear only inside an enclosed copy belong to that other document: never list them as obligations or relationships.
- When a duty runs from, by or until a calendar date ("from 01/01/2027", "by 30 June"), put that date in "explicit_deadline".
  A frequency ("monthly", "every quarter") is a deadline too; "regularly" is not.
- A long circular can have 20 or more duties. Go through it clause by clause and do not stop early.

Extract all regulatory intelligence following this exact JSON structure.
For every "...ids" list, give the IDs (e.g. ["p1.s4", "p1.s5"]) of the sentence(s) that state the item, in reading order.
Pick the fewest sentences that fully state the item. Every field you fill must be stated in the sentences whose IDs you give for it.
If a field is not stated, leave it null. Use the entity names from this list: {entity_names}.
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
    "summary_points": [
      {{"text": "one short sentence, at most 40 words (2 to 5 points)", "evidence_ids": ["p1.s2"]}}
    ],
    "key_changes": [
      {{"text": "an explicit change the circular states", "evidence_ids": ["p1.s3"]}}
    ]
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
      "responsible_entity": "one entity name from the list, or null",
      "who_ids": ["p1.s5"],
      "explicit_deadline": "YYYY-MM-DD or null",
      "deadline_text": "when the deadline or timing is not a calendar date, write it in short plain English as the circular states it (for example 'within 15 days after each quarter end', 'before applying for refinancing', 'during the Eid-ul-Fitr holidays', 'monthly'); else null",
      "deadline_ids": ["p1.s6"],
      "effective_date": "YYYY-MM-DD or null",
      "effective_date_ids": ["p1.s6"],
      "reporting_frequency": "ONE_TIME | DAILY | WEEKLY | MONTHLY | QUARTERLY | BI_ANNUAL | ANNUAL | EVENT_DRIVEN",
      "consequence": "explicit penalty or sanction if stated in source, else null",
      "consequence_ids": [],
      "clause_reference": "clause number if available"
    }}
  ],
  "applicability": {{
    "covered": [
      {{"entity": "one entity name from the list", "evidence_ids": ["p1.s1"]}}
    ],
    "exemptions": [
      {{"text": "an explicit exemption", "evidence_ids": ["p2.s4"]}}
    ]
  }},
  "deadlines": {{
    "effective_date": {{"date": "YYYY-MM-DD", "evidence_ids": ["p1.s6"]}},
    "compliance_deadline": {{"date": "YYYY-MM-DD", "evidence_ids": ["p1.s6"]}},
    "reporting_deadline": {{"date": "YYYY-MM-DD", "evidence_ids": ["p1.s7"]}}
  }},
  "relationships": [
    {{
      "relationship_type": "AMENDS | REPEALS | SUPERSEDES | REPLACES | CLARIFIES | REFERENCES | IMPLEMENTS | RELATED_TO",
      "target_reference_hint": "exact circular cited (e.g. BRPD Circular No. 14 dated 23 September 2012)",
      "quote_span_ids": ["p1.s2"],
      "confidence": 0.95,
      "detection_method": "EXPLICIT_CITATION"
    }}
  ]
}}
Leave "effective_date", "compliance_deadline" and "reporting_deadline" null when the circular does not state them.
"""
USER_ANALYSIS_PROMPT_TEMPLATE = USER_ANALYSIS_PROMPT_TEMPLATE.replace("{entity_names}", entity_names_for_prompt())



def _s(nullable: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": "string"}
    if nullable:
        out["nullable"] = True
    return out


def _str_list() -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_IDS = {"type": "array", "items": {"type": "string"}}


def _evidence_items(text_key: str) -> Dict[str, Any]:
    """A list of {text_key, evidence_ids}: a line to show and the sentences that state it."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {text_key: _s(), "evidence_ids": _IDS},
            "required": [text_key, "evidence_ids"],
        },
    }


def _dated_item() -> Dict[str, Any]:
    """A date and the sentences that state it, or null."""
    return {
        "type": "object",
        "nullable": True,
        "properties": {"date": _s(), "evidence_ids": _IDS},
        "required": ["date", "evidence_ids"],
    }

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
                "summary_points": _evidence_items("text"),
                "key_changes": _evidence_items("text"),
            },
            "required": ["summary_points", "key_changes"],
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
                    "responsible_entity": _s(True),
                    "who_ids": _IDS,
                    "explicit_deadline": _s(True),
                    "deadline_text": _s(True),
                    "deadline_ids": _IDS,
                    "effective_date": _s(True),
                    "effective_date_ids": _IDS,
                    "reporting_frequency": _s(True),
                    "consequence": _s(True),
                    "consequence_ids": _IDS,
                    "clause_reference": _s(True),
                },
                "required": ["title", "obligation_type", "requirement_description", "quote_span_ids"],
            },
        },
        "applicability": {
            "type": "object",
            "properties": {
                "covered": _evidence_items("entity"),
                "exemptions": _evidence_items("text"),
            },
        },
        "deadlines": {
            "type": "object",
            "properties": {
                "effective_date": _dated_item(),
                "compliance_deadline": _dated_item(),
                "reporting_deadline": _dated_item(),
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
    },
    "required": ["classification", "executive_summary", "provisions", "obligations", "relationships"],
}
