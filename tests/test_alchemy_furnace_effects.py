"""Furnace effects remain available to commands and injected services."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.alchemy.service import AlchemyService
from plugins.xiuxian_game.item import equipment_commands as equipment
from plugins.xiuxian_game.models.inventory import ItemInstance


@pytest.mark.parametrize(
    "level,multiplier,durability",
    [(0, 1.0, 5), (1, 1.1, 5), (2, 1.2, 4), (3, 1.3, 4),
     (4, 1.4, 4), (5, 1.5, 3), (6, 1.6, 3), (7, 1.7, 3),
     (8, 1.8, 2), (9, 1.9, 2), (10, 2.0, 2)],
)
def test_furnace_effects_support_class_and_instance_calls(level, multiplier, durability):
    service = AlchemyService(
        SimpleNamespace(), SimpleNamespace(_session=SimpleNamespace())
    )
    for effects in (AlchemyService.get_furnace_effects, service.get_furnace_effects):
        success, cost = effects(level)
        assert success == pytest.approx(multiplier)
        assert cost == durability


@pytest.mark.parametrize(
    "level,multiplier,durability,next_effects",
    [(0, "1.0", 5, (1, "1.1", 5)),
     (4, "1.4", 4, (5, "1.5", 3)),
     (10, "2.0", 2, None)],
)
async def test_furnace_detail_renders_current_and_next_effects(
    monkeypatch, level, multiplier, durability, next_effects,
):
    furnace = ItemInstance(
        id=300, player_id="furnace-player", item_id="furnace", quantity=1,
        durability=100, equipped=False, upgrade_level=level,
        extra_attrs={}, gem_slots_data={},
    )

    @asynccontextmanager
    async def session():
        yield SimpleNamespace()

    monkeypatch.setattr(equipment, "safe_session", session)
    monkeypatch.setattr(
        equipment, "require_player", AsyncMock(return_value=SimpleNamespace(id="furnace-player"))
    )
    lookup = AsyncMock(return_value=furnace)
    monkeypatch.setattr(equipment, "find_equipment_by_input", lookup)
    monkeypatch.setattr(
        equipment.ItemRepository, "get_equipment_for_numbering", AsyncMock(return_value=[furnace])
    )
    monkeypatch.setattr(equipment, "build_markdown", lambda text: text)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(equipment.equipment_detail, "finish", finish)

    with pytest.raises(FinishedException):
        await equipment.equipment_detail.handlers[0].call(
            event=SimpleNamespace(), args=Message("3")
        )

    assert lookup.await_args.args[1:] == ("furnace-player", "3")
    text = str(finish.call_args.args[0])
    assert f"当前成功率倍率：×{multiplier}" in text
    assert f"每炉耐久消耗：{durability}点" in text
    if next_effects:
        next_level, next_multiplier, next_cost = next_effects
        assert (
            f"下一阶(+{next_level})预览：成功率×{next_multiplier}，耐久消耗 {next_cost}点"
        ) in text
    else:
        assert "下一阶" not in text
    if level:
        assert f"当前耐久消耗：{durability}点/炉" in text
