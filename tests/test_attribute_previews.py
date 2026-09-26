"""属性预览和执行值必须一致，且预览保持 ORM 对象只读。"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.cultivate.reincarnation_service import ReincarnationService
from plugins.xiuxian_game.infrastructure.repositories.elixir_usage_repository import ElixirUsageRepository
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.vip_equipment_bonus_repository import VIPEquipmentBonusRepository
from plugins.xiuxian_game.item.attribute_preview_service import MAIN_ATTRS, project_equipment
from plugins.xiuxian_game.battle.attribute_summary import get_battle_attribute_summary, summarize_battle_attributes
from plugins.xiuxian_game.item import equipment_commands as commands
from plugins.xiuxian_game.models.temporary_buff import TemporaryBuff
import plugins.xiuxian_game.domain.attributes.attribute_sources.pet_source as pet_source
from plugins.xiuxian_game.item.equipment_commands import validate_equipment_swap
from plugins.xiuxian_game.item.equipment_service import EquipmentService
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.elixir_usage import ElixirUsageLog
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.vip_equipment_bonus import VIPEquipmentBonus


@pytest.fixture
async def preview_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    monkeypatch.setattr(db, "AsyncSessionLocal", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    try:
        yield
    finally:
        await engine.dispose()


def item(item_id, id, equipped=False, **kwargs):
    return ItemInstance(id=id, player_id="preview", item_id=item_id, equipped=equipped,
                        durability=100, upgrade_level=kwargs.get("upgrade_level", 0),
                        extra_attrs=kwargs.get("extra_attrs", {}),
                        gem_slots_data=kwargs.get("gem_slots_data", {}))


def equipment_service(session):
    return EquipmentService(ItemRepository(session), PlayerRepository(session))


def rebirth_service(session):
    return ReincarnationService(PlayerRepository(session), ElixirUsageRepository(session),
                                VIPEquipmentBonusRepository(session), ItemRepository(session))


def six(player):
    return {key: getattr(player, key) for key in MAIN_ATTRS}


async def test_swap_projection_matches_wear_with_ratio_gem_and_both_conversions(preview_db, monkeypatch):
    templates = {
        "preview_ratio": {"attr_bonus": {"hp": 30, "attack": 10}, "attr_ratio": {"hp": 0.5, "attack": 0.2}},
        "preview_gem": {"attr_bonus": {"hp": 9}, "attr_ratio": {"attack": 0.1}},
        "preview_mp": {"attr_bonus": {"hp": 11}, "special_effects": [{"effect": "mp_from_hp", "value": 33}]},
        "preview_hp": {"attr_bonus": {"attack": 7}, "special_effects": [{"effect": "hp_from_attack", "value": 41}]},
    }
    for name, attrs in templates.items():
        monkeypatch.setitem(config.items_config["by_id"], name, ItemConfig({
            "item_id": name, "name": name, "type": "EQUIPMENT", "description": "test", **attrs,
        }))
    async with db.safe_session() as session:
        player = Player(id="preview", uid=71001, nickname="Preview", level=300, resentment=100000)
        player.max_hp, player.max_mp, player.attack = 101, 53, 31
        session.add(player)
        ratio = item("preview_ratio", 701, upgrade_level=3,
                     extra_attrs={"nested": {"list": [1, {"value": 2}]}, "attack": 4},
                     gem_slots_data={"1": "preview_gem"})
        mp = item("preview_mp", 702, equipped=True)
        hp = item("preview_hp", 703, equipped=True)
        session.add_all([ratio, mp, hp])
        await session.flush()
        await equipment_service(session).recalc_equipment_attributes(player, [mp, hp])
        await session.flush()
        before = six(player)
        originals = {eq.id: deepcopy((eq.equipped, eq.extra_attrs, eq.gem_slots_data)) for eq in [ratio, mp, hp]}
        predicted, copies = project_equipment(player, [mp, hp], ratio)
        assert not session.dirty
        assert six(player) == before
        assert {eq.id: (eq.equipped, eq.extra_attrs, eq.gem_slots_data) for eq in [ratio, mp, hp]} == originals
        assert copies[0].extra_attrs is not mp.extra_attrs
        assert copies[-1].extra_attrs["nested"] is not ratio.extra_attrs["nested"]
        assert predicted["max_mp"] > before["max_mp"]  # 新 HP 进入生命转理智
        assert predicted["max_hp"] > before["max_hp"]
        ratio.equipped = True
        await equipment_service(session).recalc_equipment_attributes(player, [mp, hp, ratio])
        assert {key: getattr(player, key) for key in Player.INIT_ATTRS} == predicted
        assert player.hp <= player.max_hp and player.mp <= player.max_mp


async def test_rebirth_preview_matches_execution_with_negative_and_volatile_ledgers(preview_db):
    async with db.safe_session() as session:
        player = Player(id="preview", uid=71001, nickname="Preview", level=300, resentment=100000)
        player.max_hp, player.attack = 777, 300
        player.exp, player.attribute_points = 99, 13
        equipped = item("vip_blade_zhanlongshan", 704, equipped=True,
                        gem_slots_data={"0": "critical_bead_10"},
                        extra_attrs={"_persist_bonus": {"max_hp": 123}, "nested": {"x": [1]}})
        session.add_all([player, equipped,
                         ElixirUsageLog(player_id="preview", item_id="ledger_calibration", quantity=1,
                                        attribute_changes={"max_hp": -40, "attack": 25}),
                         ElixirUsageLog(player_id="preview", item_id="cooking_perfect_dish", quantity=1,
                                        attribute_changes={"luck": 900}),
                         VIPEquipmentBonus(player_id="preview", bonus_attrs={"max_mp": 44})])
        await session.flush()
        original = deepcopy(equipped.extra_attrs)
        before = six(player)
        expected = await rebirth_service(session).preview_reincarnation(player)
        assert not session.dirty
        assert six(player) == before and equipped.extra_attrs == original
        assert expected["elixir"]["max_hp"] == -40
        assert expected["elixir"].get("luck", 0) == 0
        assert set(expected["after"]) == set(MAIN_ATTRS)  # 宝石战斗值不能被误报为六维重建值
        await rebirth_service(session).perform_reincarnation(player)
        assert six(player) == expected["after"]
        assert (player.level, player.exp, player.attribute_points) == (1, 0, 0)
        assert equipped.equipped and equipped.extra_attrs["nested"] == {"x": [1]}
        assert player.hp == expected["base"]["max_hp"]  # 真实执行先回血，再加装备


def test_swap_validation_respects_name_slots_and_unwear_order(monkeypatch):
    slot_cfg = ItemConfig({"item_id": "preview_slots", "name": "扩槽玉", "type": "EQUIPMENT",
                           "description": "test", "equipment_slot_bonus": 2})
    ordinary = ItemConfig({"item_id": "preview_plain", "name": "普通装备", "type": "EQUIPMENT",
                           "description": "test"})
    monkeypatch.setitem(config.items_config["by_id"], "preview_slots", slot_cfg)
    monkeypatch.setitem(config.items_config["by_id"], "preview_plain", ordinary)
    for index in range(2, 8):
        name = f"preview_plain_{index}"
        monkeypatch.setitem(config.items_config["by_id"], name, ItemConfig({
            "item_id": name, "name": name, "type": "EQUIPMENT", "description": "test",
        }))
    player = SimpleNamespace(id="preview", level=20, reincarnation_level=0)
    slots = item("preview_slots", 1, equipped=True)
    equipped = [slots] + [item(f"preview_plain_{i}", i, equipped=True) for i in range(2, 8)]
    candidate = item("preview_plain", 8)
    assert "装备栏已满" in validate_equipment_swap(player, equipped, candidate, None)
    assert validate_equipment_swap(player, equipped, candidate, equipped[1]) is None
    assert "同名" in validate_equipment_swap(player, equipped, item("preview_plain_3", 10), equipped[1])
    assert "装备槽不足" in validate_equipment_swap(player, equipped, candidate, slots)
    assert validate_equipment_swap(player, equipped, item("preview_slots", 9), slots) is not None
    candidate.player_id = "stranger"
    assert "不属于你" in validate_equipment_swap(player, equipped, candidate, equipped[1])


async def test_gem_swap_preview_matches_commands_and_keeps_growth_pet_buffs(preview_db, monkeypatch):
    async def buffs(cls, session, player_id):
        return {"critical_rate": 3, "combo_rate": 6}

    class PetSource:
        async def calculate_full_bonus(self, player, session):
            return {"critical_rate": 2.5}

    async def require_player(session, event, matcher):
        return await session.get(Player, "preview")

    monkeypatch.setattr(TemporaryBuff, "get_total_attribute_bonuses", classmethod(buffs))
    monkeypatch.setattr(pet_source, "_instance", PetSource())
    monkeypatch.setattr(commands, "require_player", require_player)
    monkeypatch.setattr(commands, "build_markdown", lambda text: text)
    monkeypatch.setattr(commands, "message_add_head", lambda text, event: text)
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService
    monkeypatch.setattr(NoviceQuestService, "check_and_advance_quest", AsyncMock(return_value=(False, "")))
    preview_finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(commands.preview_equipment, "finish", preview_finish)
    monkeypatch.setattr(commands.unwear_equipment, "finish", AsyncMock(side_effect=FinishedException))
    monkeypatch.setattr(commands.wear_equipment, "finish", AsyncMock(side_effect=FinishedException))

    async with db.safe_session() as session:
        player = Player(id="preview", uid=71001, nickname="Preview", level=300,
                        critical_rate=35, critical_power=7, combo_rate=20)
        old = item("fog_coat", 801, equipped=True,
                   gem_slots_data={"0": "critical_bead_10", "1": "combo_bead_10"},
                   extra_attrs={"_affixes": [{"affix_id": "combo_rate", "tier": "T1", "value": 5}]})
        companion = item("lucky_scissors", 802, equipped=True)
        new = item("soul_flag", 803,
                   gem_slots_data={"0": "critical_power_agate_10", "1": "combo_bead_10", "2": "combo_bead_10"},
                   extra_attrs={"_affixes": [{"affix_id": "critical_rate", "tier": "T1", "value": 4}]})
        session.add_all([player, old, companion, new])
        await session.flush()
        await equipment_service(session).recalc_equipment_attributes(player, [old, companion])
        await session.flush()
        before_fields = {key: getattr(player, key) for key in Player.INIT_ATTRS}
        before_state = (player.hp, player.mp, player.gold)
        before_items = {eq.id: deepcopy((eq.equipped, eq.extra_attrs, eq.gem_slots_data, eq.durability))
                        for eq in [old, companion, new]}
        stored, projected_items = project_equipment(player, [old, companion], new, old)
        current = await player.get_effective_attributes(session)
        projected = {key: current[key] + stored[key] - getattr(player, key) for key in Player.INIT_ATTRS}
        expected_battle = summarize_battle_attributes(projected, projected_items, player.level)
        assert stored["critical_rate"] == 35  # 旧暴击宝石移除，永久暴击不丢失
        assert expected_battle["critical_rate"]["raw"] == 44.5
        assert expected_battle["critical_power"]["effective"] == 57
        assert expected_battle["combo_rate"]["raw"] == 66
        assert expected_battle["combo_rate"]["effective"] == 60
        assert expected_battle["combo_rate"]["overflow"] == 6
        assert not session.dirty and not session.new and not session.deleted

    for _ in range(2):  # 连续预览也不能累加或扣减属性
        with pytest.raises(FinishedException):
            await commands.handle_equipment_preview(SimpleNamespace(), Message("3 1"))
    text = preview_finish.call_args.args[0]
    assert "暴击率：生效 65.5 → 44.5%" in text
    assert "暴击力：生效 7 → 57点" in text
    assert "连击率：生效 51 → 60%" in text
    assert "溢出 0 → 6" in text
    assert "失去：雾都猎手 2件" in text
    async with db.safe_session() as session:
        player = await session.get(Player, "preview")
        assert {key: getattr(player, key) for key in Player.INIT_ATTRS} == before_fields
        assert (player.hp, player.mp, player.gold) == before_state
        items = await ItemRepository(session).get_equipment_for_numbering("preview", config.items_config["by_type"]["EQUIPMENT"])
        assert {eq.id: (eq.equipped, eq.extra_attrs, eq.gem_slots_data, eq.durability) for eq in items} == before_items

    with pytest.raises(FinishedException):
        await commands.unwear_equipment.handlers[0].call(event=SimpleNamespace(), args=Message("1"))
    with pytest.raises(FinishedException):
        await commands.wear_equipment.handlers[0].call(event=SimpleNamespace(), args=Message("3"))
    async with db.safe_session() as session:
        player = await session.get(Player, "preview")
        assert {key: getattr(player, key) for key in Player.INIT_ATTRS} == stored
        actual_battle = await get_battle_attribute_summary(player, session)
        assert actual_battle == expected_battle


@pytest.mark.parametrize("field,value,error", [
    ("level", 1, "等级不足"),
    ("reincarnation_level", 0, "转数不足"),
])
def test_swap_rejects_unmet_requirements(field, value, error):
    player = SimpleNamespace(id="preview", level=300, reincarnation_level=1)
    setattr(player, field, value)
    target = item("reality_suicide_note", 901)
    assert error in validate_equipment_swap(player, [], target, None)


def test_swap_rejects_broken_or_already_equipped():
    player = SimpleNamespace(id="preview", level=300, reincarnation_level=1)
    target = item("reality_suicide_note", 901)
    target.durability = 0
    assert "已损坏" in validate_equipment_swap(player, [], target, None)
    target.equipped = True
    assert "已经穿戴" in validate_equipment_swap(player, [target], target, None)
