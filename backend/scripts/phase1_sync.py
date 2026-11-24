"""Phase 1 (until revenue): new circulars on the server are analysed with Claude through the laptop.

The server checks bb.org.bd and reads every page itself. This script, run on the laptop twice a day, moves work
between the server and the shared analysis repo (regwatch-analysis-work), where the scheduled Claude runs already
write answers (RUNBOOK.md in that repo):

  export   asks the server which circulars wait for analysis and writes their text into the repo's inbox and
           QUEUE.txt (newest first), then commits and pushes so the next Claude run picks them up;
  upload   sends every finished answer for those circulars back to the server, one circular at a time, through the
           protected upload endpoint. The server runs the same checks as for any model answer;
  sync     export + upload (what the scheduled task runs).

The database file is never copied. Settings (environment or the repo's .env):
  REGWATCH_SERVER_URL    e.g. https://amarcircular.com
  REGWATCH_UPLOAD_TOKEN  the server's ANALYSIS_UPLOAD_TOKEN

Usage (repo root):  .venv\\Scripts\\python.exe backend\\scripts\\phase1_sync.py sync --repo F:\\side-income\\regwatch-analysis-work
Log: data/phase1_sync.log. Uploaded circulars are remembered in data/phase1_state.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "phase1_state.json"
LOG = ROOT / "data" / "phase1_sync.log"
LONG_CHARS = 60_000
TIMEOUT = 120


def log(message: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}  {message}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        env = ROOT / ".env"
        if env.exists():
            for raw in env.read_text(encoding="utf-8").splitlines():
                key, _, val = raw.partition("=")
                if key.strip() == name:
                    value = val.strip().strip('"').strip("'")
    if not value:
        sys.exit(f"{name} is not set (environment or .env).")
    return value


class Server:
    def __init__(self) -> None:
        self.base = setting("REGWATCH_SERVER_URL").rstrip("/") + "/api/v1/analysis-upload"
        if not self.base.startswith("https://") and "localhost" not in self.base and "127.0.0.1" not in self.base:
            sys.exit("REGWATCH_SERVER_URL must use https:// (the upload token must never travel in plain text).")
        self.token = setting("REGWATCH_UPLOAD_TOKEN")

    def call(self, method: str, path: str, body: Optional[bytes] = None) -> Any:
        req = urllib.request.Request(self.base + path, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "regwatch-phase1-sync/1",
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                    return json.loads(res.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")
                if e.code >= 500 and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise ServerError(e.code, detail)
            except urllib.error.URLError as e:
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise ServerError(0, str(e.reason))


class ServerError(Exception):
    def __init__(self, code: int, detail: str):
        super().__init__(f"{code}: {detail[:500]}")
        self.code, self.detail = code, detail


def load_state() -> Dict[str, Any]:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"exported": {}, "uploaded": {}}


def save_state(state: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()[:300]}")
    return out.stdout


def cmd_export(server: Server, repo: Path, state: Dict[str, Any], limit: int) -> int:
    git(repo, "pull", "--rebase", "--quiet")
    pending = server.call("GET", f"/pending?limit={limit}")["circulars"]
    answered = {p.stem for p in (repo / "answers").glob("*.json")}
    new: List[str] = []
    for c in pending:
        key = c["document_id"]
        folder = "inbox_long" if (c.get("chars") or 0) > LONG_CHARS else "inbox"
        target = repo / folder / f"{key}.txt"
        if key in answered or target.exists():
            state["exported"].setdefault(key, c.get("reference_number") or c.get("title"))
            continue
        try:
            text = server.call("GET", f"/circulars/{key}/text")["text"]
        except ServerError as e:
            log(f"export: skipped {key}: {e}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        state["exported"][key] = c.get("reference_number") or c.get("title")
        new.append(f"{folder}/{key}.txt")
    if new:
        queue = repo / "QUEUE.txt"
        old = [l for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()] if queue.exists() else []
        short = [l for l in new if l.startswith("inbox/")]
        long_ = [l for l in new if l.startswith("inbox_long/")]
        old_short = [l for l in old if l.startswith("inbox/") and l not in short]
        old_long = [l for l in old if l.startswith("inbox_long/") and l not in long_]
        # New circulars go first: banks want this week's circulars before the archive.
        queue.write_text("".join(f"{l}\n" for l in short + old_short + long_ + old_long), encoding="utf-8")
        git(repo, "add", "inbox", "inbox_long", "QUEUE.txt")
        git(repo, "commit", "--quiet", "-m", f"Queue {len(new)} new circular(s) from the server")
        git(repo, "push", "--quiet")
    save_state(state)
    log(f"export: {len(pending)} waiting on the server, {len(new)} newly queued")
    return len(new)


def cmd_upload(server: Server, repo: Path, state: Dict[str, Any]) -> int:
    git(repo, "pull", "--rebase", "--quiet")
    sent = 0
    for key in sorted(state["exported"]):
        if key in state["uploaded"]:
            continue
        answer = repo / "answers" / f"{key}.json"
        if not answer.exists():
            continue
        try:
            res = server.call("POST", f"/circulars/{key}/analysis", answer.read_bytes())
            state["uploaded"][key] = datetime.now(timezone.utc).isoformat()
            sent += 1
            log(f"upload: {state['exported'][key]} loaded, points {res.get('points')}")
        except ServerError as e:
            if e.code == 409 and "already has an analysis" in e.detail:
                state["uploaded"][key] = "already analysed on the server"
            else:
                log(f"upload: {state['exported'][key]} NOT loaded: {e}")
        save_state(state)
    log(f"upload: {sent} analysis(es) sent")
    return sent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["export", "upload", "sync"])
    ap.add_argument("--repo", required=True, help="the regwatch-analysis-work checkout")
    ap.add_argument("--limit", type=int, default=50, help="most circulars to queue per run")
    args = ap.parse_args()
    repo = Path(args.repo)
    if not (repo / "RUNBOOK.md").exists():
        sys.exit(f"{repo} is not the analysis work repo (no RUNBOOK.md).")
    server, state = Server(), load_state()
    if args.command in ("export", "sync"):
        cmd_export(server, repo, state, args.limit)
    if args.command in ("upload", "sync"):
        cmd_upload(server, repo, state)


if __name__ == "__main__":
    main()
