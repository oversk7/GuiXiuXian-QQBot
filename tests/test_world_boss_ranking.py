"""世界BOSS排行：Redis ZSet 与原 MySQL 查询结果一致（需要 GUIX_REDIS_TEST_URL）。

设置 GUIX_MYSQL_TEST_URL 时使用真实 MySQL，否则使用临时 SQLite。
"""

import os
import random
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.infrastructure.redis_service import RedisBackend, RedisUnavailable
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.world_boss_cycle_repository import (
    WorldBossCycleRepository,
)
from plugins.xiuxian_game.infrastructure.repositories.world_boss_damage_repository import (
    WorldBossDamageRepository,
)
from plugins.xiuxian_game.models.db import Base
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.world_boss import WorldBossCycle, WorldBossDamage
from plugins.xiuxian_game.world_boss import service as service_module
from plugins.xiuxian_game.world_boss.ranking_store import WorldBossRankingStore
from plugins.xiuxian_game.world_boss.service import RankingEntry, WorldBossService, sync_ranking
from tests.mysql_helpers import mysql_session_factory  # noqa: F401
from tests.redis_helpers import redis_backend_factory  # noqa: F401

TIERS = len(WorldBossService.TIER_NAMES)


@pytest.fixture
def factory(request):
    use_mysql = bool(os.environ.get("GUIX_MYSQL_TEST_URL", "").strip())
    return request.getfixturevalue("mysql_session_factory" if use_mysql else "sqlite_session_factory")


@pytest.fixture
async def sqlite_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'boss.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def store(redis_backend_factory, monkeypatch):  # noqa: F811
    store = WorldBossRankingStore(redis_backend_factory(timeout_seconds=2), TIERS)
    monkeypatch.setattr(service_module, "_ranking_store", lambda: store)
    service_module._dirty_rankings.clear()
    return store


def _service(session):
    return WorldBossService(
        session=session,
        cycle_repo=WorldBossCycleRepository(session),
        damage_repo=WorldBossDamageRepository(session),
        player_repo=PlayerRepository(session),
        item_repo=ItemRepository(session),
    )


async def _seed(factory, players=25):
    """各段位都有人；含伤害为 0 的、快照为 -1 的旧数据，以及另一个区服的玩家"""
    rng = random.Random(7)
    damages = rng.sample(range(1_000, 10_000_000_000), players)
    async with factory() as session:
        cycle = WorldBossCycle(
            cycle_key="2026W43_SAT_20", boss_name="巴虺", boss_title="深渊之蛇",
            next_refresh_at=datetime.now() + timedelta(days=2),
        )
        session.add(cycle)
        await session.flush()
        for i in range(players):
            reincarnation = i % 7
            session.add(Player(id=f"p{i}", uid=1000 + i, nickname=f"玩家{i}", server_id=1,
                               reincarnation_level=reincarnation))
            session.add(WorldBossDamage(
                cycle_id=cycle.id, player_id=f"p{i}", total_damage=damages[i],
                reincarnation_snapshot=-1 if i == 3 else reincarnation,
            ))
        session.add(Player(id="idle", uid=999, nickname="围观", server_id=1, reincarnation_level=1))
        session.add(WorldBossDamage(cycle_id=cycle.id, player_id="idle", total_damage=0, reincarnation_snapshot=1))
        session.add(Player(id="other", uid=998, nickname="二区", server_id=2, reincarnation_level=1))
        session.add(WorldBossDamage(cycle_id=cycle.id, player_id="other", total_damage=10**11,
                                    reincarnation_snapshot=1))
        await session.commit()
        return cycle


async def _views(factory, cycle_id, viewer_id, monkeypatch):
    """同一时刻分别走 Redis 和 MySQL 两条路径生成排行榜"""
    async with factory() as session:
        cycle = await session.get(WorldBossCycle, cycle_id)
        viewer = await session.get(Player, viewer_id)
        from_redis = await _service(session).build_ranking_view(cycle, viewer)
    redis_store = service_module._ranking_store
    monkeypatch.setattr(service_module, "_ranking_store",
                        lambda: WorldBossRankingStore(RedisBackend(None), TIERS))
    try:
        async with factory() as session:
            cycle = await session.get(WorldBossCycle, cycle_id)
            viewer = await session.get(Player, viewer_id)
            from_db = await _service(session).build_ranking_view(cycle, viewer)
    finally:
        monkeypatch.setattr(service_module, "_ranking_store", redis_store)
    return from_redis, from_db


async def _attack(factory, cycle_id, player_id, damage, reincarnation=None):
    """模拟一次攻击：事务里累加伤害（可选升转），提交后写排行"""
    async with factory() as session:
        cycle = await session.get(WorldBossCycle, cycle_id)
        player = await session.get(Player, player_id)
        service = _service(session)
        record = await service._get_or_create_damage_record(cycle.id, player.id)
        if reincarnation is not None:
            player.reincarnation_level = reincarnation
            record.reincarnation_snapshot = reincarnation
        record.total_damage += damage
        entry = await service.ranking_entry(cycle, player)
        await session.commit()
    await sync_ranking(entry)
    return entry


async def test_upsert_keeps_larger_score_and_moves_tier_up(store):
    expire_at = datetime.now() + timedelta(hours=1)
    await store.upsert(1, 1, [("a", 0, 500)], expire_at)
    await store.upsert(1, 1, [("a", 0, 300)], expire_at)  # 迟到的旧值不覆盖
    assert await store.top(1, 1, 0, 10) == [("a", 500)]

    await store.upsert(1, 1, [("a", 2, 800)], expire_at)  # 中途转生：搬到段位 2
    assert await store.count(1, 1, 0) == 0
    assert await store.top(1, 1, 2, 10) == [("a", 800)]

    await store.upsert(1, 1, [("a", 0, 900)], expire_at)  # 转生前的旧写入，段位只升不降
    assert await store.count(1, 1, 0) == 0
    assert await store.top(1, 1, 2, 10) == [("a", 800)]
    assert await store.rank(1, 1, 2, "a") == 1
    assert await store.rank(1, 1, 2, "nobody") is None


async def test_first_view_rebuilds_from_mysql_and_matches(factory, store, monkeypatch):
    cycle = await _seed(factory)
    from_redis, from_db = await _views(factory, cycle.id, "p10", monkeypatch)
    assert from_redis == from_db
    assert "📍 我的名次：" in from_redis and "第" in from_redis
    assert "二区" not in from_redis and "围观" not in from_redis
    assert await store.is_ready(cycle.id, 1)

    total = sum([await store.count(cycle.id, 1, tier) for tier in range(TIERS)])
    assert total == 25


async def test_attacks_after_commit_keep_ranking_in_sync(factory, store, monkeypatch):
    cycle = await _seed(factory)
    await _views(factory, cycle.id, "p0", monkeypatch)  # 先触发重建

    await _attack(factory, cycle.id, "p0", 50_000_000_000)              # 冲到本段第一
    await _attack(factory, cycle.id, "p1", 10, reincarnation=9)        # 中途转生，搬到最高段
    await _attack(factory, cycle.id, "idle", 123)                      # 第一次有伤害

    from_redis, from_db = await _views(factory, cycle.id, "p1", monkeypatch)
    assert from_redis == from_db
    assert await store.rank(cycle.id, 1, 0, "p0") == 1
    assert await store.rank(cycle.id, 1, WorldBossService.get_reincarnation_tier(9), "p1") is not None
    assert await store.rank(cycle.id, 1, WorldBossService.get_reincarnation_tier(1), "p1") is None


async def test_failed_write_is_rebuilt_on_next_view(factory, store, monkeypatch):
    cycle = await _seed(factory)
    await _views(factory, cycle.id, "p0", monkeypatch)

    async def unavailable(*args, **kwargs):
        raise RedisUnavailable("TimeoutError")

    original = store.upsert
    monkeypatch.setattr(store, "upsert", unavailable)
    await _attack(factory, cycle.id, "p2", 80_000_000_000)
    assert (cycle.id, 1) in service_module._dirty_rankings

    monkeypatch.setattr(store, "upsert", original)
    from_redis, from_db = await _views(factory, cycle.id, "p2", monkeypatch)
    assert from_redis == from_db
    assert await store.rank(cycle.id, 1, WorldBossService.get_reincarnation_tier(2), "p2") == 1
    assert not service_module._dirty_rankings


async def test_view_falls_back_to_mysql_when_redis_read_fails(factory, store, monkeypatch):
    cycle = await _seed(factory)

    async def unavailable(*args, **kwargs):
        raise RedisUnavailable("TimeoutError")

    monkeypatch.setattr(store, "is_ready", unavailable)
    from_redis, from_db = await _views(factory, cycle.id, "p5", monkeypatch)
    assert from_redis == from_db


async def test_viewer_without_damage_sees_hint(factory, store, monkeypatch):
    cycle = await _seed(factory)
    from_redis, from_db = await _views(factory, cycle.id, "idle", monkeypatch)
    assert from_redis == from_db
    assert "📍 我的名次：本期还没有出手" in from_redis


async def test_settlement_still_reads_mysql(factory, store, monkeypatch):
    """ZSet 只管展示：Redis 里的数据被改乱也不影响发奖"""
    cycle = await _seed(factory)
    await _views(factory, cycle.id, "p0", monkeypatch)
    await store.upsert(cycle.id, 1, [("p0", 0, 10**15)], datetime.now() + timedelta(hours=1))

    monkeypatch.setattr(service_module, "get_servers_config", lambda: {1: {}})
    async with factory() as session:
        cycle = await session.get(WorldBossCycle, cycle.id)
        tip = await _service(session)._settle_cycle(cycle)
        await session.commit()
    assert "25 名勇士" in tip
