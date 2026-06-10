"""战斗循环内临时buff生效性测试

历史 bug：怪物战攻击/反击判定、PVP连击、世界boss理智侵蚀等 6 处同步裸读
player 字段，吃不到开战时预计算的 _cached_battle_attrs（含临时buff/宠物/词缀）。
修复后战斗内同步判定统一走 BattleAttributeCalculator.effective_attrs_in_battle
（缓存优先）。本文件的玩家对象故意不带战斗属性字段——谁退回裸读谁直接炸。
"""
import random
from types import SimpleNamespace

from plugins.xiuxian_game.battle.battle_attributes import (
    BattleAttributeCalculator,
    BattleEffectProcessor,
)
from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine


def _cached_attrs(**overrides):
    attrs = {
        "critical_rate": 0, "critical_power": 0, "combo_rate": 0,
        "counter_rate": 0, "dodge_rate": 0, "accuracy_rate": 80,
        "skill_crit_rate": 0, "penetration_rate": 0, "anti_crit_rate": 0,
    }
    attrs.update(overrides)
    return attrs


def test_effective_attrs_prefers_cache():
    player = SimpleNamespace(_cached_battle_attrs=_cached_attrs(critical_rate=77))
    attrs = BattleAttributeCalculator.effective_attrs_in_battle(player)
    assert attrs["critical_rate"] == 77


def test_effective_attrs_falls_back_to_fields():
    player = SimpleNamespace(
        level=1, critical_rate=5, critical_power=0, combo_rate=0,
        counter_rate=0, dodge_rate=0, accuracy_rate=80,
        skill_crit_rate=0, penetration_rate=0, anti_crit_rate=0,
    )
    attrs = BattleAttributeCalculator.effective_attrs_in_battle(player)
    assert attrs["accuracy_rate"] == 80
    assert attrs["critical_rate"] == 5


def test_pve_counter_attack_reads_cached_counter_rate():
    # buff 把反击率拉到 100% → 必反击；缓存为 0 → 必不反击
    buffed = SimpleNamespace(id="P1", _cached_battle_attrs=_cached_attrs(counter_rate=100))
    plain = SimpleNamespace(id="P2", _cached_battle_attrs=_cached_attrs(counter_rate=0))
    assert BattleEffectProcessor.check_counter_attack(buffed, random.Random(1)) is True
    assert BattleEffectProcessor.check_counter_attack(plain, random.Random(1)) is False


def test_monster_attack_path_uses_cached_attrs():
    # PVE 玩家攻击怪物：命中率 500（buff 后）必中；玩家对象无字段，走裸读会 AttributeError
    engine = EnhancedBattleEngine(seed="test-seed")
    player = SimpleNamespace(
        id="P1",
        _cached_battle_attrs=_cached_attrs(accuracy_rate=500, critical_rate=100),
    )
    result = engine._process_monster_attack(player, {"defense": 0}, 100, is_skill=False)
    assert result["hit"] is True
    assert result["is_critical"] is True  # 暴击率100%（怪物无抗暴）必暴击
