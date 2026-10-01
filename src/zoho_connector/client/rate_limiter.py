import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager

from zoho_connector.errors import rate_limited

WINDOW_SECONDS = 60.0


class RateLimiter:
    """Sliding one-minute window plus a concurrency cap. Fails fast instead of queueing too long."""

    def __init__(self, per_minute: int, concurrency: int, max_wait_seconds: float):
        self._per_minute = per_minute
        self._max_wait = max_wait_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._lock = asyncio.Lock()
        self._calls: deque[float] = deque()
        self._blocked_until = 0.0

    def block(self, seconds: float) -> None:
        self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def blocked_for(self) -> float:
        return max(0.0, self._blocked_until - time.monotonic())

    @asynccontextmanager
    async def slot(self):
        async with self._semaphore:
            await self._acquire()
            yield

    async def _acquire(self) -> None:
        async with self._lock:
            while True:
                if blocked := self.blocked_for():
                    raise rate_limited(blocked, "Zoho blocked this organization for a while.")
                wait = self._wait_needed(time.monotonic())
                if wait == 0:
                    self._calls.append(time.monotonic())
                    return
                if wait > self._max_wait:
                    raise rate_limited(wait, "The per-minute call budget is used up.")
                await asyncio.sleep(wait)

    def _wait_needed(self, now: float) -> float:
        while self._calls and now - self._calls[0] >= WINDOW_SECONDS:
            self._calls.popleft()
        if len(self._calls) < self._per_minute:
            return 0.0
        return WINDOW_SECONDS - (now - self._calls[0])
