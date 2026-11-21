import asyncio, time, sys
sys.path.insert(0, ".")
import backend.app.main
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.research.service import ResearchService, _keywords
QS = ["What is the minimum capital adequacy ratio for banks?", "agent banking outlet requirements", "ঋণ শ্রেণীকরণ ও প্রভিশন"]
async def main():
    for q in QS:
        async with AsyncSessionLocal() as db:
            t = time.perf_counter(); p = await ResearchService._top_pages(db, _keywords(q), None, None, None); t1 = time.perf_counter()
            m = await ResearchService.find_matches(db, q); t2 = time.perf_counter()
        print(q[:30], _keywords(q), "top_pages %.2f  find_matches %.2f" % (t1 - t, t2 - t1))
asyncio.run(main())
