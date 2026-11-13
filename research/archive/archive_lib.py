"""Shared helpers for the archive download: polite requests, listing parser, response checks.

One request at a time to bb.org.bd across every script on this PC:
- scripts in this repo share research/.bb_request.lock (same protocol as research/detect/detect_test.py);
- the scheduled detection poll on this PC (E:/regwatch-research/detect/poll.py) keeps its own
  poll.lock while it works, so we wait whenever that file is fresh, and stay quiet at 02:00 BDT
  when the nightly full-list check runs.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://www.bb.org.bd/en/index.php/mediaroom/circular"
UA = "RegWatchBot/0.1"
BDT = timezone(timedelta(hours=6))

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
DATA = HERE / "data"
PDFS = DATA / "pdfs"
INDEX = DATA / "index.json"
STATE = DATA / "state.jsonl"
BLOCKS = DATA / "blocks.jsonl"
STOPPED = DATA / "STOPPED"
DONE = DATA / "DONE"
LOCK = RESEARCH / ".bb_request.lock"
LAST = RESEARCH / ".bb_last_request"
POLL_LOCK = Path(os.environ.get("REGWATCH_POLL_LOCK", "E:/regwatch-research/detect/poll.lock"))


def now():
    return datetime.now(BDT)


def iso(dt=None):
    return (dt or now()).isoformat(timespec="seconds")


def _external_busy():
    """True while the detection poll is working, or during the nightly check window."""
    try:
        if POLL_LOCK.exists() and time.time() - POLL_LOCK.stat().st_mtime < 900:
            return True
    except OSError:
        pass
    t = now()
    return t.hour == 2 and t.minute < 6  # nightly full-list check starts 02:00


def acquire(gap):
    deadline = time.time() + 900
    while True:
        if _external_busy():
            time.sleep(5)
            continue
        try:
            os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL))
        except FileExistsError:
            try:
                if time.time() - LOCK.stat().st_mtime > 180:
                    LOCK.unlink(missing_ok=True)
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("request lock busy")
            time.sleep(1)
            continue
        if _external_busy():  # poll started while we took the lock
            LOCK.unlink(missing_ok=True)
            continue
        break
    try:
        last = float(LAST.read_text())
    except (OSError, ValueError):
        last = 0
    wait = gap - (time.time() - last)
    if wait > 0:
        time.sleep(wait)


def release():
    try:
        LAST.write_text(str(time.time()))
    finally:
        LOCK.unlink(missing_ok=True)


def fetch(method, url, gap, body=None, timeout=120):
    """Return (status, content, headers, seconds). Network errors raise."""
    acquire(gap)
    try:
        url = urllib.parse.quote(url, safe=":/?&=%#~+,;@")  # a few file names contain spaces
        data = urllib.parse.urlencode(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "User-Agent": UA, "Accept": "text/html,application/pdf,*/*"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), dict(r.headers), time.time() - t0
        except urllib.error.HTTPError as e:
            return e.code, e.read() or b"", dict(e.headers or {}), time.time() - t0
    finally:
        release()


def classify_bytes(status, raw):
    """'pdf' | 'challenge' | 'rejected' | 'http_NNN' | 'not_pdf'. Only 'challenge' is a block."""
    if raw[:4] == b"%PDF":
        return "pdf"
    low = raw[:200000].decode("utf-8", "replace").lower()
    if "/tspd/" in low or "bobcmn" in low or "what code is in the image" in low:
        return "challenge"
    if "request rejected" in low:
        return "rejected"
    if status != 200:
        return f"http_{status}"
    return "not_pdf"


def classify_listing(status, raw):
    """Return (outcome, rows). Anything but 'ok' means failed, never 'nothing new'."""
    kind = classify_bytes(status, raw)
    if kind in ("challenge", "rejected") or kind.startswith("http_"):
        return kind, []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw.decode("utf-8", "replace"), "lxml")
    table = soup.find("table", id="sortableTable") or soup.find("table")
    if table is None:
        return "no_table", []
    rows = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        raw_date = tds[0].get_text(strip=True)
        m = re.match(r"(\d\d)/(\d\d)/(\d\d)$", raw_date)
        iso_date = None
        if m:
            dd, mm, yy = map(int, m.groups())
            iso_date = f"{(1900 + yy) if yy > 50 else (2000 + yy):04d}-{mm:02d}-{dd:02d}"
        title = re.sub(r"\s+", " ", tds[1].get_text(" ", strip=True))
        for lang, td in (("en", tds[2]), ("bn", tds[3])):
            seen = []
            for a in td.find_all("a"):
                u = a.get("href") or ""
                if not u.startswith("http"):
                    m2 = re.search(r"loadPDFDynamically\('([^']+)'", a.get("onclick") or "")
                    u = m2.group(1) if m2 else ""
                if u and u not in seen:
                    seen.append(u)
                    rows.append({"date_raw": raw_date, "date": iso_date, "title": title,
                                 "lang": lang, "url": u})
    return "ok", rows


def department_of(title):
    m = re.match(r"([A-Za-z][A-Za-z&\-\. ]{1,25}?(?:-\d+)?)\s+(?:Master |Circular|Guideline|Letter|Directive|Notice|Policy)", title)
    if m:
        return m.group(1).strip()
    m = re.match(r"([A-Z][A-Za-z&\-]{1,12})\b", title)
    return m.group(1) if m else None


def reference_of(title):
    m = re.search(r"(?:No\.?|Number)\s*[:\-]?\s*([\w\-/\.]+)", title)
    return m.group(1).rstrip(".") if m else None


def load_index():
    return json.loads(INDEX.read_text(encoding="utf-8"))


def load_state():
    """Latest record per URL from the append-only state log."""
    state = {}
    if STATE.exists():
        for line in STATE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue  # half-written last line after a crash
            state[r["url"]] = r
    return state


def save_record(rec):
    DATA.mkdir(parents=True, exist_ok=True)
    with STATE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_block(rec):
    DATA.mkdir(parents=True, exist_ok=True)
    with BLOCKS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
