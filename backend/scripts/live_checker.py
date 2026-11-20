"""Always-on live checker for new Bangladesh Bank circulars (DECISIONS.md 1).

Runs only the app's own monitoring schedule (new-circular check, daily full-list check, weekly
archive re-check), without the web server. Meant for the scheduled task RegWatchLiveChecker on
the always-on PC. Found circulars go through the normal pipeline and land in the review queue.

Schedule used here (set below unless already set in the environment):
- every 10 min Sun-Thu and every 60 min Fri-Sat, between 09:00 and 19:00 Bangladesh time;
- full-list check at 18:50;
- anything uploaded overnight is caught by the first check at 09:00 (the check asks for the last 7 days).

Never run this next to a web backend that has SCHEDULER_ENABLED=true: two checkers would break
the one-request-per-15 s rule. Log: data/live_checker.log.

Usage (repo root):
    .venv/Scripts/python.exe backend/scripts/live_checker.py
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONITOR_WINDOW_START", "9")
os.environ.setdefault("MONITOR_WINDOW_END", "19")
os.environ.setdefault("RECONCILE_TIME", "18:50")

import backend.app.database.models  # noqa: E402,F401
from backend.app.core.logging import logger  # noqa: E402
from backend.app.workers.scheduler import monitoring_scheduler  # noqa: E402

LOG = ROOT / "data" / "live_checker.log"


async def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.info("Live checker starting.")
    await monitoring_scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await monitoring_scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
