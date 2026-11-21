import asyncio, sys, time, statistics
sys.path.insert(0, "."); sys.path.insert(0, "autoresearch/ask-speed-261121")
import llm_probe as lp
from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.research import service as svc
async def build(q, chars):
    svc.PROMPT_CHARS_PER_DOC = chars
    svc.get_answer_provider = lambda: lp.Capture()
    async with AsyncSessionLocal() as db:
        await svc.ResearchService.query_regulatory_knowledge(db, q)
    return lp.CAPT["sys"], lp.CAPT["user"]
async def main():
    q = sys.argv[1]
    variants = {c: await build(q, c) for c in (5000, 2000, 800)}
    res = {c: [] for c in variants}
    for rnd in range(3):
        for c, (s, u) in variants.items():
            dt, st, us, _ = await lp.call("gemini-3.5-flash-lite", s, u, {}, settings.GEMINI_API_KEY)
            res[c].append((round(dt, 2), st, us.get("promptTokenCount"), us.get("candidatesTokenCount")))
    for c, r in res.items(): print(c, r)
asyncio.run(main())
