"""Step 3 of the scorer: score a candidate's runs against the answer keys and print one headline number.

Reads runs/<candidate>/<row>.json (made by run_candidate.py) and the answer keys. Never writes or edits a key.
Only circulars that have both a run and a key are scored; the others are listed.

Usage (repo root):
    .venv\\Scripts\\python.exe research\\scoring\\score.py --candidate gemini_flash_v3 --split dev
    ... --rows 2450,1426       only these circulars
    ... --json out.json        also write every number to a file
    ... --diff other_name      show the circulars where two candidates differ most
    ... --keys-dir DIR         read keys from another folder (made-up keys in the tests)

The last line printed is `SCORE <number>` and nothing else.
"""
import argparse
import difflib
import re
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import common
from common import ScorerError

common.point_app_at_scratch()

from backend.app.modules.claims import wording as W  # noqa: E402
from backend.app.modules.claims.checks import LINK_EXTRA_CHECKS  # noqa: E402
from backend.app.modules.relationships import linking  # noqa: E402

# ---------------------------------------------------------------------------
# Weights of the headline score (spec 3.4). Change them here and nowhere else.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "obligation_f1": 0.35,
    "links": 0.15,
    "effective": 0.10,
    "applies_to": 0.10,
    "summary_changes": 0.15,
    "no_false_alarm": 0.15,
}
LEAK_PENALTY = 200.0
FALSE_CHANGE_PENALTY = 0.5  # per false change claim, per row, inside the links score
OVERLAP_MIN = 0.5  # quotes match when they overlap by at least this share of the shorter quote

TYPE_MAP = {
    "MANDATORY": "must", "PROHIBITION": "must_not", "PERMISSION": "may", "REPORTING": "report",
    "RECORD_RETENTION": "keep_records", "APPROVAL": "get_approval", "DISCLOSURE": "disclose",
    "CONDITIONAL": "must", "RECOMMENDATION": "must",
}
ENTITY_MAP = {
    "SCHEDULED_BANK": "all_scheduled_banks", "SCHEDULED_COMMERCIAL_BANK": "all_scheduled_banks",
    "STATE_OWNED_BANK": "state_owned_banks", "PRIVATE_COMMERCIAL_BANK": "private_commercial_banks",
    "ISLAMIC_BANK": "islamic_banks", "FOREIGN_BANK": "foreign_banks", "SPECIALIZED_BANK": "specialized_banks",
    "NBFI": "nbfis", "AUTHORIZED_DEALER": "authorized_dealers", "MONEY_CHANGER": "money_changers",
    "PAYMENT_SERVICE_PROVIDER": "payment_system_operators", "MOBILE_FINANCIAL_SERVICE": "mfs_providers",
    "MICROFINANCE_INSTITUTION": "mfis", "EXCHANGE_HOUSE": "exchange_houses",
    "OFFSHORE_BANKING_UNIT": "offshore_banking_units",
}
SCHEDULED_SUBTYPES = {"state_owned_banks", "private_commercial_banks", "islamic_banks", "foreign_banks", "specialized_banks"}
CHANGE_TYPES = {"amends", "repeals", "replaces"}
LINK_TYPE_MAP = {"AMENDS": "amends", "REPEALS": "repeals", "REPLACES": "replaces", "SUPERSEDES": "replaces",
                 "CLARIFIES": "clarifies", "REFERENCES": "references", "IMPLEMENTS": "references", "RELATED_TO": "references"}

# Frequency words, English and Bangla, each mapped to one name.
FREQUENCY_WORDS = {
    "daily": ("daily", "every day", "প্রতিদিন", "দৈনিক"),
    "weekly": ("weekly", "every week", "প্রতি সপ্তাহ", "সাপ্তাহিক"),
    "fortnightly": ("fortnightly", "পাক্ষিক"),
    "monthly": ("monthly", "every month", "each month", "প্রতি মাস", "মাসিক"),
    "quarterly": ("quarterly", "each quarter", "every quarter", "ত্রৈমাসিক", "প্রতি কোয়ার্টার"),
    "half_yearly": ("half-yearly", "half yearly", "halfyearly", "bi-annual", "biannual", "semi-annual", "semiannual",
                    "six-monthly", "ষান্মাসিক", "অর্ধবার্ষিক"),
    "annual": ("annual", "annually", "yearly", "every year", "each year", "বার্ষিক", "প্রতি বছর"),
}
APP_FREQUENCY = {"DAILY": "daily", "WEEKLY": "weekly", "MONTHLY": "monthly", "QUARTERLY": "quarterly",
                 "BI_ANNUAL": "half_yearly", "ANNUAL": "annual"}


# ---------------------------------------------------------------------------
# Text overlap
# ---------------------------------------------------------------------------
@lru_cache(maxsize=200000)
def _overlap_norm(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if short in long_:
        return 1.0
    sm = difflib.SequenceMatcher(None, short, long_, autojunk=False)
    matched = sum(block.size for block in sm.get_matching_blocks())
    return matched / len(short)


def overlap(a: str, b: str) -> float:
    """Share of the shorter text that is found in the other (after the app's own text clean-up)."""
    return _overlap_norm(W.norm(a), W.norm(b))


def best_overlap(frags: List[Tuple[str, str]], page_id: Optional[str], text: str) -> float:
    """Overlap of a key quote with the predicted fragments that sit on the same page."""
    best = 0.0
    for pid, t in frags:
        if page_id and pid != page_id:
            continue
        best = max(best, overlap(t, text))
    return best


# ---------------------------------------------------------------------------
# Reading the key and the run
# ---------------------------------------------------------------------------
def load_key(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enclosure_pages(key: Dict[str, Any]) -> Set[str]:
    pages: Set[str] = set()
    for e in key.get("enclosures") or []:
        for p in e.get("page_ids") or []:
            pages.add(p)
    for n in key.get("page_notes") or []:
        if n.get("content") == "enclosure" and n.get("page_id"):
            pages.add(n["page_id"])
    return pages


def frags_of(claim: Dict[str, Any]) -> List[Tuple[str, str]]:
    return [(f["page_id"], f["text"]) for f in claim.get("fragments") or []]


def claim_pages(claim: Dict[str, Any]) -> Set[str]:
    pages = {f["page_id"] for f in claim.get("fragments") or []}
    return pages or set(claim.get("evidence_pages") or [])


def checks_failed(claim: Dict[str, Any]) -> List[str]:
    return [c["name"] for c in claim.get("checks") or [] if c.get("result") == "FAIL"]


# ---------------------------------------------------------------------------
# Field comparisons
# ---------------------------------------------------------------------------
def map_entity(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip()
    if v.upper() in ENTITY_MAP:
        return ENTITY_MAP[v.upper()]
    if v.lower().startswith("other:"):
        return v.lower()
    if v.lower() in ENTITY_MAP.values():
        return v.lower()
    ent = W.entity_for(v)
    if ent and ent in ENTITY_MAP:
        return ENTITY_MAP[ent]
    return "other:" + v.lower()


def entities_equal(pred: Optional[str], key: Optional[str]) -> bool:
    if not pred or not key:
        return False
    if pred.startswith("other:") and key.startswith("other:"):
        return True
    return pred == key


def freq_words_in(text: str) -> Set[str]:
    t = W.norm(text)
    return {name for name, words in FREQUENCY_WORDS.items() if any(w in t for w in words)}


def deadline_right(claim_fields: Dict[str, Any], key_deadline: Optional[str]) -> bool:
    pred_deadline = (claim_fields.get("deadline") or claim_fields.get("deadline_text") or None)
    pred_freq = APP_FREQUENCY.get(str(claim_fields.get("frequency") or "").upper())
    if not key_deadline:
        return not pred_deadline and not pred_freq
    key_date = W.parse_iso_date(key_deadline)
    if key_date is not None:
        if pred_deadline:
            if W.parse_iso_date(pred_deadline) == key_date:
                return True
            return key_date in W.dates_in(str(pred_deadline))
        return False
    # Relative wording or a frequency word.
    key_freq = freq_words_in(key_deadline)
    pred_words = freq_words_in(str(pred_deadline or ""))
    if pred_freq:
        pred_words.add(pred_freq)
    if key_freq and key_freq & pred_words:
        return True
    if pred_deadline:
        # Different numbers are a different deadline, however alike the words ("within 15 days" vs "within 30 days").
        k_nums = {w for w in content_words(key_deadline) if w.isdigit()}
        p_nums = {w for w in content_words(str(pred_deadline)) if w.isdigit()}
        if k_nums and p_nums and k_nums != p_nums:
            return False
        ratio = difflib.SequenceMatcher(None, W.norm(str(pred_deadline)), W.norm(key_deadline)).ratio()
        if ratio >= 0.8:
            return True
        # Same meaning in other words (added 14 Nov, AUTORESEARCH_LOG round 8): every content word of one wording
        # is in the other ("within 1 month of the circular date" = "within 1 month from the date of this circular").
        # Numbers are content words, so "within 15 days" never matches "within 30 days".
        k, p = content_words(key_deadline), content_words(str(pred_deadline))
        if k and k <= p:
            return True
        if len(p) >= 2 and p <= k:
            return True
    return False


_DEADLINE_STOP = {"the", "of", "a", "an", "from", "this", "that", "to", "at", "on", "in", "by", "for", "and", "or", "its",
                  "is", "be", "upcoming", "said"}


def content_words(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+|[ঀ-৿]+", W.norm(text))
    out = set()
    for w in words:
        if w in _DEADLINE_STOP:
            continue
        if w.isdigit():
            w = w.lstrip("0") or "0"
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def obligation_fields_right(claim: Dict[str, Any], key_ob: Dict[str, Any]) -> Dict[str, bool]:
    f = claim.get("fields") or {}
    pred_type = TYPE_MAP.get(str(f.get("obligation_type") or "MANDATORY").upper(), "must")
    return {
        "type": pred_type == key_ob.get("type"),
        "subject": entities_equal(map_entity(f.get("who")), map_entity(key_ob.get("subject"))),
        "deadline": deadline_right(f, key_ob.get("deadline")),
    }


# ---------------------------------------------------------------------------
# Matching obligations (spec 3.1)
# ---------------------------------------------------------------------------
def match_obligations(preds: List[Dict[str, Any]], key_obs: List[Dict[str, Any]]) -> Dict[int, Tuple[int, float, Dict[str, bool]]]:
    """One-to-one, best overlap first. Returns {index of prediction: (index of key item, overlap, field results)}."""
    cands = []
    for pi, c in enumerate(preds):
        frags = frags_of(c)
        for ki, k in enumerate(key_obs):
            ov = best_overlap(frags, k.get("page_id"), k.get("quote") or "")
            if ov >= OVERLAP_MIN:
                fields = obligation_fields_right(c, k)
                cands.append((ov, sum(fields.values()), 1 if c.get("shown") else 0, pi, ki, fields))
    cands.sort(key=lambda x: (-round(x[0], 6), -x[1], -x[2], x[3], x[4]))
    used_p: Set[int] = set()
    used_k: Set[int] = set()
    out: Dict[int, Tuple[int, float, Dict[str, bool]]] = {}
    for ov, _n, _s, pi, ki, fields in cands:
        if pi in used_p or ki in used_k:
            continue
        used_p.add(pi)
        used_k.add(ki)
        out[pi] = (ki, ov, fields)
    return out


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------
def key_link_keys(rel: Dict[str, Any]) -> Set[str]:
    ref = rel.get("target_reference") or ""
    keys = set(linking.reference_keys(ref))
    if rel.get("target_date"):
        keys |= set(linking.reference_keys(f"{ref} dated {rel['target_date']}"))
    return keys


def pred_link_keys(claim: Dict[str, Any]) -> Set[str]:
    return set(linking.reference_keys((claim.get("fields") or {}).get("target_hint")))


def pred_link_type(claim: Dict[str, Any]) -> str:
    return LINK_TYPE_MAP.get(str((claim.get("fields") or {}).get("claimed_type") or "REFERENCES").upper(), "references")


def match_links(preds: List[Dict[str, Any]], key_rels: List[Dict[str, Any]], enclosed: Set[str]) -> Dict[int, Tuple[int, bool]]:
    """One-to-one by target reference; the same type is preferred. Returns {pred index: (key index, type equal)}."""
    cands = []
    for pi, c in enumerate(preds):
        if claim_pages(c) & enclosed:
            continue
        pk = pred_link_keys(c)
        for ki, r in enumerate(key_rels):
            if pk and pk & key_link_keys(r):
                cands.append((1 if pred_link_type(c) == r.get("type") else 0, 1 if c.get("shown") else 0, pi, ki))
    cands.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
    used_p: Set[int] = set()
    used_k: Set[int] = set()
    out: Dict[int, Tuple[int, bool]] = {}
    for same, _s, pi, ki in cands:
        if pi in used_p or ki in used_k:
            continue
        used_p.add(pi)
        used_k.add(ki)
        out[pi] = (ki, bool(same))
    return out


# ---------------------------------------------------------------------------
# Effective date
# ---------------------------------------------------------------------------
def predicted_effective(claims: List[Dict[str, Any]]) -> Tuple[Optional[date], str]:
    """The effective date the shown claims give, and its quote."""
    for c in claims:
        f = c.get("fields") or {}
        if c["kind"] == "DATE" and f.get("date_kind") == "EFFECTIVE" and c.get("shown"):
            d = W.parse_iso_date(f.get("date"))
            if d:
                return d, c.get("quote") or ""
    dates = []
    quotes = []
    for c in claims:
        if c["kind"] == "OBLIGATION" and c.get("shown"):
            d = W.parse_iso_date((c.get("fields") or {}).get("effective_date"))
            if d:
                dates.append(d)
                quotes.append(c.get("quote") or "")
    shown_obs = [c for c in claims if c["kind"] == "OBLIGATION" and c.get("shown")]
    if dates and len(set(dates)) == 1 and len(dates) == len(shown_obs):
        return dates[0], quotes[0]
    return None, ""


def effective_result(key: Dict[str, Any], claims: List[Dict[str, Any]], issue: Optional[date]) -> Dict[str, Any]:
    eff = key.get("effective") or {}
    basis = eff.get("basis")
    pred, quote = predicted_effective(claims)
    right = False
    if basis == "stated":
        right = pred is not None and pred == W.parse_iso_date(eff.get("date"))
    elif basis == "immediate":
        right = pred is not None and issue is not None and pred == issue and W.has_immediate_effect(quote)
    elif basis == "not_stated":
        right = pred is None
    return {
        "basis": basis, "right": right, "predicted": pred.isoformat() if pred else None,
        "issue_date_as_effective": basis == "not_stated" and pred is not None and issue is not None and pred == issue,
    }


# ---------------------------------------------------------------------------
# One circular
# ---------------------------------------------------------------------------
def row_failed(run: Dict[str, Any]) -> bool:
    return run.get("status") != "OK" or not run.get("claims")


def new_counts() -> Counter:
    return Counter()


def score_row(key: Dict[str, Any], run: Dict[str, Any], window: Optional[Set[str]] = None,
              issue_fallback: Optional[date] = None) -> Dict[str, Any]:
    """All counts for one circular, plus a label (right or wrong) for every scored claim."""
    n = new_counts()
    labelled: List[Dict[str, Any]] = []
    key_obs = key.get("obligations") or []
    key_rels = key.get("relationships") or []
    key_applies = key.get("applies_to") or []
    key_exempt = key.get("exempt") or []
    key_points = list(key.get("summary_points") or []) + list(key.get("key_changes") or [])
    enclosed = enclosure_pages(key)
    issue = W.parse_iso_date((key.get("metadata") or {}).get("issue_date")) or issue_fallback

    n["rows"] = 1
    n["key_obligations"] = len(key_obs)
    n["key_links"] = len(key_rels)
    n["key_points"] = len(key_points)
    n["key_exempt"] = len(key_exempt)
    key_ents = {map_entity(a.get("entity")) for a in key_applies if a.get("entity")}
    n["key_applies"] = len(key_ents)

    failed = row_failed(run)
    if failed:
        n["failed_rows"] = 1
        eff_key = key.get("effective") or {}
        return {"counts": n, "labelled": [], "effective": {"basis": eff_key.get("basis"), "right": False, "predicted": None,
                                                           "issue_date_as_effective": False},
                "failed": True, "status": run.get("status")}

    claims = run["claims"]
    n["claims_total"] = len([c for c in claims if c["kind"] != "PROVISION"])
    n["claims_shown"] = len([c for c in claims if c["kind"] != "PROVISION" and c.get("shown")])
    n["claims_hidden"] = n["claims_total"] - n["claims_shown"]

    def label(claim: Dict[str, Any], right: bool) -> None:
        labelled.append({"kind": claim["kind"], "shown": bool(claim.get("shown")), "right": right,
                         "failed": checks_failed(claim), "checks": [c["name"] for c in claim.get("checks") or []
                                                                   if c.get("result") in ("PASS", "FAIL")],
                         "link_extra_only": claim["kind"] == "LINK"})

    # -- obligations ----------------------------------------------------------------------
    obs = [c for c in claims if c["kind"] == "OBLIGATION"]
    in_window = []
    for c in obs:
        pages = claim_pages(c)
        if window is not None and pages and not (pages & window):
            n["obligations_outside_window"] += 1
            continue
        in_window.append(c)
    matches = match_obligations(in_window, key_obs)
    shown_ob = 0
    for pi, c in enumerate(in_window):
        m = matches.get(pi)
        fully = bool(m) and all(m[2].values())
        if claim_pages(c) & enclosed:
            n["obligations_on_enclosures"] += 1
        shown = bool(c.get("shown"))
        if shown:
            shown_ob += 1
        if m:
            n["ob_matched_all"] += 1
            for fname, ok in m[2].items():
                n[f"ob_field_{fname}_total"] += 1
                n[f"ob_field_{fname}_right"] += int(ok)
            if shown:
                n["ob_matched_shown"] += 1
                if fully:
                    n["ob_fully_right_shown"] += 1
        label(c, fully)
    n["ob_pred_shown"] = shown_ob
    n["ob_pred_all"] = len(in_window)

    # -- applies to / exemptions -----------------------------------------------------------
    applies = [c for c in claims if c["kind"] == "APPLIES_TO"]
    pred_ents_shown: List[str] = []
    for c in applies:
        e = map_entity((c.get("fields") or {}).get("entity"))
        ok = any(entities_equal(e, k) or (k == "all_scheduled_banks" and e in SCHEDULED_SUBTYPES) for k in key_ents if k)
        if c.get("shown") and e:
            pred_ents_shown.append(e)
            n["applies_pred_shown"] += 1
            n["applies_pred_right"] += int(ok)
        label(c, ok)
    for k in key_ents:
        if not k:
            continue
        if any(entities_equal(e, k) or (k == "all_scheduled_banks" and e in SCHEDULED_SUBTYPES) for e in pred_ents_shown):
            n["applies_key_found"] += 1

    exempts = [c for c in claims if c["kind"] == "EXEMPTION"]
    for c in exempts:
        ok = any(best_overlap(frags_of(c), k.get("page_id"), k.get("quote") or "") >= OVERLAP_MIN for k in key_exempt)
        if c.get("shown"):
            n["exempt_pred_shown"] += 1
            n["exempt_pred_right"] += int(ok)
        label(c, ok)
    shown_exempts = [c for c in exempts if c.get("shown")]
    for k in key_exempt:
        if any(best_overlap(frags_of(c), k.get("page_id"), k.get("quote") or "") >= OVERLAP_MIN for c in shown_exempts):
            n["exempt_key_found"] += 1

    # -- summary points and key changes ------------------------------------------------------
    points = [c for c in claims if c["kind"] in ("SUMMARY_POINT", "KEY_CHANGE")]
    support = [(k.get("page_id"), k.get("quote") or "") for k in key_points] + [(k.get("page_id"), k.get("quote") or "") for k in key_obs]
    shown_points = [c for c in points if c.get("shown")]
    for c in points:
        ok = any(best_overlap(frags_of(c), pid, q) >= OVERLAP_MIN for pid, q in support)
        if c.get("shown"):
            n["points_pred_shown"] += 1
            n["points_pred_right"] += int(ok)
        label(c, ok)
    for k in key_points:
        if any(best_overlap(frags_of(c), k.get("page_id"), k.get("quote") or "") >= OVERLAP_MIN for c in shown_points):
            n["points_key_found"] += 1

    # -- dates -----------------------------------------------------------------------------
    key_deadline_dates = {W.parse_iso_date(o.get("deadline")) for o in key_obs if o.get("deadline")} - {None}
    eff = effective_result(key, claims, issue)
    key_eff_date = W.parse_iso_date((key.get("effective") or {}).get("date"))
    for c in [c for c in claims if c["kind"] == "DATE"]:
        f = c.get("fields") or {}
        d = W.parse_iso_date(f.get("date"))
        if f.get("date_kind") == "EFFECTIVE":
            basis = (key.get("effective") or {}).get("basis")
            if basis == "stated":
                ok = d is not None and d == key_eff_date
            elif basis == "immediate":
                ok = d is not None and issue is not None and d == issue and W.has_immediate_effect(c.get("quote") or "")
            else:
                ok = False
        else:
            ok = d is not None and d in key_deadline_dates
        label(c, ok)

    # -- links ------------------------------------------------------------------------------
    links = [c for c in claims if c["kind"] == "LINK"]
    link_matches = match_links(links, key_rels, enclosed)
    shown_links = 0
    for pi, c in enumerate(links):
        m = link_matches.get(pi)
        ptype = pred_link_type(c)
        right = bool(m) and m[1]
        shown = bool(c.get("shown"))
        if shown:
            shown_links += 1
            if m:
                n["links_matched_shown"] += 1
                n["links_type_right_shown"] += int(m[1])
            if ptype in CHANGE_TYPES:
                # A change claim is false when the key has no such link, or says it only references or clarifies.
                key_type = key_rels[m[0]].get("type") if m else None
                if key_type not in CHANGE_TYPES:
                    n["false_change_claims"] += 1
        label(c, right)
    n["links_pred_shown"] = shown_links
    # A key link counts as found when a shown prediction matched it.
    shown_matches = {pi: m for pi, m in link_matches.items() if links[pi].get("shown")}
    n["links_key_found"] = len({m[0] for m in shown_matches.values()})
    n["links_key_found_typed"] = len({m[0] for m in shown_matches.values() if m[1]})

    # -- the labels crossed with shown / hidden (spec 3.3) -------------------------------------
    for lab in labelled:
        if lab["right"]:
            n["right_total"] += 1
            n["right_hidden"] += int(not lab["shown"])
            n["right_shown"] += int(lab["shown"])
        else:
            n["wrong_total"] += 1
            n["wrong_shown"] += int(lab["shown"])
        n["shown_total"] += int(lab["shown"])

    return {"counts": n, "labelled": labelled, "effective": eff, "failed": False, "status": run.get("status")}


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------
def f1(tp: float, pred: float, key: float) -> Tuple[float, float, float]:
    p = tp / pred if pred else 0.0
    r = tp / key if key else 0.0
    return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)


def metrics(counts: Counter, eff_right: int, eff_rows: int) -> Dict[str, Any]:
    n = counts
    ob_p, ob_r, ob_f1 = f1(n["ob_fully_right_shown"], n["ob_pred_shown"], n["key_obligations"])
    # Applies to: a predicted entity is right, a key entity is found: micro precision and recall.
    ap_p = n["applies_pred_right"] / n["applies_pred_shown"] if n["applies_pred_shown"] else 0.0
    ap_r = n["applies_key_found"] / n["key_applies"] if n["key_applies"] else 0.0
    ap_f1 = 2 * ap_p * ap_r / (ap_p + ap_r) if (ap_p + ap_r) else 0.0
    sp = n["points_pred_right"] / n["points_pred_shown"] if n["points_pred_shown"] else 0.0
    sr = n["points_key_found"] / n["key_points"] if n["key_points"] else 0.0
    sf = 2 * sp * sr / (sp + sr) if (sp + sr) else 0.0
    ex_p = n["exempt_pred_right"] / n["exempt_pred_shown"] if n["exempt_pred_shown"] else 0.0
    ex_r = n["exempt_key_found"] / n["key_exempt"] if n["key_exempt"] else 0.0
    link_recall = n["links_key_found"] / n["key_links"] if n["key_links"] else 0.0
    link_prec = n["links_matched_shown"] / n["links_pred_shown"] if n["links_pred_shown"] else 0.0
    type_acc = n["links_type_right_shown"] / n["links_matched_shown"] if n["links_matched_shown"] else 0.0
    rows = max(1, n["rows"])
    links_score = max(0.0, link_recall * type_acc - FALSE_CHANGE_PENALTY * n["false_change_claims"] / rows)
    eff_acc = eff_right / eff_rows if eff_rows else 0.0
    leak = n["wrong_shown"] / n["shown_total"] if n["shown_total"] else 0.0
    false_alarm = n["right_hidden"] / n["right_total"] if n["right_total"] else 0.0
    score = 100 * (
        WEIGHTS["obligation_f1"] * ob_f1
        + WEIGHTS["links"] * links_score
        + WEIGHTS["effective"] * eff_acc
        + WEIGHTS["applies_to"] * ap_f1
        + WEIGHTS["summary_changes"] * sf
        + WEIGHTS["no_false_alarm"] * (1 - false_alarm)
    ) - LEAK_PENALTY * leak
    return {
        "score": score,
        "obligation": {"precision": ob_p, "recall": ob_r, "f1": ob_f1, "key": n["key_obligations"],
                       "predicted_shown": n["ob_pred_shown"], "fully_right_shown": n["ob_fully_right_shown"],
                       "matched_all": n["ob_matched_all"], "outside_window": n["obligations_outside_window"],
                       "on_enclosures": n["obligations_on_enclosures"],
                       "type_accuracy": _ratio(n["ob_field_type_right"], n["ob_field_type_total"]),
                       "subject_accuracy": _ratio(n["ob_field_subject_right"], n["ob_field_subject_total"]),
                       "deadline_accuracy": _ratio(n["ob_field_deadline_right"], n["ob_field_deadline_total"])},
        "links": {"score": links_score, "recall": link_recall, "precision": link_prec, "type_accuracy": type_acc,
                  "false_change_claims": n["false_change_claims"], "key": n["key_links"], "predicted_shown": n["links_pred_shown"]},
        "effective": {"accuracy": eff_acc, "right": eff_right, "rows": eff_rows},
        "applies_to": {"precision": ap_p, "recall": ap_r, "f1": ap_f1},
        "summary_changes": {"precision": sp, "recall": sr, "f1": sf, "key": n["key_points"], "predicted_shown": n["points_pred_shown"]},
        "exemptions": {"precision": ex_p, "recall": ex_r, "key": n["key_exempt"], "predicted_shown": n["exempt_pred_shown"]},
        "leak_rate": leak, "false_alarm_rate": false_alarm,
        "claims": {"shown": n["claims_shown"], "hidden": n["claims_hidden"], "total": n["claims_total"],
                   "wrong_shown": n["wrong_shown"], "right_hidden": n["right_hidden"], "right_total": n["right_total"],
                   "shown_scored": n["shown_total"]},
    }


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def check_stats(row_results: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """For each check: how often it failed a right claim (false alarm) and how often it failed a wrong claim (caught)."""
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"right_applicable": 0, "wrong_applicable": 0,
                                                            "failed_right": 0, "failed_wrong": 0, "shape_only": 0})
    for rr in row_results:
        for lab in rr["labelled"]:
            for name in lab["checks"]:
                s = stats[name]
                s["right_applicable" if lab["right"] else "wrong_applicable"] += 1
                if name in LINK_EXTRA_CHECKS:
                    s["shape_only"] = 1
            for name in lab["failed"]:
                stats[name]["failed_right" if lab["right"] else "failed_wrong"] += 1
    return dict(stats)


def score_all(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`rows` is a list of {row, key, run, window, issue, meta}. Returns the totals, each row's own numbers and the check table."""
    total = new_counts()
    per_row = []
    eff_right = 0
    results = []
    for r in rows:
        rr = score_row(r["key"], r["run"], r.get("window"), r.get("issue"))
        results.append(rr)
        total.update(rr["counts"])
        eff_right += int(rr["effective"]["right"])
        m = metrics(rr["counts"], int(rr["effective"]["right"]), 1)
        per_row.append({"row": r["row"], "status": rr["status"], "metrics": m, "effective": rr["effective"],
                        "calls": r["run"].get("calls_made", 0), "tokens": (r["run"].get("tokens") or {}).get("total", 0),
                        "seconds": (r["run"].get("model_latency_ms") or 0) / 1000.0, "cache_hit": r["run"].get("cache_hit")})
    m = metrics(total, eff_right, len(rows))
    m["effective"]["issue_date_as_effective"] = sum(int(rr["effective"].get("issue_date_as_effective", False)) for rr in results)
    m["rows"] = {"scored": len(rows), "failed": total["failed_rows"]}
    return {"total": m, "per_row": per_row, "checks": check_stats(results)}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def render_report(candidate: str, split: str, result: Dict[str, Any], missing: Dict[str, List[int]]) -> str:
    t = result["total"]
    lines: List[str] = []
    a = lines.append
    a(f"Candidate {candidate}, split {split}: {t['rows']['scored']} circulars scored ({t['rows']['failed']} failed rows count as zero)")
    if missing["no_key"]:
        a(f"  No answer key yet for {len(missing['no_key'])} circulars with a run: {', '.join(map(str, missing['no_key'][:20]))}{' ...' if len(missing['no_key']) > 20 else ''}")
    if missing["no_run"]:
        a(f"  No run yet for {len(missing['no_run'])} circulars with a key: {', '.join(map(str, missing['no_run'][:20]))}{' ...' if len(missing['no_run']) > 20 else ''}")
    a("")
    a("Headline numbers")
    a(f"  Obligations (fully right, shown): precision {pct(t['obligation']['precision'])}  recall {pct(t['obligation']['recall'])}  F1 {pct(t['obligation']['f1'])}"
      f"   ({t['obligation']['fully_right_shown']} right of {t['obligation']['predicted_shown']} shown, key has {t['obligation']['key']})")
    a(f"    field accuracy on matched: type {pct(t['obligation']['type_accuracy'])}  who {pct(t['obligation']['subject_accuracy'])}  deadline {pct(t['obligation']['deadline_accuracy'])}")
    a(f"    outside the key's page window (not scored): {t['obligation']['outside_window']}; on enclosure pages (wrong): {t['obligation']['on_enclosures']}")
    a(f"  Links: score {pct(t['links']['score'])}  recall {pct(t['links']['recall'])}  precision {pct(t['links']['precision'])}  type accuracy {pct(t['links']['type_accuracy'])}"
      f"  false change claims {t['links']['false_change_claims']}")
    a(f"  Effective date: {pct(t['effective']['accuracy'])} ({t['effective']['right']} of {t['effective']['rows']}); issue date given as effective when the key says not stated: {t['effective']['issue_date_as_effective']}")
    a(f"  Applies to: precision {pct(t['applies_to']['precision'])}  recall {pct(t['applies_to']['recall'])}  F1 {pct(t['applies_to']['f1'])}")
    a(f"  Summary points and key changes (evidence overlap): precision {pct(t['summary_changes']['precision'])}  recall {pct(t['summary_changes']['recall'])}  F1 {pct(t['summary_changes']['f1'])}")
    a(f"  Exemptions: precision {pct(t['exemptions']['precision'])}  recall {pct(t['exemptions']['recall'])}   (not in the score)")
    c = t["claims"]
    a(f"  Claims: {c['shown']} shown, {c['hidden']} hidden of {c['total']} scored kinds")
    a(f"  LEAK RATE (wrong and shown / shown): {pct(t['leak_rate'])}  ({c['wrong_shown']} of {c['shown_scored']})")
    a(f"  FALSE-ALARM RATE (right and hidden / right): {pct(t['false_alarm_rate'])}  ({c['right_hidden']} of {c['right_total']})")
    a("")
    a("Per circular")
    a("  row    status        ob F1   links  eff  applies  summary  shown/hid  leak   calls  tokens   secs")
    for r in result["per_row"]:
        m = r["metrics"]
        a(f"  {r['row']:<6} {r['status']:<13} {pct(m['obligation']['f1'])} {pct(m['links']['score'])} {'yes' if r['effective']['right'] else ' no'} "
          f"{pct(m['applies_to']['f1'])} {pct(m['summary_changes']['f1'])}  {m['claims']['shown']:>3}/{m['claims']['hidden']:<3}   "
          f"{pct(m['leak_rate'])} {r['calls']:>5} {r['tokens']:>8} {r['seconds']:>6.1f}")
    a("")
    a("Code checks: how often each check failed a RIGHT claim (false alarm) and a WRONG claim (caught)")
    a("  check            on right  fail on right   on wrong  fail on wrong")
    for name, s in sorted(result["checks"].items()):
        note = "  (decides link wording only)" if s["shape_only"] else ""
        a(f"  {name:<16} {s['right_applicable']:>8}  {s['failed_right']:>13}   {s['wrong_applicable']:>8}  {s['failed_wrong']:>13}{note}")
    return "\n".join(lines)


def render_diff(a_name: str, b_name: str, a: Dict[str, Any], b: Dict[str, Any], top: int = 10) -> str:
    by_a = {r["row"]: r for r in a["per_row"]}
    by_b = {r["row"]: r for r in b["per_row"]}
    rows = sorted(set(by_a) & set(by_b))
    diffs = sorted(rows, key=lambda r: -abs(by_a[r]["metrics"]["score"] - by_b[r]["metrics"]["score"]))
    out = [f"Rows where {a_name} and {b_name} differ most (row score, then leak rate and obligation F1):"]
    for r in diffs[:top]:
        ma, mb = by_a[r]["metrics"], by_b[r]["metrics"]
        out.append(f"  row {r}: {ma['score']:6.1f} vs {mb['score']:6.1f} (diff {ma['score'] - mb['score']:+.1f})   "
                   f"leak {pct(ma['leak_rate'])} vs {pct(mb['leak_rate'])}   ob F1 {pct(ma['obligation']['f1'])} vs {pct(mb['obligation']['f1'])}")
    ta, tb = a["total"], b["total"]
    out.append(f"  Total: {ta['score']:.2f} vs {tb['score']:.2f} on {len(rows)} shared rows")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Loading everything and running
# ---------------------------------------------------------------------------
def gather(candidate: str, split: str, keys_dir: Path, runs_dir: Path, rows: Optional[List[int]]):
    infos = {r.row: r for r in common.load_rows(split, rows)}
    runs = {int(p.stem): p for p in runs_dir.glob("*.json") if p.stem.isdigit()}
    items = []
    no_key: List[int] = []
    no_run: List[int] = []
    for rid in sorted(infos):
        kp = keys_dir / f"{rid}.json"
        has_key = kp.exists()
        has_run = rid in runs
        if has_key and has_run:
            info = infos[rid]
            window = {p.page_id for p in info.pages if p.in_window}
            try:
                issue = date.fromisoformat(info.date)
            except ValueError:
                issue = None
            items.append({"row": rid, "key": load_key(kp), "run": common.read_json(runs[rid]), "window": window, "issue": issue})
        elif has_run:
            no_key.append(rid)
        elif has_key:
            no_run.append(rid)
    return items, {"no_key": no_key, "no_run": no_run}


def run_score(args: argparse.Namespace) -> int:
    common.require_split(args.split, args.final)
    keys_dir = Path(args.keys_dir) if args.keys_dir else common.keys_dir(args.split)
    runs_dir = Path(args.runs_dir) if args.runs_dir else common.runs_dir(args.candidate)
    items, missing = gather(args.candidate, args.split, keys_dir, runs_dir, common.parse_rows_arg(args.rows))
    if not items:
        raise ScorerError(
            f"Nothing to score: no circular has both a run and an answer key. Keys are read from {keys_dir} "
            f"({len(missing['no_run'])} keys waiting for a run, {len(missing['no_key'])} runs waiting for a key)."
        )
    result = score_all(items)
    text = render_report(args.candidate, args.split, result, missing)
    print(text)
    if args.diff:
        other_dir = Path(args.runs_dir).parent / args.diff if args.runs_dir else common.runs_dir(args.diff)
        other_items, _ = gather(args.diff, args.split, keys_dir, other_dir, common.parse_rows_arg(args.rows))
        if other_items:
            print("\n" + render_diff(args.candidate, args.diff, result, score_all(other_items)))
        else:
            print(f"\nNo runs found for {args.diff}; nothing to compare.")
    stamp = datetime.now().strftime("%Y%m%d")
    try:
        rp = common.reports_dir() / f"{common.safe_name(args.candidate)}_{args.split}_{stamp}.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        print(f"(report file not written: {e})")
    if args.json:
        common.write_json(Path(args.json), result)
    score = result["total"]["score"]
    if args.final:
        common.log_final(args.candidate, f"score {args.split}", score)
    print(f"SCORE {score:.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Score a candidate's runs against the answer keys.")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--rows")
    ap.add_argument("--json", help="also write every number to this file")
    ap.add_argument("--diff", help="another candidate name: show the rows where the two differ most")
    ap.add_argument("--keys-dir", help="read answer keys from this folder instead (used by the tests)")
    ap.add_argument("--runs-dir", help="read runs from this folder instead (used by the tests)")
    ap.add_argument("--final", action="store_true", help="needed for --split test (final run only)")
    args = ap.parse_args()
    try:
        return run_score(args)
    except ScorerError as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
