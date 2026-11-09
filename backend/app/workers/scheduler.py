import asyncio
from datetime import datetime, timezone
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.database.session import AsyncSessionLocal
from backend.app.modules.sources.models import Source
from backend.app.modules.sources.service import source_monitoring_service


class ScheduledMonitoringService:
    def __init__(self, interval_seconds: int = 3600):
        self.interval_seconds = interval_seconds
        self._is_running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Scheduled Regulatory Source Monitoring worker started (interval: {self.interval_seconds}s).")

    async def stop(self):
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduled Regulatory Source Monitoring worker stopped.")

    async def _run_loop(self):
        # Initial brief wait on startup before first check
        await asyncio.sleep(5)
        while self._is_running:
            try:
                await self.poll_active_sources()
            except Exception as e:
                logger.error(f"Error in scheduled monitoring cycle: {e}")

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def poll_active_sources(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Source).where(Source.is_active == True)
            )
            sources = result.scalars().all()
            if not sources:
                logger.info("No active regulatory sources configured for monitoring.")
                return

            logger.info(f"Scheduled monitoring checking {len(sources)} active regulatory source(s)...")
            for source in sources:
                try:
                    run = await source_monitoring_service.execute_source_monitoring(
                        db=session,
                        source_id=source.id,
                        run_type="SCHEDULED_POLL"
                    )
                    logger.info(f"Source '{source.name}' poll completed with status {run.status} ({run.valid_documents_discovered} new candidates).")
                except Exception as ex:
                    logger.error(f"Failed scheduled monitoring run for source '{source.name}': {ex}")


monitoring_scheduler = ScheduledMonitoringService(
    interval_seconds=getattr(settings, "SOURCE_MONITORING_INTERVAL_SECONDS", 900)
)

