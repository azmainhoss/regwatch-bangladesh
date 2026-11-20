"""Check answer-key files in answers/ against the rules in PROMPT.md.

Usage (Python 3.8+, standard library only), from this folder:
    python check_key.py            # every file in answers/
    python check_key.py 2450 1426  # only these rows
ERROR lines must be fixed. WARN lines must be re-checked against the page image.
"""
import json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_TYPES = {"master_circular", "circular", "circular_letter", "guideline", "policy", "notification", "letter", "other"}
ENTITIES = {"all_scheduled_banks", "state_owned_banks", "private_commercial_banks", "islamic_banks", "foreign_banks",
            "specialized_banks", "nbfis", "authorized_dealers", "money_changers", "payment_system_operators",
            "mfs_providers", "mfis", "exchange_houses", "offshore_banking_units"}
OB_TYPES = {"must", "must_not", "may", "report", "keep_records", "get_approval", "disclose"}
REL_TYPES = {"amends", "repeals", "replaces", "clarifies", "references"}
EFFECTIVE = {"stated", "immediate", "not_stated"}
PAGE_CONTENT = {"letterhead_only", "blank", "form_or_table_only", "partly_illegible", "enclosure"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

manifest = {m["row"]: m for m in json.load(open(os.path.join(HERE, "manifest.json"), encoding="utf-8"))}


def norm(s):
    s = unicodedata.normalize("NFC", s or "").replace("­", "")
    return re.sub(r"\s+", " ", s).strip()


def page_text(page_id):
    p = os.path.join(HERE, "english_text", page_id + ".txt")
    return norm(open(p, encoding="utf-8").read()) if os.path.exists(p) else None


def check_quote(where, quote, page_id, pages, out, enclosure_pages=(), obligation=False):
    if not quote or not page_id:
        out.append(f"ERROR {where}: missing quote or page_id"); return
    if page_id not in pages:
        out.append(f"ERROR {where}: page_id {page_id} is not a page of this circular"); return
    if obligation and not pages[page_id]["in_obligation_window"]:
        out.append(f"ERROR {where}: page {page_id} is outside the obligation window")
    if obligation and page_id in enclosure_pages:
        out.append(f"ERROR {where}: page {page_id} is inside an enclosure; its rules belong to the enclosed document")
    q = norm(quote)
    if pages[page_id]["kind"] == "english_text":
        t = page_text(page_id)
        if t is None or q not in t:
            out.append(f"ERROR {where}: quote is not word for word in english_text/{page_id}.txt: {q[:80]!r}")
    else:
        out.append(f"WARN {where}: {pages[page_id]['kind']} page; confirm the quote letter by letter against the image")


def entity_ok(e):
    return e in ENTITIES or (isinstance(e, str) and e.startswith("other:") and len(e) > 6)


def items(g, key, out):
    v = g.get(key)
    if not isinstance(v, list):
        out.append(f"ERROR {key} must be a list"); return []
    return v


def validate(row):
    out = []
    path = os.path.join(HERE, "answers", f"{row}.json")
    if row not in manifest:
        return [f"ERROR row {row}: not in manifest.json"]
    if not os.path.exists(path):
        return [f"ERROR row {row}: answers/{row}.json missing"]
    try:
        g = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return [f"ERROR row {row}: bad JSON: {e}"]
    if g.get("row") != row: out.append("ERROR row field does not match the file name")
    pages = {p["page_id"]: p for p in manifest[row]["pages"]}

    enc_pages = set()
    for i, e in enumerate(items(g, "enclosures", out)):
        if not e.get("what"): out.append(f"ERROR enclosures[{i}].what missing")
        for pid in e.get("page_ids", []):
            if pid not in pages: out.append(f"ERROR enclosures[{i}]: unknown page {pid}")
            enc_pages.add(pid)

    md = g.get("metadata", {})
    if md.get("doc_type") not in DOC_TYPES: out.append(f"ERROR metadata.doc_type {md.get('doc_type')!r}")
    for k in ("department", "reference_number"):
        if not md.get(k): out.append(f"ERROR metadata.{k} missing")
    if not DATE.match(str(md.get("issue_date", ""))): out.append(f"ERROR metadata.issue_date {md.get('issue_date')!r}")
    check_quote("metadata.issue_date_quote", md.get("issue_date_quote"), md.get("issue_date_page_id"), pages, out)

    eff = g.get("effective", {})
    basis = eff.get("basis")
    if basis not in EFFECTIVE: out.append(f"ERROR effective.basis {basis!r}")
    if basis == "stated":
        if not DATE.match(str(eff.get("date", ""))): out.append(f"ERROR effective.date {eff.get('date')!r}")
    elif eff.get("date") is not None:
        out.append("ERROR effective.date must be null unless basis is 'stated'")
    if basis in ("stated", "immediate"):
        check_quote("effective.quote", eff.get("quote"), eff.get("page_id"), pages, out)
    elif eff.get("quote"):
        out.append("ERROR effective.quote must be null when basis is 'not_stated'")

    for k in ("applies_to", "exempt"):
        for i, a in enumerate(items(g, k, out)):
            if not entity_ok(a.get("entity")): out.append(f"ERROR {k}[{i}].entity {a.get('entity')!r}")
            check_quote(f"{k}[{i}]", a.get("quote"), a.get("page_id"), pages, out)

    ids = set()
    for i, o in enumerate(items(g, "obligations", out)):
        w = f"obligations[{i}]"
        if not o.get("id") or o.get("id") in ids: out.append(f"ERROR {w}: missing or duplicate id")
        ids.add(o.get("id"))
        if o.get("type") not in OB_TYPES: out.append(f"ERROR {w}.type {o.get('type')!r}")
        if not entity_ok(o.get("subject")): out.append(f"ERROR {w}.subject {o.get('subject')!r}")
        if not o.get("what"): out.append(f"ERROR {w}.what missing")
        check_quote(w, o.get("quote"), o.get("page_id"), pages, out, enc_pages, obligation=True)
        if o.get("deadline") is not None:
            if not o.get("deadline_quote"): out.append(f"ERROR {w}.deadline_quote missing")
            else: check_quote(w + ".deadline_quote", o.get("deadline_quote"), o.get("deadline_page_id") or o.get("page_id"), pages, out)

    for i, r in enumerate(items(g, "relationships", out)):
        w = f"relationships[{i}]"
        if r.get("type") not in REL_TYPES: out.append(f"ERROR {w}.type {r.get('type')!r}")
        if not r.get("target_reference"): out.append(f"ERROR {w}.target_reference missing")
        td = r.get("target_date")
        if td is not None and not DATE.match(str(td)): out.append(f"ERROR {w}.target_date {td!r}")
        if r.get("page_id") in enc_pages: out.append(f"ERROR {w}: quote is inside an enclosure; that link belongs to the enclosed document")
        check_quote(w, r.get("quote"), r.get("page_id"), pages, out)

    for key, lo, hi in (("summary_points", 2, 6), ("key_changes", 0, 8)):
        lst = items(g, key, out)
        if not (lo <= len(lst) <= hi): out.append(f"ERROR {key} has {len(lst)} items (need {lo}-{hi})")
        for i, s in enumerate(lst):
            if not s.get("text"): out.append(f"ERROR {key}[{i}].text missing")
            check_quote(f"{key}[{i}]", s.get("quote"), s.get("page_id"), pages, out)

    if not g.get("summary_en"): out.append("ERROR summary_en missing")
    for i, n in enumerate(items(g, "page_notes", out)):
        if n.get("page_id") not in pages: out.append(f"ERROR page_notes[{i}]: unknown page {n.get('page_id')}")
        if n.get("content") not in PAGE_CONTENT: out.append(f"ERROR page_notes[{i}].content {n.get('content')!r}")
    if not isinstance(g.get("uncertain", []), list): out.append("ERROR uncertain must be a list")
    return [f"row {row}: {m}" for m in out]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        rows = [int(a) for a in sys.argv[1:]]
    else:
        rows = sorted(int(f[:-5]) for f in os.listdir(os.path.join(HERE, "answers")) if f.endswith(".json"))
    msgs = [m for r in rows for m in validate(r)]
    for m in msgs: print(m)
    e = sum(" ERROR " in m for m in msgs); w = sum(" WARN " in m for m in msgs)
    done = sum(os.path.exists(os.path.join(HERE, "answers", f"{r}.json")) for r in manifest)
    print(f"checked {len(rows)} rows: {e} errors, {w} warnings. Answer files present: {done} of {len(manifest)}")
