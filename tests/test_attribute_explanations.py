"""属性解释必须与实际开战值一致，且展示不能改变角色状态。"""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game.battle.attribute_summary import (
    format_battle_attribute_line, get_battle_attribute_summary, summarize_battle_attributes,
)
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator
from plugins.xiuxian_game.battle.integration_helper import BattleIntegrationHelper
from plugins.xiuxian_game.item.buff_commands import format_attribute_breakdown
from plugins.xiuxian_game.item.set_bonus_service import get_set_t1_bonuses
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.elixir_usage import ElixirUsageLog
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.temporary_buff import TemporaryBuff
import plugins.xiuxian_game.domain.attributes.attribute_sources.pet_source as pet_source


@pytest.mark.parametrize("name,cap", BattleAttributeCalculator.ATTRIBUTE_CAPS.items())
def test_overflow_uses_the_actual_combat_cap(name, cap):
    values = dict(Player.INIT_ATTRS)
    values[name] = cap + 12.5
    player = SimpleNamespace(level=1, **values)
    row = summarize_battle_attributes(values)[name]
    assert row["raw"] == cap + 12.5
    assert row["effective"] == BattleAttributeCalculator.calculate_effective_attributes(player)[name] == cap
    assert row["overflow"] == 12.5
    assert "溢出12.5个百分点" in format_battle_attribute_line(name, row)


def test_opponent_dependent_probability_is_not_called_overflow():
    rows = summarize_battle_attributes({"accuracy_rate": 160, "critical_rate": 140, "critical_power": 250})
    assert rows["accuracy_rate"]["overflow"] == 0
    assert rows["critical_rate"]["effective"] == 140
    assert rows["critical_power"]["cap"] is None
    assert rows["critical_power"]["effective"] == 250
    assert "250点" in format_battle_attribute_line("critical_power", rows["critical_power"])
    assert "溢出" not in format_battle_attribute_line("accuracy_rate", rows["accuracy_rate"])
    assert BattleAttributeCalculator.calculate_hit_chance(rows["accuracy_rate"]["effective"], 80) == 0.8


def test_negative_and_uncapped_values_keep_existing_battle_semantics():
    rows = summarize_battle_attributes({"critical_rate": -20, "lifesteal_rate": 150, "regen_rate": 120, "true_damage_rate": 120})
    assert rows["critical_rate"]["raw"] == -20
    assert rows["critical_rate"]["effective"] == 0
    assert rows["critical_rate"]["overflow"] == 0
    assert rows["lifesteal_rate"]["effective"] == 150
    assert rows["regen_rate"]["effective"] == 120
    assert rows["true_damage_rate"]["effective"] == 120
    assert "触发概率最多100%" in format_battle_attribute_line("true_damage_rate", rows["true_damage_rate"])


@pytest.fixture
async def explanation_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        monkeypatch.setattr(db, "AsyncSessionLocal", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))

        async def buffs(cls, session, player_id):
            return {"attack": -5, "defense": 100, "critical_rate": 4, "combo_rate": 5}

        async def permanent(cls, session, player_id):
            return {"attack": 10, "defense": -2}

        class PetSource:
            async def calculate_full_bonus(self, player, session):
                return {"attack": 2, "critical_rate": 3.25}

        monkeypatch.setattr(TemporaryBuff, "get_total_attribute_bonuses", classmethod(buffs))
        monkeypatch.setattr(ElixirUsageLog, "get_total_attribute_changes", classmethod(permanent))
        monkeypatch.setattr(pet_source, "_instance", PetSource())
        async with db.safe_session() as session:
            session.add(Player(
                id="explain", uid=98100, nickname="收益测试", attack=130, defense=10,
                critical_rate=25, critical_power=250, combo_rate=58,
            ))
            session.add_all([
                ItemInstance(
                    id=98101, player_id="explain", item_id="fog_coat", equipped=True,
                    durability=100, upgrade_level=0, gem_slots_data={"0": "critical_bead_10"},
                    extra_attrs={
                        "_persist_bonus": {"attack": 20, "critical_rate": 20, "combo_rate": 58},
                        "_affixes": [
                            {"affix_id": "critical_rate", "tier": "T1", "value": 6.5},
                            {"affix_id": "combo_rate", "tier": "T1", "value": 7.5},
                            {"affix_id": "immobilize_rate", "tier": "T1", "value": 2.75},
                        ],
                    },
                ),
                ItemInstance(
                    id=98102, player_id="explain", item_id="lucky_scissors", equipped=True,
                    durability=100, upgrade_level=0, gem_slots_data={}, extra_attrs={},
                ),
            ])
        yield
    finally:
        await engine.dispose()


async def test_sources_sum_to_battle_input_and_cap_matches_engine(explanation_db):
    async with db.safe_session() as session:
        player = await session.get(Player, "explain")
        eq = await session.get(ItemInstance, 98101)
        saved_extra = deepcopy(eq.extra_attrs)
        saved_gems = deepcopy(eq.gem_slots_data)
        breakdown = await player.get_attribute_breakdown(session)
        rows = await get_battle_attribute_summary(player, session, effective_attrs=breakdown["total"])
        assert rows["critical_rate"]["raw"] == 43.75
        assert rows["combo_rate"]["raw"] == 70.5
        assert rows["combo_rate"]["effective"] == 60
        assert rows["combo_rate"]["overflow"] == 10.5
        assert rows["immobilize_rate"]["raw"] == 2.75
        assert rows["critical_rate"]["affix"] == 6.5
        assert rows["critical_rate"]["set"] == 5
        extra = get_set_t1_bonuses(["fog_coat", "lucky_scissors"])
        for name, value in {"critical_rate": 6.5, "combo_rate": 7.5, "immobilize_rate": 2.75}.items():
            extra[name] = extra.get(name, 0) + value
        combat = await BattleAttributeCalculator.calculate_effective_attributes_async(player, session, extra)
        assert {name: row["effective"] for name, row in rows.items()} == combat
        for name, row in rows.items():
            source_sum = sum(breakdown[key][name] for key in (
                "base", "permanent", "vip_equipment", "equipment", "pet", "temporary",
            )) + row["affix"] + row["set"] + row["level"]
            assert source_sum == pytest.approx(row["raw"])
        text = "\n".join(format_attribute_breakdown(breakdown, rows))
        assert "装备含宝石20" in text
        assert "伙伴3.25" in text and "词缀6.5" in text and "套装5" in text
        assert "临时-5" in text and "丹药/奖励-2" in text
        assert "溢出10.5个百分点" in text
        assert "定身率" in text
        assert eq.extra_attrs == saved_extra and eq.gem_slots_data == saved_gems
        assert not session.dirty and not session.new and not session.deleted


async def test_battle_panel_uses_effective_defense_and_no_uncapped_dice_prediction(explanation_db):
    async with db.safe_session() as session:
        player = await session.get(Player, "explain")
        player._cached_defense = 999999  # 不能读取前一场战斗留下的快照
        player.vip_equipment_data = {"dice_buff": {"attribute": "combo_rate", "consumed": False}}
        await session.flush()
        text = await BattleIntegrationHelper.get_battle_attribute_display_async(player, session)
        assert "原始70.5% → 生效60%" in text
        assert "溢出10.5个百分点" in text
        assert "先抵挡至多22伤害" in text  # (10+100) * .2
        assert "26.5倍" in text
        assert "吸血率" in text and "真伤率" in text and "回复率" in text
        assert "待生效骰相：连击率" in text
        assert "🎲160" not in text
        assert not session.dirty
