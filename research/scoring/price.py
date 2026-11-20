"""Price one run of a candidate over a split, before anything is sent. Calls nothing.

Per circular: input tokens and output tokens from the saved free runs of the same circular (the real
counts the model reported), or a rough estimate from the text length when there is none. Then times the
candidate's prices, which are written in its config file together with the page and date they were checked:
    "price_input_per_mtok", "price_output_per_mtok"   (US dollars per million tokens)
    "batch_discount"                                  (for example 0.5 when the vendor halves the price for batches)
    "price_source", "price_checked"                   (the vendor's own price page, and the date)

Usage (repo root):
    .venv\\Scripts\\python.exe research\\scoring\\price.py --candidate paid_example --split dev
"""
import argparse
import asyncio
import math
import statistics
import sys
from typing import Any, Dict, List

import common
from common import ScorerError

common.point_app_at_scratch()
common.assert_scratch_database()

FALLBACK_OUTPUT_TOKENS = 3000


def estimate_input_tokens(req: Dict[str, Any]) -> int:
    """Rough count when no real one exists: about 4 English characters per token, about 2 other characters per token."""
    text = (req["system"] or "") + (req["user"] or "")
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return math.ceil(ascii_chars / 4 + other / 2)


def saved_usage(unit: str) -> List[Dict[str, int]]:
    """Real token counts from any saved answer for this circular."""
    out = []
    for f in common.cache_dir().glob(f"{common.safe_name(unit)}__*.json"):
        try:
            usage = common.read_json(f)["response"].get("token_usage") or {}
        except (OSError, ValueError, KeyError):
            continue
        if usage.get("prompt_tokens"):
            out.append({"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)})
    return out


def estimate(cand: common.Candidate, reqs: List[Dict[str, Any]]) -> Dict[str, Any]:
    raw = cand.raw
    rows = []
    known_outputs = []
    for r in reqs:
        usage = saved_usage(r["unit"])
        if usage:
            tin, tout, basis = usage[0]["in"], usage[0]["out"], "saved run"
            known_outputs.append(tout)
        else:
            tin, tout, basis = estimate_input_tokens(r), None, "estimate"
        rows.append({"row": r["row"], "unit": r["unit"], "input": tin, "output": tout, "basis": basis})
    typical_out = int(statistics.median(known_outputs)) if known_outputs else FALLBACK_OUTPUT_TOKENS
    for r in rows:
        if r["output"] is None:
            r["output"] = typical_out
    tot_in = sum(r["input"] for r in rows)
    tot_out = sum(r["output"] for r in rows)
    p_in, p_out = raw.get("price_input_per_mtok"), raw.get("price_output_per_mtok")
    out: Dict[str, Any] = {"rows": rows, "input_tokens": tot_in, "output_tokens": tot_out, "priced": False}
    if p_in is not None and p_out is not None:
        standard = tot_in / 1e6 * float(p_in) + tot_out / 1e6 * float(p_out)
        discount = float(raw.get("batch_discount", 1.0))
        out.update(priced=True, standard_usd=standard, batch_usd=standard * discount, batch_discount=discount,
                   source=raw.get("price_source"), checked=raw.get("price_checked"))
    return out


def print_estimate(cand: common.Candidate, est: Dict[str, Any]) -> None:
    n_saved = sum(1 for r in est["rows"] if r["basis"] == "saved run")
    print(f"\nPrice estimate for {cand.name} ({cand.model}), {len(est['rows'])} circulars:")
    print(f"  Input tokens:  {est['input_tokens']:,} ({n_saved} circulars from saved runs, the rest estimated from text length)")
    print(f"  Output tokens: {est['output_tokens']:,}")
    if not est["priced"]:
        print("  No prices in the candidate config. Fill in price_input_per_mtok, price_output_per_mtok, "
              "price_source and price_checked from the vendor's own price page.")
        return
    print(f"  Normal price: ${est['standard_usd']:.2f}")
    print(f"  Batch price:  ${est['batch_usd']:.2f} (batch discount factor {est['batch_discount']})")
    print(f"  Prices from: {est['source']} (checked {est['checked']})")
    if not est["source"] or not est["checked"]:
        print("  WARNING: the config has no price_source or price_checked. Do not trust this number.")


async def main_async(args: argparse.Namespace) -> int:
    common.require_split(args.split, args.final)
    import run_candidate as rc

    cand = common.load_candidate(args.candidate)
    rows = common.load_rows(args.split, common.parse_rows_arg(args.rows))
    variant = rc.load_prompt(cand)
    reqs = await rc.capture_requests(rows, cand, variant)
    skipped = len(rows) - len(reqs)
    if not reqs:
        raise ScorerError("No circular is ready (inputs missing), so there is nothing to price.")
    est = estimate(cand, reqs)
    print_estimate(cand, est)
    if skipped:
        print(f"  {skipped} circulars were left out because their inputs are not ready yet; the real total will be higher.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Estimate the cost of one run of a candidate over a split.")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--rows")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args))
    except ScorerError as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
