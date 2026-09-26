"""Shared admission limiter with a process-local fallback."""

from __future__ import annotations

from .redis_service import RedisBackend, get_redis_backend
from ..rate_limiter import SlidingWindowRateLimiter


class SharedSlidingWindowRateLimiter:
    def __init__(
        self,
        scope: str,
        *,
        backend: RedisBackend | None = None,
        local: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self._scope = scope
        self._backend = backend
        self._local = local if local is not None else SlidingWindowRateLimiter()

    async def allow(self, key: str, limit: int, window_seconds: float = 60) -> bool:
        backend = self._backend if self._backend is not None else get_redis_backend()
        result = await backend.allow(self._scope, key, limit, window_seconds)
        local_key = f"{self._scope}:{key}"
        if result is None:
            return self._local.allow(local_key, limit, window_seconds)
        if result:
            self._local.allow(local_key, limit, window_seconds)
        return result

    def reset(self) -> None:
        self._local.reset()
