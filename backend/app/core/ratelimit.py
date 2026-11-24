"""A small in-process rate limiter (one backend process on one server, so no shared store is needed).

Each key keeps the times of its recent hits in a deque; a check costs a few dictionary and deque operations.
Limits are set well above what a person does by hand, so only scripts and abuse ever reach them.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request

MAX_KEYS = 50_000  # memory bound: old keys are dropped when the table grows past this


class RateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, window: float, now: float) -> Deque[float]:
        q = self._hits.get(key)
        if q is None:
            return deque()
        cut = now - window
        while q and q[0] <= cut:
            q.popleft()
        return q

    def _prune(self, now: float) -> None:
        # Drop keys whose newest hit is more than a day old, then the oldest keys if still too many.
        for k in [k for k, q in self._hits.items() if not q or q[-1] < now - 86400]:
            del self._hits[k]
        while len(self._hits) >= MAX_KEYS:
            del self._hits[next(iter(self._hits))]

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._recent(key, window, time.monotonic()))

    def _add_locked(self, key: str, n: int, now: float) -> None:
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= MAX_KEYS:
                self._prune(now)
            q = self._hits[key] = deque()
        q.extend([now] * n)

    def add(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._add_locked(key, n, time.monotonic())

    def allow(self, key: str, limit: int, window: float, cost: int = 1) -> bool:
        """Records `cost` hits and returns True when they fit inside `limit` per `window` seconds."""
        with self._lock:
            now = time.monotonic()
            q = self._recent(key, window, now)
            if len(q) + cost > limit:
                return False
            self._add_locked(key, cost, now)
        return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Optional[Request]) -> str:
    """The caller's address. Behind Caddy, uvicorn's --proxy-headers puts the real client address here."""
    if request is None or request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def too_many(detail: str = "Too many tries. Please wait a few minutes and try again.", retry_after: int = 300) -> HTTPException:
    return HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(retry_after)})


def enforce(key: str, limit: int, window: float, detail: Optional[str] = None, cost: int = 1) -> None:
    if not limiter.allow(key, limit, window, cost):
        raise too_many(detail or "Too many requests. Please wait a few minutes and try again.", int(window))
