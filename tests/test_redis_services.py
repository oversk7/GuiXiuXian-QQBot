"""Redis fallback behavior and optional localhost integration coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from plugins.xiuxian_game.infrastructure import redis_service
from plugins.xiuxian_game.infrastructure.redis_service import RedisBackend, RedisSettings
from plugins.xiuxian_game.rate_limiter import SlidingWindowRateLimiter
from plugins.xiuxian_game.infrastructure.shared_rate_limiter import SharedSlidingWindowRateLimiter
from tests.redis_helpers import _local_redis_url, redis_backend_factory


@pytest.mark.parametrize("url", [
    "redis://remote.example/0", "rediss://localhost/0", "redis://localhost/0?host=elsewhere",
    "redis://localhost/0#fragment", "redis://localhost:invalid/0", "invalid",
])
def test_test_url_rejects_remote_or_overridable_endpoints(url):
    with pytest.raises(ValueError, match="本机 redis://"):
        _local_redis_url(url)


def test_test_url_accepts_loopback():
    assert _local_redis_url("redis://127.0.0.1:6379/0") == "redis://127.0.0.1:6379/0"


@pytest.mark.parametrize("field", [
    "guix_redis_timeout_seconds", "guix_redis_retry_seconds", "guix_map_cache_ttl_seconds",
])
def test_settings_reject_invalid_timeouts(field):
    for value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            RedisSettings(**{field: value})


def test_settings_and_backend_initialize_lazily(monkeypatch):
    redis_service.get_redis_settings.cache_clear()
    load = lambda _: RedisSettings(guix_redis_url=None)
    monkeypatch.setattr(redis_service, "get_plugin_config", load)
    monkeypatch.setattr(redis_service, "_backend", None)
    monkeypatch.setattr(redis_service, "_shutdown_registered", False)
    settings = redis_service.get_redis_settings()
    assert redis_service.get_redis_settings() is settings
    backend = redis_service.get_redis_backend()
    assert backend is redis_service.get_redis_backend()
    assert backend._client is None
    redis_service.get_redis_settings.cache_clear()


async def test_missing_url_uses_local_limiter():
    backend = RedisBackend(None)
    assert await backend.get("key") is None
    assert not await backend.set("key", "value", 1)
    assert await backend.allow("commands", "actor", 1, 5) is None
    now = [0.0]
    local = SlidingWindowRateLimiter(lambda: now[0])
    limiter = SharedSlidingWindowRateLimiter("commands", backend=backend, local=local)
    assert await limiter.allow("actor", 1, 5)
    assert not await limiter.allow("actor", 1, 5)
    limiter.reset()
    assert await limiter.allow("actor", 1, 5)


async def test_connection_failure_cools_down_without_leaking_url(monkeypatch):
    warning = Mock()
    monkeypatch.setattr(redis_service, "logger", SimpleNamespace(warning=warning))
    now = [100.0]
    monkeypatch.setattr(redis_service, "time", SimpleNamespace(monotonic=lambda: now[0]))
    backend = RedisBackend("redis://:secret@localhost/0", retry_seconds=10)
    client = SimpleNamespace(get=AsyncMock(side_effect=RedisConnectionError("password secret")))
    monkeypatch.setattr(backend, "_connection", lambda: client)
    assert await backend.get("key") is None
    assert await backend.allow("scope", "key", 1, 5) is None
    assert not await backend.set("key", "value", 5)
    client.get.assert_awaited_once()
    warning.assert_called_once()
    assert "secret" not in str(warning.call_args)
    now[0] = 110.1
    client.get.side_effect = None
    client.get.return_value = "recovered"
    assert await backend.get("key") == "recovered"
    client.get.assert_awaited_with("guixiuxian2:key")


async def test_timeout_cools_down_and_falls_back(monkeypatch):
    backend = RedisBackend("redis://localhost/0", timeout_seconds=0.01)
    async def stalled(*args):
        await asyncio.sleep(1)
    client = SimpleNamespace(eval=stalled)
    monkeypatch.setattr(backend, "_connection", lambda: client)
    limiter = SharedSlidingWindowRateLimiter("notice", backend=backend)
    assert await limiter.allow("actor", 1, 2)
    assert not await limiter.allow("actor", 1, 2)
    assert backend._retry_at > 0


async def test_cancelled_operation_propagates(monkeypatch):
    backend = RedisBackend("redis://localhost/0", timeout_seconds=5)
    started = asyncio.Event()
    async def stalled(*args):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(backend, "_connection", lambda: SimpleNamespace(get=stalled))
    task = asyncio.create_task(backend.get("actor"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert backend._retry_at == 0


async def test_shared_limiter_records_success_and_scopes_local_fallback():
    backend = SimpleNamespace(allow=AsyncMock(side_effect=[True, None, None, None]))
    local = SlidingWindowRateLimiter()
    command = SharedSlidingWindowRateLimiter("command", backend=backend, local=local)
    notice = SharedSlidingWindowRateLimiter("notice", backend=backend, local=local)
    assert await command.allow("actor", 1, 60)
    assert not await command.allow("actor", 1, 60)
    assert await notice.allow("actor", 1, 60)
    assert not await notice.allow("actor", 1, 60)


@pytest.mark.redis
async def test_redis_cache_uses_millisecond_expiry(redis_backend_factory):
    backend = redis_backend_factory()
    assert await backend.set("map:actor", "here", 0.15)
    assert await backend.get("map:actor") == "here"
    ttl = await backend._connection().pttl(f"{backend._prefix}:map:actor")
    assert 0 < ttl <= 150
    await asyncio.sleep(0.19)
    assert await backend.get("map:actor") is None


@pytest.mark.redis
async def test_two_clients_share_atomic_admission_and_scopes(redis_backend_factory):
    first, second = redis_backend_factory(), redis_backend_factory()
    assert first._client is None and second._client is None
    results = await asyncio.gather(*(
        (first if index % 2 else second).allow("command", "same actor", 7, 2)
        for index in range(100)
    ))
    assert results.count(True) == 7
    assert results.count(False) == 93
    assert await first.allow("notice", "same actor", 1, 2)
    assert await second.allow("command", "another actor", 1, 2)
    assert await second.allow("notice", "same actor", 1, 2) is False


@pytest.mark.redis
async def test_boundary_and_rejection_do_not_extend_window(redis_backend_factory):
    backend = redis_backend_factory()
    assert await backend.allow("boundary", "actor", 1, 0.3)
    key = f"{backend._prefix}:rate:boundary:*"
    matches = [value async for value in backend._connection().scan_iter(match=key)]
    assert len(matches) == 1
    await asyncio.sleep(0.12)
    before = await backend._connection().pttl(matches[0])
    assert await backend.allow("boundary", "actor", 1, 0.3) is False
    after = await backend._connection().pttl(matches[0])
    assert 0 < after <= before
    await asyncio.sleep(0.22)
    assert await backend.allow("boundary", "actor", 1, 0.3)
    assert await backend.allow("boundary", "actor", 1, 0.3) is False
