"""In-memory per-client-IP sliding-window limits.

Kept in process memory, like the event bus and the session locks: the app runs a single
worker (see README), and a limit that resets on restart is fine for its purpose — stopping
one client from creating sessions or burning the shared daily chat quota in bulk.
"""

import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self,
        *,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sweep_every: int = 1000,
    ) -> None:
        self._window = window_seconds
        self._clock = clock
        self._sweep_every = sweep_every
        self._calls = 0
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int) -> bool:
        """Records a hit for `key` and returns True, unless `key` already has `limit` hits
        within the window (then nothing is recorded, so retrying doesn't extend the block)."""
        now = self._clock()
        self._calls += 1
        if self._calls % self._sweep_every == 0:
            self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def _sweep(self, now: float) -> None:
        cutoff = now - self._window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]
