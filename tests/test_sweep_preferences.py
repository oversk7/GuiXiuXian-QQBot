"""扫荡品质选择、跨来源入包与真实 SQLite 容量/持久化回归。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.item import inventory
from plugins.xiuxian_game.item.sweep_dungeon_service import SweepDungeonService
from plugins.xiuxian_game.item.sweep_preferences import (
    PREFERENCE_KEY, RARITY_ORDER, get_keep_rarities, parse_keep_rarities, preference_label, set_keep_rarities,
)
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository


@pytest.fixture
async def store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Player.__table__.create)
        await connection.run_sync(ItemInstance.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=30))
    items = {}
    for rarity in RARITY_ORDER:
        item = ItemConfig(dict(item_id=f"sweep_test_{rarity}", name=rarity,
                               type="MATERIAL", description="test", rarity=rarity))
        monkeypatch.setitem(config.items_config["by_id"], item.item_id, item)
        items[rarity] = item.item_id
    async with db.safe_session() as session:
        session.add(Player(id="sweep", uid=123, nickname="测试", region="20层诡域",
                           stamina=10, mp=100, hp=10000, extra_attrs={"other": {"value": 7}}))
    try:
        yield factory, items
    finally:
        await engine.dispose()


async def quantities(session):
    rows = (await session.scalars(select(ItemInstance))).all()
    result = {}
    for row in rows:
        result[row.item_id] = result.get(row.item_id, 0) + row.quantity
    return result


def service(session, monster, basic):
    svc = SweepDungeonService(SimpleNamespace(update=AsyncMock()), ItemRepository(session))
    svc._calculate_high_grade_rewards = AsyncMock(return_value=monster)
    svc._calculate_material_rewards = AsyncMock(return_value=basic)
    return svc


@pytest.mark.parametrize("text,expected", [
    ("蓝 橙", ["blue", "orange"]), ("紫", ["purple"]),
    ("蓝以上", ["blue", "purple", "orange"]),
    ("蓝色及以上", ["blue", "purple", "orange"]),
    ("BLUE、橙色", ["blue", "orange"]), ("蓝,紫，橙", ["blue", "purple", "orange"]),
    ("白", ["white"]), ("全部", list(RARITY_ORDER)), ("无", []), ("不保留", []),
])
def test_parser(text, expected):
    assert parse_keep_rarities(text) == expected


@pytest.mark.parametrize("text", ["", "未知", "蓝 红", "全部 紫", "、", "蓝以下", "无 蓝"])
def test_invalid_input_preserves_attrs(text):
    original = {"other": {"value": 1}, PREFERENCE_KEY: ["blue"]}
    player = SimpleNamespace(extra_attrs=original)
    with pytest.raises(ValueError):
        set_keep_rarities(player, text)
    assert player.extra_attrs is original


@pytest.mark.parametrize("attrs", [None, {}, {PREFERENCE_KEY: None}, {PREFERENCE_KEY: "blue"},
                                   {PREFERENCE_KEY: ["red"]}, {PREFERENCE_KEY: [{}]}])
def test_default_and_invalid_stored_preference(attrs):
    assert get_keep_rarities(SimpleNamespace(extra_attrs=attrs)) == list(RARITY_ORDER)
    assert get_keep_rarities(SimpleNamespace()) == list(RARITY_ORDER)


def test_explicit_empty_preference_is_distinct_from_missing():
    assert get_keep_rarities(SimpleNamespace(extra_attrs={PREFERENCE_KEY: []})) == []
    assert preference_label([]) == "不保留任何材料"


async def test_no_materials_preserves_existing_items_and_normal_sweep_costs(store, monkeypatch):
    _, ids = store
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=1))
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        set_keep_rarities(player, "无")
        session.add(ItemInstance(player_id=player.id, item_id=ids["white"], quantity=100))
        await session.flush()
        before_exp, before_stamina, before_gold = player.exp, player.stamina, player.gold
        svc = service(session, [(ids[r], 1) for r in RARITY_ORDER], [(ids[r], 2) for r in RARITY_ORDER])
        svc._item_repo.add_item_partial = AsyncMock()
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert result.success
        assert await quantities(session) == {ids["white"]: 100}
        svc._item_repo.add_item_partial.assert_not_awaited()
        assert player.exp > before_exp and player.stamina == before_stamina - 1
        assert player.mp == 0 and player.gold == before_gold
        assert "不保留任何材料" in result.message and "按品质设置舍弃" in result.message
        assert all(f"{r} ✖️3" in result.message for r in RARITY_ORDER)
        assert "背包已满，溢出丢失" not in result.message
        harvest = result.message.split("**━━ 收获 ━━**")[1].split("**━━ 消耗 ━━**")[0]
        assert "经验" in harvest and "✖️" not in harvest


async def test_default_all_sources_and_duplicate_merging(store):
    _, ids = store
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        repo = ItemRepository(session)
        original_add = repo.add_item_partial
        repo.add_item_partial = AsyncMock(side_effect=original_add)
        svc = SweepDungeonService(SimpleNamespace(update=AsyncMock()), repo)
        svc._calculate_high_grade_rewards = AsyncMock(return_value=[(ids["green"], 4), (ids["blue"], 3)])
        svc._calculate_material_rewards = AsyncMock(return_value=[(ids["white"], 2), (ids["blue"], 5), (ids["blue"], 7)])
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert await quantities(session) == {ids["white"]: 2, ids["green"]: 4, ids["blue"]: 15}
        assert repo.add_item_partial.await_count == 3
        assert result.message.count("blue ✖️15") == 1
        assert "全部品质" in result.message and "扫荡设置" in result.message
        assert "按品质设置舍弃" not in result.message


@pytest.mark.parametrize("selection,kept", [("蓝 橙", {"blue", "orange"}), ("紫", {"purple"}),
                                          ("蓝以上", {"blue", "purple", "orange"})])
async def test_filter_all_sources_before_insertion(store, selection, kept):
    _, ids = store
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        set_keep_rarities(player, selection)
        svc = service(session, [(ids[r], 1) for r in RARITY_ORDER], [(ids[r], 2) for r in RARITY_ORDER])
        original_add = svc._item_repo.add_item_partial
        svc._item_repo.add_item_partial = AsyncMock(side_effect=original_add)
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert await quantities(session) == {ids[r]: 3 for r in kept}
        assert {call.args[1] for call in svc._item_repo.add_item_partial.await_args_list} == {ids[r] for r in kept}
        assert "按品质设置舍弃" in result.message
        assert "背包已满，溢出丢失" not in result.message


async def test_remaining_slots_prioritize_orange_purple_and_preserve_existing(store, monkeypatch):
    _, ids = store
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=3))
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        session.add(ItemInstance(player_id=player.id, item_id=ids["white"], quantity=100))
        await session.flush()
        svc = service(session, [(ids[r], 100) for r in ("green", "blue", "purple", "orange")], [])
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert await quantities(session) == {ids["white"]: 100, ids["orange"]: 100, ids["purple"]: 100}
        harvest = result.message.split("**━━ 收获 ━━**")[1].split("⚠️ **背包已满")[0]
        assert "orange ✖️100" in harvest and "purple ✖️100" in harvest
        assert "blue ✖️" not in harvest and "green ✖️" not in harvest


async def test_basic_high_quality_precedes_monster_low_and_report_separates_losses(store, monkeypatch):
    _, ids = store
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=1))
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        set_keep_rarities(player, "蓝以上")
        svc = service(session, [(ids["green"], 5), (ids["blue"], 20)],
                      [(ids["white"], 3), (ids["orange"], 110)])
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert await quantities(session) == {ids["orange"]: 100}
        discarded = result.message.split("**按品质设置舍弃**：")[1].split("**━━ 收获 ━━**")[0]
        assert "green ✖️5" in discarded and "white ✖️3" in discarded
        assert "orange" not in discarded and "blue" not in discarded
        overflow = result.message.split("**背包已满，溢出丢失**：")[1].split("\n")[0]
        assert "orange ✖️10" in overflow and "blue ✖️20" in overflow
        assert "white" not in overflow and "green" not in overflow
        harvest = result.message.split("**━━ 收获 ━━**")[1].split("⚠️ **背包已满")[0]
        assert "orange ✖️100" in harvest and "blue ✖️" not in harvest


async def test_settings_handler_persists_and_invalid_or_view_do_not_mutate(store, monkeypatch):
    factory, _ = store
    async def require_player(session, event, matcher):
        return await session.get(Player, "sweep")
    monkeypatch.setattr("plugins.xiuxian_game.platform_utils.require_player", require_player)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(inventory.sweep_settings_cmd, "finish", finish)
    for text, expected in [("蓝 橙", ["blue", "orange"]), ("非法", ["blue", "orange"]),
                           ("", ["blue", "orange"]), ("紫", ["purple"]),
                           ("蓝色及以上", ["blue", "purple", "orange"]),
                           ("无", []), ("非法", []), ("", []), ("全部", list(RARITY_ORDER))]:
        with pytest.raises(FinishedException):
            await inventory.handle_sweep_settings(SimpleNamespace(), Message(text))
        # 新会话确认 JSON 赋值确实持久化，而非只修改对象内存。
        async with factory() as session:
            player = await session.get(Player, "sweep")
            assert player.extra_attrs == {"other": {"value": 7}, PREFERENCE_KEY: expected}
        if text == "":
            expected_label = "蓝色、橙色" if expected else "不保留任何材料"
            assert expected_label in finish.call_args.args[0]


async def test_reward_generation_keeps_rates_quantities_and_random_draws(store, monkeypatch):
    _, ids = store
    module = "plugins.xiuxian_game.item.sweep_dungeon_service"
    monkeypatch.setattr(module + ".get_region_materials", lambda region: {
        "merchant": list(ids.values()), "basic": [ids["white"]],
    })
    draws = []
    def choose(candidates):
        draws.append(list(candidates))
        return candidates[0]
    monkeypatch.setattr(module + ".random.choice", choose)
    monkeypatch.setattr(module + ".random.randint", lambda a, b: 3)
    rolls = iter([0.1, 0.9])
    monkeypatch.setattr(module + ".random.random", lambda: next(rolls))
    monkeypatch.setattr(module + ".luck_prob", lambda luck: 0.5)
    repo = SimpleNamespace(add_item_partial=AsyncMock())
    svc = SweepDungeonService(SimpleNamespace(), repo)
    player = SimpleNamespace(id="sweep", region="20层诡域", luck=60)
    high = await svc._calculate_high_grade_rewards(player, 200, 100)
    basic = await svc._calculate_material_rewards(player, 2)
    assert high == [(ids["green"], 30), (ids["blue"], 30), (ids["purple"], 12), (ids["orange"], 1)]
    assert basic == [(ids["white"], 4), (ids["white"], 3)]
    assert len(draws) == 6
    repo.add_item_partial.assert_not_awaited()


async def test_mp_exhaustion_still_kills_and_clears_streak(store):
    async with db.safe_session() as session:
        player = await session.get(Player, "sweep")
        player.mp = 40
        player.dungeon_kill_streak = 9
        svc = service(session, [], [])
        result = await svc.execute(player, config.items_config["by_id"]["sweep_token"], 1)
        assert result.success and player.hp == 0 and player.mp == 0
        assert player.dungeon_kill_streak == 0
        assert "理智耗尽，陷入疯狂" in result.message
