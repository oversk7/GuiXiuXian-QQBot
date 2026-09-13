from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.daily_task import DailyTask
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService as Novice
from tests.test_novice_onboarding import game_store, seed_player, seed_progress


@pytest.mark.parametrize("command", ["角色", "闭关"])
async def test_full_bag_backfill_preserves_command_and_retries_once(game_store, monkeypatch, command):
    await seed_player(game_store, level=2, exp=0)
    capacity = AsyncMock(return_value=0)
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", capacity)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {1}, 2)

    for _ in range(2):
        async with db.safe_session(game_store) as session:
            player = await session.get(Player, "newbie")
            original_gold = player.gold
            player.is_secluded = command == "闭关"
            completed, message = await Novice.check_and_advance_quest(
                session, player, "command", {"command": command}
            )
            assert not completed and "背包空间不足" in message
            assert (player.exp, player.gold) == (0, original_gold)
            assert player.is_secluded == (command == "闭关")
            assert (await Novice.get_current_quest(session, player.id)).quest_step == 6

    capacity.return_value = 80
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert player.is_secluded == (command == "闭关")
        completed, _ = await Novice.check_and_advance_quest(session, player, "state")
        assert completed
        assert (player.exp, player.gold) == (500, original_gold + 3000)
        completed, _ = await Novice.check_and_advance_quest(session, player, "state")
        assert not completed
        assert (player.exp, player.gold) == (500, original_gold + 3000)
        assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 10


async def test_chain_reward_full_bag_rolls_back_step_and_partial_items(game_store, monkeypatch):
    await seed_player(game_store, level=2, exp=0)
    capacity = AsyncMock(return_value=1)
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", capacity)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", set(range(1, 10)), 10)

    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        original_gold = player.gold
        completed, message = await Novice.check_and_advance_quest(
            session, player, "command", {"command": "传送"}
        )
        assert not completed and "背包空间不足" in message
        assert "✨ 完成" not in message
        assert (player.exp, player.gold) == (0, original_gold)
        assert await session.scalar(select(func.count()).select_from(ItemInstance)) == 0
        current = await Novice.get_current_quest(session, player.id)
        assert (current.quest_chain_id, current.quest_step, current.status) == ("novice_basic", 10, "accepted")
        assert await session.scalar(select(func.count()).select_from(DailyTask).where(
            DailyTask.quest_chain_id == "novice_survival"
        )) == 0

    capacity.return_value = 80
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        completed, _ = await Novice.check_and_advance_quest(
            session, player, "command", {"command": "传送"}
        )
        assert completed
        assert (player.exp, player.gold) == (3800, original_gold + 11500)
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.item_id == "heal_potion"
        )) == 70
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.item_id == "sweep_token"
        )) == 5
