"""Download every circular PDF (English and Bangla) from the Bangladesh Bank list, slowly and politely.

Usage (use E:/regwatch-research/venv/Scripts/python.exe):
    python fetch_all.py index        # build data/index.json (once)
    python fetch_all.py speedtest    # staged rate test, stops at the first challenge page
    python fetch_all.py run          # full download, resumable, backs off on challenge pages
    python fetch_all.py status       # counts so far

Rules:
- Own name RegWatchBot/0.1, one request at a time (shared lock, see archive_lib.py).
- The gap between requests is read from data/gap.txt before every file (never below 2 s, default 5 s).
- A challenge page (HTTP 200 HTML, /TSPD/, "What code is in the image") is a block: back off
  30 min, doubling up to 6 h; after 3 blocks in one Bangladesh day, write data/STOPPED and exit.
- A "Request Rejected" page for one URL means skip that file (status rejected), not a block.
- Progress is appended to data/state.jsonl after every file, so a restart resumes where it left off.
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

from archive_lib import (BLOCKS, DATA, DONE, PDFS, STATE, STOPPED, URL, classify_bytes, fetch,
                         iso, load_index, load_state, log_block, now, save_record)

MIN_GAP = 2.0
DEFAULT_GAP = 5.0
GAP_FILE = DATA / "gap.txt"
BACKOFF = DATA / "backoff.json"
STATUS = DATA / "status.json"
RUN_LOG = DATA / "run.log"
MAX_ATTEMPTS = 3
BLOCKS_PER_DAY_LIMIT = 3


def log(msg):
    DATA.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{iso()} {msg}\n")


def current_gap():
    try:
        g = float(GAP_FILE.read_text().strip())
    except (OSError, ValueError):
        g = DEFAULT_GAP
    return max(g, MIN_GAP)


def safe_name(item):
    base = re.sub(r"[^A-Za-z0-9._-]", "_", item["url"].rsplit("/", 1)[-1])
    h = hashlib.sha1(item["url"].encode()).hexdigest()[:8]
    return f"{item['date']}_{h}_{base}"


def pending_items(index, state):
    fresh, retry = [], []
    for it in index["pdfs"]:
        rec = state.get(it["url"])
        if rec is None:
            fresh.append(it)
        elif rec["status"] == "failed" and rec.get("attempts", 1) < MAX_ATTEMPTS:
            retry.append(it)
    key = lambda i: (i["date"] or "", i["lang"] == "en")  # newest first, English before Bangla
    fresh.sort(key=key, reverse=True)
    return fresh, retry


def base_record(item, attempts=1):
    return {"url": item["url"], "reference": item["title"].split(":")[0].strip(),
            "title": item["title"], "date": item["date"], "department": item["department"],
            "lang": item["lang"], "circular_id": item["circular_id"], "attempts": attempts,
            "at": iso()}


def download_one(item, gap, prev=None):
    """Return (record, outcome). outcome is 'challenge' for a block, else the record status."""
    attempts = (prev or {}).get("attempts", 0) + 1
    rec = base_record(item, attempts)
    try:
        status, raw, headers, secs = fetch("GET", item["url"], gap, timeout=180)
    except Exception as e:  # network trouble: retry later, not a block
        rec.update(status="failed", reason=f"error:{type(e).__name__}")
        return rec, "failed"
    kind = classify_bytes(status, raw)
    rec["http"] = status
    rec["secs"] = round(secs, 2)
    if kind == "pdf":
        PDFS.mkdir(parents=True, exist_ok=True)
        name = safe_name(item)
        tmp = PDFS / (name + ".part")
        tmp.write_bytes(raw)
        os.replace(tmp, PDFS / name)
        rec.update(status="ok", file=name, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                   etag=headers.get("ETag"), last_modified=headers.get("Last-Modified"))
        return rec, "ok"
    if kind == "challenge":
        rec.update(status="challenge", bytes=len(raw))
        return rec, "challenge"
    if kind == "rejected":
        rec.update(status="rejected", reason="request rejected")
        return rec, "rejected"
    rec.update(status="failed", reason=kind, bytes=len(raw))
    return rec, "failed"


# ---------------------------------------------------------------- speed test

def speedtest():
    """100 files at 5 s, then 100 at 3 s, then 100 at 2 s. Stop at the FIRST challenge page."""
    log_path = Path(__file__).resolve().parent / "SPEED_TEST.md"
    index = load_index()
    state = load_state()
    fresh, _ = pending_items(index, state)
    queue = iter(fresh)
    if not log_path.exists():
        log_path.write_text("# Archive download: speed test\n\nOwn name `RegWatchBot/0.1`, one request at a time. "
                            "Gap = pause from the end of one request to the start of the next. "
                            "Avg file time = time the server took to send the file.\n\n"
                            "| Start (BDT) | Gap (s) | Planned | Done | OK | Rejected | Failed | Challenge pages | "
                            "Avg file time (s) | Wall time (min) | Result |\n|---|---|---|---|---|---|---|---|---|---|---|\n",
                            encoding="utf-8")
    for gap, planned in ((5, 100), (3, 100), (2, 100)):
        t0, start = time.time(), iso()
        c = {"ok": 0, "rejected": 0, "failed": 0, "challenge": 0}
        secs, done = [], 0
        for item in queue:
            rec, outcome = download_one(item, gap)
            done += 1
            if outcome == "challenge":
                c["challenge"] += 1
                log_block({"at": iso(), "where": f"speedtest gap {gap}", "url": item["url"],
                           "bytes": rec.get("bytes")})
                break
            save_record(rec)
            c[outcome] += 1
            secs.append(rec.get("secs", 0))
            if done >= planned:
                break
        avg = sum(secs) / len(secs) if secs else 0
        result = "BLOCKED, stopped" if c["challenge"] else "clean"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"| {start[:19]} | {gap} | {planned} | {done} | {c['ok']} | {c['rejected']} | {c['failed']} | "
                    f"{c['challenge']} | {avg:.2f} | {(time.time()-t0)/60:.1f} | {result} |\n")
        print(f"stage gap={gap}: {result} done={done} {c} avg={avg:.2f}s", flush=True)
        if c["challenge"]:
            return 3
    return 0


# ---------------------------------------------------------------- full run

def write_status(**kw):
    STATUS.write_text(json.dumps({"at": iso(), "pid": os.getpid(), **kw}), encoding="utf-8")


def blocks_today():
    if not BLOCKS.exists():
        return 0
    today = now().date().isoformat()
    n = 0
    for line in BLOCKS.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line)["at"][:10] == today:
                n += 1
        except (ValueError, KeyError):
            pass
    return n


def sleep_until(ts, why):
    while time.time() < ts:
        write_status(state=why, resume_at=iso(now() + timedelta(seconds=ts - time.time())))
        time.sleep(min(60, max(1, ts - time.time())))


def backoff_state():
    try:
        return json.loads(BACKOFF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"consecutive": 0, "until": 0}


def handle_block(url):
    """Record a block, then wait and probe with one listing request. Return False if we must stop."""
    while True:
        log_block({"at": iso(), "where": "run", "url": url})
        n = blocks_today()
        b = backoff_state()
        b["consecutive"] += 1
        wait = min(6 * 3600, 1800 * 2 ** (b["consecutive"] - 1))
        log(f"BLOCK #{n} today (consecutive {b['consecutive']}), url {url}")
        if n >= BLOCKS_PER_DAY_LIMIT:
            STOPPED.write_text(f"{iso()} stopped after {n} blocks in one day. Delete this file to resume.\n",
                               encoding="utf-8")
            log("STOPPED: 3 blocks in one day")
            write_status(state="stopped")
            return False
        b["until"] = time.time() + wait
        BACKOFF.write_text(json.dumps(b), encoding="utf-8")
        sleep_until(b["until"], "backoff")
        day = now().date()
        body = {"from_date": (day - timedelta(days=1)).isoformat(), "to_date": day.isoformat(),
                "search_circular": "Search"}
        try:
            status, raw, _, _ = fetch("POST", URL, 5, body=body, timeout=60)
            kind = classify_bytes(status, raw)
        except Exception as e:
            log(f"probe error {type(e).__name__}")
            kind = "error"
        if kind == "challenge":
            url = "probe"
            continue
        if kind in ("not_pdf", "pdf", "rejected") or kind.startswith("http_2"):
            log(f"probe ok ({kind}), resuming")
            return True
        log(f"probe inconclusive ({kind}), waiting again")
        BACKOFF.write_text(json.dumps({**b, "until": time.time() + 1800}), encoding="utf-8")
        sleep_until(time.time() + 1800, "backoff")
        return True


def single_instance():
    import msvcrt
    f = open(DATA / "run.lock", "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return None
    return f  # keep referenced for the life of the process


def run():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = single_instance()
    if lock is None:
        return
    if STOPPED.exists():
        log("STOPPED file present, exiting")
        return
    if DONE.exists():
        return
    log(f"start, gap {current_gap()} s")
    b = backoff_state()
    if b["until"] > time.time():
        sleep_until(b["until"], "backoff")
    index = load_index()
    clean_streak = 0
    while True:
        if STOPPED.exists():
            return
        state = load_state()
        fresh, retry = pending_items(index, state)
        if not fresh and not retry:
            DONE.write_text(iso() + "\n", encoding="utf-8")
            log("DONE")
            write_status(state="done")
            return
        if not fresh:
            log(f"{len(retry)} failed files to retry in 10 min")
            sleep_until(time.time() + 600, "retry wait")
        total = len(index["pdfs"])
        for n, item in enumerate(fresh or retry):
            gap = current_gap()
            rec, outcome = download_one(item, gap, state.get(item["url"]))
            if outcome == "challenge":
                if not handle_block(item["url"]):
                    return
                clean_streak = 0
                break  # rebuild the pending list and carry on
            save_record(rec)
            clean_streak += 1
            if clean_streak == 20:
                BACKOFF.write_text(json.dumps({"consecutive": 0, "until": 0}), encoding="utf-8")
            if n % 25 == 0 or outcome != "ok":
                done = sum(1 for r in state.values() if r["status"] in ("ok", "rejected")) + n + 1
                write_status(state="downloading", gap=gap, last=outcome, approx_done=done, total=total)
            if STOPPED.exists():
                return


def status():
    index = load_index()
    state = load_state()
    counts = {}
    size = 0
    for it in index["pdfs"]:
        r = state.get(it["url"])
        k = r["status"] if r else "pending"
        counts[k] = counts.get(k, 0) + 1
        if r and r["status"] == "ok":
            size += r.get("size", 0)
    print(f"index: {len(index['pdfs'])} PDFs in {len({i['circular_id'] for i in index['pdfs']})} circulars")
    print(f"states: {counts}  downloaded {size/1e6:.1f} MB")
    print(f"blocks today: {blocks_today()}  STOPPED={STOPPED.exists()} DONE={DONE.exists()}  gap={current_gap()}")
    if STATUS.exists():
        print(STATUS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "index":
        import build_index
        build_index.main()
    elif cmd == "speedtest":
        sys.exit(speedtest())
    elif cmd == "run":
        try:
            run()
        except Exception:  # pythonw has no console: keep the reason in the log, then exit non-zero
            import traceback
            log("CRASH " + traceback.format_exc().replace("\n", " | "))
            sys.exit(1)
    elif cmd == "status":
        status()
    else:
        sys.exit(__doc__)
