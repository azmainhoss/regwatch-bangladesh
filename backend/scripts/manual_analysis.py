"""Analyse archive circulars by hand (outside the app) and load the answers through the app's normal checks.

Why: the build has no paid model, so the analysis of the chosen archive circulars is written in a coding
session instead. The session sees exactly what a model would see (the page text with sentence IDs) and
answers in exactly the app's JSON format. Loading runs the same pipeline as a live model: sentence IDs
become exact quotes, every point is checked by code, and points that fail are held for a person.

Chosen circulars ("target"): shared library, issued on or after 2024-11-14, or any Master Circular.
Order: newest first. Very long circulars (over --max-chars characters of text) wait for a later phase.

Work folder: research/archive/data/manual_analysis/ (git-ignored)
    INSTRUCTIONS.md       the rules (built from the app's own prompt, so they never drift)
    inbox/<doc_id>.txt    a circular handed out for analysis: its pages with sentence IDs
    answers/<doc_id>.json the analysis written for it
    done/<doc_id>.json    answers that were loaded
    log.jsonl             one line per load
    REDO.txt              circulars handed out or analysed while some pages were unread (see mark-redo)
    done/replaced/        old answers set aside when a circular is analysed again

A REDO.txt line whose reason starts with "approved" (mark-redo --approved) is a person's go-ahead to analyse
an already analysed circular again: once all its pages are read, export writes its text out again and
removes its old answer from the work repo (prints "Redo: <doc> | <reference>"); the new answer replaces the
old analysis when it is loaded. Until then its old answer and inbox file stay as they are.

A circular is handed out only when every page has usable text: none still waiting to be read, and none
whose reading failed or whose text is damaged (a short but clean page is fine).

Usage (from the repo root, with the repo .venv):
    .venv/Scripts/python.exe backend/scripts/manual_analysis.py status
    .venv/Scripts/python.exe backend/scripts/manual_analysis.py next --n 10
    .venv/Scripts/python.exe backend/scripts/manual_analysis.py check            # all files in answers/
    .venv/Scripts/python.exe backend/scripts/manual_analysis.py load             # check, then load all answers/
    .venv/Scripts/python.exe backend/scripts/manual_analysis.py mark-redo <doc_id> ... --reason "..."
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the database path in .env is relative to the repo root

import backend.app.database.models  # noqa: E402,F401  (registers all models)
from backend.app.core.config import settings  # noqa: E402
from backend.app.modules.analysis import prompts  # noqa: E402
from backend.app.modules.analysis.providers.base import BaseAIProvider, LLMResponse  # noqa: E402
from backend.app.modules.analysis.sentences import SentenceIndex  # noqa: E402
from backend.app.modules.extraction.quality import ExtractionQualityAssessor, text_layer_looks_damaged  # noqa: E402

WORK = ROOT / "research" / "archive" / "data" / "manual_analysis"
INBOX, ANSWERS, DONE = WORK / "inbox", WORK / "answers", WORK / "done"
LOG = WORK / "log.jsonl"
REDO = WORK / "REDO.txt"
CUTOFF = "2024-11-14"
MODEL_NAME = "manual-analysis-v1"

OBLIGATION_TYPES = {"MANDATORY", "CONDITIONAL", "PROHIBITION", "PERMISSION", "RECOMMENDATION", "REPORTING",
                    "RECORD_RETENTION", "APPROVAL", "DISCLOSURE"}
RELATIONSHIP_TYPES = {"AMENDS", "REPEALS", "SUPERSEDES", "REPLACES", "CLARIFIES", "REFERENCES", "IMPLEMENTS", "RELATED_TO"}
ID_RE = re.compile(r"^p\d+\.s\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _db_path() -> str:
    url = settings.SYNC_DATABASE_URL
    path = url.split("///", 1)[1]
    return str((ROOT / path).resolve()) if not os.path.isabs(path) else path


def _ro() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)


TARGET_SQL = f"""
select d.id, d.current_version_id, d.title, d.reference_number, d.publication_date,
  (select count(*) from document_pages p where p.document_version_id = d.current_version_id) as pages,
  (select coalesce(sum(length(coalesce(p.cleaned_text, p.raw_text, ''))), 0) from document_pages p
     where p.document_version_id = d.current_version_id) as chars,
  (select count(*) from document_pages p where p.document_version_id = d.current_version_id
     and p.quality_status = 'PENDING_VISION' and coalesce(p.is_human_corrected, 0) = 0) as waiting,
  (select count(*) from document_analyses a where a.document_version_id = d.current_version_id) as analyses
from documents d
where coalesce(d.is_synthetic_fixture, 0) = 0 and d.owner_user_id is null and d.current_version_id is not null
  and d.source_url like '%bb.org.bd/%'
  and (d.publication_date >= '{CUTOFF}' or lower(d.title) like '%master circular%')
order by d.publication_date desc, d.title
"""


def _hex(value: Any) -> str:
    return str(value).replace("-", "").lower()


STUCK_SQL = """
select p.document_version_id, coalesce(nullif(p.cleaned_text, ''), p.raw_text, '')
from document_pages p
where p.quality_status in ('NEEDS_HUMAN_REVIEW', 'READ_FAILED') and coalesce(p.is_human_corrected, 0) = 0
"""


def page_text_unusable(text: str) -> bool:
    """A page that was not read (or an old page flagged for review) has no usable text when it is
    empty or its text looks damaged."""
    text = (text or "").strip()
    if not text:
        return True
    return text_layer_looks_damaged(ExtractionQualityAssessor.assess_page(1, text, "TEXT_LAYER"))


def targets() -> List[Dict[str, Any]]:
    """The chosen circulars. `unread` counts pages without usable text yet: still waiting to be read,
    or with a person and empty or damaged."""
    with _ro() as c:
        cols = ["id", "version_id", "title", "reference", "date", "pages", "chars", "waiting", "analyses"]
        rows = [dict(zip(cols, r)) for r in c.execute(TARGET_SQL)]
        stuck: Dict[str, int] = {}
        for version_id, text in c.execute(STUCK_SQL):
            if page_text_unusable(text):
                stuck[_hex(version_id)] = stuck.get(_hex(version_id), 0) + 1
    for r in rows:
        r["stuck"] = stuck.get(_hex(r["version_id"]), 0)
        r["unread"] = (r["waiting"] or 0) + r["stuck"]
    return rows


def read_redo() -> Dict[str, str]:
    """REDO.txt: one `<doc_id> | reason` line per circular to analyse again once its pages are all read."""
    if not REDO.exists():
        return {}
    out: Dict[str, str] = {}
    for line in REDO.read_text(encoding="utf-8").splitlines():
        key, _, reason = line.partition("|")
        if key.strip():
            out[key.strip()] = reason.strip()
    return out


def redo_approved(items: Dict[str, str]) -> set:
    """REDO.txt keys a person approved for a fresh analysis (reason starts with "approved")."""
    return {k for k, v in items.items() if v.lower().startswith("approved")}


def write_redo(items: Dict[str, str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    REDO.write_text("".join(f"{k} | {v}\n" for k, v in items.items()), encoding="utf-8")


def _file_key(doc_id: Any) -> str:
    return str(UUID(_hex(doc_id)))


def write_instructions() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    user_rules = prompts.USER_ANALYSIS_PROMPT_TEMPLATE.replace(
        "{document_pages_text}", "(the circular: see the inbox file)").replace("{{", "{").replace("}}", "}")
    text = f"""# Manual analysis: rules

Prompt version {prompts.PROMPT_VERSION}. Built from backend/app/modules/analysis/prompts.py; do not edit by hand.

For each file in inbox/: read the whole circular, write answers/<same name>.json in the JSON shape below,
then run `manual_analysis.py check` and fix every ERROR. Work one circular at a time. Only sentence IDs that
appear in the inbox file may be used. Every field you fill must be stated in the sentences you give for it.
Bangla text: give English in "title", "requirement_description", summary and change lines.

## System rules
{prompts.SYSTEM_REGULATORY_PROMPT}

## Task rules and JSON shape
{user_rules}
"""
    (WORK / "INSTRUCTIONS.md").write_text(text, encoding="utf-8")


async def _load_pages(version_id: str) -> List[Dict[str, Any]]:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.analysis.service import pages_payload_for
    from backend.app.modules.documents.models import DocumentVersion
    async with AsyncSessionLocal() as db:
        version = (await db.execute(select(DocumentVersion).options(selectinload(DocumentVersion.pages))
                                    .where(DocumentVersion.id == UUID(_hex(version_id))))).scalar_one()
        return pages_payload_for(version)


def cmd_status(args) -> None:
    rows = targets()
    ready = [r for r in rows if not r["unread"]]
    done = [r for r in rows if r["analyses"]]
    big = [r for r in ready if r["chars"] > args.max_chars and not r["analyses"]]
    print(f"Chosen circulars: {len(rows)}")
    print(f"  analysed: {len(done)}")
    print(f"  ready, not analysed: {len(ready) - len([r for r in ready if r['analyses']])} "
          f"(of which {len(big)} are long, over {args.max_chars} characters)")
    print(f"  pages still being read: {len([r for r in rows if r['waiting']])} circulars; "
          f"pages with a person and no usable text: {len([r for r in rows if r['stuck']])} circulars")
    print(f"  to analyse again once read (REDO.txt): {len(read_redo())}")
    print(f"  handed out (inbox): {len(list(INBOX.glob('*.txt'))) if INBOX.exists() else 0}, "
          f"answers waiting to load: {len(list(ANSWERS.glob('*.json'))) if ANSWERS.exists() else 0}")
    left = [r for r in ready if not r["analyses"] and r["chars"] <= args.max_chars]
    print(f"  short ones left: {len(left)}, about {sum(r['chars'] for r in left):,} characters")


async def cmd_next(args) -> None:
    write_instructions()
    INBOX.mkdir(parents=True, exist_ok=True)
    ANSWERS.mkdir(parents=True, exist_ok=True)
    taken = {p.stem for p in INBOX.glob("*.txt")} | {p.stem for p in ANSWERS.glob("*.json")}
    picked = []
    for r in targets():
        key = _file_key(r["id"])
        if r["unread"] or r["analyses"] or key in taken:
            continue
        if (r["chars"] > args.max_chars) != args.long:
            continue
        picked.append(r)
        if len(picked) >= args.n:
            break
    for r in picked:
        pages = await _load_pages(r["version_id"])
        index = SentenceIndex.build(pages)
        header = (f"# {r['title']}\n# reference: {r['reference'] or '-'} | listed date: {r['date']} | "
                  f"pages: {r['pages']} | document: {_file_key(r['id'])}\n\n")
        (INBOX / f"{_file_key(r['id'])}.txt").write_text(header + index.render_for_prompt(), encoding="utf-8")
        print(f"{_file_key(r['id'])}  {r['date']}  {r['pages']:>3}p  {r['chars']:>7}ch  {r['title'][:90]}")
    print(f"Handed out {len(picked)}. Rules: {WORK / 'INSTRUCTIONS.md'}")


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


def _version_for(doc_key: str) -> Optional[str]:
    with _ro() as c:
        row = c.execute("select current_version_id from documents where replace(lower(id),'-','') = ?",
                        (_hex(doc_key),)).fetchone()
    return row[0] if row else None


async def _check_file(path: Path) -> List[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"ERROR not valid JSON: {e}"]
    version = _version_for(path.stem)
    if not version:
        return ["ERROR no such document"]
    index = SentenceIndex.build(await _load_pages(version))
    return check_answer(payload, index)


async def _dispose() -> None:
    from backend.app.database.session import async_engine
    await async_engine.dispose()


async def cmd_check(args) -> int:
    files = [Path(f) for f in args.files] or sorted(ANSWERS.glob("*.json"))
    bad = 0
    for f in files:
        errs = await _check_file(f)
        bad += bool(errs)
        print(f"{f.stem}: {'OK' if not errs else f'{len(errs)} problem(s)'}")
        for e in errs[:40]:
            print("   ", e)
    print(f"{len(files) - bad} of {len(files)} pass")
    return 1 if bad else 0


class AnswerFileProvider(BaseAIProvider):
    """Returns an answer written in advance, as if a model had just given it."""

    def __init__(self, payload: Dict[str, Any], raw: str):
        super().__init__(MODEL_NAME)
        self.payload, self.raw = payload, raw

    async def generate_structured_json(self, system_prompt, user_prompt, json_schema=None, temperature=0.0):
        return LLMResponse(raw_content=self.raw, parsed_json=json.loads(self.raw), model_name=MODEL_NAME, success=True)


async def _load_one(path: Path) -> Dict[str, Any]:
    from sqlalchemy import func, select
    from backend.app.database.session import AsyncSessionLocal
    from backend.app.modules.analysis.models import AnalysisClaim
    from backend.app.modules.analysis.service import AnalysisService
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    async with AsyncSessionLocal() as db:
        analysis = await AnalysisService.analyze_document_version(
            db, UUID(_hex(path.stem)), provider=AnswerFileProvider(payload, raw))
        rows = (await db.execute(select(AnalysisClaim.check_status, func.count())
                                 .where(AnalysisClaim.analysis_id == analysis.id)
                                 .group_by(AnalysisClaim.check_status))).all()
        return {k: n for k, n in rows}


async def cmd_load(args) -> int:
    DONE.mkdir(parents=True, exist_ok=True)
    files = [Path(f) for f in args.files] or sorted(ANSWERS.glob("*.json"))
    failed = 0
    for f in files:
        errs = await _check_file(f)
        if errs:
            failed += 1
            print(f"{f.stem}: not loaded, {len(errs)} problem(s); run check")
            continue
        try:
            counts = await _load_one(f)
        except Exception as e:
            failed += 1
            print(f"{f.stem}: load failed: {e}")
            continue
        shutil.move(str(f), DONE / f.name)
        redo = read_redo()
        if f.stem in redo_approved(redo):
            redo.pop(f.stem)  # the fresh analysis is in: nothing left to redo
            write_redo(redo)
        (INBOX / f"{f.stem}.txt").unlink(missing_ok=True)
        with LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"doc": f.stem, "at": datetime.now(timezone.utc).isoformat(), "points": counts}) + "\n")
        print(f"{f.stem}: loaded, points {counts}")
    print(f"Loaded {len(files) - failed} of {len(files)}")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# Shared work repo (cloud runs). The cloud has no database, so it gets each circular's text in a git repo,
# writes answers there, and this PC loads them. Layout of the repo:
#   RUNBOOK.md, INSTRUCTIONS.md, check.py, RUNLOG.md
#   inbox/<doc>.txt        short circulars still to analyse
#   inbox_long/<doc>.txt   long circulars, done after the short ones
#   answers/<doc>.json     written by the cloud runs
# ---------------------------------------------------------------------------
_CHECK_PY_HEAD = '''"""Checks answers/<doc>.json against inbox/<doc>.txt (standard library only).

Usage: python check.py                 # every file in answers/
       python check.py answers/X.json  # one file
Generated from the app's own checker; do not edit by hand.
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, List

HERE = Path(__file__).resolve().parent
OBLIGATION_TYPES = {obligation_types!r}
RELATIONSHIP_TYPES = {relationship_types!r}
ID_RE = re.compile(r"^p\\d+\\.s\\d+$")
DATE_RE = re.compile(r"^\\d{{4}}-\\d{{2}}-\\d{{2}}$")


class _Index:
    def __init__(self, text):
        self.sentences = set(re.findall(r"^\\[(p\\d+\\.s\\d+)\\]", text, flags=re.M))


'''

_CHECK_PY_TAIL = '''

def main():
    files = [Path(a) for a in sys.argv[1:]] or sorted((HERE / "answers").glob("*.json"))
    bad = 0
    for f in files:
        src = None
        for folder in ("inbox", "inbox_long"):
            if (HERE / folder / (f.stem + ".txt")).exists():
                src = HERE / folder / (f.stem + ".txt")
        if src is None:
            errs = ["ERROR no inbox file for this answer"]
        else:
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
                errs = check_answer(payload, _Index(src.read_text(encoding="utf-8")))
            except Exception as e:
                errs = ["ERROR not valid JSON: %s" % e]
        bad += bool(errs)
        print("%s: %s" % (f.stem, "OK" if not errs else "%d problem(s)" % len(errs)))
        for e in errs[:40]:
            print("    " + e)
    print("%d of %d pass" % (len(files) - bad, len(files)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _write_check_py(repo: Path) -> None:
    import inspect
    head = _CHECK_PY_HEAD.format(obligation_types=sorted(OBLIGATION_TYPES), relationship_types=sorted(RELATIONSHIP_TYPES))
    head = head.replace("OBLIGATION_TYPES = [", "OBLIGATION_TYPES = set([").replace("RELATIONSHIP_TYPES = [", "RELATIONSHIP_TYPES = set([")
    head = re.sub(r"(_TYPES = set\(\[[^\]]*\])", r"\1)", head)
    body = inspect.getsource(check_answer).replace("index: SentenceIndex", "index").replace(" -> List[str]", "")
    body = body.replace("errs: List[str] = []", "errs = []").replace("payload: Any", "payload")
    (repo / "check.py").write_text(head + body + _CHECK_PY_TAIL, encoding="utf-8")


async def cmd_export(args) -> None:
    """Writes every chosen circular that is ready and not yet analysed into the work repo."""
    repo = Path(args.repo)
    write_instructions()
    for folder in ("inbox", "inbox_long", "answers"):
        (repo / folder).mkdir(parents=True, exist_ok=True)
    rules = (WORK / "INSTRUCTIONS.md").read_text(encoding="utf-8").replace(
        "then run `manual_analysis.py check`", "then run `python check.py answers/<name>.json`")
    (repo / "INSTRUCTIONS.md").write_text(rules, encoding="utf-8")
    _write_check_py(repo)
    have = ({p.stem for p in ANSWERS.glob("*.json")} | {p.stem for p in DONE.glob("*.json")}
            | {p.stem for p in (repo / "answers").glob("*.json")} | {p.stem for p in INBOX.glob("*.txt")})
    added = removed = held = pulled = 0
    redo = read_redo()
    approved = redo_approved(redo)
    redo_ready: List[str] = []
    redo_now: List[str] = []
    repo_answers = {p.stem for p in (repo / "answers").glob("*.json")}
    for r in targets():
        key = _file_key(r["id"])
        if key in approved:
            # A person approved analysing it again. Wait until every page is read; then write its text out
            # again and drop the old answer so its lane picks it up. Never taken off the queue meanwhile.
            if not r["unread"] and (key in repo_answers or r["analyses"]):
                header = (f"# {r['title']}\n# reference: {r['reference'] or '-'} | listed date: {r['date']} | "
                          f"pages: {r['pages']} | document: {key}\n\n")
                fresh = header + SentenceIndex.build(await _load_pages(r["version_id"])).render_for_prompt()
                folder = "inbox_long" if r["chars"] > args.max_chars else "inbox"
                old = repo / folder / f"{key}.txt"
                if not old.exists() or old.read_text(encoding="utf-8") != fresh:
                    for other in ("inbox", "inbox_long"):
                        (repo / other / f"{key}.txt").unlink(missing_ok=True)
                    (repo / folder / f"{key}.txt").write_text(fresh, encoding="utf-8")
                    (repo / "answers" / f"{key}.json").unlink(missing_ok=True)
                    if (DONE / f"{key}.json").exists():
                        (DONE / "replaced").mkdir(parents=True, exist_ok=True)
                        shutil.move(str(DONE / f"{key}.json"), DONE / "replaced" / f"{key}.json")
                    redo_now.append(f"Redo: {key} | {r['reference'] or r['title']}")
            continue
        if (r["analyses"] or key in have) and key not in repo_answers:
            # Done on this PC (or handed out here): take it off the cloud's list.
            for folder in ("inbox", "inbox_long"):
                stale = repo / folder / f"{key}.txt"
                if stale.exists():
                    stale.unlink()
                    removed += 1
        if r["unread"]:
            # Some pages have no usable text yet: hold it back, and take it off the cloud's list if nobody
            # answered it yet, so it is never analysed with pages missing. It goes out again once read.
            if not r["analyses"] and key not in have:
                held += 1
            if key not in repo_answers:
                for folder in ("inbox", "inbox_long"):
                    early = repo / folder / f"{key}.txt"
                    if early.exists():
                        early.unlink()
                        pulled += 1
            continue
        if r["analyses"] or key in have:
            if key in redo:
                redo_ready.append(key)  # read now, but already analysed: replacing that is a person's call
            continue
        folder = repo / ("inbox_long" if r["chars"] > args.max_chars else "inbox")
        out = folder / f"{key}.txt"
        if out.exists():
            continue
        index = SentenceIndex.build(await _load_pages(r["version_id"]))
        header = (f"# {r['title']}\n# reference: {r['reference'] or '-'} | listed date: {r['date']} | "
                  f"pages: {r['pages']} | document: {key}\n\n")
        out.write_text(header + index.render_for_prompt(), encoding="utf-8")
        added += 1
        redo.pop(key, None)  # handed out again with every page read: nothing left to redo
    if REDO.exists() or redo:
        write_redo(redo)
    # Work order: short circulars newest first, then the long ones newest first.
    order = [_file_key(r["id"]) for r in targets()]
    short = [k for k in order if (repo / "inbox" / f"{k}.txt").exists()]
    long_ = [k for k in order if (repo / "inbox_long" / f"{k}.txt").exists()]
    (repo / "QUEUE.txt").write_text(
        "".join(f"inbox/{k}.txt\n" for k in short) + "".join(f"inbox_long/{k}.txt\n" for k in long_), encoding="utf-8")
    print(f"Exported {added} new circular(s), removed {removed} done here, held back {held} with unread pages "
          f"(took {pulled} off the queue), to {repo}; queue has {len(short)} short and {len(long_)} long")
    for line in redo_now:
        print(line)
    if redo_ready:
        print(f"{len(redo_ready)} circular(s) in REDO.txt are now fully read but already analysed; "
              f"analysing them again replaces the old answer, so a person decides: {', '.join(redo_ready)}")


def cmd_mark_redo(args) -> None:
    """Notes circulars to analyse again once all their pages are read (they went out with pages unread)."""
    items = read_redo()
    reason = args.reason
    if getattr(args, "approved", False) and not reason.lower().startswith("approved"):
        reason = f"approved: {reason}"
    for key in args.docs:
        items[_file_key(key)] = reason
    write_redo(items)
    print(f"REDO.txt now lists {len(items)} circular(s).")


async def cmd_pull(args) -> int:
    """Loads answers from the work repo that this PC has not loaded yet."""
    repo = Path(args.repo)
    ANSWERS.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in DONE.glob("*.json")}
    new = []
    for f in sorted((repo / "answers").glob("*.json")):
        if f.stem not in done:
            shutil.copy2(f, ANSWERS / f.name)
            new.append(ANSWERS / f.name)
    if not new:
        print("No new answers.")
        return 0
    args.files = [str(p) for p in new]
    return await cmd_load(args)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "next"):
        p = sub.add_parser(name)
        p.add_argument("--max-chars", type=int, default=60000, help="longer circulars wait for the long phase")
        if name == "next":
            p.add_argument("--n", type=int, default=5)
            p.add_argument("--long", action="store_true", help="hand out the long circulars instead")
    for name in ("check", "load"):
        sub.add_parser(name).add_argument("files", nargs="*")
    p = sub.add_parser("export", help="write ready circulars into the shared work repo")
    p.add_argument("--repo", required=True)
    p.add_argument("--max-chars", type=int, default=60000)
    sub.add_parser("pull", help="load new answers from the shared work repo").add_argument("--repo", required=True)
    p = sub.add_parser("mark-redo", help="list circulars to analyse again once all their pages are read")
    p.add_argument("docs", nargs="+")
    p.add_argument("--reason", default="handed out while some pages were unread")
    p.add_argument("--approved", action="store_true", help="a person approved analysing it again once read")
    args = ap.parse_args()
    if args.cmd == "status":
        cmd_status(args)
        return 0
    if args.cmd == "mark-redo":
        cmd_mark_redo(args)
        return 0
    fn = {"next": cmd_next, "check": cmd_check, "load": cmd_load, "export": cmd_export, "pull": cmd_pull}[args.cmd]

    async def run() -> int:
        try:
            return (await fn(args)) or 0
        finally:
            await _dispose()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
