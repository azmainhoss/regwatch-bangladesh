"""Step 2 of the scorer: run one candidate (model + prompt) on the circulars of a split.

For each circular: the saved inputs are loaded into a throwaway database through the app's own models, and
the app's own analysis service builds, code-checks and routes the claims. The model's raw answer is cached,
so a re-run with the same model, prompt and inputs makes no model call.

Usage (repo root):
    .venv\\Scripts\\python.exe research\\scoring\\run_candidate.py --candidate gemini_flash_v3 --split dev
    ... --rows 2450,1426           only these circulars
    ... --force                    ask the model again even when an answer is saved
    ... --rescore-only             never call a model; rebuild claims and checks from the saved answers
    ... --batch                    paid candidates: write the vendor's batch request file (calls nothing)
    ... --batch --submit --yes-spend    send it (OpenAI-style endpoints only; prints the estimate first)
    ... --collect [results.jsonl]  read a finished batch into the cache
"""
import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import common
import quota
from common import ScorerError

common.point_app_at_scratch()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

import backend.app.database.models  # noqa: E402,F401
from backend.app.database.base import Base  # noqa: E402
from backend.app.modules.analysis import pipeline as pipeline_mod  # noqa: E402
from backend.app.modules.analysis import service as service_mod  # noqa: E402
from backend.app.modules.analysis.models import AnalysisClaim, DocumentAnalysis  # noqa: E402
from backend.app.modules.analysis.sentences import SentenceIndex  # noqa: E402
from backend.app.modules.claims import checks as claims_checks  # noqa: E402
from backend.app.modules.claims import reading as claims_reading  # noqa: E402
from backend.app.modules.claims import status as claim_status  # noqa: E402
from backend.app.modules.documents.models import Document, DocumentPage, DocumentVersion  # noqa: E402
from backend.app.modules.institutions.models import Institution  # noqa: E402
from provider_cache import CachingProvider  # noqa: E402

common.assert_scratch_database()
common.quiet_app_logs()

STATUS_OK = "OK"
STATUS_EMPTY = "EMPTY_ANSWER"
STATUS_ERROR = "ERROR"
STATUS_NOT_READY = "NOT_READY"
STATUS_NOT_CACHED = "NOT_CACHED"


class RunStopped(Exception):
    """The run cannot go on (free quota used up, key refused). Rows already done are kept."""


def say(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Prompt variants
# ---------------------------------------------------------------------------
@dataclass
class PromptVariant:
    system: str
    user_template: str
    version: str


def load_prompt(cand: common.Candidate) -> Optional[PromptVariant]:
    """None for the app's own prompt. A variant file has a '=== SYSTEM ===' part and a '=== USER ===' part.

    The user part is a Python format string like the app's: it must contain {document_pages_text}, and a literal
    brace of the JSON example is written {{ or }}. The placeholder {entity_names} is filled in with the app's entity list.
    """
    if cand.prompt in ("", "app"):
        return None
    p = Path(cand.prompt)
    if not p.is_absolute() and not p.exists():
        p = common.CANDIDATES_DIR / cand.prompt
    if not p.exists():
        raise ScorerError(f"Prompt file not found: {cand.prompt}")
    text = p.read_text(encoding="utf-8")
    if "=== SYSTEM ===" not in text or "=== USER ===" not in text:
        raise ScorerError("A prompt file needs a '=== SYSTEM ===' part and a '=== USER ===' part.")
    system = text.split("=== SYSTEM ===", 1)[1].split("=== USER ===", 1)[0].strip()
    user = text.split("=== USER ===", 1)[1].strip()
    if "{document_pages_text}" not in user:
        raise ScorerError("The USER part of a prompt file must contain {document_pages_text}.")
    from backend.app.modules.claims.wording import entity_names_for_prompt
    names = entity_names_for_prompt()
    return PromptVariant(system.replace("{entity_names}", names), user.replace("{entity_names}", names), f"variant:{p.stem}")


@contextlib.contextmanager
def app_patched(provider: CachingProvider, variant: Optional[PromptVariant]):
    """Swaps in the caching provider and the prompt variant, and switches the second reading of quotes off
    (scorer spec 2: reading checks are not run here). Everything is put back afterwards."""
    saved = {
        "get_ai_provider": service_mod.get_ai_provider,
        "system": pipeline_mod.SYSTEM_REGULATORY_PROMPT,
        "user": pipeline_mod.USER_ANALYSIS_PROMPT_TEMPLATE,
        "version": pipeline_mod.PROMPT_VERSION,
        "needs_reading": claims_reading.needs_reading,
        "needs_reading_check": claims_checks.PageInfo.needs_reading_check,
    }
    service_mod.get_ai_provider = lambda name=None: provider
    if variant:
        pipeline_mod.SYSTEM_REGULATORY_PROMPT = variant.system
        pipeline_mod.USER_ANALYSIS_PROMPT_TEMPLATE = variant.user_template
        pipeline_mod.PROMPT_VERSION = variant.version
    claims_reading.needs_reading = lambda page: False
    claims_checks.PageInfo.needs_reading_check = property(lambda self: False)
    try:
        yield
    finally:
        service_mod.get_ai_provider = saved["get_ai_provider"]
        pipeline_mod.SYSTEM_REGULATORY_PROMPT = saved["system"]
        pipeline_mod.USER_ANALYSIS_PROMPT_TEMPLATE = saved["user"]
        pipeline_mod.PROMPT_VERSION = saved["version"]
        claims_reading.needs_reading = saved["needs_reading"]
        claims_checks.PageInfo.needs_reading_check = saved["needs_reading_check"]


# ---------------------------------------------------------------------------
# Inputs and the throwaway database
# ---------------------------------------------------------------------------
def load_inputs(row: common.RowInfo) -> Optional[List[Dict[str, Any]]]:
    """The saved pages of the analysed file, in page order; None when any is missing."""
    out = []
    for ref in row.pages_of(row.main_stem):
        f = common.inputs_dir() / f"{ref.page_id}.json"
        if not f.exists():
            return None
        out.append(common.read_json(f))
    return out


def inputs_hash(pages: List[Dict[str, Any]]) -> str:
    return common.sha("\n".join(f"{p['page_id']}|{p.get('method')}|{p.get('cleaned_text') or ''}" for p in pages))


def reference_number(row: common.RowInfo) -> str:
    """As the archive import writes it: the reference from the listing title plus the year."""
    ref = row.title.split(":")[0].strip()
    year = (row.date or "")[:4]
    return f"{ref}/{year}" if year else ref


async def build_scratch(db_path: Path, row: common.RowInfo, pages: List[Dict[str, Any]]):
    """One document, one version, its pages, in a fresh database."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        inst = Institution(code="BB", name="Bangladesh Bank", is_active=True)
        db.add(inst)
        await db.flush()
        try:
            published = date.fromisoformat(row.date)
        except ValueError:
            published = date(2000, 1, 1)
        doc = Document(
            institution_id=inst.id, reference_number=reference_number(row), title=row.title or f"Circular {row.row}",
            document_type="CIRCULAR", publication_date=published, publication_status="EXTRACTED",
        )
        db.add(doc)
        await db.flush()
        version = DocumentVersion(
            document_id=doc.id, version_number=1, file_sha256=common.sha(row.main_stem), file_size_bytes=0,
            storage_path="", page_count=len(pages), language="en", status="CURRENT",
        )
        db.add(version)
        await db.flush()
        for p in pages:
            db.add(DocumentPage(
                document_version_id=version.id, page_number=int(p["page"]), raw_text=p.get("text") or "",
                cleaned_text=p.get("cleaned_text"), extraction_method=p.get("method") or "TEXT_LAYER",
                has_tables=bool(p.get("has_tables")), extracted_tables=[], quality_status=p.get("quality_status") or "SUCCESS_NATIVE",
                quality_score=float(p.get("quality_score") or 1.0), line_boxes=p.get("line_boxes"),
                layout_hierarchy={}, is_human_corrected=False,
            ))
        doc.current_version_id = version.id
        await db.commit()
        doc_id = doc.id
    return engine, factory, doc_id


# ---------------------------------------------------------------------------
# Claim records for the output file
# ---------------------------------------------------------------------------
def _page_id(stem: str, page_number: int) -> str:
    return f"{stem}_p{page_number}"


def claim_record(c: AnalysisClaim, index: SentenceIndex, stem: str) -> Dict[str, Any]:
    ev = c.evidence or {}
    span = index.resolve(ev.get("quote") or [])
    fragments = []
    if span.ok:
        fragments = [{"page_id": _page_id(stem, f["page_number"]), "text": f["text"], "sentence_ids": f["sentence_ids"]}
                     for f in span.fragments]
    ev_pages = []
    for ids in ev.values():
        for sid in ids or []:
            s = index.sentences.get(sid)
            if s is not None:
                pid = _page_id(stem, s.page_number)
                if pid not in ev_pages:
                    ev_pages.append(pid)
    return {
        "kind": c.kind,
        "order": c.order_index,
        "fields": c.fields or {},
        "check_status": c.check_status,
        "review_queue": c.review_queue,
        "high_stakes": bool(c.is_high_stakes),
        "shown": bool(claim_status.is_shown(c)),
        "quote": " … ".join(f["text"] for f in fragments),
        "fragments": fragments,
        "evidence_pages": ev_pages,
        "evidence_ids": ev,
        "quote_state": c.verification_status,
        "checks": c.checks or [],
    }


# ---------------------------------------------------------------------------
# One circular
# ---------------------------------------------------------------------------
async def run_row(row: common.RowInfo, cand: common.Candidate, mode: str, force: bool, allow_spend: bool = False,
                  variant: Optional[PromptVariant] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "row": row.row, "split": row.split, "candidate": cand.name, "model": cand.model, "unit": row.main_stem,
        "status": STATUS_OK, "error": None, "claims": [], "reading_checks": "not_run",
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    pages = load_inputs(row)
    if pages is None:
        result.update(status=STATUS_NOT_READY, error="Some pages of this circular are not read yet.")
        return result
    result["inputs_hash"] = inputs_hash(pages)
    unit = f"{row.row}_{row.main_stem}"
    provider = CachingProvider(cand, unit, mode=mode, force=force, allow_spend=allow_spend)
    work = common.SCORING_ROOT / "work"
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / f"row_{row.row}_{os.getpid()}.db"
    engine = None
    started = time.time()
    try:
        engine, factory, doc_id = await build_scratch(db_path, row, pages)
        async with factory() as db:
            try:
                with app_patched(provider, variant):
                    await service_mod.AnalysisService.analyze_document_version(db, doc_id)
            except (RuntimeError, ValueError) as e:
                if provider.stop_reason:
                    raise RunStopped(provider.stop_reason)
                if provider.miss:
                    result.update(status=STATUS_NOT_CACHED, error="No saved answer for this request.")
                elif provider.last_kind == "EMPTY":
                    result.update(status=STATUS_EMPTY, error="The model's answer was empty.")
                else:
                    result.update(status=STATUS_ERROR, error=str(e)[:500])
                _fill_call_info(result, provider)
                return result
            analysis = (await db.execute(select(DocumentAnalysis).order_by(DocumentAnalysis.created_at.desc()))).scalars().first()
            claim_rows = (await db.execute(
                select(AnalysisClaim).where(AnalysisClaim.analysis_id == analysis.id).order_by(AnalysisClaim.order_index)
            )).scalars().all()
            version = (await db.execute(
                select(DocumentVersion).options(selectinload(DocumentVersion.pages))
            )).scalars().first()
            index = SentenceIndex.build(service_mod.pages_payload_for(version))
            doc = await db.get(Document, doc_id)
            result["claims"] = [claim_record(c, index, row.main_stem) for c in claim_rows]
            result["doc_status"] = doc.publication_status
            result["claim_counts"] = claim_status.counts(claim_rows)
            result["prompt_version"] = analysis.prompt_version
            if not result["claims"]:
                result.update(status=STATUS_EMPTY, error="The analysis gave no claims at all.")
    finally:
        if engine is not None:
            await engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            with contextlib.suppress(OSError):
                Path(str(db_path) + suffix).unlink()
    _fill_call_info(result, provider)
    result["seconds"] = round(time.time() - started, 1)
    return result


def _fill_call_info(result: Dict[str, Any], provider: CachingProvider) -> None:
    result["cache_hit"] = provider.cache_hit
    result["calls_made"] = provider.calls_made
    result["prompt_hash"] = provider.prompt_hash
    result["input_hash"] = provider.input_hash
    result["cache_file"] = provider.cache_file.name if provider.cache_file else None
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    latency = 0
    if provider.cache_file and provider.cache_file.exists():
        try:
            resp = common.read_json(provider.cache_file)["response"]
            usage = resp.get("token_usage") or {}
            tokens = {"prompt": usage.get("prompt_tokens", 0), "completion": usage.get("completion_tokens", 0),
                      "total": usage.get("total_tokens", 0)}
            latency = resp.get("latency_ms", 0)
        except (OSError, ValueError, KeyError):
            pass
    result["tokens"] = tokens
    result["model_latency_ms"] = latency


def run_file(candidate: str, row: int) -> Path:
    return common.runs_dir(candidate) / f"{row}.json"


# ---------------------------------------------------------------------------
# Batch files (paid candidates)
# ---------------------------------------------------------------------------
async def capture_requests(rows: List[common.RowInfo], cand: common.Candidate,
                           variant: Optional[PromptVariant]) -> List[Dict[str, Any]]:
    """The exact request the app would send for each ready circular. Nothing is sent."""
    import logging

    logging.getLogger("regwatch").setLevel(logging.CRITICAL)  # the "request captured" stand-in failure is expected
    out = []
    for row in rows:
        pages = load_inputs(row)
        if pages is None:
            continue
        unit = f"{row.row}_{row.main_stem}"
        provider = CachingProvider(cand, unit, mode="capture")
        engine, factory, doc_id = await build_scratch(common.SCORING_ROOT / "work" / f"cap_{row.row}_{os.getpid()}.db", row, pages)
        try:
            async with factory() as db:
                try:
                    with app_patched(provider, variant):
                        await service_mod.AnalysisService.analyze_document_version(db, doc_id)
                except (RuntimeError, ValueError):
                    pass
        finally:
            await engine.dispose()
            for suffix in ("", "-wal", "-shm"):
                with contextlib.suppress(OSError):
                    Path(str(common.SCORING_ROOT / "work" / f"cap_{row.row}_{os.getpid()}.db") + suffix).unlink()
        if provider.captured:
            out.append({"row": row.row, "unit": unit, **provider.captured})
    logging.getLogger("regwatch").setLevel(logging.WARNING)
    return out


def batch_line(cand: common.Candidate, req: Dict[str, Any]) -> Dict[str, Any]:
    """One line of the vendor's batch file."""
    if cand.provider == "gemini":
        from backend.app.modules.analysis.providers.gemini import to_gemini_schema
        gen: Dict[str, Any] = {"temperature": req["temperature"], "responseMimeType": "application/json"}
        if req["schema"]:
            gen["responseSchema"] = to_gemini_schema(req["schema"])
        return {"key": req["unit"], "request": {
            "contents": [{"role": "user", "parts": [{"text": req["user"]}]}],
            "systemInstruction": {"parts": [{"text": req["system"]}]},
            "generationConfig": gen}}
    from backend.app.modules.analysis.providers.openai_compat import OpenAICompatibleProvider
    s = cand.settings
    prov = OpenAICompatibleProvider(model_name=cand.model, base_url=s.get("base_url") or "x", api_key="", response_format=s.get("response_format"))
    return {"custom_id": req["unit"], "method": "POST", "url": "/v1/chat/completions",
            "body": prov._payload(req["system"], req["user"], req["schema"], req["temperature"])}


def write_batch(cand: common.Candidate, split: str, reqs: List[Dict[str, Any]]) -> Dict[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d")
    base = common.batch_dir() / f"{cand.name}_{split}_{stamp}"
    jsonl = base.with_suffix(".jsonl")
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("w", encoding="utf-8") as f:
        for r in reqs:
            f.write(json.dumps(batch_line(cand, r), ensure_ascii=False) + "\n")
    manifest = base.with_suffix(".manifest.json")
    common.write_json(manifest, {
        "candidate": cand.name, "model": cand.model, "provider": cand.provider, "split": split,
        "items": [{"unit": r["unit"], "row": r["row"], "cache_file": r["cache_file"],
                   "prompt_hash": r["prompt_hash"], "input_hash": r["input_hash"]} for r in reqs],
    })
    return {"jsonl": jsonl, "manifest": manifest}


def collect_batch(manifest_path: Path, results_path: Path) -> Dict[str, int]:
    """Reads a finished batch's result lines into the cache (same format a live call would save)."""
    from backend.app.modules.analysis.providers.base import LLMResponse, TokenUsage
    from backend.app.modules.analysis.providers.http_retry import parse_json_text

    man = common.read_json(manifest_path)
    items = {i["unit"]: i for i in man["items"]}
    saved = failed = 0
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        unit = rec.get("custom_id") or rec.get("key")
        item = items.get(unit)
        if not item:
            continue
        body = (rec.get("response") or {}).get("body") if "custom_id" in rec else rec.get("response")
        text, usage = "", TokenUsage()
        if isinstance(body, dict) and body.get("choices"):
            text = (body["choices"][0].get("message") or {}).get("content") or ""
            u = body.get("usage") or {}
            usage = TokenUsage(prompt_tokens=u.get("prompt_tokens", 0), completion_tokens=u.get("completion_tokens", 0),
                               total_tokens=u.get("total_tokens", 0))
        elif isinstance(body, dict) and body.get("candidates"):
            parts = (body["candidates"][0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            u = body.get("usageMetadata") or {}
            usage = TokenUsage(prompt_tokens=u.get("promptTokenCount", 0), completion_tokens=u.get("candidatesTokenCount", 0),
                               total_tokens=u.get("totalTokenCount", 0))
        try:
            parsed = parse_json_text(text)
        except (ValueError, json.JSONDecodeError):
            failed += 1
            continue
        usable = isinstance(parsed, dict) and bool(parsed)
        resp = LLMResponse(raw_content=text, parsed_json=parsed, token_usage=usage, model_name=man["model"], success=True)
        common.write_json(common.cache_dir() / item["cache_file"], {
            "kind": "OK" if usable else "EMPTY", "unit": unit, "candidate": man["candidate"], "model": man["model"],
            "prompt_hash": item["prompt_hash"], "input_hash": item["input_hash"],
            "saved_at": datetime.now(timezone.utc).isoformat(), "from_batch": True, "response": resp.model_dump()})
        saved += 1
    return {"saved": saved, "failed": failed}


def submit_batch_openai(cand: common.Candidate, files: Dict[str, Path]) -> str:
    """Uploads the batch file and starts the batch at an OpenAI-style endpoint. Not exercised against a live
    service yet: it is only reached with --yes-spend."""
    import httpx

    s = cand.settings
    key = os.environ.get(s.get("api_key_env", ""), "")
    base = (s.get("base_url") or "").rstrip("/")
    if not key or not base:
        raise ScorerError("Set base_url and api_key_env in the candidate's settings, and the key in the environment.")
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=300) as c:
        up = c.post(f"{base}/files", headers=headers, data={"purpose": "batch"},
                    files={"file": (files["jsonl"].name, files["jsonl"].read_bytes(), "application/jsonl")})
        up.raise_for_status()
        b = c.post(f"{base}/batches", headers=headers, json={
            "input_file_id": up.json()["id"], "endpoint": "/v1/chat/completions", "completion_window": "24h"})
        b.raise_for_status()
        batch_id = b.json()["id"]
    man = common.read_json(files["manifest"])
    man["batch_id"] = batch_id
    common.write_json(files["manifest"], man)
    return batch_id


def fetch_batch_openai(cand: common.Candidate, manifest_path: Path) -> Optional[Path]:
    """Downloads the results when the batch has finished; None while it is still running."""
    import httpx

    man = common.read_json(manifest_path)
    s = cand.settings
    key = os.environ.get(s.get("api_key_env", ""), "")
    base = (s.get("base_url") or "").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=300) as c:
        info = c.get(f"{base}/batches/{man['batch_id']}", headers=headers)
        info.raise_for_status()
        data = info.json()
        if data.get("status") != "completed":
            say(f"Batch status: {data.get('status')}")
            return None
        out = c.get(f"{base}/files/{data['output_file_id']}/content", headers=headers)
        out.raise_for_status()
    path = manifest_path.with_suffix(".results.jsonl")
    path.write_bytes(out.content)
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
async def run_all(args: argparse.Namespace) -> int:
    common.require_split(args.split, args.final)
    cand = common.load_candidate(args.candidate)
    rows = common.load_rows(args.split, common.parse_rows_arg(args.rows))
    variant = load_prompt(cand)
    if args.final:
        common.log_final(cand.name, f"run_candidate {args.split}")

    if args.batch or args.collect is not None:
        return await batch_mode(args, cand, rows, variant)

    mode = "cache_only" if args.rescore_only else "run"
    if mode == "run" and cand.provider == "gemini":
        quota.load([cand.model])
    if cand.paid and mode == "run" and not args.yes_spend:
        raise ScorerError("This candidate is paid. Price it (price.py), then run it as a batch with --yes-spend.")

    totals = {"ok": 0, "empty": 0, "error": 0, "not_ready": 0, "not_cached": 0, "calls": 0, "cached": 0}
    stopped: Optional[str] = None
    for row in rows:
        try:
            res = await run_row(row, cand, mode, args.force, allow_spend=args.yes_spend, variant=variant)
        except RunStopped as e:
            stopped = str(e)
            say(f"STOPPED before row {row.row}: {stopped}")
            break
        status = res["status"]
        if status in (STATUS_NOT_READY, STATUS_NOT_CACHED):
            totals["not_ready" if status == STATUS_NOT_READY else "not_cached"] += 1
            say(f"row {row.row}: {status} ({res['error']})")
            continue
        common.write_json(run_file(cand.name, row.row), res)
        totals["calls"] += res.get("calls_made", 0)
        totals["cached"] += 1 if res.get("cache_hit") else 0
        key = {"OK": "ok", "EMPTY_ANSWER": "empty", "ERROR": "error"}[status]
        totals[key] += 1
        counts = res.get("claim_counts") or {}
        say(f"row {row.row}: {status}, claims {counts.get('total', 0)} (shown {counts.get('shown', 0)}), "
            f"calls {res.get('calls_made', 0)}{' (saved answer)' if res.get('cache_hit') else ''}"
            f"{' - ' + res['error'] if res.get('error') else ''}")
    if cand.provider == "gemini" and mode == "run":
        quota.save()
    print(f"\nRows run: {totals['ok'] + totals['empty'] + totals['error']} of {len(rows)} "
          f"(ok {totals['ok']}, empty answer {totals['empty']}, error {totals['error']})")
    print(f"Inputs not ready: {totals['not_ready']}. No saved answer (rescore only): {totals['not_cached']}.")
    print(f"Model calls made this run: {totals['calls']}. Rows answered from the saved answers: {totals['cached']}.")
    if stopped:
        print(f"Run stopped early: {stopped}")
        return 3
    return 0


async def batch_mode(args, cand, rows, variant) -> int:
    if args.collect is not None:
        manifests = sorted(common.batch_dir().glob(f"{cand.name}_{args.split}_*.manifest.json"))
        if not manifests:
            raise ScorerError("No batch manifest found for this candidate and split. Run with --batch first.")
        manifest = manifests[-1]
        if args.collect:
            results = Path(args.collect)
        else:
            results = fetch_batch_openai(cand, manifest)
            if results is None:
                return 0
        res = collect_batch(manifest, results)
        print(f"Collected: {res['saved']} answers saved to the cache, {res['failed']} unreadable.")
        print("Now run again with --rescore-only to build claims and checks from them.")
        return 0

    reqs = await capture_requests(rows, cand, variant)
    if not reqs:
        raise ScorerError("No circular is ready (inputs missing), so there is nothing to put in a batch.")
    files = write_batch(cand, args.split, reqs)
    print(f"Batch file: {files['jsonl']}\nManifest:   {files['manifest']}\nRequests:   {len(reqs)} circulars")
    import price
    est = price.estimate(cand, reqs)
    price.print_estimate(cand, est)
    if args.submit:
        if not cand.paid:
            raise ScorerError("Batches are for paid candidates. Free candidates run directly.")
        if not args.yes_spend:
            raise ScorerError("Nothing paid is sent without --yes-spend. Read the estimate above first.")
        if cand.provider == "gemini":
            raise ScorerError("Sending a Gemini batch is not built. Upload the batch file in the vendor's console, then use --collect <results file>.")
        batch_id = submit_batch_openai(cand, files)
        print(f"Batch sent. Id: {batch_id}. When it is finished: run_candidate.py --candidate {cand.name} --split {args.split} --collect")
    else:
        print("Nothing was sent. To send an OpenAI-style batch add --submit --yes-spend.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one candidate on a split.")
    ap.add_argument("--candidate", required=True, help="a config file or a name in research/scoring/candidates/")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--rows", help="only these rows, e.g. 2450,1426")
    ap.add_argument("--force", action="store_true", help="ask the model again even when an answer is saved")
    ap.add_argument("--rescore-only", action="store_true", help="never call a model; rebuild claims and checks from saved answers")
    ap.add_argument("--final", action="store_true", help="needed for --split test (final run only)")
    ap.add_argument("--batch", action="store_true", help="write the vendor's batch request file; calls nothing")
    ap.add_argument("--submit", action="store_true", help="with --batch: send it (needs --yes-spend)")
    ap.add_argument("--collect", nargs="?", const="", default=None, help="read a finished batch into the cache (optional results file)")
    ap.add_argument("--yes-spend", action="store_true", help="allow a paid run")
    args = ap.parse_args()
    try:
        return asyncio.run(run_all(args))
    except ScorerError as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
