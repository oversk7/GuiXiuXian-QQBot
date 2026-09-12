"""进程内滑动窗口限频器。"""

from __future__ import annotations

from collections import defaultdict, deque
import time
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.monotonic
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._calls_since_cleanup = 0
        self._max_window_seconds = 0.0

    def allow(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        """记录一次获准调用；窗口内已达到上限时返回 False。"""
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit 和 window_seconds 必须大于 0")
        now = self._clock()
        self._max_window_seconds = max(self._max_window_seconds, window_seconds)
        self._calls_since_cleanup += 1
        if self._calls_since_cleanup >= 256:
            self.cleanup(now=now)
            self._calls_since_cleanup = 0
        queue = self._events[key]
        cutoff = now - window_seconds
        while queue and queue[0] <= cutoff:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

    def cleanup(self, *, now: float | None = None) -> int:
        now = self._clock() if now is None else now
        cutoff = now - self._max_window_seconds
        stale = [
            key for key, queue in self._events.items()
            if not queue or queue[-1] <= cutoff
        ]
        for key in stale:
            self._events.pop(key, None)
        return len(stale)

    def reset(self) -> None:
        self._events.clear()
        self._calls_since_cleanup = 0
        self._max_window_seconds = 0.0

    def __len__(self) -> int:
        return len(self._events)
