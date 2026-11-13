"""Old-versus-new comparison of two stored circular files, page text against page text.

The text shown is what a reader sees on each page: the cleaned text, else the raw text (the same
rule as search). The pages are cut into clauses or paragraphs, the two lists are lined up, and
inside a changed paragraph the words are compared. Every piece of text in the result is copied
from the stored page text, never reworded.
"""
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.documents.access import can_view_document
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.schemas import (
    CompareOp,
    ComparePageSummary,
    CompareResponse,
    CompareSide,
    CompareStats,
    CompareWord,
)
from backend.app.modules.identity.models import User

MAX_PAGES_PER_SIDE = 300
# Past this many paragraph pairs in one changed block, pair them in order instead of searching for the best match.
MAX_PAIRING_CELLS = 2500
MIN_PAIR_RATIO = 0.5

# A line that starts a new clause: "1.", "1.1", "2(a)", "(a)", and the same with Bangla digits.
_CLAUSE_START = re.compile(
    r"^[ \t]*(?:\d+(?:\.\d+)+\.?|\d+[A-Z]?\.|\d+\([A-Za-z0-9]{1,3}\)|\([A-Za-z0-9]{1,4}\)|[০-৯]+(?:\.[০-৯]+)*[.)])[ \t]+\S"
)
_WORD_PIECE = re.compile(r"\S+\s*")

Paragraph = Tuple[str, int, str]  # (exact text, page number, comparison key)


def reader_text(page: DocumentPage) -> str:
    """The page text a reader sees: cleaned text when there is any, else the raw text."""
    cleaned = page.cleaned_text
    return cleaned if cleaned else (page.raw_text or "")


def split_paragraphs(text: str) -> List[str]:
    """Cuts a page's text at blank lines and at clause numbers. Each piece is an exact substring of `text`."""
    pieces: List[str] = []
    start: Optional[int] = None
    end = 0
    offset = 0
    for line in text.split("\n"):
        line_end = offset + len(line)
        if not line.strip():
            if start is not None:
                pieces.append(text[start:end])
                start = None
        else:
            if start is not None and _CLAUSE_START.match(line):
                pieces.append(text[start:end])
                start = None
            if start is None:
                start = offset
            end = line_end
        offset = line_end + 1
    if start is not None:
        pieces.append(text[start:end])
    return [p.strip() for p in pieces if p.strip()]


def _key(text: str) -> str:
    return " ".join(text.split())


def build_paragraphs(pages: Sequence[Tuple[int, str]]) -> List[Paragraph]:
    out: List[Paragraph] = []
    for number, text in pages:
        for piece in split_paragraphs(text):
            out.append((piece, number, _key(piece)))
    return out


def _merge_words(words: List[CompareWord]) -> List[CompareWord]:
    merged: List[CompareWord] = []
    for w in words:
        if merged and merged[-1].op == w.op:
            merged[-1] = CompareWord(op=w.op, text=merged[-1].text + w.text)
        else:
            merged.append(w)
    return merged


def word_diff(left: str, right: str) -> List[CompareWord]:
    """Word-level diff. Equal and deleted pieces are cut from `left`, inserted ones from `right`."""
    lp, rp = _WORD_PIECE.findall(left), _WORD_PIECE.findall(right)
    sm = SequenceMatcher(None, [p.strip() for p in lp], [p.strip() for p in rp], autojunk=False)
    words: List[CompareWord] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            words.append(CompareWord(op="equal", text="".join(lp[i1:i2])))
            continue
        if i2 > i1:
            words.append(CompareWord(op="delete", text="".join(lp[i1:i2])))
        if j2 > j1:
            words.append(CompareWord(op="insert", text="".join(rp[j1:j2])))
    return _merge_words(words)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def _pair_block(left: Sequence[Paragraph], right: Sequence[Paragraph]) -> List[CompareOp]:
    """Lines up the paragraphs of one changed block: similar ones are paired as edits, the rest are deletions or insertions."""
    ops: List[CompareOp] = []

    def delete(p: Paragraph):
        ops.append(CompareOp(op="delete", left_text=p[0], left_page=p[1], words=[CompareWord(op="delete", text=p[0])]))

    def insert(p: Paragraph):
        ops.append(CompareOp(op="insert", right_text=p[0], right_page=p[1], words=[CompareWord(op="insert", text=p[0])]))

    def replace(a: Paragraph, b: Paragraph):
        ops.append(CompareOp(op="replace", left_text=a[0], right_text=b[0], left_page=a[1], right_page=b[1], words=word_diff(a[0], b[0])))

    if len(left) * len(right) > MAX_PAIRING_CELLS:
        for a, b in zip(left, right):
            replace(a, b)
        for p in left[len(right):]:
            delete(p)
        for p in right[len(left):]:
            insert(p)
        return ops

    j = 0
    for a in left:
        best, best_ratio = None, MIN_PAIR_RATIO
        for k in range(j, len(right)):
            ratio = _similarity(a[2], right[k][2])
            if ratio > best_ratio:
                best, best_ratio = k, ratio
        if best is None:
            delete(a)
            continue
        for k in range(j, best):
            insert(right[k])
        replace(a, right[best])
        j = best + 1
    for k in range(j, len(right)):
        insert(right[k])
    return ops


def diff_paragraphs(left: Sequence[Paragraph], right: Sequence[Paragraph]) -> List[CompareOp]:
    sm = SequenceMatcher(None, [p[2] for p in left], [p[2] for p in right], autojunk=False)
    ops: List[CompareOp] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for a, b in zip(left[i1:i2], right[j1:j2]):
                ops.append(CompareOp(op="equal", left_text=a[0], right_text=b[0], left_page=a[1], right_page=b[1]))
        else:
            ops.extend(_pair_block(left[i1:i2], right[j1:j2]))
    return ops


def summarize_pages(ops: Sequence[CompareOp]) -> List[ComparePageSummary]:
    table: Dict[Tuple[Optional[int], Optional[int]], ComparePageSummary] = {}
    for op in ops:
        key = (op.left_page, op.right_page)
        row = table.setdefault(key, ComparePageSummary(left_page=op.left_page, right_page=op.right_page))
        if op.op == "equal":
            row.unchanged += 1
        elif op.op == "insert":
            row.inserted += 1
        elif op.op == "delete":
            row.deleted += 1
        else:
            row.changed += 1
    return sorted(table.values(), key=lambda r: (r.right_page if r.right_page is not None else 10**9, r.left_page if r.left_page is not None else 10**9))


def compare_page_texts(left_pages: Sequence[Tuple[int, str]], right_pages: Sequence[Tuple[int, str]]):
    ops = diff_paragraphs(build_paragraphs(left_pages), build_paragraphs(right_pages))
    stats = CompareStats()
    for op in ops:
        setattr(stats, op.op, getattr(stats, op.op) + 1)
    return ops, stats, summarize_pages(ops)


async def _load_side(db: AsyncSession, version_id: UUID, user: Optional[User]):
    version = await db.get(DocumentVersion, version_id)
    doc = await db.get(Document, version.document_id) if version else None
    if version is None or not can_view_document(doc, user):
        raise HTTPException(status_code=404, detail="Document version not found")
    pages = (
        await db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number)
            .limit(MAX_PAGES_PER_SIDE)
        )
    ).scalars().all()
    texts = [(p.page_number, reader_text(p)) for p in pages]
    side = CompareSide(
        version_id=version.id,
        document_id=doc.id,
        reference_number=doc.reference_number,
        title=doc.title,
        version_number=version.version_number,
        language=version.language,
        page_count=version.page_count or len(texts),
        pages_compared=len(texts),
    )
    return side, texts


async def compare_versions(db: AsyncSession, left_id: UUID, right_id: UUID, user: Optional[User]) -> CompareResponse:
    import asyncio

    left_side, left_pages = await _load_side(db, left_id, user)
    right_side, right_pages = await _load_side(db, right_id, user)
    ops, stats, pages = await asyncio.to_thread(compare_page_texts, left_pages, right_pages)
    truncated = left_side.page_count > left_side.pages_compared or right_side.page_count > right_side.pages_compared
    return CompareResponse(left=left_side, right=right_side, truncated=truncated, stats=stats, pages=pages, ops=ops)
