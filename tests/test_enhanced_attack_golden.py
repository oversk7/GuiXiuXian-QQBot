"""_execute_enhanced_attack 金样回归测试

用固定随机种子跑覆盖各分支的攻击场景，完整输出(战斗消息+伤害数字)必须与
tests/golden/enhanced_attack_golden.json 逐字一致。

用途：重构 enhanced_engine.py 前后各跑一次本测试——重构不允许改变任何行为，
测试变红即说明拆分引入了偏差。

重新生成金样（仅当"有意"改变战斗行为时才允许）：
    uv run python -m tests.test_enhanced_attack_golden
"""
import json
from pathlib import Path
from types import SimpleNamespace

import nonebot

# 支持独立运行生成金样（pytest 下由 conftest 初始化，这里自动跳过）
try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()
    nonebot.load_plugin("nonebot_plugin_apscheduler")

from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine
from plugins.xiuxian_game.battle.battle_effects import (
    BattleEffect, EffectType, TriggerType, TriggerConfig,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "enhanced_attack_golden.json"


def _full_attrs(**overrides):
    attrs = {
        "critical_rate": 0, "critical_power": 0, "combo_rate": 0,
        "counter_rate": 0, "dodge_rate": 0, "accuracy_rate": 500,
        "skill_crit_rate": 0, "penetration_rate": 0, "anti_crit_rate": 0,
        "anti_combo_rate": 0, "anti_counter_rate": 0,
        "lifesteal_rate": 0, "immobilize_rate": 0,
        "true_damage_rate": 0, "regen_rate": 0,
    }
    attrs.update(overrides)
    return attrs


def _make_player(pid, name, attack=100, defense=0, **attr_overrides):
    return SimpleNamespace(
        id=pid, uid=pid, hp=1000, mp=0, max_mp=0, nickname=name,
        attack=attack, defense=defense, agility=10, level=10,
        _cached_attack=attack, _cached_defense=defense,
        _cached_max_hp=1000, _cached_agility=10,
        _cached_battle_attrs=_full_attrs(**attr_overrides),
        region="", extra_attrs={},
    )


def _attack(engine, attacker, defender, **kwargs):
    result = engine._execute_enhanced_attack(attacker, defender, True, **kwargs)
    # 只保留可稳定序列化的字段
    return {k: v for k, v in sorted(result.items()) if isinstance(v, (str, int, float, bool, list))}


def run_scenarios():
    """跑全部场景，返回 {场景名: 结果} 快照字典"""
    snap = {}

    # 1. 普通命中（无暴击/连击）
    eng = EnhancedBattleEngine(seed="golden-plain")
    snap["plain_hit"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙", defense=50))

    # 2. 技能必暴击（skill_crit_rate 拉满）
    eng = EnhancedBattleEngine(seed="golden-crit")
    snap["skill_crit"] = _attack(
        eng, _make_player("A", "甲", skill_crit_rate=2000, critical_power=10),
        _make_player("B", "乙", defense=50), is_skill=True)

    # 3. 连击（combo_rate 拉满，含子攻击完整流程）
    eng = EnhancedBattleEngine(seed="golden-combo")
    snap["combo"] = _attack(
        eng, _make_player("A", "甲", combo_rate=2000), _make_player("B", "乙", defense=30))

    # 4. 闪避+反击（固定种子序列中取第一次未命中）
    for i in range(80):
        eng = EnhancedBattleEngine(seed=f"golden-dodge-{i}")
        r = _attack(
            eng, _make_player("A", "甲", accuracy_rate=0),
            _make_player("B", "乙", attack=200, dodge_rate=500, counter_rate=100))
        if not r["hit"]:
            snap["dodge_counter"] = {"seed_index": i, **r}
            break

    # 5. 对怪物攻击（dict 防御者路径）
    eng = EnhancedBattleEngine(seed="golden-monster")
    snap["monster"] = _attack(
        eng, _make_player("A", "甲"), {"name": "孤影鬼", "defense": 30})

    # 6. 防御方护盾（部分吸收+破碎）
    eng = EnhancedBattleEngine(seed="golden-shield")
    d = _make_player("B", "乙")
    shield = BattleEffect(effect_type=EffectType.SHIELD, value=0, duration=3,
                          source="测试", is_percentage=False)
    shield.shield_value = 40
    eng.effect_manager.add_effect("B", shield)
    snap["shield_partial"] = _attack(eng, _make_player("A", "甲"), d)

    # 7. 防御方减伤(DAMAGE_REDUCTION 30%)
    eng = EnhancedBattleEngine(seed="golden-dr")
    eng.effect_manager.add_effect("B", BattleEffect(
        effect_type=EffectType.DAMAGE_REDUCTION, value=30, duration=3,
        source="归雨·伞下", source_equipment="归雨"))
    snap["damage_reduction"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 8. 防御方恐惧（+20%增伤）
    eng = EnhancedBattleEngine(seed="golden-fear")
    eng.effect_manager.add_effect("B", BattleEffect(
        effect_type=EffectType.FEAR, value=0, duration=2, source="测试"))
    snap["fear_bonus"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 9. 防御方无敌（常规伤害免疫）
    eng = EnhancedBattleEngine(seed="golden-inv")
    eng.effect_manager.add_effect("B", BattleEffect(
        effect_type=EffectType.INVINCIBLE, value=0, duration=2, source="测试"))
    snap["invincible"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 10. 无敌 + 攻击方绝魔体质50%（部分无视）
    eng = EnhancedBattleEngine(seed="golden-inv-bypass")
    eng.effect_manager.add_effect("B", BattleEffect(
        effect_type=EffectType.INVINCIBLE, value=0, duration=2, source="测试"))
    eng.effect_manager.add_effect("A", BattleEffect(
        effect_type=EffectType.IGNORE_SPECIAL, value=50, duration=-1, source="绝魔体质"))
    snap["invincible_bypass"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 11. 虎标弹链（次数耗尽→触发猛虎标弹）
    eng = EnhancedBattleEngine(seed="golden-tiger")
    eng.effect_manager.add_effect("A", BattleEffect(
        effect_type=EffectType.TIGER_BULLET, value=50, duration=0, source="天退星刀",
        max_trigger_count=1, next_effect="fierce_tiger_bullet",
        source_equipment="天退星刀"))
    a, d = _make_player("A", "甲"), _make_player("B", "乙")
    snap["tiger_chain_hit1"] = _attack(eng, a, d)
    snap["tiger_chain_hit2"] = _attack(eng, a, d)  # 第二击应吃到猛虎标弹加成

    # 12. 攻击方刚气-心（自身伤害-10%）+ 防御方刚气-心（受伤-60%）
    eng = EnhancedBattleEngine(seed="golden-rigid")
    eng.effect_manager.add_effect("A", BattleEffect(
        effect_type=EffectType.RIGID_QI_HEART, value=60, duration=3, source="测试"))
    eng.effect_manager.add_effect("B", BattleEffect(
        effect_type=EffectType.RIGID_QI_HEART, value=60, duration=3, source="测试"))
    snap["rigid_qi_both"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 13. 属性面板真伤率100% + 吸血率20%
    eng = EnhancedBattleEngine(seed="golden-truedmg")
    snap["stat_true_damage_lifesteal"] = _attack(
        eng, _make_player("A", "甲", true_damage_rate=100, lifesteal_rate=20),
        _make_player("B", "乙", defense=80))

    # 14. 定身率100%（命中后施加1回合恐惧）
    eng = EnhancedBattleEngine(seed="golden-immob")
    snap["immobilize"] = _attack(
        eng, _make_player("A", "甲", immobilize_rate=100), _make_player("B", "乙"))
    snap["immobilize"]["defender_controlled"] = eng.effect_manager.has_control_effect("B")

    # 15. 触发型吸血（ON_HIT 100%触发 LIFESTEAL 30%）
    eng = EnhancedBattleEngine(seed="golden-trig-ls")
    eng.effect_manager.register_triggers("A", [TriggerConfig(
        trigger=TriggerType.ON_HIT, chance=100, effect=EffectType.LIFESTEAL,
        value=30, description="噬血", source_equipment="噬血刃")])
    snap["trigger_lifesteal"] = _attack(eng, _make_player("A", "甲"), _make_player("B", "乙"))

    # 16. 触发型反弹（ON_DEFENSE 100%触发 REFLECT 25%）+ 攻击方持续穿透50%
    eng = EnhancedBattleEngine(seed="golden-reflect-pen")
    eng.effect_manager.register_triggers("B", [TriggerConfig(
        trigger=TriggerType.ON_DEFENSE, chance=100, effect=EffectType.REFLECT,
        value=25, description="荆棘", source_equipment="镜怨之衣")])
    eng.effect_manager.add_effect("A", BattleEffect(
        effect_type=EffectType.DEFENSE_PENETRATION, value=50, duration=3,
        source="伞骨穿", source_equipment="归雨"))
    snap["reflect_and_penetration"] = _attack(
        eng, _make_player("A", "甲"), _make_player("B", "乙", defense=100))

    return snap


def test_enhanced_attack_matches_golden():
    assert GOLDEN_PATH.exists(), (
        f"金样文件缺失: {GOLDEN_PATH}，先运行 "
        "uv run python -m tests.test_enhanced_attack_golden 生成")
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    actual = run_scenarios()
    assert set(actual) == set(golden), f"场景集合变化: {set(actual) ^ set(golden)}"
    for name in golden:
        assert actual[name] == golden[name], (
            f"场景[{name}]行为改变:\n期望: {json.dumps(golden[name], ensure_ascii=False, indent=1)}\n"
            f"实际: {json.dumps(actual[name], ensure_ascii=False, indent=1)}")


if __name__ == "__main__":
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(
        json.dumps(run_scenarios(), ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")
    print(f"金样已写入 {GOLDEN_PATH}")
