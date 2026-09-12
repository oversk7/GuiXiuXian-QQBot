import asyncio
from unittest.mock import AsyncMock

from sqlalchemy import func, select

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.models.db import safe_session
from plugins.xiuxian_game.models.daily_task import DailyTask
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService as Novice
from tests.mysql_helpers import mysql_session_factory


async def test_concurrent_recovery_and_state_backfill_reward_once(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=80))
    async with safe_session(factory) as session:
        session.add(Player(id="newbie", uid=100, nickname="新人", level=2, exp=0))
        session.add(DailyTask(
            player_id="newbie", task_type="tutorial", title="破茧蜕变", description="突破",
            target_x=0, target_y=0, enemy_name="", enemy_level=0, enemy_hp=0,
            enemy_attack=0, enemy_defense=0, enemy_agility=0,
            quest_chain_id="novice_basic", quest_step=6, quest_progress=0,
            is_tutorial=True, status="expired",
        ))

    entered_reward = asyncio.Event()
    release_reward = asyncio.Event()
    second_started = asyncio.Event()
    give_rewards = Novice._give_rewards

    async def paused_reward(session, player, rewards):
        entered_reward.set()
        await release_reward.wait()
        return await give_rewards(session, player, rewards)

    monkeypatch.setattr(Novice, "_give_rewards", staticmethod(paused_reward))

    async def recover(second=False):
        async with safe_session(factory) as session:
            player = await session.get(Player, "newbie")
            if second:
                second_started.set()
            return await Novice.check_and_advance_quest(session, player, "state")

    first = asyncio.create_task(recover())
    try:
        await asyncio.wait_for(entered_reward.wait(), timeout=5)
        second = asyncio.create_task(recover(second=True))
        await asyncio.wait_for(second_started.wait(), timeout=5)
        release_reward.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=10)
    finally:
        release_reward.set()
        if not first.done():
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
    assert sum(completed for completed, _ in results) == 1

    async with safe_session(factory) as session:
        player = await session.get(Player, "newbie")
        assert (player.exp, player.gold) == (500, 4000)
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(ItemInstance.item_id == "spirit_herb")) == 10
        active = (await session.execute(select(DailyTask).where(DailyTask.status == "accepted"))).scalars().all()
        assert len(active) == 1 and active[0].quest_step == 5
        assert await session.scalar(select(func.count()).select_from(DailyTask).where(DailyTask.status == "completed")) == 1
