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


def test_normal_reflect_cannot_kill_attacker():
    assert _apply_nonlethal_reflect(50, 200) == 1
    assert _apply_nonlethal_reflect(50, 20) == 30
    assert _apply_nonlethal_reflect(0, 20) == 0
