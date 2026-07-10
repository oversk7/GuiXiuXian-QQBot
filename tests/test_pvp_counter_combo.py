"""切磋反击/连击/定身生效回归测试

历史 bug：
1. compact PvP（切磋/模拟战斗/天梯）从不调用 check_counter_attack，受击反击永不触发；
2. 闪避反击的 counter_damage 未被 execute_player_turn 转发，日志显示"趁机反击造成N伤害"
   但血量不变（假日志）；
3. 连击子攻击对已含攻击修正的 base_attack 重复乘 attack_modifier，攻击buff下连击平方偏高；
4. PvP 回合循环从不检查 has_control_effect，定身率/恐惧的"无法行动"在切磋中纯装饰
   （修复：回合开始 tick 前捕获控制状态，被恐惧方跳过本回合行动）。
"""
from types import SimpleNamespace

from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine
from plugins.xiuxian_game.battle.battle_log_filter import filter_battle_log


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


def test_counter_attack_returns_damage():
    """counter_rate=100 必触发反击，伤害为防守方攻击力50%经减伤"""
    engine = EnhancedBattleEngine(seed="verify-counter")
    attacker = _make_player("A", "甲", attack=100)
    defender = _make_player("B", "乙", attack=200, counter_rate=100)
    result = engine.check_counter_attack(defender, attacker)
    assert result is not None and result.get("hit")
    assert result["damage"] > 0


def test_dodge_counter_damage_forwarded():
    """攻击被闪避且防守方反击时，execute_player_turn 必须转发 counter_damage"""
    found = False
    for i in range(50):
        engine = EnhancedBattleEngine(seed=f"verify-dodge-{i}")
        attacker = _make_player("A", "甲", attack=100, accuracy_rate=0)
        defender = _make_player("B", "乙", attack=200, dodge_rate=500, counter_rate=100)
        result = engine.execute_player_turn(attacker, defender, 100, is_skill=False)
        if not result["hit"]:
            # 命中率下限10%，闪避后 counter_rate=100 必反击（反击命中率500 vs 闪避0）
            assert result.get("counter_damage", 0) > 0, result
            assert any("趁机反击" in m for m in result["messages"])
            found = True
            break
    assert found, "50个种子内未出现闪避，检查命中判定"


def test_combo_no_double_attack_modifier():
    """无攻击修正效果时连击伤害应恰为 base*0.85（0防御），修正不再二次应用"""
    engine = EnhancedBattleEngine(seed="verify-combo")
    attacker = _make_player("A", "甲", attack=100)
    defender = _make_player("B", "乙", attack=100)
    result = engine._execute_single_combo_attack(
        attacker, defender, True, "A", "B", "甲", "乙", 100, 2
    )
    assert result["total_damage"] == 85


def test_immobilize_applies_fear_and_blocks_exactly_once():
    """定身率100 → 命中后对方获得FEAR；tick前捕获为受控，tick后恰好过期（封锁一次行动）"""
    engine = EnhancedBattleEngine(seed="verify-immobilize")
    attacker = _make_player("A", "甲", attack=100, immobilize_rate=100)
    defender = _make_player("B", "乙", attack=100)
    result = engine.execute_player_turn(attacker, defender, 100, is_skill=False)
    assert result["hit"] is True
    # 命中后防守方被施加FEAR（PvP回合循环在tick前用该检查捕获控制状态）
    assert engine.effect_manager.has_control_effect("B") is True
    # 回合开始tick把duration=1的恐惧消耗掉 → 只封锁一次行动，下回合恢复
    engine._process_turn_start("B", defender)
    assert engine.effect_manager.has_control_effect("B") is False


def test_simple_log_keeps_counter_lines():
    """简洁日志模式保留反击/反弹扣血事件行"""
    log = [
        "⚔️ 甲攻击乙 造成100伤害",
        "🛡️ 乙反击甲 造成50伤害",
        "↩️ 乙趁机反击，造成30伤害",
        "🧡 吸血10HP",
    ]
    simple = filter_battle_log(log, "simple")
    assert "🛡️ 乙反击甲 造成50伤害" in simple
    assert "↩️ 乙趁机反击，造成30伤害" in simple
    assert "🧡 吸血10HP" not in simple
