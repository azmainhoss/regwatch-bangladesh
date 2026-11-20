"""Simulate Decisions-API checks on saved runs (experiment, 14 Nov 2026). No model calls, no app code changed.

Reads runs\\<base>\\<row>.json and decisions\\<row>.json, writes runs\\<base>__<variant>\\<row>.json with a changed
`shown` flag on OBLIGATION claims, so score.py can score each variant:
  .venv\\Scripts\\python.exe research\\scoring\\decisions_sim.py --base gemini_flash_v6_types
  .venv\\Scripts\\python.exe research\\scoring\\score.py --candidate gemini_flash_v6_types__gate --split dev
Variants:
  gate     shown as now, AND the quoted sentences' best duty probability >= 0.5
  replace  duty-word check replaced: shown when every other check passes and duty >= 0.5 and the Decisions kind
           agrees with the claimed kind (or the claimed kind is MANDATORY/CONDITIONAL and Decisions says must/must_not)
"""
import argparse
import json
import shutil
from pathlib import Path

RUNS = Path(r"E:\regwatch-research\scoring\runs")
DEC = Path(r"E:\regwatch-research\scoring\decisions")
APP_TO_KIND = {"MANDATORY": "must", "CONDITIONAL": "must", "RECOMMENDATION": "must", "PROHIBITION": "must_not",
               "PERMISSION": "may", "REPORTING": "report", "RECORD_RETENTION": "keep_records", "APPROVAL": "get_approval",
               "DISCLOSURE": "disclose"}


def ids_of(claim: dict) -> list:
    ev = claim.get("evidence_ids")
    if isinstance(ev, dict):
        return list(ev.get("quote") or [])
    return list(ev or [])


def features(claim: dict, labels: dict) -> dict:
    ids = [i for i in ids_of(claim) if i in labels]
    if not ids:
        return {}
    duty = max(labels[i]["duty"] for i in ids)
    kinds: dict = {}
    for i in ids:
        for k, p in labels[i]["kind"].items():
            kinds[k] = kinds.get(k, 0) + p / len(ids)
    return {"duty": duty, "kind": max(kinds, key=kinds.get), "kinds": kinds}


def decide(variant: str, claim: dict, f: dict) -> bool:
    shown = bool(claim.get("shown"))
    if not f:
        return shown
    if variant == "gate":
        return shown and f["duty"] >= 0.5
    if variant == "replace":
        fails = [c["name"] for c in claim.get("checks") or [] if c.get("result") == "FAIL"]
        others_fail = [n for n in fails if n != "DUTY_WORDING"]
        if others_fail or not str(claim.get("quote_state") or "VERIFIED").startswith("VERIFIED"):
            return shown and f["duty"] >= 0.5
        claimed = APP_TO_KIND.get(str(claim["fields"].get("obligation_type") or "").upper(), "must")
        agree = f["kind"] == claimed or (claimed == "must" and f["kind"] in ("must", "must_not"))
        return f["duty"] >= 0.5 and agree
    raise ValueError(variant)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    for variant in ("gate", "replace"):
        out = RUNS / f"{a.base}__{variant}"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        changed = 0
        for f in (RUNS / a.base).glob("*.json"):
            run = json.loads(f.read_text(encoding="utf-8"))
            dfile = DEC / f.name
            labels = json.loads(dfile.read_text(encoding="utf-8")) if dfile.exists() else {}
            for c in run.get("claims") or []:
                if c["kind"] != "OBLIGATION":
                    continue
                new = decide(variant, c, features(c, labels))
                if new != bool(c.get("shown")):
                    changed += 1
                c["shown"] = new
            run["candidate"] = out.name
            (out / f.name).write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
        print(f"{out.name}: {changed} obligation claims changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
