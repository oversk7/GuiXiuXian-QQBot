"""Map snapshots stay short lived and Redis can share them across workers."""

import asyncio

import pytest

from plugins.xiuxian_game.web import map_cache
from tests.redis_helpers import redis_backend_factory


def snapshot(ts, **fields):
    return {"ts": ts, "cities": [], "players": [], "mansions": [], "guilds": [], **fields}


class FakeRedis:
    def __init__(self, clock):
        self.clock = clock
        self.value = None
        self.expires = 0
        self.fail = False
        self.reads = 0

    async def get(self, key):
        self.reads += 1
        if self.fail:
            raise ConnectionError("redis unavailable")
        return self.value if self.clock[0] < self.expires else None

    async def set(self, key, value, ttl_seconds):
        if self.fail:
            raise ConnectionError("redis unavailable")
        self.value = value
        self.expires = self.clock[0] + ttl_seconds
        return True


async def test_local_cache_coalesces_misses_and_expires_without_read_extension(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(map_cache, "get_redis_backend", lambda: None)
    cache = map_cache.MapSnapshotCache(ttl_seconds=5, clock=lambda: now[0])
    loads = 0

    async def loader():
        nonlocal loads
        loads += 1
        await asyncio.sleep(0)
        return snapshot(loads)

    snapshots = await asyncio.gather(*(cache.get_or_load(loader) for _ in range(20)))
    assert all(item == snapshot(1) for item in snapshots)
    assert loads == 1
    now[0] = 4.9
    assert (await cache.get_or_load(loader))["ts"] == 1
    now[0] = 5.0
    assert (await cache.get_or_load(loader))["ts"] == 2
    assert loads == 2
    cache.clear()
    assert (await cache.get_or_load(loader))["ts"] == 3


async def test_redis_snapshot_shared_without_renewing_a_read_snapshot():
    now = [0.0]
    redis = FakeRedis(now)
    writer = map_cache.MapSnapshotCache(backend=redis, ttl_seconds=5, clock=lambda: now[0])
    reader = map_cache.MapSnapshotCache(backend=redis, ttl_seconds=5, clock=lambda: now[0])
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return snapshot(calls)

    assert (await writer.get_or_load(loader))["ts"] == 1
    now[0] = 4
    assert (await reader.get_or_load(loader))["ts"] == 1
    assert calls == 1
    now[0] = 5
    assert (await reader.get_or_load(loader))["ts"] == 2
    assert calls == 2


@pytest.mark.parametrize("bad_value", [
    "{invalid", "{}", '{"ts": 1, "players": []}',
    '{"ts": NaN, "cities": [], "players": [], "mansions": [], "guilds": []}',
])
async def test_corrupt_redis_and_failure_use_short_local_fallback(bad_value):
    now = [0.0]
    redis = FakeRedis(now)
    redis.value = bad_value
    redis.expires = 10
    cache = map_cache.MapSnapshotCache(backend=redis, ttl_seconds=5, clock=lambda: now[0])
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return snapshot(calls)

    assert (await cache.get_or_load(loader))["ts"] == 1
    redis.fail = True
    now[0] = 4
    assert (await cache.get_or_load(loader))["ts"] == 1
    now[0] = 5
    assert (await cache.get_or_load(loader))["ts"] == 2
    assert calls == 2


async def test_failed_or_cancelled_load_does_not_poison_cache(monkeypatch):
    monkeypatch.setattr(map_cache, "get_redis_backend", lambda: None)
    cache = map_cache.MapSnapshotCache(ttl_seconds=5)

    async def failed():
        raise RuntimeError("db unavailable")

    async def cancelled():
        raise asyncio.CancelledError

    with pytest.raises(RuntimeError):
        await cache.get_or_load(failed)
    with pytest.raises(asyncio.CancelledError):
        await cache.get_or_load(cancelled)
    assert await cache.get_or_load(lambda: asyncio.sleep(0, result=snapshot(3))) == snapshot(3)


async def test_real_redis_shares_snapshots(redis_backend_factory):
    first = map_cache.MapSnapshotCache(backend=redis_backend_factory(), ttl_seconds=5)
    second = map_cache.MapSnapshotCache(backend=redis_backend_factory(), ttl_seconds=5)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return snapshot(123, players=[{"uid": 1}])

    assert await first.get_or_load(loader) == await second.get_or_load(loader)
    assert calls == 1
