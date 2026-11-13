"""On Bijoy (legacy-font) pages, are the numbers in the PDF text layer the same as in the image reading?
If yes, the text layer is a free, independent check on numbers and dates in quotes."""
import json, os, re
from collections import Counter
R = "E:/regwatch-research"
BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
NUM = re.compile(r"\d+")
cls = {}
for f, info in json.load(open(f"{R}/pages.json", encoding="utf-8")).items():
    for p in info["pages"]:
        cls[os.path.basename(p["png"])[:-4]] = p["cls"]
tot = Counter()
for fn in os.listdir(f"{R}/reading/gemini-3.5-flash-lite"):
    pid = fn[:-4]
    c = cls.get(pid)
    if c not in ("bangla_bijoy", "mixed", "bangla_other_legacy"):
        continue
    raw_p = f"{R}/reading/pymupdf_raw/{fn}"
    if not os.path.exists(raw_p):
        continue
    lite = open(f"{R}/reading/gemini-3.5-flash-lite/{fn}", encoding="utf-8").read().translate(BN)
    raw = open(raw_p, encoding="utf-8", errors="replace").read()
    a = Counter(n for n in NUM.findall(lite) if len(n) >= 2)
    b = Counter(n for n in NUM.findall(raw) if len(n) >= 2)
    if not b:
        tot[c + ":no_digits_in_layer"] += 1
        continue
    tot[c + ":pages"] += 1
    tot[c + ":lite_nums"] += sum(a.values())
    tot[c + ":lite_nums_in_layer"] += sum(min(v, b[k]) for k, v in a.items())
    tot[c + ":layer_nums"] += sum(b.values())
for k in sorted(tot): print(k, tot[k])
