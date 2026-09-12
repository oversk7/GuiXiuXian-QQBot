import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException
from sqlalchemy import select

from plugins.xiuxian_game import world_boss
from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.economy.part_time_job_service import PartTimeJobService
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.item import item_effects
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.part_time_job import PartTimeJob, PlayerJobStats
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


@pytest.mark.parametrize("quantity", [1, 2])
async def test_concurrent_chest_opening_consumes_each_reward(mysql_session_factory, monkeypatch, quantity):
    factory = mysql_session_factory
    async with factory() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=0))
        await setup.flush()
        setup.add(ItemInstance(player_id="p", item_id="abyss_test_chest", quantity=quantity))
        await setup.commit()

    barrier = asyncio.Barrier(2)
    async def require_player(session, event, matcher):
        player = await session.get(Player, "p")
        await barrier.wait()
        return player

    async def reward(player, item, count, context, session):
        player.gold += 100 * count
        session.add(ItemInstance(player_id=player.id, item_id="bone_fragment", quantity=count))
        await session.flush()
        return True, "reward"

    async def finish(message):
        raise FinishedException

    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(world_boss, "require_player", require_player)
    monkeypatch.setattr(world_boss, "message_add_head", lambda message, event: message)
    monkeypatch.setattr(world_boss.open_chest_cmd, "finish", finish)
    monkeypatch.setattr(item_effects, "apply_effect", reward)
    monkeypatch.setitem(config.items_config["by_id"], "abyss_test_chest", SimpleNamespace(name="测试箱"))
    event = SimpleNamespace()
    args = SimpleNamespace(extract_plain_text=lambda: "1")
    results = await asyncio.wait_for(asyncio.gather(
        world_boss.handle_open_chest(event, args),
        world_boss.handle_open_chest(event, args),
        return_exceptions=True,
    ), timeout=10)
    assert all(isinstance(result, FinishedException) for result in results), results
    async with factory() as check:
        rows = (await check.execute(select(ItemInstance))).scalars().all()
        assert sum(row.quantity for row in rows if row.item_id == "bone_fragment") == quantity
        assert not any(row.item_id == "abyss_test_chest" for row in rows)
        assert (await check.get(Player, "p")).gold == 100 * quantity


async def test_prologue_claim_with_pending_activity_awards_once(mysql_session_factory, monkeypatch):
    from plugins.xiuxian_game.player import prologue

    factory = mysql_session_factory
    async with factory() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=0, exp=0, prologue_step=1))
        await setup.commit()
    barrier = asyncio.Barrier(2)

    async def require_player(session, event, matcher):
        player = await session.get(Player, "p")
        player.last_active_at = datetime.now()
        await barrier.wait()
        return player

    async def add_item(session, player_id, item_id, quantity):
        session.add(ItemInstance(player_id=player_id, item_id=item_id, quantity=quantity))
        await session.flush()

    async def finish(message):
        raise FinishedException

    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(prologue, "require_player", require_player)
    monkeypatch.setattr(prologue, "calculate_level_up_exp", lambda level, server: 10)
    monkeypatch.setattr(ItemInstance, "add_item", add_item)
    matcher = SimpleNamespace(finish=finish)
    results = await asyncio.wait_for(asyncio.gather(
        prologue._finish_prologue(matcher, SimpleNamespace(), "intro"),
        prologue._finish_prologue(matcher, SimpleNamespace(), "intro"),
        return_exceptions=True,
    ), timeout=10)
    assert all(isinstance(result, FinishedException) for result in results), results
    async with factory() as check:
        player = await check.get(Player, "p")
        assert (player.prologue_step, player.gold, player.exp) == (2, prologue.PROLOGUE_GOLD, 10)
        assert len((await check.execute(select(ItemInstance))).scalars().all()) == 1


async def test_concurrent_job_completion_pays_and_counts_once(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    async with factory() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=0))
        setup.add(PartTimeJob(
            player_id="p", job_location_id="shop", job_type="cashier",
            is_working=True, end_time=datetime.now() - timedelta(minutes=1),
        ))
        setup.add(PlayerJobStats(player_id="p"))
        await setup.commit()
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    monkeypatch.setattr(PartTimeJobService, "roll_item_drop", lambda *args: None)
    barrier = asyncio.Barrier(2)

    async def complete():
        async with UnitOfWork(factory) as uow:
            player = await uow.players.get_by_id("p")
            await barrier.wait()
            service = PartTimeJobService(
                uow.players, uow.part_time_jobs, uow.job_locations, uow.player_job_stats
            )
            return await service.complete_job(player)

    results = await asyncio.wait_for(asyncio.gather(complete(), complete()), timeout=10)
    successful = [result for result in results if result[0]]
    assert len(successful) == 1
    reward = successful[0][2]["total_reward"]
    async with factory() as check:
        assert (await check.get(Player, "p")).gold == reward
        stats = (await check.execute(select(PlayerJobStats))).scalar_one()
        assert stats.total_jobs_completed == 1
        assert stats.total_earnings == reward
        assert not (await check.execute(select(PartTimeJob))).scalar_one().is_working
