from types import SimpleNamespace

from plugins.xiuxian_game.battle.battle_effects import EffectType, TriggerConfig, TriggerType
from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine
from plugins.xiuxian_game.battle.integration_helper import _apply_nonlethal_reflect


def _battle_attrs():
    return {
        "critical_rate": 0,
        "critical_power": 0,
        "combo_rate": 0,
        "counter_rate": 0,
        "dodge_rate": 0,
        "accuracy_rate": 500,
        "skill_crit_rate": 0,
        "penetration_rate": 0,
        "anti_crit_rate": 0,
        "anti_combo_rate": 0,
        "anti_counter_rate": 0,
        "lifesteal_rate": 0,
        "immobilize_rate": 0,
        "true_damage_rate": 0,
        "regen_rate": 0,
    }


def _player(pid: str, name: str, attack: int):
    return SimpleNamespace(
        id=pid,
        hp=1000,
        mp=0,
        max_mp=0,
        nickname=name,
        attack=attack,
        defense=0,
        agility=10,
        _cached_attack=attack,
        _cached_defense=0,
        _cached_max_hp=1000,
        _cached_battle_attrs=_battle_attrs(),
        region="",
    )


def test_reflect_damage_is_capped_by_defender_attack():
    engine = EnhancedBattleEngine(seed="reflect-cap")
    engine.effect_manager.register_triggers("D", [
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=100,
            description="反弹一",
        ),
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=100,
            description="反弹二",
        ),
    ])

    result = engine._execute_enhanced_attack(
        _player("A", "攻击者", attack=1000),
        _player("D", "防守者", attack=40),
        True,
    )

    assert result["reflect_damage"] == 400
    assert result["effects_triggered"].count("reflect") == 1


def test_pvp_reflect_total_is_capped_by_actual_loss():
    """PvP同一次受击的反弹总量不能超过防守者本次实际损失生命。"""
    engine = EnhancedBattleEngine(seed="reflect-pvp-loss-cap")
    engine.effect_manager.register_triggers("D", [
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=100,
            description="反弹一",
        ),
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=100,
            description="反弹二",
        ),
    ])

    result = engine._execute_enhanced_attack(
        _player("A", "高攻攻击者", attack=100000),
        _player("D", "低血防守者", attack=1000),
        True,
        defender_hp=100,
    )

    assert result["reflect_damage"] == 100


def test_pvp_reflect_uses_total_attack_event_damage():
    """PvP反弹基数包含命中后追加伤害，而不是只取首段。"""
    engine = EnhancedBattleEngine(seed="reflect-pvp-total-damage")
    engine.effect_manager.register_triggers("A", [
        TriggerConfig(
            trigger=TriggerType.ON_HIT,
            chance=100,
            effect=EffectType.DAMAGE_BOOST,
            value=100,
            description="命中增伤",
        ),
    ])
    engine.effect_manager.register_triggers("D", [
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=50,
            description="反弹",
        ),
    ])

    result = engine._execute_enhanced_attack(
        _player("A", "攻击者", attack=100),
        _player("D", "防守者", attack=100),
        True,
        defender_hp=1000,
    )

    assert result["total_damage"] == 200
    assert result["reflect_damage"] == 100


def test_reflect_based_on_actual_hp_loss():
    """反弹按本次实际损失生命计算，秒杀/过量伤害不再放大反弹。"""
    engine = EnhancedBattleEngine(seed="reflect-actual")
    engine.effect_manager.register_triggers("D", [
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=50,
            description="反弹残血",
        ),
    ])

    # 防守者仅剩100HP，攻击者伤害远超其生命：反弹只按实际损失的100HP×50%计算
    result = engine._execute_enhanced_attack(
        _player("A", "攻击者", attack=10000),
        _player("D", "防守者", attack=100),
        True,
        defender_hp=100,
    )

    assert 0 < result["reflect_damage"] <= 50


def test_pve_reflect_uses_hp_before_monster_damage():
    """PvE怪物攻击玩家时，反弹基数使用扣血前HP，不能使用扣血后的剩余HP。"""
    engine = EnhancedBattleEngine(seed="reflect-pve-before-hit")
    player = _player("P", "玩家", attack=100)

    # 玩家受击前1000HP，怪物造成800伤害；正确反弹基数为800，而非扣血后的200。
    reflect_damage = engine._calc_reflect_damage(
        player,
        damage=800,
        value_pct=50,
        defender_current_hp=1000,
        cap_at_actual_loss=True,
    )

    assert reflect_damage == 400


def test_reflect_uses_current_hp_when_provided():
    """传入防守者当前HP时，反弹基数取 min(伤害, 当前HP)，而非初始HP。"""
    engine = EnhancedBattleEngine(seed="reflect-curhp")
    engine.effect_manager.register_triggers("D", [
        TriggerConfig(
            trigger=TriggerType.ON_ATTACKED,
            chance=100,
            effect=EffectType.REFLECT,
            value=100,
            description="反弹测试",
        ),
    ])

    result = engine._execute_enhanced_attack(
        _player("A", "攻击者", attack=10000),
        _player("D", "防守者", attack=100),
        True,
        defender_hp=30,
    )

    assert result["reflect_damage"] <= 30
    assert result["reflect_damage"] > 0


def test_normal_reflect_cannot_kill_attacker():
    assert _apply_nonlethal_reflect(50, 200) == 1
    assert _apply_nonlethal_reflect(50, 20) == 30
    assert _apply_nonlethal_reflect(0, 20) == 0
