"""One place that decides whether a document is a synthetic test/sample record.

Real circulars must never be hidden because a word like "Test" or "Latest"
appears in their title, so only explicit markers count:

* the ``is_synthetic_fixture`` flag on the document (set this for any new
  fixture or sample record), or
* the fixed prefixes that existing fixture generators and test suites use:
  titles starting with "Sample " and reference numbers starting with
  SAMPLE-, BRPD(P), VCP-, UTD- or GP-.
"""
from typing import Optional

from sqlalchemy import func, or_

from backend.app.modules.documents.models import Document

SYNTHETIC_TITLE_PREFIXES = ("sample ",)
SYNTHETIC_REFERENCE_PREFIXES = ("sample-", "brpd(p)", "vcp-", "utd-", "gp-")


def is_synthetic_document(
    title: Optional[str],
    reference_number: Optional[str],
    flag: Optional[bool] = False,
    status: Optional[str] = None,
    version_count: Optional[int] = None,
) -> bool:
    if flag:
        return True
    t_low = (title or "").strip().lower()
    r_low = (reference_number or "").strip().lower()
    if t_low.startswith(SYNTHETIC_TITLE_PREFIXES):
        return True
    if r_low.startswith(SYNTHETIC_REFERENCE_PREFIXES):
        return True
    # A draft with no stored file at all is a placeholder, not a publication.
    if status == "DRAFT" and version_count == 0:
        return True
    return False


def synthetic_sql_condition():
    """SQL version of is_synthetic_document (without the draft placeholder rule)."""
    ref = func.lower(func.coalesce(Document.reference_number, ""))
    title = func.lower(func.coalesce(Document.title, ""))
    conditions = [Document.is_synthetic_fixture == True]  # noqa: E712
    conditions += [title.like(f"{p}%") for p in SYNTHETIC_TITLE_PREFIXES]
    conditions += [ref.like(f"{p}%") for p in SYNTHETIC_REFERENCE_PREFIXES]
    return or_(*conditions)
