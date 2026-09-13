from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.daily_task import DailyTask
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService as Novice


@pytest.fixture
async def game_store(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'novice.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: db.Base.metadata.create_all(
            conn, tables=[Player.__table__, DailyTask.__table__, ItemInstance.__table__]
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(Novice, "_quest_config", None)
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    monkeypatch.setattr(AchievementService, "check_achievements", AsyncMock(return_value=[]))
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=80))
    monkeypatch.setattr(Player, "get_effective_attributes", AsyncMock(return_value={"max_hp": 20}))
    from plugins.xiuxian_game import platform_utils
    from plugins.xiuxian_game.social import level_hooks

    async def require_player(session, _event, _matcher):
        return await session.get(Player, "newbie")

    monkeypatch.setattr(platform_utils, "require_player", require_player)
    monkeypatch.setattr(level_hooks, "on_player_level_up", AsyncMock(return_value=[]))
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_player(factory, *, server_id=1, level=1, exp=10, last_sign=None):
    async with db.safe_session(factory) as session:
        player = Player(
            id="newbie", uid=100, nickname="新人", server_id=server_id,
            level=level, exp=exp, prologue_step=2, last_sign=last_sign,
        )
        session.add(player)
        await session.flush()
        if level == 1:
            await Novice.init_novice_quests(session, player)


async def seed_progress(session, chain_id, completed_steps, pending_step=None, status="expired", progress=0):
    chain = Novice._get_chain_config(chain_id)
    for step in chain["steps"]:
        if step["step"] not in completed_steps and step["step"] != pending_step:
            continue
        session.add(DailyTask(
            player_id="newbie", task_type="tutorial", title=step["title"],
            description=step["description"], target_x=0, target_y=0,
            enemy_name="", enemy_level=0, enemy_hp=0, enemy_attack=0, enemy_defense=0, enemy_agility=0,
            quest_chain_id=chain_id, quest_step=step["step"], is_tutorial=True,
            status="completed" if step["step"] in completed_steps else status,
            quest_progress=progress if step["step"] == pending_step else 0,
            task_date=date.today() - timedelta(days=3),
        ))


@pytest.mark.parametrize("server_id,required_exp", [(1, 10), (2, 20)])
async def test_first_breakthrough_immediately_unlocks_assign_points(game_store, monkeypatch, server_id, required_exp):
    from plugins.xiuxian_game.cultivate import core

    await seed_player(game_store, server_id=server_id, exp=required_exp)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(core.breakthrough, "finish", finish)
    with pytest.raises(FinishedException):
        await core.handle_breakthrough(SimpleNamespace(), Message())
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert (player.level, player.attribute_points) == (2, 10)
        current = await Novice.get_current_quest(session, player.id)
        assert current.quest_step == 5
        assert "加点 力 5" in Novice.format_current_quest(current, player)
        reward_exp = player.exp
        await Novice.check_and_advance_quest(session, player, "state")
        assert player.exp == reward_exp
        completed = (await session.execute(select(DailyTask).where(DailyTask.status == "completed"))).scalars().all()
        assert [quest.quest_step for quest in completed] == [6]


@pytest.mark.parametrize("current_step", ["assign", "job"])
async def test_assign_points_sends_tutorial_links_as_native_markdown(game_store, monkeypatch, current_step):
    from plugins.xiuxian_game.cultivate import core

    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        player.attribute_points = 50
        if current_step == "assign":
            await seed_progress(session, "novice_basic", {6}, 5)
        else:
            await seed_progress(session, "novice_basic", set(range(1, 11)))
            await seed_progress(session, "novice_survival", {1}, 2)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(core.assign_points, "finish", finish)
    with pytest.raises(FinishedException):
        await core.handle_assign(SimpleNamespace(), Message("智 50"))

    message = Message(finish.await_args.args[0])
    assert [segment.type for segment in message] == ["markdown"]
    content = message[0].data["markdown"].content
    assert "智 +50" in content
    assert '<qqbot-cmd-input text="新手任务"' in content
    assert ('text="打工"' if current_step == "job" else 'text="面板"') in content
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert player.attribute_points == (10 if current_step == "assign" else 0)


@pytest.mark.parametrize("server_id,level", [(1, 5), (2, 4)])
async def test_continuous_breakthrough_updates_tutorial(game_store, monkeypatch, server_id, level):
    from plugins.xiuxian_game.cultivate import core

    await seed_player(game_store, server_id=server_id, exp=100)
    monkeypatch.setattr(core.continuous_breakthrough, "finish", AsyncMock(side_effect=FinishedException))
    with pytest.raises(FinishedException):
        await core.handle_continuous_breakthrough(SimpleNamespace(), Message())
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert player.level == level
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 5


async def test_expired_and_duplicate_legacy_rows_restore_without_repaying_completed_steps(game_store):
    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {6, 5, 7, 1, 2, 3}, 4, progress=2)
        await seed_progress(session, "novice_basic", set(), 1, status="TaskStatus.ACCEPTED")
        await seed_progress(session, "novice_basic", set(), 1, status="TaskStatus.ACCEPTED")
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        current = await Novice.get_current_quest(session, player.id)
        assert (current.quest_step, current.quest_progress, current.status) == (4, 2, "accepted")
        assert player.exp == 0
        completed, message = await Novice.check_and_advance_quest(session, player, "state")
        assert not completed and "2/3" in message
        completed, _ = await Novice.check_and_advance_quest(session, player, "command", {"command": "修炼"})
        assert completed
        assert player.exp == 1000
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 8
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        await Novice.check_and_advance_quest(session, player, "state")
        assert player.exp == 1000
        active = (await session.execute(select(DailyTask).where(DailyTask.status == "accepted"))).scalars().all()
        assert len(active) == 1
        assert not (await session.execute(select(DailyTask).where(DailyTask.status.like("TaskStatus.%")))).scalars().all()


async def test_reordered_steps_keep_completed_observation(game_store):
    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {1}, 2, status="TaskStatus.ACCEPTED")
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        await Novice.check_and_advance_quest(session, player, "state")
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 5
        await Novice.check_and_advance_quest(session, player, "command", {"command": "加点"})
        await Novice.check_and_advance_quest(session, player, "command", {"command": "角色"})
        current = await Novice.get_current_quest(session, player.id)
        assert current.quest_step == 2
        assert player.exp == 1000
        hint = Novice.format_current_quest(current, player)
        assert "导航 地点名" in hint
        assert '<qqbot-cmd-input text="导航 ' in hint
        assert '<qqbot-cmd-input text="导航 地点名"' not in hint


async def test_first_cultivation_does_not_count_again_in_next_task(game_store):
    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {6, 5, 7, 1, 2}, 3)
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        await Novice.check_and_advance_quest(session, player, "command", {"command": "修炼"})
        current = await Novice.get_current_quest(session, player.id)
        assert (current.quest_step, current.quest_progress) == (4, 0)
        for count in (1, 2):
            completed, message = await Novice.check_and_advance_quest(session, player, "command", {"command": "修炼"})
            assert not completed
            assert f"{count}/3" in message
        completed, _ = await Novice.check_and_advance_quest(session, player, "command", {"command": "修炼"})
        assert completed
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 8


async def test_chapter_reward_and_preexisting_sign_in_paid_once(game_store):
    await seed_player(game_store, level=2, exp=0, last_sign=datetime.now())
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {6, 5, 7, 1, 2, 3, 4, 8, 9}, 10)
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        completed, _ = await Novice.check_and_advance_quest(session, player, "command", {"command": "传送"})
        assert completed
        assert player.exp == 800 + 3000 + 800
        current = await Novice.get_current_quest(session, player.id)
        assert (current.quest_chain_id, current.quest_step) == ("novice_survival", 2)
        before = player.exp
        await Novice.check_and_advance_quest(session, player, "command", {"command": "传送"})
        assert player.exp == before
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(ItemInstance.item_id == "sweep_token")) == 5


async def test_failed_reward_rolls_back_progress_and_original_action(game_store, monkeypatch):
    await seed_player(game_store)
    monkeypatch.setattr(ItemInstance, "add_item", AsyncMock(side_effect=ValueError("背包空间不足")))
    with pytest.raises(ValueError, match="背包空间不足"):
        async with db.safe_session(game_store) as session:
            player = await session.get(Player, "newbie")
            player.level = 2
            player.exp = 0
            await Novice.check_and_advance_quest(session, player, "level_up")
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert (player.level, player.exp, player.gold) == (1, 10, 1000)
        current = await Novice.get_current_quest(session, player.id)
        assert (current.quest_step, current.status) == (6, "accepted")
        assert await session.scalar(select(func.count()).select_from(ItemInstance)) == 0


@pytest.mark.parametrize("starting_hp,remaining_potions", [(20, 10), (10, 9)])
async def test_healing_tutorial_sends_markdown_and_only_consumes_when_injured(
    game_store, monkeypatch, starting_hp, remaining_potions
):
    from plugins.xiuxian_game.item import inventory

    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {6, 5, 7, 1, 2, 3, 4}, 8)
        player = await session.get(Player, "newbie")
        player.hp = starting_hp
        session.add(ItemInstance(player_id="newbie", item_id="heal_potion", quantity=10))
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(inventory.use_item, "finish", finish)
    with pytest.raises(FinishedException):
        await inventory.handle_use_item(SimpleNamespace(), Message("回春散"))
    message = Message(finish.await_args.args[0])
    assert [segment.type for segment in message] == ["markdown"]
    assert '<qqbot-cmd-input text="任务"' in message[0].data["markdown"].content
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert player.hp == 20
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 9
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(ItemInstance.item_id == "heal_potion")) == remaining_potions


async def test_equipping_item_renders_next_tutorial_command(game_store, monkeypatch):
    from plugins.xiuxian_game.item import equipment_commands

    await seed_player(game_store, level=29, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", set(range(1, 11)))
        await seed_progress(session, "novice_survival", {1, 2}, 3)
        equipment = ItemInstance(
            player_id="newbie", item_id="bone_armor", quantity=1,
            durability=config.items_config["by_id"]["bone_armor"].durability,
        )
        session.add(equipment)
        await session.flush()
        equipment_id = equipment.id

    async def require_player(session, _event, _matcher):
        return await session.get(Player, "newbie")

    monkeypatch.setattr(equipment_commands, "require_player", require_player)
    monkeypatch.setattr(equipment_commands.EquipmentService, "recalc_equipment_attributes", AsyncMock())
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(equipment_commands.wear_equipment, "finish", finish)
    handler = equipment_commands.wear_equipment.handlers[0].call
    with pytest.raises(FinishedException):
        await handler(SimpleNamespace(), Message(str(equipment_id)))
    message = Message(finish.await_args.args[0])
    assert [segment.type for segment in message] == ["markdown"]
    assert '<qqbot-cmd-input text="锻造"' in message[0].data["markdown"].content
    async with db.safe_session(game_store) as session:
        assert (await session.get(ItemInstance, equipment_id)).equipped


async def test_daily_preview_below_level_30_awards_valid_items_and_unlocks_dungeon(game_store, monkeypatch):
    from plugins.xiuxian_game.daily_task import commands

    await seed_player(game_store, level=2, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", {6, 5, 7, 1, 2, 3, 4, 8}, 9)

    async def require_player(session, _event, _matcher):
        return await session.get(Player, "newbie")

    monkeypatch.setattr(commands, "AsyncSessionLocal", game_store)
    monkeypatch.setattr(commands, "require_player", require_player)
    monkeypatch.setattr(commands.daily_task_cmd, "finish", AsyncMock(side_effect=FinishedException))
    with pytest.raises(FinishedException):
        await commands.handle_daily_task(SimpleNamespace())
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert player.level == 2
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 10
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(ItemInstance.item_id == "sweep_token")) == 2


async def test_legacy_completed_characters_do_not_restart_tutorial(game_store):
    await seed_player(game_store, level=40)
    async with db.safe_session(game_store) as session:
        assert await Novice.get_current_quest(session, "newbie") is None
        for chain in Novice._load_quest_config()["chains"]:
            await seed_progress(session, chain["chain_id"], {step["step"] for step in chain["steps"]})
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert await Novice.check_and_advance_quest(session, player, "state") == (False, None)
        assert player.exp == 10


@pytest.mark.parametrize("level,reincarnation,status", [
    (30, 0, "accepted"),
    (100, 0, "TaskStatus.ACCEPTED"),
    (1, 1, "expired"),
])
async def test_established_players_keep_records_without_tutorial_rewards_or_hints(
    game_store, level, reincarnation, status
):
    await seed_player(game_store, level=level)
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        player.reincarnation_level = reincarnation
        await seed_progress(session, "novice_basic", set(), 6, status=status)
    async with db.safe_session(game_store) as session:
        before = list((await session.execute(select(DailyTask.id, DailyTask.status, DailyTask.quest_progress))).all())
        player = await session.get(Player, "newbie")
        balance = (player.exp, player.gold, player.attribute_points)
        assert await Novice.get_current_quest(session, player.id) is None
        assert await Novice.check_and_advance_quest(session, player, "command", {"command": "角色"}) == (False, None)
        assert (player.exp, player.gold, player.attribute_points) == balance
    async with db.safe_session(game_store) as session:
        after = list((await session.execute(select(DailyTask.id, DailyTask.status, DailyTask.quest_progress))).all())
        assert after == before
        assert await session.scalar(select(func.count()).select_from(ItemInstance)) == 0


async def test_level_29_without_reincarnation_still_receives_guidance(game_store):
    await seed_player(game_store, level=29, exp=0)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", set(), 6)
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        completed, message = await Novice.check_and_advance_quest(session, player, "state")
        assert completed and "加点 力 5" in message
        assert (await Novice.get_current_quest(session, player.id)).quest_step == 5
        assert player.exp == 500


async def test_breakthrough_to_level_30_stops_tutorial_in_same_reply(game_store, monkeypatch):
    from plugins.xiuxian_game.cultivate import core
    from plugins.xiuxian_game.utils import calculate_level_up_exp

    required_exp = calculate_level_up_exp(29, 1)
    await seed_player(game_store, level=29, exp=required_exp)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", set(), 6)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(core.breakthrough, "finish", finish)
    with pytest.raises(FinishedException):
        await core.handle_breakthrough(SimpleNamespace(), Message())
    message = Message(finish.await_args.args[0])
    assert "新手任务" not in message[0].data["markdown"].content
    async with db.safe_session(game_store) as session:
        player = await session.get(Player, "newbie")
        assert (player.level, player.exp, player.gold) == (30, 0, 1000)
        quest = (await session.execute(select(DailyTask))).scalar_one()
        assert quest.status == "expired"


async def test_manual_tutorial_command_explains_retirement_without_restarting(game_store, monkeypatch):
    from plugins.xiuxian_game.quest import commands

    await seed_player(game_store, level=30)
    async with db.safe_session(game_store) as session:
        await seed_progress(session, "novice_basic", set(), 6)

    async def require_player(session, _event, _matcher):
        return await session.get(Player, "newbie")

    monkeypatch.setattr(commands, "require_player", require_player)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(commands.novice_quest_cmd, "finish", finish)
    with pytest.raises(FinishedException):
        await commands.handle_novice_quest(SimpleNamespace())
    message = Message(finish.await_args.args[0])
    assert "无需再完成新手任务" in message[0].data["markdown"].content
    async with db.safe_session(game_store) as session:
        quest = (await session.execute(select(DailyTask))).scalar_one()
        assert quest.status == "expired"
        assert (await session.get(Player, "newbie")).exp == 10


def test_all_tutorial_reward_item_ids_exist():
    for chain in Novice._load_quest_config()["chains"]:
        rewards = [step["rewards"] for step in chain["steps"]] + [chain["completion_reward"]]
        for reward in rewards:
            for item in reward.get("items", []):
                assert item["item_id"] in config.items_config["by_id"]
