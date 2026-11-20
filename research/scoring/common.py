"""Shared helpers for the scorer: paths, the circular list, the split guard, hashing.

Nothing here talks to the network. Nothing here reads an answer key unless a script asks for one.

The app is pointed at a throwaway database BEFORE any app module is imported (`point_app_at_scratch`),
so no script in this folder can ever touch data/regwatch.db.
"""
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CANDIDATES_DIR = HERE / "candidates"
TEST_RUNS_LOG = HERE / "TEST_RUNS.log"

# Where the research data lives, and where this tool keeps its own data. Tests override both.
RESEARCH_ROOT = Path(os.environ.get("REGWATCH_RESEARCH_ROOT", r"E:\regwatch-research"))
SCORING_ROOT = Path(os.environ.get("REGWATCH_SCORING_ROOT", str(RESEARCH_ROOT / "scoring")))

SPLITS = ("dev", "test")


class ScorerError(Exception):
    """A plain-words error that scripts print and exit on."""


def point_app_at_scratch() -> Path:
    """Sets the app's database and storage to a throwaway place. Call before importing any app module."""
    scratch = SCORING_ROOT / "work"
    scratch.mkdir(parents=True, exist_ok=True)
    db = scratch / "app_default.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    os.environ["STORAGE_LOCAL_ROOT"] = str(scratch / "storage")
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["SEED_ON_STARTUP"] = "false"
    os.environ["VISION_WORKER_ENABLED"] = "false"
    os.environ["ALERTS_KICK_AFTER_COMMIT"] = "false"
    os.environ["ALERTS_WORKER_ENABLED"] = "false"
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    return db


def _ensure_scratch_on_import() -> None:
    """Every script imports this module first, so the app can never be imported before it is pointed at the scratch database."""
    point_app_at_scratch()


def quiet_app_logs() -> None:
    import logging

    logging.getLogger("regwatch").setLevel(logging.WARNING)


def assert_scratch_database() -> None:
    from backend.app.core.config import settings

    if "regwatch.db" in settings.DATABASE_URL or "regwatch.db" in (settings.SYNC_DATABASE_URL or ""):
        raise ScorerError("The app is pointed at the real database. Stopping so nothing is touched.")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def inputs_dir() -> Path:
    return SCORING_ROOT / "inputs"


def cache_dir() -> Path:
    return SCORING_ROOT / "cache"


def runs_dir(candidate: str) -> Path:
    return SCORING_ROOT / "runs" / candidate


def reports_dir() -> Path:
    return SCORING_ROOT / "reports"


def batch_dir() -> Path:
    return SCORING_ROOT / "batches"


def pdf_path(stem: str) -> Path:
    return RESEARCH_ROOT / "pdfs" / f"{stem}.pdf"


def keys_dir(split: str) -> Path:
    return RESEARCH_ROOT / ("answer_key_kit" if split == "dev" else "answer_key_test") / "answers"


# ---------------------------------------------------------------------------
# The split guard
# ---------------------------------------------------------------------------
def require_split(split: str, final: bool) -> None:
    """The test split is frozen: it is only touched with --final."""
    if split not in SPLITS:
        raise ScorerError(f"Unknown split '{split}'. Use dev or test.")
    if split == "test" and not final:
        raise ScorerError(
            "The test split is frozen. It can only be used for the final run: add --final "
            "(every final run is written to research/scoring/TEST_RUNS.log)."
        )
    if final and split != "test":
        raise ScorerError("--final only goes with --split test.")
    if split == "test":
        verify_frozen()


def verify_frozen() -> None:
    """The frozen split file must still match the hash written when the sample was frozen."""
    frozen = RESEARCH_ROOT / "split_FROZEN.json"
    sums = RESEARCH_ROOT / "FROZEN.sha256"
    if not frozen.exists() or not sums.exists():
        return  # nothing to compare with (a test run with made-up data)
    want = None
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == frozen.name:
            want = parts[0].lower()
    if want and hashlib.sha256(frozen.read_bytes()).hexdigest() != want:
        raise ScorerError("split_FROZEN.json no longer matches FROZEN.sha256. The split was changed; stopping.")


def log_final(candidate: str, what: str, score: Optional[float] = None) -> None:
    """Appends one line to TEST_RUNS.log for every --final run."""
    TEST_RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    s = "n/a" if score is None else f"{score:.2f}"
    with TEST_RUNS_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\t{candidate}\t{what}\t{s}\n")


# ---------------------------------------------------------------------------
# The circular list
# ---------------------------------------------------------------------------
@dataclass
class PageRef:
    page_id: str  # "2450_0_p1"
    stem: str  # "2450_0"
    page: int  # 1-based page number in that file
    in_window: bool
    kind: Optional[str] = None


@dataclass
class RowInfo:
    row: int
    split: str
    title: str
    date: str  # issue date from the website listing, YYYY-MM-DD
    pages: List[PageRef]

    @property
    def stems(self) -> List[str]:
        out: List[str] = []
        for p in self.pages:
            if p.stem not in out:
                out.append(p.stem)
        return out

    @property
    def main_stem(self) -> str:
        """The file the app analyses: the first (English) one. A Bangla twin file is a language
        variant stored beside it and is not analysed, as in the app."""
        return sorted(self.stems, key=lambda s: int(s.rsplit("_", 1)[-1]) if s.rsplit("_", 1)[-1].isdigit() else 0)[0]

    def pages_of(self, stem: str) -> List[PageRef]:
        return sorted((p for p in self.pages if p.stem == stem), key=lambda p: p.page)


def _page_ref(p: Dict[str, Any]) -> PageRef:
    pid = p["page_id"]
    stem, _, num = pid.rpartition("_p")
    return PageRef(page_id=pid, stem=stem, page=int(p.get("page") or num), in_window=bool(p.get("in_obligation_window", True)),
                   kind=p.get("cls") or p.get("kind"))


def load_rows(split: str, rows: Optional[List[int]] = None) -> List[RowInfo]:
    """The circulars of one split (from gold/doc_index.json), optionally only some rows."""
    index_path = RESEARCH_ROOT / "gold" / "doc_index.json"
    if not index_path.exists():
        raise ScorerError(f"Circular list not found: {index_path}")
    data = json.loads(index_path.read_text(encoding="utf-8"))
    out: List[RowInfo] = []
    for item in data:
        if item.get("split") != split:
            continue
        if rows and int(item["row"]) not in rows:
            continue
        out.append(RowInfo(
            row=int(item["row"]),
            split=split,
            title=item.get("title") or "",
            date=item.get("date") or "",
            pages=[_page_ref(p) for p in item.get("pages", [])],
        ))
    out.sort(key=lambda r: r.row)
    if rows:
        missing = sorted(set(rows) - {r.row for r in out})
        if missing:
            raise ScorerError(f"Rows not in the {split} split: {missing}")
    return out


def parse_rows_arg(text: Optional[str]) -> Optional[List[int]]:
    if not text:
        return None
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise ScorerError("--rows must be numbers separated by commas, for example --rows 2450,1426")


# ---------------------------------------------------------------------------
# Hashing and files
# ---------------------------------------------------------------------------
def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def write_json(path: Path, data: Any) -> None:
    """Writes through a temp file so a stopped run never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_name(text: str) -> str:
    return "".join(c if (c.isalnum() or c in "-._") else "_" for c in text)


# ---------------------------------------------------------------------------
# Candidate config
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    name: str
    provider: str  # gemini | openai_compat | mock
    model: str
    prompt: str  # "app" or a path to a prompt variant file
    method: str
    paid: bool
    settings: Dict[str, Any]
    raw: Dict[str, Any]
    path: Optional[Path] = None


def load_candidate(spec: str) -> Candidate:
    """`spec` is a path to a config file, or a name in research/scoring/candidates/."""
    p = Path(spec)
    if not p.exists():
        p = CANDIDATES_DIR / (spec if spec.endswith(".json") else f"{spec}.json")
    if not p.exists():
        raise ScorerError(f"Candidate config not found: {spec}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    for key in ("name", "provider", "model"):
        if not raw.get(key) and raw.get(key) != "":
            raise ScorerError(f"Candidate config {p.name} has no '{key}'.")
    if raw["provider"] not in ("gemini", "openai_compat", "mock"):
        raise ScorerError("Candidate provider must be gemini, openai_compat or mock.")
    method = raw.get("method", "whole_document")
    if method != "whole_document":
        raise ScorerError("Only the whole-document method is built so far.")
    return Candidate(
        name=raw["name"], provider=raw["provider"], model=raw.get("model", ""),
        prompt=raw.get("prompt", "app"), method=method, paid=bool(raw.get("paid", False)),
        settings=raw.get("settings", {}) or {}, raw=raw, path=p,
    )


_ensure_scratch_on_import()
