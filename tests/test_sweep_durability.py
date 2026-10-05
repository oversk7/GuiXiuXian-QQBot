from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.item.sweep_dungeon_service import SweepDungeonService


def make_player(**overrides):
    attrs = dict(
        id="sweep-test", region="20层诡域", stamina=10,
        mp=1000, max_mp=4000, hp=2000, max_hp=2000,
        attack=100, defense=50, luck=0, exp=0, gold=100000,
        dungeon_kill_streak=0,
    )
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def make_equipment(durability):
    return SimpleNamespace(
        durability=durability, equipped=True,
        config=SimpleNamespace(name="测试装备", durability=100),
        extra_attrs={"_persist_bonus": {"max_mp": 3000, "attack": 50}},
    )


def make_service(equipment):
    player_repo = SimpleNamespace(update=AsyncMock())
    item_repo = SimpleNamespace(
        get_equipped_equipment=AsyncMock(return_value=equipment),
        update_extra_attrs_batch=AsyncMock(),
    )
    equipment_service = SimpleNamespace(recalc_equipment_attributes=AsyncMock())
    service = SweepDungeonService(player_repo, item_repo, equipment_service)
    service._calculate_high_grade_rewards = AsyncMock(return_value=[])
    service._calculate_material_rewards = AsyncMock(return_value=[])
    return service, item_repo, equipment_service


@pytest.mark.parametrize(("quantity", "remaining"), [(1, [1, 40]), (3, [1, 1])])
async def test_sweep_preserves_worn_equipment_and_original_rewards(quantity, remaining, monkeypatch):
    monkeypatch.setattr("plugins.xiuxian_game.item.sweep_dungeon_service.random.randint", lambda a, b: 2)
    equipment = [make_equipment(60), make_equipment(100)]
    bonuses = [deepcopy(eq.extra_attrs) for eq in equipment]
    service, item_repo, equipment_service = make_service(equipment)
    player = make_player()

    result = await service.execute(player, config.items_config["by_id"]["sweep_token"], quantity)

    assert result.success
    # 原公式：min(1000 // 2, int(60 / 0.75)) = 80 格/张。
    assert f"探索 **{80 * quantity}** 格" in result.message
    assert player.exp == 60 * quantity * 2 * 100
    assert player.mp == 1000 - 160 * quantity
    assert player.stamina == 10 - quantity
    assert player.gold == 100000
    service._calculate_high_grade_rewards.assert_awaited_once_with(player, 100, 60 * quantity)
    service._calculate_material_rewards.assert_awaited_once_with(player, 16 * quantity)
    assert [eq.durability for eq in equipment] == remaining
    assert all(eq.equipped for eq in equipment)
    assert [eq.extra_attrs for eq in equipment] == bonuses
    assert player.max_mp == 4000 and player.attack == 100
    equipment_service.recalc_equipment_attributes.assert_not_awaited()
    item_repo.update_extra_attrs_batch.assert_awaited_once_with(equipment)
    assert "仍保持穿戴" in result.message
    assert "自动卸下" not in result.message


async def test_mp_limited_sweep_keeps_normal_durability_loss():
    equipment = [make_equipment(60)]
    service, _, _ = make_service(equipment)
    player = make_player(mp=41)

    result = await service.execute(player, config.items_config["by_id"]["sweep_token"], 1)

    assert result.success
    assert "探索 **20** 格" in result.message
    assert equipment[0].durability == 45
    assert equipment[0].equipped
    assert player.mp == 1


async def test_one_durability_still_blocks_next_sweep_before_consumption():
    equipment = [make_equipment(60)]
    service, item_repo, _ = make_service(equipment)
    player = make_player()
    token = config.items_config["by_id"]["sweep_token"]
    first = await service.execute(player, token, 1)
    assert first.success and equipment[0].durability == 1
    before = deepcopy(vars(player))
    service._calculate_high_grade_rewards.reset_mock()
    service._calculate_material_rewards.reset_mock()
    item_repo.update_extra_attrs_batch.reset_mock()

    second = await service.execute(player, token, 1)

    assert not second.success
    assert "一键修理" in second.message
    assert vars(player) == before
    assert equipment[0].durability == 1 and equipment[0].equipped
    service._calculate_high_grade_rewards.assert_not_awaited()
    service._calculate_material_rewards.assert_not_awaited()
    item_repo.update_extra_attrs_batch.assert_not_awaited()


async def test_already_broken_equipment_is_not_repaired_by_sweep():
    equipment = [make_equipment(0)]
    service, item_repo, _ = make_service(equipment)
    player = make_player()
    before = deepcopy(vars(player))

    result = await service.execute(player, config.items_config["by_id"]["sweep_token"], 1)

    assert not result.success
    assert equipment[0].durability == 0
    assert vars(player) == before
    item_repo.update_extra_attrs_batch.assert_not_awaited()


async def test_unequipped_sweep_keeps_original_mp_limit():
    service, item_repo, _ = make_service([])
    player = make_player(mp=41)

    result = await service.execute(player, config.items_config["by_id"]["sweep_token"], 1)

    assert result.success
    assert "探索 **20** 格" in result.message
    assert player.mp == 1
    item_repo.update_extra_attrs_batch.assert_not_awaited()
