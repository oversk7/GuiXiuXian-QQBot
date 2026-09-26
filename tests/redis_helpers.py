"""Isolated, optional localhost Redis fixture for integration tests."""

from __future__ import annotations

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from plugins.xiuxian_game.infrastructure.redis_service import RedisBackend


def _local_redis_url(raw_url: str) -> str:
    try:
        parsed = urlsplit(raw_url)
        if (parsed.scheme != "redis" or parsed.hostname not in {"localhost", "127.0.0.1"}
                or parsed.query or parsed.fragment or parsed.port == 0):
            raise ValueError
    except ValueError:
        raise ValueError("GUIX_REDIS_TEST_URL 只允许无 query 的本机 redis:// 地址") from None
    return raw_url


@pytest.fixture
async def redis_backend_factory():
    raw_url = os.environ.get("GUIX_REDIS_TEST_URL", "").strip()
    if not raw_url:
        pytest.skip("设置 GUIX_REDIS_TEST_URL 运行 Redis 集成测试")
    url = _local_redis_url(raw_url)
    prefix = f"guixiuxian2_test_{uuid4().hex}"
    backends: list[RedisBackend] = []

    def factory(**kwargs) -> RedisBackend:
        suffix = kwargs.pop("prefix", "")
        backend = RedisBackend(url, prefix=f"{prefix}:{suffix}" if suffix else prefix, **kwargs)
        backends.append(backend)
        return backend

    cleaner = Redis.from_url(
        url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2,
    )
    try:
        await cleaner.ping()
        yield factory
    finally:
        # Test keys are always scoped to this fixture's random prefix.
        try:
            keys = [key async for key in cleaner.scan_iter(match=f"{prefix}:*")]
            if keys:
                await cleaner.delete(*keys)
        finally:
            await cleaner.aclose()
            for backend in backends:
                await backend.close()
