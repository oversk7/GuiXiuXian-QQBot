"""Equipment quality is independent of wear requirements and legacy investment."""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.economy.equipment_trade_service import EquipmentTradeService
from plugins.xiuxian_game.item.catalog import _get_equipment_drop_note
from plugins.xiuxian_game.item.equipment_upgrade_service import EquipmentUpgradeService
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.world import dungeon_generation_service as dungeon


NEW_EQUIPMENT = {
    "sealed_patient_coat": (40, 0, "blue", 0.30, 3),
    "mourning_bell": (100, 0, "green", 0.40, 2),
    "warding_mirror": (100, 0, "purple", 0.60, 4),
    "execution_cord": (200, 0, "blue", 0.75, 3),
    "wake_guard_lantern": (200, 0, "orange", 1.05, 5),
    "returning_soul_register": (150, 1, "purple", 1.20, 4),
}


def test_new_equipment_stage_budgets():
    templates = config.items_config["by_id"]
    new_ids = {iid for iid, tpl in templates.items() if tpl.dungeon_drop}
    assert new_ids == set(NEW_EQUIPMENT)
    for iid, (level, reincarnation, rarity, budget, slots) in NEW_EQUIPMENT.items():
        tpl = templates[iid]
        assert (tpl.required_level, tpl.required_reincarnation, tpl.rarity) == (
            level, reincarnation, rarity,
        )
        assert sum(tpl.attr_ratio.values()) == pytest.approx(budget)
        assert tpl.gem_slots == slots
        assert not tpl.recipe
        assert not tpl.special_effects
        assert tpl.dungeon_drop["min_level"] >= level
        assert tpl.dungeon_drop["weight"] > 0


def test_all_equipment_sockets_increase_strictly_with_rarity():
    slots_by_rarity = {"white": 1, "green": 2, "blue": 3,
                       "purple": 4, "orange": 5, "red": 6}
    equipment = [config.items_config["by_id"][iid]
                 for iid in config.items_config["by_type"]["EQUIPMENT"]]
    for tpl in equipment:
        assert tpl.gem_slots == slots_by_rarity[tpl.rarity], tpl.item_id
        instance = ItemInstance(item_id=tpl.item_id, gem_slots_data={})
        assert instance.available_gem_slots == slots_by_rarity[tpl.rarity]
    for lower in equipment:
        for higher in equipment:
            if slots_by_rarity[higher.rarity] > slots_by_rarity[lower.rarity]:
                assert higher.gem_slots > lower.gem_slots, (
                    lower.item_id, higher.item_id,
                )


def test_legacy_upgrade_material_costs_preserved():
    for iid in config.items_config["by_type"]["EQUIPMENT"]:
        if iid in NEW_EQUIPMENT:
            continue
        tpl = config.items_config["by_id"][iid]
        if tpl.recipe:
            continue
        # Freeze the previous material-selection contract for existing items.
        if tpl.rarity == "orange" or tpl.required_level >= 150:
            expected = "rare_orange"
        elif tpl.rarity == "purple" or tpl.required_level >= 100:
            expected = "rare_purple"
        elif tpl.rarity == "blue" or tpl.required_level >= 60:
            expected = "rare_blue"
        else:
            expected = "rare_default"
        assert EquipmentUpgradeService._get_rare_material_tier(tpl) == expected, iid


def test_material_defaults_do_not_infer_quality_from_level():
    choose = EquipmentUpgradeService._get_rare_material_tier
    assert choose(SimpleNamespace(rarity="green", required_level=999)) == "rare_default"
    assert choose(SimpleNamespace(rarity="orange", required_level=1)) == "rare_orange"
    assert choose(SimpleNamespace(
        rarity="blue", required_level=40, upgrade_material_tier="rare_default",
    )) == "rare_default"


@pytest.mark.parametrize(("level", "expected"), [
    (39, set()),
    (40, {"sealed_patient_coat"}),
    (99, {"sealed_patient_coat"}),
    (100, {"mourning_bell", "warding_mirror"}),
    (199, {"mourning_bell", "warding_mirror"}),
    (200, {"execution_cord", "wake_guard_lantern"}),
    (299, {"execution_cord", "wake_guard_lantern"}),
    (300, {"returning_soul_register"}),
    (10000, {"returning_soul_register"}),
])
def test_additional_drop_level_boundaries(level, expected):
    rng = Mock()
    rng.random.return_value = 0.0
    rng.choices.side_effect = lambda population, **kwargs: [population[0]]
    result = dungeon._roll_additional_equipment(level, True, 0, rng)
    if not expected:
        assert result is None
        rng.random.assert_not_called()
        return
    population = rng.choices.call_args.args[0]
    assert {tpl.item_id for tpl in population} == expected
    assert result.item_id in expected
    assert rng.choices.call_args.kwargs["weights"] == [
        tpl.dungeon_drop["weight"] for tpl in population
    ]


@pytest.mark.parametrize(("elite", "threshold"), [(False, 0.0025), (True, 0.01)])
def test_additional_drop_rates(elite, threshold):
    rng = Mock()
    rng.random.return_value = threshold
    assert dungeon._roll_additional_equipment(100, elite, 0, rng) is None
    rng.random.return_value = threshold - 0.000001
    rng.choices.side_effect = lambda population, **kwargs: [population[0]]
    assert dungeon._roll_additional_equipment(100, elite, 0, rng) is not None


@pytest.mark.parametrize("elite", [False, True])
@pytest.mark.parametrize("level", [100, 250, 350])
async def test_new_pool_does_not_change_existing_loot(monkeypatch, elite, level):
    player = SimpleNamespace(id="test", luck=0)
    monkeypatch.setattr(ItemInstance, "add_item", AsyncMock(return_value=True))
    items = config.items_config
    original_roll = dungeon._roll_additional_equipment
    legacy_items = {
        "by_id": {iid: tpl for iid, tpl in items["by_id"].items() if iid not in NEW_EQUIPMENT},
        "by_name": {name: tpl for name, tpl in items["by_name"].items() if tpl.item_id not in NEW_EQUIPMENT},
        "by_type": {
            kind: [iid for iid in ids if iid not in NEW_EQUIPMENT]
            for kind, ids in items["by_type"].items()
        },
    }

    async def run(seed):
        added = []
        text = await dungeon.handle_monster_drops(
            SimpleNamespace(add=added.append), player, level,
            "第20层诡域", random.Random(seed), elite,
        )
        return text, [(eq.item_id, eq.extra_attrs) for eq in added]

    for seed in range(12):
        monkeypatch.setattr(config, "_cached_items_config", legacy_items)
        before = await run(seed)
        monkeypatch.setattr(config, "_cached_items_config", items)
        # With the extra roll suppressed, every existing drop and affix must match.
        monkeypatch.setattr(dungeon, "_roll_additional_equipment", lambda *args: None)
        assert await run(seed) == before
        monkeypatch.setattr(dungeon, "_roll_additional_equipment", original_roll)


def test_legacy_instance_upgrade_and_sockets_are_unchanged():
    tpl = config.items_config["by_id"]["world_fragment_blade"]
    eq = ItemInstance(
        item_id=tpl.item_id, equipped=True, upgrade_level=7,
        durability=123, extra_attrs={"_affixes": [], "_player_locked": True},
        gem_slots_data={"5": "existing_socket_content"},
    )
    assert eq.get_upgrade_bonus_multiplier() == pytest.approx(2.4)
    assert eq.available_gem_slots == 5
    assert eq.get_gem_in_slot(5) == "existing_socket_content"
    assert eq.durability == 123
    assert eq.extra_attrs["_player_locked"] is True
    assert (tpl.required_level, tpl.required_reincarnation) == (150, 1)


def test_template_defaults_leave_existing_drop_pool_unchanged():
    tpl = ItemConfig({
        "item_id": "example", "name": "Example", "description": "",
        "type": "EQUIPMENT",
    })
    assert tpl.dungeon_drop is None
    assert tpl.upgrade_material_tier is None


@pytest.mark.parametrize("iid", NEW_EQUIPMENT)
def test_trade_summary_shows_wear_requirements(iid):
    tpl = config.items_config["by_id"][iid]
    eq = ItemInstance(
        item_id=iid, upgrade_level=0, durability=tpl.durability,
        extra_attrs={}, gem_slots_data={},
    )
    summary = EquipmentTradeService.generate_equipment_summary(eq)
    assert tpl.get_display_name() in summary
    assert f"Lv.{tpl.required_level}" in summary
    assert ("·1转" in summary) == bool(tpl.required_reincarnation)
    assert EquipmentTradeService.is_instance_trade(iid)


def test_catalog_drop_ranges_are_separate_from_wear_level():
    templates = config.items_config["by_id"]
    assert "Lv.40-99" in _get_equipment_drop_note(templates["sealed_patient_coat"])
    assert "Lv.300及以上" in _get_equipment_drop_note(templates["returning_soul_register"])
    assert _get_equipment_drop_note(templates["world_fragment_blade"]) == ""


async def test_additional_drop_creates_tradeable_affixed_instance(monkeypatch):
    tpl = config.items_config["by_id"]["wake_guard_lantern"]
    monkeypatch.setattr(dungeon, "_roll_additional_equipment", lambda *args: tpl)
    monkeypatch.setattr(ItemInstance, "add_item", AsyncMock(return_value=True))
    added = []
    text = await dungeon.handle_monster_drops(
        SimpleNamespace(add=added.append), SimpleNamespace(id="test", luck=0),
        250, "第50层诡域", random.Random(1), False,
    )
    equipment = next(eq for eq in added if eq.item_id == tpl.item_id)
    assert equipment.player_id == "test"
    assert equipment.quantity == 1
    assert equipment.durability == tpl.durability
    assert len(equipment.extra_attrs["_affixes"]) == 4
    assert tpl.name in text
    assert "4条词缀" in text
