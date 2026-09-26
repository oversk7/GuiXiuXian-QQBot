"""Short-lived public map snapshots shared through Redis when available."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from redis.exceptions import RedisError

from ..infrastructure.redis_service import get_redis_backend, get_redis_settings


_MAP_SNAPSHOT_KEY = "web:map:snapshot:v1"


class MapSnapshotCache:
    """Coalesce loads within this process; Redis shares results across processes."""

    def __init__(
        self,
        *,
        backend: Any = None,
        ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._ttl_seconds = (
            get_redis_settings().guix_map_cache_ttl_seconds
            if ttl_seconds is None else ttl_seconds
        )
        if not math.isfinite(self._ttl_seconds) or self._ttl_seconds <= 0:
            raise ValueError("map snapshot TTL must be positive")
        self._clock = clock
        self._lock = asyncio.Lock()
        self._local: dict | None = None
        self._expires_at = 0.0

    def clear(self) -> None:
        """Clear only this instance's short-lived local snapshot."""
        self._local = None
        self._expires_at = 0.0

    def _local_hit(self) -> dict | None:
        if self._local is not None and self._clock() < self._expires_at:
            return self._local
        return None

    async def _redis_hit(self, backend: Any) -> dict | None:
        if backend is None:
            return None
        try:
            raw = await backend.get(_MAP_SNAPSHOT_KEY)
        except (RedisError, OSError, asyncio.TimeoutError):
            return None
        if raw is None:
            return None
        try:
            snapshot = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if (not isinstance(snapshot, dict)
                or type(snapshot.get("ts")) not in (int, float)
                or (isinstance(snapshot["ts"], float) and not math.isfinite(snapshot["ts"]))
                or not all(isinstance(snapshot.get(field), list)
                           for field in ("cities", "players", "mansions", "guilds"))):
            return None
        return snapshot

    async def get_or_load(self, loader: Callable[[], Awaitable[dict]]) -> dict:
        hit = self._local_hit()
        if hit is not None:
            return hit

        backend = self._backend if self._backend is not None else get_redis_backend()
        hit = await self._redis_hit(backend)
        if hit is not None:
            return hit

        async with self._lock:
            hit = self._local_hit()
            if hit is not None:
                return hit
            hit = await self._redis_hit(backend)
            if hit is not None:
                return hit

            snapshot = await loader()
            expires_at = self._clock() + self._ttl_seconds
            if backend is not None:
                try:
                    await backend.set(
                        _MAP_SNAPSHOT_KEY,
                        json.dumps(snapshot, ensure_ascii=False),
                        self._ttl_seconds,
                    )
                except (RedisError, OSError, asyncio.TimeoutError):
                    pass  # A completed database read still supplies a local snapshot.
            self._local = snapshot
            self._expires_at = expires_at
            return snapshot
