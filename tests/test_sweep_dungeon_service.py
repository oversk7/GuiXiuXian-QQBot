from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.item.sweep_dungeon_service import SweepDungeonService


def make_player(**overrides):
    attrs = dict(
        id="sweep-player", region="20层诡域", stamina=10,
        mp=400, max_mp=400, hp=1000, defense=50, luck=0,
        exp=0, gold=1_000_000, dungeon_kill_streak=3,
    )
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def make_service(equipment=()):
    player_repo = SimpleNamespace(update=AsyncMock())
    item_repo = SimpleNamespace(
        get_equipped_equipment=AsyncMock(return_value=list(equipment)),
        update_extra_attrs_batch=AsyncMock(),
    )
    service = SweepDungeonService(player_repo, item_repo)
    service._calculate_high_grade_rewards = AsyncMock(return_value=([], []))
    service._calculate_material_rewards = AsyncMock(return_value=[])
    return service, player_repo, item_repo


async def sweep(service, player, quantity=1):
    return await service.execute(player, config.items_config["by_id"]["sweep_token"], quantity)


@pytest.mark.parametrize("durability", [0, 1, 100])
async def test_equipped_and_naked_have_same_tiles_and_fee(durability, monkeypatch):
    monkeypatch.setattr("plugins.xiuxian_game.item.sweep_dungeon_service.random.randint", lambda a, b: 2)
    equipment = SimpleNamespace(
        equipped=True, durability=durability,
        extra_attrs={"_persist_bonus": {"max_mp": 600}},
    )
    before = deepcopy(vars(equipment))
    dressed = make_player(mp=1000, max_mp=1000)
    naked = make_player()
    dressed_service, _, item_repo = make_service([equipment])
    naked_service, _, _ = make_service()

    dressed_result = await sweep(dressed_service, dressed)
    naked_result = await sweep(naked_service, naked)

    assert dressed_result.success and naked_result.success
    assert dressed.exp == naked.exp == 30_000
    assert dressed.gold == naked.gold == 965_000
    assert dressed_result.attribute_changes["mp"] == naked_result.attribute_changes["mp"] == -400
    assert "探索 **200** 格" in dressed_result.message
    assert "裸装理智 **400**" in dressed_result.message
    assert "扫荡修理费 **35,000**" in dressed_result.message
    assert vars(equipment) == before
    item_repo.update_extra_attrs_batch.assert_not_awaited()
    assert dressed.mp == 600
    assert naked.mp == naked.hp == 0
    assert naked.dungeon_kill_streak == 0


async def test_current_mp_below_naked_max_is_not_replaced_by_full_mp():
    equipment = SimpleNamespace(extra_attrs={"_persist_bonus": {"max_mp": 600}})
    service, _, _ = make_service([equipment])
    player = make_player(mp=123, max_mp=1000)

    result = await sweep(service, player)

    assert result.success
    assert "探索 **61** 格" in result.message
    assert "裸装理智 **123**" in result.message
    assert result.attribute_changes["mp"] == -122
    assert player.mp == 1
    assert player.hp >= 1
    assert player.gold == 1_000_000 - 45 * 50 * 5


@pytest.mark.parametrize(("region", "cap"), [
    ("1层诡域", 2_000),
    ("7层诡域", 2_000),
    ("8层诡域", 7_500),
    ("19层诡域", 7_500),
    ("20层诡域", 35_000),
    ("39层诡域", 35_000),
    ("40层诡域", 108_000),
    ("59层诡域", 108_000),
    ("60层诡域", 250_000),
    ("第200层诡域", 250_000),
])
async def test_region_standard_fee_caps(region, cap):
    service, _, _ = make_service()
    player = make_player(region=region, mp=1_000_000, max_mp=1_000_000)

    result = await sweep(service, player)

    assert result.success
    assert result.attribute_changes["gold"] == -cap
    assert player.gold == 1_000_000 - cap


async def test_batch_keeps_tile_multiplier_and_charges_cap_per_token():
    service, _, _ = make_service()
    player = make_player()

    result = await sweep(service, player, 3)

    assert result.success
    assert "探索 **600** 格" in result.message
    assert result.attribute_changes["mp"] == -1200
    assert result.attribute_changes["gold"] == -105_000
    assert player.gold == 895_000
    assert player.stamina == 7
    assert player.mp == player.hp == 0
    service._calculate_high_grade_rewards.assert_awaited_once_with(player, 100, 450)
    service._calculate_material_rewards.assert_awaited_once_with(player, 120)


async def test_batch_fee_uses_per_token_rounding():
    service, _, _ = make_service()
    player = make_player(mp=14, max_mp=14)

    result = await sweep(service, player, 2)

    assert result.success
    assert "探索 **14** 格" in result.message
    assert player.gold == 1_000_000 - 5 * 50 * 5 * 2


async def test_insufficient_gold_leaves_player_and_rewards_untouched():
    service, player_repo, _ = make_service()
    player = make_player(gold=104_999)
    before = deepcopy(vars(player))

    result = await sweep(service, player, 3)

    assert not result.success
    assert "需要 105,000 金币" in result.message
    assert vars(player) == before
    player_repo.update.assert_not_awaited()
    service._calculate_high_grade_rewards.assert_not_awaited()
    service._calculate_material_rewards.assert_not_awaited()


async def test_exact_gold_can_pay_and_succeed():
    service, _, _ = make_service()
    player = make_player(gold=35_000)

    result = await sweep(service, player)

    assert result.success
    assert player.gold == 0


@pytest.mark.parametrize("overrides", [
    {"region": "大都会"},
    {"region": "不存在的诡域"},
    {"stamina": 0},
])
async def test_original_prechecks_still_do_not_charge(overrides):
    service, player_repo, _ = make_service()
    player = make_player(**overrides)
    before = deepcopy(vars(player))

    result = await sweep(service, player)

    assert not result.success
    assert vars(player) == before
    player_repo.update.assert_not_awaited()
