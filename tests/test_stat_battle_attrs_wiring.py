"""数值型战斗属性（吸血/定身/真伤/回复）接线测试

历史 bug：lifesteal_rate/immobilize_rate/true_damage_rate/regen_rate 四个玩家
字段在战斗档 11 键映射之外被静默丢弃（T1词缀嗜血/禁锢/回春/真伤洗出即白洗），
且引擎内除定身外无任何消费方。修复后：
- 战斗档计算（同步/异步/回退）均含这 4 键
- 引擎经 _unit_battle_attr 读缓存（含buff/宠物/T1词缀），消费点全部接通
"""
import random
from types import SimpleNamespace

from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator
from plugins.xiuxian_game.battle.enhanced_engine import (
    EnhancedBattleEngine,
    _effective_max_hp,
    _unit_battle_attr,
)


def _full_cached_attrs(**overrides):
    attrs = {
        "critical_rate": 0, "critical_power": 0, "combo_rate": 0,
        "counter_rate": 0, "dodge_rate": 0, "accuracy_rate": 80,
        "skill_crit_rate": 0, "penetration_rate": 0, "anti_crit_rate": 0,
        "lifesteal_rate": 0, "immobilize_rate": 0,
        "true_damage_rate": 0, "regen_rate": 0,
    }
    attrs.update(overrides)
    return attrs


def test_sync_calc_includes_new_attrs():
    player = SimpleNamespace(
        level=1, critical_rate=5, critical_power=0, combo_rate=0,
        counter_rate=0, dodge_rate=0, accuracy_rate=80,
        skill_crit_rate=0, penetration_rate=0, anti_crit_rate=0,
        anti_combo_rate=0, anti_counter_rate=0,
        lifesteal_rate=3, immobilize_rate=2, true_damage_rate=4, regen_rate=1,
    )
    attrs = BattleAttributeCalculator.calculate_effective_attributes(player)
    assert attrs["lifesteal_rate"] == 3
    assert attrs["immobilize_rate"] == 2
    assert attrs["true_damage_rate"] == 4
    assert attrs["regen_rate"] == 1


def test_t1_affix_bonus_not_dropped():
    """T1词缀经 equipment_bonus 传入的 4 项新属性不再被丢弃"""
    player = SimpleNamespace(
        level=1, critical_rate=0, critical_power=0, combo_rate=0,
        counter_rate=0, dodge_rate=0, accuracy_rate=80,
        skill_crit_rate=0, penetration_rate=0, anti_crit_rate=0,
        anti_combo_rate=0, anti_counter_rate=0,
        lifesteal_rate=0, immobilize_rate=0, true_damage_rate=0, regen_rate=0,
    )
    attrs = BattleAttributeCalculator.calculate_effective_attributes(
        player, equipment_bonus={"lifesteal_rate": 5.0, "regen_rate": 2.5}
    )
    assert attrs["lifesteal_rate"] == 5.0
    assert attrs["regen_rate"] == 2.5


def test_critical_power_not_capped_at_default_100():
    """critical_power 不在 ATTRIBUTE_CAPS 表内，不应被默认值 100 截断

    历史bug：面板/战斗档用 ATTRIBUTE_CAPS.get(attr, 100) 兜底，导致暴击力
    >100 点后全部无效（如 5 颗十级暴击力玛瑙=250 点仍显示 11.5 倍）。
    """
    player = SimpleNamespace(
        level=1, critical_rate=0, critical_power=250, combo_rate=0,
        counter_rate=0, dodge_rate=0, accuracy_rate=80,
        skill_crit_rate=0, penetration_rate=0, anti_crit_rate=0,
        anti_combo_rate=0, anti_counter_rate=0,
        lifesteal_rate=0, immobilize_rate=0, true_damage_rate=0, regen_rate=0,
    )
    attrs = BattleAttributeCalculator.calculate_effective_attributes(player)
    assert attrs["critical_power"] == 250
    assert 1.5 + attrs["critical_power"] * 0.1 == 26.5
    # 表内属性上限不受影响
    assert attrs["critical_rate"] == 0

    player.combo_rate = 999
    attrs = BattleAttributeCalculator.calculate_effective_attributes(player)
    assert attrs["combo_rate"] == 60


def test_unit_battle_attr_prefers_cache():
    player = SimpleNamespace(
        lifesteal_rate=0,
        _cached_battle_attrs=_full_cached_attrs(lifesteal_rate=50),
    )
    assert _unit_battle_attr(player, "lifesteal_rate") == 50
    # 无缓存回退裸字段；怪物dict走get
    assert _unit_battle_attr(SimpleNamespace(lifesteal_rate=7), "lifesteal_rate") == 7
    assert _unit_battle_attr({"true_damage_rate": 15}, "true_damage_rate") == 15


def test_stat_lifesteal_heals_on_attack():
    """吸血率50% → 命中后 hp_restored 含伤害的50%（走完整攻击流程）"""
    engine = EnhancedBattleEngine(seed="ls-test")
    player = SimpleNamespace(
        id="P1", hp=100, nickname="测试", attack=100,
        _cached_attack=100, _cached_max_hp=100,
        _cached_battle_attrs=_full_cached_attrs(accuracy_rate=500, lifesteal_rate=50),
    )
    result = engine._execute_enhanced_attack(
        player, {"name": "木桩", "defense": 0, "hp": 1000, "max_hp": 1000}, True
    )
    assert result["hit"] is True
    damage = result["total_damage"]
    assert damage > 0
    assert result["hp_restored"] >= int(damage * 50 / 100)


def test_stat_regen_heals_each_turn():
    """回复率10% → 每回合回复 max_hp 的10%"""
    engine = EnhancedBattleEngine(seed="regen-test")
    player = SimpleNamespace(
        id="P1", hp=50, nickname="测试",
        _cached_max_hp=200,
        _cached_battle_attrs=_full_cached_attrs(regen_rate=10),
    )
    _msgs, hp_restored = engine._process_turn_start("P1", player)
    assert hp_restored == 20  # 200 * 10%


def test_sync_unit_attr_caps_cached_value():
    """骰子buff类直写缓存需套 ATTRIBUTE_CAPS：连击不可破60"""
    player = SimpleNamespace(
        combo_rate=0,
        _cached_battle_attrs=_full_cached_attrs(combo_rate=30),
    )
    EnhancedBattleEngine._sync_unit_attr(player, "combo_rate", 130)
    assert player.combo_rate == 130  # 裸字段保持原值用于战后回退
    assert player._cached_battle_attrs["combo_rate"] == 60  # 缓存镜像套上限


def test_effective_max_hp_prefers_cache():
    assert _effective_max_hp(SimpleNamespace(_cached_max_hp=500, max_hp=100)) == 500
    assert _effective_max_hp(SimpleNamespace(max_hp=100)) == 100
    assert _effective_max_hp({"max_hp": 300}) == 300
