"""Sorts circulars into subject categories (taxonomy.py) with the analysis model, many at a time.

Fully automatic: every circular gets at least one category ("Other" when nothing fits). New
circulars are sorted by `classify_pending`, which the live checker runs after each check and the
backlog script (`backend/scripts/classify_topics.py`) runs for the archive.

Input per circular: reference number, English and Bangla titles, department, the analysed subject
and summary when there is one, and the start of page 1. Short numeric ids are used in the prompt
so the model never has to copy a long id.
"""
from backend.app.core import gemini_http
import asyncio
import json
from typing import Dict, List, Optional, Sequence

import httpx
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.modules.analysis.models import DocumentAnalysis
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion
from backend.app.modules.documents.synthetic import synthetic_sql_condition
from backend.app.modules.extraction.vision import gemini_keys, is_dead_key_reply
from backend.app.modules.topics.models import DocumentTopic
from backend.app.modules.topics.taxonomy import CODES, TOPICS

BATCH_SIZE = 25
PAGE_START_CHARS = 700
MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = (
    "You sort Bangladesh Bank circulars into subject categories for bank compliance staff. "
    "A circular can belong to several categories; give every category whose subject the circular "
    "really deals with (usually 1 to 4), most important first. Use OTHER only when none fits. "
    "Use only the category codes given. Judge by what the circular is about, not by passing mentions.\n\n"
    "Categories (code: what belongs there):\n"
    + "\n".join(f"{t.code}: {t.hint}" for t in TOPICS)
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "results": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "n": {"type": "INTEGER"},
                    "topics": {"type": "ARRAY", "items": {"type": "STRING", "enum": CODES}},
                },
                "required": ["n", "topics"],
            },
        }
    },
    "required": ["results"],
}


def _summary_bits(analysis: Optional[DocumentAnalysis]) -> str:
    if not analysis:
        return ""
    payload = analysis.structured_payload or {}
    cls = payload.get("classification") or {}
    bits = [cls.get("subject") or "", cls.get("regulatory_topic") or ""]
    points = ((payload.get("executive_summary") or {}).get("summary_points") or [])[:3]
    bits += [p.get("text", "") for p in points if isinstance(p, dict)]
    if not points and analysis.executive_summary:
        bits.append(analysis.executive_summary[:400])
    return " | ".join(b for b in bits if b)


def describe(n: int, doc: Document, dept: str, page_text: str, analysis: Optional[DocumentAnalysis]) -> str:
    lines = [f"[{n}] {doc.reference_number or ''} ({dept or 'department unknown'})", f"Title: {doc.title}"]
    if doc.title_bn and doc.title_bn != doc.title:
        lines.append(f"Bangla title: {doc.title_bn}")
    s = _summary_bits(analysis)
    if s:
        lines.append(f"Subject: {s[:700]}")
    if page_text:
        lines.append("Page 1 starts: " + " ".join(page_text.split())[:PAGE_START_CHARS])
    return "\n".join(lines)


def parse_reply(text: str, count: int) -> Dict[int, List[str]]:
    """{n: [codes]} for the items the reply covered; unknown codes are dropped, repeats removed."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    out: Dict[int, List[str]] = {}
    for item in (data.get("results") or []) if isinstance(data, dict) else []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError, AttributeError):
            continue
        if not 1 <= n <= count:
            continue
        codes: List[str] = []
        for c in item.get("topics") or []:
            c = str(c).strip().upper()
            if c in CODES and c not in codes:
                codes.append(c)
        if len(codes) > 1 and "OTHER" in codes:
            codes.remove("OTHER")
        out[n] = codes[:5] or ["OTHER"]
    return out


class _KeyRing:
    def __init__(self, keys: Sequence[str]):
        self.keys = list(keys)
        self.i = 0

    def next(self) -> Optional[str]:
        if not self.keys:
            return None
        k = self.keys[self.i % len(self.keys)]
        self.i += 1
        return k

    def drop(self, key: str) -> None:
        if key in self.keys:
            self.keys.remove(key)


async def _ask_model(client: httpx.AsyncClient, ring: _KeyRing, prompt: str, tries: Optional[int] = None) -> Optional[str]:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA},
    }
    tries = tries or max(6, 2 * len(ring.keys))
    last = ""
    for attempt in range(tries):
        key = ring.next()
        if not key:
            return None
        try:
            r = await client.post(f"{gemini_http.models_url()}/{MODEL}:generateContent", json=body, headers=gemini_http.headers(key))
        except httpx.HTTPError as err:
            logger.warning(f"Category sorting: network error ({type(err).__name__}); trying again.")
            await asyncio.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, ValueError):
                continue
        if is_dead_key_reply(r.status_code, r.text):
            ring.drop(key)
            continue
        # Busy or out of quota on this key: rest a little and use the next key.
        last = f"HTTP {r.status_code}"
        await asyncio.sleep(min(60, 6 * (attempt + 1)))
    if last:
        logger.warning(f"Category sorting: no answer after {tries} tries (last reply {last}).")
    return None


async def _unsorted_documents(db: AsyncSession, limit: int) -> List[Document]:
    has_topic = exists(select(1).where(DocumentTopic.document_id == Document.id))
    rows = await db.execute(
        select(Document)
        .options(selectinload(Document.department))
        .where(~has_topic, ~synthetic_sql_condition(), Document.owner_user_id.is_(None))
        .order_by(Document.publication_date.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def _context(db: AsyncSession, docs: Sequence[Document]):
    version_ids = [d.current_version_id for d in docs if d.current_version_id]
    pages: Dict[str, str] = {}
    analyses: Dict[str, DocumentAnalysis] = {}
    if version_ids:
        for vid, text, raw in (await db.execute(
            select(DocumentPage.document_version_id, DocumentPage.cleaned_text, DocumentPage.raw_text)
            .where(DocumentPage.document_version_id.in_(version_ids), DocumentPage.page_number == 1)
        )).all():
            pages[str(vid)] = text or raw or ""
        for a in (await db.execute(
            select(DocumentAnalysis).where(DocumentAnalysis.document_version_id.in_(version_ids))
            .order_by(DocumentAnalysis.created_at)
        )).scalars().all():
            analyses[str(a.document_version_id)] = a  # latest wins
    return pages, analyses


async def classify_pending(db: AsyncSession, limit: int = 200, pause_seconds: float = 4.0,
                           client: Optional[httpx.AsyncClient] = None) -> int:
    """Sorts up to `limit` circulars that have no category yet. Returns how many were sorted."""
    ring = _KeyRing(gemini_keys())
    if not ring.keys:
        return 0
    docs = await _unsorted_documents(db, limit)
    if not docs:
        return 0
    own = client is None
    client = client or httpx.AsyncClient(timeout=90.0)
    done = 0
    try:
        for start in range(0, len(docs), BATCH_SIZE):
            batch = docs[start:start + BATCH_SIZE]
            pages, analyses = await _context(db, batch)
            prompt = "Sort these circulars. Reply with one result per number.\n\n" + "\n\n".join(
                describe(i + 1, d, d.department.code if d.department else "", pages.get(str(d.current_version_id), ""),
                         analyses.get(str(d.current_version_id)))
                for i, d in enumerate(batch)
            )
            reply = await _ask_model(client, ring, prompt)
            if reply is None:
                logger.warning("Category sorting stopped: no key answered. The rest are sorted on the next run.")
                break
            found = parse_reply(reply, len(batch))
            for i, d in enumerate(batch):
                for code in found.get(i + 1, []):
                    db.add(DocumentTopic(document_id=d.id, topic=code, source="AI"))
            await db.commit()
            done += len(found)
            if start + BATCH_SIZE < len(docs):
                await asyncio.sleep(pause_seconds)
    finally:
        if own:
            await client.aclose()
    if done:
        logger.info(f"Category sorting: {done} circulars sorted.")
    return done


async def topics_by_document(db: AsyncSession, document_ids: Sequence) -> Dict[str, List[str]]:
    if not document_ids:
        return {}
    out: Dict[str, List[str]] = {}
    for doc_id, topic in (await db.execute(
        select(DocumentTopic.document_id, DocumentTopic.topic).where(DocumentTopic.document_id.in_(list(document_ids)))
    )).all():
        out.setdefault(str(doc_id), []).append(topic)
    order = {c: i for i, c in enumerate(CODES)}
    return {k: sorted(v, key=lambda c: order.get(c, 99)) for k, v in out.items()}
