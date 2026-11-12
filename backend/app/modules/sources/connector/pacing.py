"""One request at a time to bb.org.bd, at least BB_REQUEST_INTERVAL_SECONDS apart.

Every request the app sends to the site (listing checks, PDF downloads, HEAD checks)
goes through `bb_request_gate.slot()`. The gate holds a lock for the whole request and
remembers when the last request finished, so the next one waits out the gap first.

The scheduler runs in a single process (SCHEDULER_ENABLED), so an in-process lock is
enough. The clock and sleep functions can be swapped in tests.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, Optional

from backend.app.core.config import settings


class RequestGate:
    def __init__(
        self,
        min_gap_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._min_gap = min_gap_seconds
        self.clock = clock
        self.sleep = sleep
        self.last_request_end: Optional[float] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop = None

    @property
    def min_gap(self) -> float:
        if self._min_gap is not None:
            return self._min_gap
        return float(settings.BB_REQUEST_INTERVAL_SECONDS)

    def _get_lock(self) -> asyncio.Lock:
        # A lock belongs to one event loop; tests start a fresh loop per test.
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @asynccontextmanager
    async def slot(self):
        """Wait for our turn and for the gap since the last request, then hold the gate."""
        async with self._get_lock():
            if self.last_request_end is not None:
                wait = self.min_gap - (self.clock() - self.last_request_end)
                if wait > 0:
                    await self.sleep(wait)
            try:
                yield
            finally:
                self.last_request_end = self.clock()


bb_request_gate = RequestGate()
