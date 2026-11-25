"""Tells Bing (and the other IndexNow search engines) about new public pages within the hour.

Google does not use IndexNow; it reads the sitemap. Runs only on the live server (production, SCHEDULER_ENABLED):
every hour it lists the public pages (list pages and indexable circulars), sends the ones not sent before, and
remembers them in data/indexnow_sent.txt. The key file is frontend/public/<INDEXNOW_KEY>.txt.
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Set

import httpx

from backend.app.core.config import settings
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.library.public import _hubs_from, path_index

logger = logging.getLogger(__name__)

INDEXNOW_KEY = "60b49caa6f7be62ceb2165ea3dc93699"
ENDPOINT = "https://api.indexnow.org/indexnow"
SENT_FILE = Path("data/indexnow_sent.txt")
EVERY_SECONDS = 3600
FIRST_WAIT_SECONDS = 180


def site() -> str:
    return settings.APP_PUBLIC_URL.rstrip("/")


async def public_urls() -> List[str]:
    async with AsyncSessionLocal() as db:
        idx = await path_index(db, fresh=True)
    base = site()
    hubs = _hubs_from(idx["items"])
    urls = [f"{base}/", f"{base}/circulars"]
    urls += [f"{base}/circulars/{h.code}" for h in hubs.departments + hubs.years]
    urls += [f"{base}/circulars/topic/{h.code}" for h in hubs.topics]
    urls += [f"{base}{i['path']}" for i in idx["items"] if i["indexable"]]
    return urls


def load_sent() -> Set[str]:
    try:
        return set(SENT_FILE.read_text(encoding="utf-8").split())
    except FileNotFoundError:
        return set()


async def submit(urls: List[str]) -> bool:
    host = site().split("://", 1)[-1]
    body = {"host": host, "key": INDEXNOW_KEY, "keyLocation": f"{site()}/{INDEXNOW_KEY}.txt", "urlList": urls[:10000]}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(ENDPOINT, json=body, headers={"Content-Type": "application/json; charset=utf-8"})
    if r.status_code in (200, 202):
        return True
    logger.warning("IndexNow refused %d URLs: %s %s", len(urls), r.status_code, r.text[:200])
    return False


async def run_once() -> int:
    """Sends the pages not sent before. Returns how many were sent."""
    urls = await public_urls()
    sent = load_sent()
    # The home and /circulars pages change with every new circular: send them again whenever anything is new.
    fresh = [u for u in urls if u not in sent]
    if not fresh:
        return 0
    always = [f"{site()}/", f"{site()}/circulars"]
    batch = list(dict.fromkeys(always + fresh))
    if await submit(batch):
        SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SENT_FILE.open("a", encoding="utf-8") as f:
            f.writelines(f"{u}\n" for u in fresh)
        logger.info("IndexNow: sent %d new pages", len(fresh))
        return len(fresh)
    return 0


async def loop() -> None:
    await asyncio.sleep(FIRST_WAIT_SECONDS)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # A failed round is retried next hour.
            logger.exception("IndexNow round failed")
        await asyncio.sleep(EVERY_SECONDS)


def enabled() -> bool:
    return settings.is_production and settings.SCHEDULER_ENABLED and settings.APP_PUBLIC_URL.startswith("https://")
