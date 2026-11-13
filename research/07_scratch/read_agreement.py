"""How often do two independent page readings (Flash-Lite and Flash) agree?

Read-only, no API calls. For every page both models read in the reading benchmark, measures:
- page-level character disagreement (the 2% rule in DECISIONS.md 10);
- sentence-level: share of Flash-Lite sentences that appear word for word in the Flash reading;
- numbers: share of number tokens (Latin or Bangla digits) that both readings contain.
Splits by the frozen dev/test split so the numbers can be quoted per split.
"""
import difflib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, "F:/side-income/regwatch-bangladesh")
from backend.app.modules.analysis.sentences import split_sentences  # noqa: E402

R = "E:/regwatch-research"
split = json.load(open(f"{R}/split_FROZEN.json", encoding="utf-8"))
row_split = {}
if isinstance(split, dict):
    for k, v in split.items():
        if isinstance(v, list):
            for r in v:
                row_split[int(r if not isinstance(r, dict) else r.get("row"))] = k
pages = {}
for f, info in json.load(open(f"{R}/pages.json", encoding="utf-8")).items():
    for p in info["pages"]:
        pid = os.path.basename(p["png"])[:-4]
        pages[pid] = p["cls"]

BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
NUM = re.compile(r"\d[\d,\./-]*\d|\d")


def norm(t):
    t = unicodedata.normalize("NFC", t)
    return re.sub(r"\s+", " ", t).strip()


def key(t):
    t = t.translate(BN)
    t = re.sub(r"[‌‍]", "", t)
    t = re.sub(r"[^\wঀ-৿]+", "", t)
    return t.lower()


def cer(a, b):
    if not a and not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return 1 - (2 * sum(m.size for m in sm.get_matching_blocks()) / (len(a) + len(b)))


rows = []
lite_dir, flash_dir = f"{R}/reading/gemini-3.5-flash-lite", f"{R}/reading/gemini-3.5-flash"
for fn in sorted(os.listdir(lite_dir)):
    pid = fn[:-4]
    fp = os.path.join(flash_dir, fn)
    if not os.path.exists(fp):
        continue
    a = norm(open(os.path.join(lite_dir, fn), encoding="utf-8").read())
    b = norm(open(fp, encoding="utf-8").read())
    if not a or not b:
        continue
    cls = pages.get(pid, "?")
    row = int(pid.split("_")[0])
    sa = [norm(s) for s in split_sentences(a) if len(norm(s)) >= 15]
    same_sent = sum(1 for s in sa if s in b)
    bk = key(b)
    loose_sent = sum(1 for s in sa if key(s) and key(s) in bk)
    na = NUM.findall(a.translate(BN))
    nb = set(NUM.findall(b.translate(BN)))
    num_same = sum(1 for n in na if n in nb)
    rows.append({"pid": pid, "cls": cls, "split": row_split.get(row, "?"), "cer": cer(a, b),
                 "sents": len(sa), "sents_same": same_sent, "sents_loose": loose_sent, "nums": len(na), "nums_same": num_same})

print(f"pages read by both: {len(rows)}")
for grp in ("all", "dev", "test"):
    sel = [r for r in rows if grp == "all" or r["split"] == grp]
    sel_bn = [r for r in sel if r["cls"] != "english_clean"]
    if not sel_bn:
        continue
    agree2 = sum(1 for r in sel_bn if r["cer"] <= 0.02)
    agree5 = sum(1 for r in sel_bn if r["cer"] <= 0.05)
    s_tot = sum(r["sents"] for r in sel_bn)
    s_same = sum(r["sents_same"] for r in sel_bn)
    s_loose = sum(r["sents_loose"] for r in sel_bn)
    print(f"   sentences equal after dropping spaces/punctuation: {s_loose}/{s_tot} ({s_loose/max(s_tot,1):.0%})")
    n_tot = sum(r["nums"] for r in sel_bn)
    n_same = sum(r["nums_same"] for r in sel_bn)
    print(f"[{grp}] non-English pages: {len(sel_bn)}; pages agreeing within 2%: {agree2} ({agree2/len(sel_bn):.0%}); within 5%: {agree5} ({agree5/len(sel_bn):.0%})")
    print(f"   sentences (15+ chars) identical in both readings: {s_same}/{s_tot} ({s_same/max(s_tot,1):.0%})")
    print(f"   number tokens found in both readings: {n_same}/{n_tot} ({n_same/max(n_tot,1):.0%})")
print("splits seen:", {r['split'] for r in rows})
