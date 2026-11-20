"""Label every sentence of the dev circulars with the Gemini Decisions API (experiment, 14 Nov 2026).

For each sentence of the analysed file it asks three questions in one request per chunk of pages:
  duty  (yes/no)  does this sentence itself place a duty on the addressed institutions?
  kind  (choice)  must / must_not / may / report / keep_records / get_approval / disclose / none
  who   (choice)  which kind of institution must act (the app's entity names) or not_named
Results are cached in E:\\regwatch-research\\scoring\\decisions\\<row>.json keyed by sentence ID, the same IDs the app uses.

Usage (repo root):  .venv\\Scripts\\python.exe research\\scoring\\decisions_label.py [--rows 190,239]
No model text is generated; the Decisions API returns probabilities only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from backend.app.modules.analysis.sentences import SentenceIndex  # noqa: E402
from backend.app.modules.claims.wording import ENTITIES  # noqa: E402

OUT = Path(r"E:\regwatch-research\scoring\decisions")
URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"
MAX_SENTENCES = 40           # per request: 3 questions each
TOKENS_PER_MINUTE = 45000    # stay under the free tier's 50,000

KINDS = {
    "must": "a positive duty: the institutions must do something",
    "must_not": "a prohibition or an upper limit: must not do something, shall not exceed",
    "may": "an explicit permission or option the institutions may use",
    "report": "submit a return, report or information to Bangladesh Bank",
    "keep_records": "keep or maintain records or a register",
    "get_approval": "obtain prior approval or permission",
    "disclose": "publish, display, or inform customers or the public",
    "none": "no duty: background, the regulator's own action, a reference, a heading, an address or a closing line",
}


def keys() -> list:
    env = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    out = [os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY") or ""]
    out += [k for k in (env.get("GEMINI_EXTRA_API_KEYS") or "").split(",") if k.strip()]
    return [k for k in out if k]


def pages_of(row: int) -> list:
    stem = f"{row}_0"
    pages = []
    for p in sorted(common.inputs_dir().glob(f"{stem}_p*.json"), key=lambda x: int(x.stem.rsplit("_p", 1)[1])):
        d = json.loads(p.read_text(encoding="utf-8"))
        pages.append({"page_number": d["page"], "cleaned_text": d.get("cleaned_text") or d.get("text") or "",
                      "line_boxes": d.get("line_boxes")})
    return pages


def ask(key: str, text: str, questions: dict) -> dict:
    body = json.dumps({"model": MODEL, "input": text, "questions": questions}).encode()
    for attempt in range(6):
        req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as e:
            msg = e.read()[:300].decode("utf-8", "replace")
            if e.code in (429, 500, 503):
                time.sleep(30 * (attempt + 1))
                continue
            raise RuntimeError(f"{e.code} {msg}")
    raise RuntimeError("busy after 6 tries")


def label_row(row: int, key: str) -> dict:
    pages = pages_of(row)
    index = SentenceIndex.build(pages)
    sids = [sid for p in sorted(index.order) for sid in index.order[p]
            if len(re.sub(r"\s+", " ", index.sentences[sid].text).strip()) >= 15]
    first_page = index.pages.get(1, "")[:3000]
    who_opts = {e.lower(): f"{e.replace('_', ' ').lower()}" for e in ENTITIES}
    who_opts["not_named"] = "the sentence names no institution and the addressee cannot be inferred"
    out = {}
    for start in range(0, len(sids), MAX_SENTENCES):
        chunk = sids[start:start + MAX_SENTENCES]
        pages_in = sorted({index.sentences[s].page_number for s in chunk})
        text = "Start of the circular (who it is addressed to):\n" + first_page + "\n\nPages being checked:\n" + \
            "\n".join(index.pages[p] for p in pages_in)
        qs = {}
        for n, sid in enumerate(chunk):
            s = re.sub(r"\s+", " ", index.sentences[sid].text).strip()[:600]
            qs[f"d{n}"] = {"type": "noul", "instructions": (
                "Does this sentence itself place a requirement, prohibition, permission, reporting, record-keeping, "
                "approval or disclosure duty on the institutions the circular is addressed to? Background, the "
                "regulator's own actions, references to other circulars, headings, addresses and polite closing lines "
                f"(such as 'please bring this to the notice of all concerned') do not count. Sentence: \"{s}\"")}
            qs[f"k{n}"] = {"type": "choice", "instructions": f"What kind of duty does this sentence state? Sentence: \"{s}\"",
                           "criteria": KINDS}
            qs[f"w{n}"] = {"type": "choice", "instructions": (
                "Which kind of institution must act on this sentence? If the sentence names none, use the institutions "
                f"the circular is addressed to. Sentence: \"{s}\""), "criteria": who_opts}
        t0 = time.time()
        res = ask(key, text, qs)
        a = res["answers"]
        for n, sid in enumerate(chunk):
            out[sid] = {"duty": a[f"d{n}"]["noul"], "kind": a[f"k{n}"]["probabilities"], "who": a[f"w{n}"]["probabilities"],
                        "page": index.sentences[sid].page_number}
        used = res.get("usage", {}).get("total_input_tokens", 0)
        wait = used / TOKENS_PER_MINUTE * 60 - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    key_dir = Path("E:/regwatch-research/answer_key_kit/answers")
    rows = [int(r) for r in a.rows.split(",")] if a.rows else sorted(int(p.stem) for p in key_dir.glob("*.json"))
    ks = keys()
    for i, row in enumerate(rows):
        f = OUT / f"{row}.json"
        if f.exists():
            continue
        try:
            labels = label_row(row, ks[i % len(ks)])
        except Exception as e:  # one bad row should not stop the rest
            print(f"row {row}: FAILED {e}")
            continue
        f.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
        print(f"row {row}: {len(labels)} sentences, {sum(1 for v in labels.values() if v['duty'] >= 0.5)} duties")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
