"""Answers written outside the app (the laptop's Claude analysis, Phase 1) and how they are checked.

An answer is the JSON a model would return for a circular (prompt format in prompts.py), with sentence IDs
instead of quotes. `check_answer` lists everything the app would drop or reject; `AnswerFileProvider` hands a
checked answer to the normal analysis pipeline, so every point goes through the same automatic checks as a
live model's. Used by backend/scripts/manual_analysis.py and the upload endpoint (analysis/upload_router.py).
"""
import json
import re
from typing import Any, Dict, List

from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse
from backend.app.modules.analysis.sentences import SentenceIndex

MODEL_NAME = "manual-analysis-v1"

OBLIGATION_TYPES = {"MANDATORY", "CONDITIONAL", "PROHIBITION", "PERMISSION", "RECOMMENDATION", "REPORTING",
                    "RECORD_RETENTION", "APPROVAL", "DISCLOSURE"}
RELATIONSHIP_TYPES = {"AMENDS", "REPEALS", "SUPERSEDES", "REPLACES", "CLARIFIES", "REFERENCES", "IMPLEMENTS", "RELATED_TO"}
ID_RE = re.compile(r"^p\d+\.s\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_answer(payload: Any, index: SentenceIndex) -> List[str]:
    """ERROR lines for anything the app would drop or reject. An empty list means it can be loaded."""
    errs: List[str] = []
    if not isinstance(payload, dict):
        return ["ERROR the file is not a JSON object"]
    for key in ("classification", "executive_summary", "provisions", "obligations", "relationships"):
        if key not in payload:
            errs.append(f"ERROR missing '{key}'")

    def ids_ok(where: str, ids: Any, required: bool = False) -> None:
        if ids in (None, []):
            if required:
                errs.append(f"ERROR {where}: no sentence IDs")
            return
        if not isinstance(ids, list):
            errs.append(f"ERROR {where}: IDs must be a list")
            return
        for sid in ids:
            if not isinstance(sid, str) or not ID_RE.match(sid) or sid not in index.sentences:
                errs.append(f"ERROR {where}: unknown sentence ID {sid!r}")

    def date_ok(where: str, value: Any) -> None:
        if value not in (None, "") and not (isinstance(value, str) and DATE_RE.match(value)):
            errs.append(f"ERROR {where}: date must be YYYY-MM-DD, got {value!r}")

    cls = payload.get("classification") or {}
    date_ok("classification.publication_date", cls.get("publication_date"))
    summ = payload.get("executive_summary") or {}
    points = summ.get("summary_points") or []
    if not points:
        errs.append("ERROR executive_summary.summary_points is empty")
    for i, it in enumerate(points):
        ids_ok(f"summary_points[{i}]", (it or {}).get("evidence_ids"), required=True)
    for i, it in enumerate(summ.get("key_changes") or []):
        ids_ok(f"key_changes[{i}]", (it or {}).get("evidence_ids"), required=True)
    for i, it in enumerate(payload.get("provisions") or []):
        ids_ok(f"provisions[{i}]", (it or {}).get("quote_span_ids"), required=True)
    for i, ob in enumerate(payload.get("obligations") or []):
        ob = ob or {}
        if ob.get("obligation_type") not in OBLIGATION_TYPES:
            errs.append(f"ERROR obligations[{i}]: obligation_type {ob.get('obligation_type')!r}")
        for f in ("title", "requirement_description"):
            if not (isinstance(ob.get(f), str) and ob[f].strip()):
                errs.append(f"ERROR obligations[{i}]: '{f}' is empty")
        ids_ok(f"obligations[{i}].quote_span_ids", ob.get("quote_span_ids"), required=True)
        for f in ("who_ids", "deadline_ids", "effective_date_ids", "consequence_ids"):
            ids_ok(f"obligations[{i}].{f}", ob.get(f))
        date_ok(f"obligations[{i}].explicit_deadline", ob.get("explicit_deadline"))
        date_ok(f"obligations[{i}].effective_date", ob.get("effective_date"))
        if ob.get("responsible_entity") and not ob.get("who_ids"):
            errs.append(f"ERROR obligations[{i}]: responsible_entity given without who_ids")
        if (ob.get("explicit_deadline") or ob.get("deadline_text")) and not ob.get("deadline_ids"):
            errs.append(f"ERROR obligations[{i}]: deadline given without deadline_ids")
    app = payload.get("applicability") or {}
    for i, it in enumerate(app.get("covered") or []):
        ids_ok(f"applicability.covered[{i}]", (it or {}).get("evidence_ids"), required=True)
    for i, it in enumerate(app.get("exemptions") or []):
        ids_ok(f"applicability.exemptions[{i}]", (it or {}).get("evidence_ids"), required=True)
    for k, it in (payload.get("deadlines") or {}).items():
        if it:
            date_ok(f"deadlines.{k}", it.get("date"))
            ids_ok(f"deadlines.{k}", it.get("evidence_ids"), required=True)
    for i, rel in enumerate(payload.get("relationships") or []):
        rel = rel or {}
        if rel.get("relationship_type") not in RELATIONSHIP_TYPES:
            errs.append(f"ERROR relationships[{i}]: relationship_type {rel.get('relationship_type')!r}")
        ids_ok(f"relationships[{i}]", rel.get("quote_span_ids"), required=True)
    return errs


class AnswerFileProvider(BaseAIProvider):
    """Returns an answer written in advance, as if a model had just given it."""

    def __init__(self, payload: Dict[str, Any], raw: str):
        super().__init__(MODEL_NAME)
        self.payload, self.raw = payload, raw

    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        return LLMResponse(raw_content=self.raw, parsed_json=json.loads(self.raw), model_name=MODEL_NAME, success=True)
