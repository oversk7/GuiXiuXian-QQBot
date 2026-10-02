"""Legacy sockets retain their contents while only template slots take effect."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine
from plugins.xiuxian_game.economy.equipment_trade_service import EquipmentTradeService
from plugins.xiuxian_game.item.gem_socket_service import GemSocketService
from plugins.xiuxian_game.item import inscription_service
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.infrastructure.exceptions import InventoryCapacityError


@pytest.fixture
def equipment(monkeypatch):
    templates = config.items_config["by_id"].copy()
    for data in [
        {"item_id": "test_socket_equipment", "name": "Test equipment", "type": "EQUIPMENT",
         "gem_slots": 2, "durability": 100, "rarity": "red"},
        {"item_id": "test_socket_gem", "name": "Test gem", "type": "GEM",
         "attr_bonus": {"attack": 7}, "attr_ratio": {"hp": 0.1}},
        {"item_id": "test_socket_inscription", "name": "Test inscription", "type": "INSCRIPTION"},
    ]:
        data["description"] = "test"
        templates[data["item_id"]] = ItemConfig(data)
    monkeypatch.setattr(config, "_cached_items_config", {"by_id": templates})
    return ItemInstance(
        player_id="test", item_id="test_socket_equipment", equipped=False,
        durability=79, upgrade_level=0, extra_attrs={}, gem_slots_data={}, quantity=1,
    )


@pytest.fixture
def service_player():
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    repo = SimpleNamespace(
        _session=session, add_item=AsyncMock(return_value=True),
        consume_item=AsyncMock(return_value=True),
        get_material_total_quantity=AsyncMock(return_value=10),
        get_all_by_player_id=AsyncMock(return_value=[]),
    )
    player_repo = SimpleNamespace(update=AsyncMock())
    player = SimpleNamespace(
        id="test", gold=2000,
        get_effective_inventory_capacity=AsyncMock(return_value=20),
    )
    return GemSocketService(repo, player_repo), player


def inscription(value):
    return {"item_id": "test_socket_inscription", "values": {"chance": value}}


def test_only_valid_occupied_slots_count_and_contribute_attributes(equipment):
    legacy = {"0": "test_socket_gem", "1": inscription(0.13),
              "2": "test_socket_gem", "5": inscription(0.91),
              "-1": "test_socket_gem", "bad": "test_socket_gem"}
    equipment.gem_slots_data = legacy.copy()
    assert equipment.available_gem_slots == 2  # Runtime obeys template, even for red.
    assert equipment.active_gem_slots_data == {"0": "test_socket_gem", "1": inscription(0.13)}
    assert equipment.used_gem_slots == 2
    assert equipment.free_gem_slots == 0
    attrs = {"attack": 10, "max_hp": 100}
    equipment._apply_gem_bonus(attrs, {"attack": 10, "max_hp": 100})
    assert attrs == {"attack": 17, "max_hp": 110}
    assert equipment.gem_slots_data == legacy


def test_overflow_only_and_empty_values_do_not_fill_valid_slots(equipment):
    equipment.gem_slots_data = {"0": None, "2": "test_socket_gem", "bad": inscription(0.9)}
    assert equipment.used_gem_slots == 0
    assert equipment.free_gem_slots == 2
    attrs = {"attack": 10, "max_hp": 100}
    equipment._apply_gem_bonus(attrs)
    assert attrs == {"attack": 10, "max_hp": 100}


def test_info_exposes_overflow_including_malformed_keys(equipment):
    equipment.gem_slots_data = {"3": "test_socket_gem", "5": inscription(0.91), "bad": "test_socket_gem"}
    info = GemSocketService.get_equipment_gem_info(equipment)
    assert len(info) == 5
    assert all(slot["is_empty"] and not slot["overflow"] for slot in info[:2])
    assert [slot["slot_number"] for slot in info[2:]] == [4, 6, "bad"]
    assert all(slot["overflow"] and not slot["is_empty"] for slot in info[2:])
    assert info[3]["inscription_data"] == inscription(0.91)


def test_battle_and_trade_read_only_active_inscriptions(equipment, monkeypatch):
    equipment.gem_slots_data = {"0": inscription(0.13), "2": inscription(0.91)}
    converter = Mock(side_effect=lambda data, **kwargs: [data])
    monkeypatch.setattr(inscription_service, "inscription_to_trigger_configs", converter)
    manager = SimpleNamespace(register_triggers=Mock())
    engine = SimpleNamespace(effect_manager=manager)
    EnhancedBattleEngine._register_equipment_triggers(engine, "test", [equipment])
    active_inscription = {**inscription(0.13), "slot_index": 0}
    converter.assert_called_once_with(active_inscription, source_name="Test equipment")
    assert manager.register_triggers.call_args_list[0].args == ("test", [active_inscription])
    assert "1铭文" in EquipmentTradeService.generate_equipment_summary(equipment)
    equipment.gem_slots_data = {"2": inscription(0.91)}
    assert "铭文" not in EquipmentTradeService.generate_equipment_summary(equipment)


@pytest.mark.parametrize("slot", [-1, 2, 5])
async def test_overflow_cannot_be_socketed(equipment, service_player, slot):
    service, player = service_player
    equipment.gem_slots_data = {"5": "test_socket_gem"}
    success, _ = await service.socket_gem(equipment, "test_socket_gem", slot, player)
    assert not success
    assert equipment.gem_slots_data == {"5": "test_socket_gem"}
    service._item_repo.consume_item.assert_not_awaited()


@pytest.mark.parametrize("protection", [False, True])
@pytest.mark.parametrize("is_inscription", [False, True])
async def test_overflow_recovery_is_free_lossless_and_preserves_values(
    equipment, service_player, monkeypatch, protection, is_inscription,
):
    service, player = service_player
    player.gold = 0
    service._item_repo.get_material_total_quantity.return_value = 0
    equipment.gem_slots_data = {"5": inscription(0.13789) if is_inscription else "test_socket_gem"}
    random_roll = Mock(side_effect=AssertionError("Overflow must not roll removal risks"))
    monkeypatch.setattr("plugins.xiuxian_game.item.gem_socket_service.random.random", random_roll)
    success, message = await service.remove_gem(equipment, 5, player, protection)
    assert success and "免费无损" in message
    assert equipment.gem_slots_data == {}
    assert (player.gold, equipment.durability) == (0, 79)
    service._item_repo.consume_item.assert_not_awaited()
    service._item_repo.get_material_total_quantity.assert_not_awaited()
    service._player_repo.update.assert_not_awaited()
    if is_inscription:
        restored = service._item_repo._session.add.call_args.args[0]
        assert restored.item_id == "test_socket_inscription"
        assert restored.extra_attrs == {"_inscription_values": {"chance": 0.13789}}
        service._item_repo._session.flush.assert_awaited_once()
    else:
        service._item_repo.add_item.assert_awaited_once_with("test", "test_socket_gem", 1)


async def test_full_inventory_preserves_overflow_gem(equipment, service_player):
    service, player = service_player
    content = "test_socket_gem"
    equipment.gem_slots_data = {"5": content}
    service._item_repo.add_item.side_effect = InventoryCapacityError()
    success, message = await service.remove_gem(equipment, 5, player, True)
    assert not success and "背包空间不足" in message
    assert equipment.gem_slots_data == {"5": content}
    assert (player.gold, equipment.durability) == (2000, 79)
    service._item_repo.consume_item.assert_not_awaited()
    service._item_repo._session.add.assert_not_called()
    service._player_repo.update.assert_not_awaited()


async def test_full_inventory_does_not_block_inscription_recovery(equipment, service_player):
    service, player = service_player
    player.get_effective_inventory_capacity.return_value = 0
    service._item_repo.add_item.side_effect = InventoryCapacityError()
    equipment.gem_slots_data = {"5": inscription(0.13789)}
    success, _ = await service.remove_gem(equipment, 5, player)
    assert success
    assert equipment.gem_slots_data == {}
    restored = service._item_repo._session.add.call_args.args[0]
    assert restored.extra_attrs == {"_inscription_values": {"chance": 0.13789}}
    player.get_effective_inventory_capacity.assert_not_awaited()
    service._item_repo.get_all_by_player_id.assert_not_awaited()
    service._item_repo.consume_item.assert_not_awaited()


async def test_normal_protected_removal_keeps_existing_costs(equipment, service_player):
    service, player = service_player
    equipment.gem_slots_data = {"0": "test_socket_gem", "5": inscription(0.91)}
    success, _ = await service.remove_gem(equipment, 0, player, True)
    assert success
    assert player.gold == 1500
    assert equipment.durability == 79
    assert equipment.gem_slots_data == {"5": inscription(0.91)}
    assert [call.args for call in service._item_repo.consume_item.await_args_list] == [
        ("test", "gem_chisel", 1), ("test", "stabilizer_crystal", 1),
    ]
    service._player_repo.update.assert_awaited_once_with(player)


async def test_overflow_empty_or_equipped_equipment_cannot_be_removed(equipment, service_player):
    service, player = service_player
    assert not (await service.can_remove_gem(equipment, 5, player))[0]
    equipment.gem_slots_data = {"5": "test_socket_gem"}
    equipment.equipped = True
    assert not (await service.can_remove_gem(equipment, 5, player))[0]
