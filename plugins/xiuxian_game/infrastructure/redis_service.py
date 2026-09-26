"""Optional Redis backend for short lived caches and shared admission limits."""

from __future__ import annotations

import asyncio
from functools import lru_cache
import hashlib
import math
import time
from uuid import uuid4

from nonebot import get_driver, get_plugin_config, logger
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError


class RedisSettings(BaseModel):
    guix_redis_url: str | None = None
    guix_redis_prefix: str = "guixiuxian2"
    guix_redis_timeout_seconds: float = Field(default=0.2, gt=0, allow_inf_nan=False)
    guix_redis_retry_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)
    guix_map_cache_ttl_seconds: float = Field(default=5.0, gt=0, allow_inf_nan=False)


@lru_cache(maxsize=1)
def get_redis_settings() -> RedisSettings:
    return get_plugin_config(RedisSettings)


# Use Redis time so clients with different clocks agree on the window boundary.
# A rejected request does not add an event or refresh the key's expiry.
_ALLOW_SCRIPT = """
local now = redis.call('TIME')
local now_ms = now[1] * 1000 + math.floor(now[2] / 1000)
local window_ms = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms - window_ms)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
    return 0
end
redis.call('ZADD', KEYS[1], now_ms, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window_ms)
return 1
"""


class RedisBackend:
    def __init__(
        self,
        url: str | None,
        *,
        prefix: str = "guixiuxian2",
        timeout_seconds: float = 0.2,
        retry_seconds: float = 10.0,
    ) -> None:
        if not prefix or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Redis prefix and timeout must be positive")
        if not math.isfinite(retry_seconds) or retry_seconds <= 0:
            raise ValueError("Redis retry interval must be positive")
        self._url = url.strip() if url else None
        self._prefix = prefix
        self._timeout_seconds = timeout_seconds
        self._retry_seconds = retry_seconds
        self._retry_at = 0.0
        self._client: Redis | None = None
        self._slots = asyncio.Semaphore(32)

    def _available(self) -> bool:
        return bool(self._url) and time.monotonic() >= self._retry_at

    def _connection(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=self._timeout_seconds,
                socket_timeout=self._timeout_seconds,
                max_connections=32,
                retry_on_timeout=False,
            )
        return self._client

    async def _execute(self, operation: str, *args, **kwargs):
        # 等待连接额度也包含在调用超时内，避免突发请求直接耗尽连接池。
        async with self._slots:
            return await getattr(self._connection(), operation)(*args, **kwargs)

    def _failed(self, error: BaseException) -> None:
        now = time.monotonic()
        if now >= self._retry_at:
            self._retry_at = now + self._retry_seconds
            logger.warning(
                f"[Redis] {type(error).__name__}: 使用本地回退，{self._retry_seconds:g} 秒后重试"
            )

    async def get(self, key: str) -> str | None:
        if not self._available():
            return None
        try:
            return await asyncio.wait_for(
                self._execute("get", f"{self._prefix}:{key}"), self._timeout_seconds
            )
        except (RedisError, OSError, asyncio.TimeoutError, ValueError) as exc:
            self._failed(exc)
            return None

    async def set(self, key: str, value: str, ttl_seconds: float) -> bool:
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive and finite")
        if not self._available():
            return False
        try:
            return bool(await asyncio.wait_for(
                self._execute(
                    "set", f"{self._prefix}:{key}", value, px=math.ceil(ttl_seconds * 1000)
                ),
                self._timeout_seconds,
            ))
        except (RedisError, OSError, asyncio.TimeoutError, ValueError) as exc:
            self._failed(exc)
            return False

    async def allow(
        self, scope: str, key: str, limit: int, window_seconds: float
    ) -> bool | None:
        if limit <= 0 or not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive and finite")
        if not self._available():
            return None
        actor = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = f"{self._prefix}:rate:{scope}:{actor}"
        try:
            result = await asyncio.wait_for(
                self._execute(
                    "eval", _ALLOW_SCRIPT, 1, redis_key, math.ceil(window_seconds * 1000),
                    limit, uuid4().hex,
                ),
                self._timeout_seconds,
            )
            return bool(result)
        except (RedisError, OSError, asyncio.TimeoutError, ValueError) as exc:
            self._failed(exc)
            return None

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


_backend: RedisBackend | None = None
_shutdown_registered = False


async def _close_redis_backend() -> None:
    global _backend
    backend, _backend = _backend, None
    if backend is not None:
        await backend.close()


def get_redis_backend() -> RedisBackend:
    global _backend, _shutdown_registered
    if _backend is None:
        settings = get_redis_settings()
        _backend = RedisBackend(
            settings.guix_redis_url,
            prefix=settings.guix_redis_prefix,
            timeout_seconds=settings.guix_redis_timeout_seconds,
            retry_seconds=settings.guix_redis_retry_seconds,
        )
    if not _shutdown_registered:
        get_driver().on_shutdown(_close_redis_backend)
        _shutdown_registered = True
    return _backend
