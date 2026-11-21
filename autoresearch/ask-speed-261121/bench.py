"""Ask-a-question speed test: times /research/matches and /research/query for 12 questions,
both sent at once like the Ask screen does. Usage: python bench.py <label> [--matches-only]"""
import asyncio, json, sys, time, uuid, statistics, pathlib
import httpx

API = "http://localhost:8000/api/v1"
QUESTIONS = [
    "What is the minimum capital adequacy ratio for banks?",
    "loan classification and provisioning for SME loans",
    "When must banks submit the CRR and SLR return?",
    "What are the rules for opening a student file for foreign remittance?",
    "agent banking outlet requirements",
    "Interest rate cap on credit card loans",
    "How long must KYC records be kept?",
    "rescheduling of defaulted loans down payment",
    "mobile financial services transaction limit per day",
    "ঋণ শ্রেণীকরণ ও প্রভিশন",
    "export retention quota foreign currency account",
    "Who must approve the appointment of a bank managing director?",
]
OUT = pathlib.Path(__file__).parent

async def token(c):
    email = f"bench-{uuid.uuid4().hex[:8]}@regwatch-local.com"
    pw = "Bench-pass-123!"
    r = await c.post(f"{API}/auth/register", json={"email": email, "password": pw, "full_name": "Speed Test"})
    if r.status_code >= 400:
        print("register", r.status_code, r.text[:300]); sys.exit(1)
    b = r.json()
    t = b.get("access_token") or (b.get("token") or {}).get("access_token")
    if not t:
        r = await c.post(f"{API}/auth/login", data={"username": email, "password": pw})
        t = r.json().get("access_token")
    return t

async def timed(c, path, q, h):
    t0 = time.perf_counter()
    r = await c.post(f"{API}{path}", json={"query": q}, headers=h)
    return time.perf_counter() - t0, r.status_code, (r.json() if r.status_code == 200 else r.text[:200])

async def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    only_m = "--matches-only" in sys.argv
    async with httpx.AsyncClient(timeout=120) as c:
        h = {"Authorization": f"Bearer {await token(c)}"}
        rows = []
        for q in QUESTIONS:
            jobs = [timed(c, "/research/matches", q, h)]
            if not only_m:
                jobs.append(timed(c, "/research/query", q, h))
            res = await asyncio.gather(*jobs)
            m = res[0]; a = res[1] if not only_m else None
            row = {"q": q, "matches_s": round(m[0], 3), "n_matches": len(m[2]["matches"]) if m[1] == 200 else m[1]}
            if a:
                body = a[2] if a[1] == 200 else {}
                row.update(answer_s=round(a[0], 3), grounded=body.get("is_grounded"),
                           n_quotes=len(body.get("citations", [])), answer=(body.get("answer") or str(a[2]))[:140],
                           caveats=body.get("caveats", [])[:2])
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))
    ms = [r["matches_s"] for r in rows]
    summ = {"label": label, "matches_median": round(statistics.median(ms), 3), "matches_max": max(ms)}
    if not only_m:
        an = [r["answer_s"] for r in rows]
        summ.update(answer_median=round(statistics.median(an), 3), answer_max=max(an),
                    grounded=sum(1 for r in rows if r["grounded"]))
    print("SUMMARY", json.dumps(summ))
    (OUT / f"{label}.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT / "results.tsv", "a", encoding="utf-8") as f:
        f.write("\t".join(str(summ.get(k, "")) for k in ["label", "matches_median", "matches_max", "answer_median", "answer_max", "grounded"]) + "\n")

asyncio.run(main())
