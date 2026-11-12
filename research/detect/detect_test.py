"""Live test of new-circular detection on bb.org.bd (decision 1 in DECISIONS.md).

Usage:
    python detect_test.py poll        # run by a scheduled task every 10 min
    python detect_test.py reconcile   # run by a scheduled task at 17:50
    python detect_test.py summary     # print results

Standard library only. Data goes to research/detect/data/ (not committed).
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"
UA = "RegWatchBot/0.1"
GAP_S = 15
BDT = timezone(timedelta(hours=6))
TEST_START = datetime(2026, 11, 12, 12, 0, tzinfo=BDT)
TEST_END = datetime(2026, 11, 19, 18, 0, tzinfo=BDT)
DAY_START, DAY_END = 10, 18  # the PC is only on 10:00-18:00 BDT

DATA = Path(__file__).resolve().parent / "data"
SEEN = DATA / "seen.json"
RUNS = DATA / "runs.jsonl"


def now():
    return datetime.now(BDT)


SHARED = Path(__file__).resolve().parent.parent  # research/
LOCK = SHARED / ".bb_request.lock"
LAST = SHARED / ".bb_last_request"


def _acquire():
    """One request to bb.org.bd at a time across all scripts, at least GAP_S apart."""
    import os
    deadline = time.time() + 300
    while True:
        try:
            os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL))
            break
        except FileExistsError:
            if time.time() - LOCK.stat().st_mtime > 180:
                LOCK.unlink(missing_ok=True)
            elif time.time() > deadline:
                raise TimeoutError("bb.org.bd lock busy")
            time.sleep(1)
    try:
        last = float(LAST.read_text())
    except (OSError, ValueError):
        last = 0
    wait = GAP_S - (time.time() - last)
    if wait > 0:
        time.sleep(wait)


def _release():
    LAST.write_text(str(time.time()))
    LOCK.unlink(missing_ok=True)


def fetch(method, url, body=None, timeout=60):
    _acquire()
    try:
        return _fetch(method, url, body, timeout)
    finally:
        _release()


def _fetch(method, url, body=None, timeout=60):
    data = urllib.parse.urlencode(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "User-Agent": UA, "Accept": "text/html,application/pdf,*/*",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b"", dict(e.headers or {}), time.time() - t0


def classify(status, html):
    """Return (outcome, rows). Anything but 'ok' means 'failed, try later', never 'nothing new'."""
    low = html.lower()
    if "/tspd/" in low or "bobcmn" in low or "what code is in the image" in low:
        return "challenge", []
    if "request rejected" in low:
        return "rejected", []
    if status != 200:
        return f"http_{status}", []
    i = html.find("<table")
    if i < 0 or "<th" not in html[i:i + 2000]:
        return "no_table", []
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", html[i:html.find("</table>", i)], re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 4:
            continue
        title = unescape(re.sub(r"<[^>]+>|\s+", " ", tds[1])).strip()
        for lang, cell in (("en", tds[2]), ("bn", tds[3])):
            for pdf in set(re.findall(r"https?://[^'\"\s]+\.pdf", cell, re.I)):
                rows.append({"date": tds[0].strip(), "title": title, "lang": lang, "pdf": pdf})
    return "ok", rows


def load_seen():
    return json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}


def save_seen(seen):
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def log(rec):
    DATA.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def last_ok_poll():
    if not RUNS.exists():
        return None
    last = None
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["kind"] == "poll" and r["outcome"] == "ok":
            last = r["at"]
    return datetime.fromisoformat(last) if last else None


def due(t):
    if not DAY_START <= t.hour < DAY_END:
        return False
    if t.weekday() in (6, 0, 1, 2, 3):  # Sun-Thu: every run (10 min)
        return True
    last = last_ok_poll()
    return last is None or t - last >= timedelta(minutes=55)


def pdf_last_modified(url):
    status, _, headers, _ = fetch("HEAD", url, timeout=30)
    lm = headers.get("Last-Modified")
    return status, lm, headers.get("ETag")


def record_new(rows, seen, t, source):
    new = []
    for row in rows:
        if row["pdf"] in seen:
            continue
        status, lm, etag = pdf_last_modified(row["pdf"])
        seen[row["pdf"]] = {**row, "first_seen": t.isoformat(), "found_by": source,
                            "last_modified": lm, "etag": etag, "head_status": status}
        new.append(row["pdf"])
    return new


def poll():
    t = now()
    if t > TEST_END or not due(t):
        return
    DATA.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    baseline = not seen
    body = {"from_date": (t - timedelta(days=7)).strftime("%Y-%m-%d"),
            "to_date": t.strftime("%Y-%m-%d"), "search_circular": "Search"}
    try:
        status, raw, _, secs = fetch("POST", URL, body)
        outcome, rows = classify(status, raw.decode("utf-8", "replace"))
        size = len(raw)
    except Exception as e:  # network error: a failure, not "nothing new"
        outcome, rows, size, secs = f"error:{type(e).__name__}", [], 0, 0
    new = []
    if outcome == "ok":
        if baseline:
            for row in rows:
                seen[row["pdf"]] = {**row, "first_seen": t.isoformat(), "found_by": "baseline"}
        else:
            new = record_new(rows, seen, t, "poll")
        save_seen(seen)
    log({"kind": "poll", "at": t.isoformat(), "outcome": outcome, "rows": len(rows),
         "new": new, "bytes": size, "secs": round(secs, 2), "baseline": baseline})


def reconcile():
    t = now()
    if t > TEST_END or not DAY_START <= t.hour < DAY_END:
        return
    seen = load_seen()
    try:
        status, raw, _, secs = fetch("GET", URL, timeout=120)
        outcome, rows = classify(status, raw.decode("utf-8", "replace"))
    except Exception as e:
        outcome, rows, secs = f"error:{type(e).__name__}", [], 0
    missed = []
    if outcome == "ok":
        start = TEST_START.date()
        for row in rows:
            try:
                d = datetime.strptime(row["date"], "%d/%m/%y").date()
            except ValueError:
                continue
            if d >= start and row["pdf"] not in seen:
                missed.append(row["pdf"])
        record_new([r for r in rows if r["pdf"] in missed], seen, t, "reconcile")
        save_seen(seen)
    log({"kind": "reconcile", "at": t.isoformat(), "outcome": outcome, "rows": len(rows),
         "missed": missed, "secs": round(secs, 2)})


def summary():
    runs = [json.loads(l) for l in RUNS.read_text(encoding="utf-8").splitlines()] if RUNS.exists() else []
    seen = load_seen()
    polls = [r for r in runs if r["kind"] == "poll"]
    recs = [r for r in runs if r["kind"] == "reconcile"]
    outcomes = {}
    for r in polls:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    found = [v for v in seen.values() if v.get("found_by") == "poll"]
    late = [v for v in seen.values() if v.get("found_by") == "reconcile"]
    delays = []
    for v in found:
        if v.get("last_modified"):
            lm = datetime.strptime(v["last_modified"], "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            delays.append((datetime.fromisoformat(v["first_seen"]) - lm).total_seconds() / 60)
    delays.sort()
    print(f"Window: {TEST_START:%d %b %H:%M} to {TEST_END:%d %b %H:%M} BDT")
    print(f"Polls: {len(polls)}  outcomes: {outcomes}")
    print(f"Nightly checks: {len(recs)}  outcomes: {[r['outcome'] for r in recs]}")
    print(f"New circular PDFs caught by the poll: {len(found)}")
    print(f"Missed by the poll, caught at night: {len(late)}")
    if delays:
        print(f"Minutes from upload to detection: median {delays[len(delays)//2]:.0f}, "
              f"max {delays[-1]:.0f}")
    for v in sorted(found + late, key=lambda v: v["first_seen"]):
        print(f"  {v['first_seen'][:16]} [{v['found_by']}] {v['title'][:70]} ({v['lang']})")


if __name__ == "__main__":
    {"poll": poll, "reconcile": reconcile, "summary": summary}[sys.argv[1]]()
