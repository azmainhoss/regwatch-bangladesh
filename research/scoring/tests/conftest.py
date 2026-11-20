"""Test setup: made-up research and scoring folders, so no test reads real keys or touches real data.

The folders are chosen before any scorer module is imported (the scorer reads them at import time).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="scorer_test_"))
RESEARCH = _ROOT / "research"
SCORING = _ROOT / "scoring"
os.environ["REGWATCH_RESEARCH_ROOT"] = str(RESEARCH)
os.environ["REGWATCH_SCORING_ROOT"] = str(SCORING)
(RESEARCH / "gold").mkdir(parents=True)
SCORING.mkdir(parents=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))

PAGE_TEXT_1 = (
    "BRPD Circular No. 15\n"
    "Date: November 27, 2024\n"
    "All scheduled commercial banks must classify their credit facilities into three distinct stages:\n"
    "1.1 Stage 1 (Performing): Loans with no significant increase in credit risk. General provision: 1.00%.\n"
    "1.2 Stage 2 (Underperforming): Significant increase in credit risk (overdue 30-89 days). Provision: 5.00%.\n"
    "All banks must submit an initial readiness report to BRPD within 31 December 2024.\n"
    "Failure to comply with these provisions will attract penal actions under Section 109(7) of the Bank Company Act, 1991.\n"
    "This is an IFRS 9 master policy."
)

# Made-up circulars. Rows 9001 and 9002 are not real: they only exist for these tests.
DOC_INDEX = [
    {"row": 9001, "split": "dev", "title": "BRPD Circular No. 15: Made-up circular one", "date": "2024-11-27",
     "pages": [{"page_id": "9001_0_p1", "file": "pdfs/9001_0.pdf", "page": 1, "cls": "english_clean", "in_obligation_window": True},
               {"page_id": "9001_0_p2", "file": "pdfs/9001_0.pdf", "page": 2, "cls": "english_clean", "in_obligation_window": False}]},
    {"row": 9002, "split": "dev", "title": "BRPD Circular No. 16: Made-up circular two", "date": "2024-12-01",
     "pages": [{"page_id": "9002_0_p1", "file": "pdfs/9002_0.pdf", "page": 1, "cls": "english_clean", "in_obligation_window": True}]},
    {"row": 9101, "split": "test", "title": "Made-up test circular", "date": "2025-01-01",
     "pages": [{"page_id": "9101_0_p1", "file": "pdfs/9101_0.pdf", "page": 1, "cls": "english_clean", "in_obligation_window": True}]},
]
(RESEARCH / "gold" / "doc_index.json").write_text(json.dumps(DOC_INDEX), encoding="utf-8")


def write_fake_inputs(page_ids=("9001_0_p1", "9001_0_p2", "9002_0_p1")):
    d = SCORING / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    for pid in page_ids:
        stem, _, num = pid.rpartition("_p")
        text = PAGE_TEXT_1 if num == "1" else "Annex: a list of branch names for reference only."
        rec = {"page_id": pid, "row": int(stem.split("_")[0]), "stem": stem, "page": int(num), "method": "TEXT_LAYER",
               "route_reason": "clean_text_layer", "language": "en", "text": text, "cleaned_text": text,
               "line_boxes": None, "has_tables": False, "quality_status": "SUCCESS_NATIVE", "quality_score": 1.0, "model": None}
        (d / f"{pid}.json").write_text(json.dumps(rec), encoding="utf-8")
