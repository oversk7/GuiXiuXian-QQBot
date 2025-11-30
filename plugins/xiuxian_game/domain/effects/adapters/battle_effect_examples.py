"""
战斗效果桥接器示例

提供常见战斗效果的桥接器示例，展示如何使用BattleEffectBridge
"""

from .battle_effect_bridge import BattleEffectBridge, create_bridge_for_trigger_config
from plugins.xiuxian_game.battle.battle_effects import (
    TriggerConfig,
    TriggerType,
    EffectType,
)


# 示例1: 吸血效果（ON_HIT触发）
def create_lifesteal_bridge(
    lifesteal_percent: float = 0.15,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建吸血效果桥接器

    效果：命中时恢复造成伤害的X%生命值

    Args:
        lifesteal_percent: 吸血百分比（0.15 = 15%）
        effect_id_suffix: 效果ID后缀（用于区分不同装备）

    Returns:
        BattleEffectBridge: 吸血效果桥接器

    示例：
        ```python
        # 创建15%吸血效果
        lifesteal = create_lifesteal_bridge(0.15, "斩龙闪")

        # 检查是否触发
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_HIT,
            session=session,
            metadata={
                "unit_id": "player",
                "battle_state": battle_state,
                "damage_dealt": 100
            }
        )

        if lifesteal.can_trigger(context):
            result = await lifesteal.execute(context)
            # 吸血15点（100 * 0.15）
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.ON_HIT,
        effect=EffectType.LIFESTEAL,
        value=lifesteal_percent,
        chance=1.0,  # 100%触发
        duration=0,  # 瞬时效果
        description=f"吸血 {int(lifesteal_percent * 100)}%"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"lifesteal_{effect_id_suffix}"
    )


# 示例2: 攻击力提升（FIRST_TURN触发）
def create_attack_buff_bridge(
    attack_increase: int = 50,
    duration: int = 3,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建攻击力提升效果桥接器

    效果：战斗开始时提升X点攻击力，持续Y回合

    Args:
        attack_increase: 攻击力提升值
        duration: 持续回合数
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 攻击力提升效果桥接器

    示例：
        ```python
        # 创建+50攻击力buff，持续3回合
        attack_buff = create_attack_buff_bridge(50, 3, "天退星刀")

        # 战斗开始时触发
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_BATTLE_START,
            session=session,
            metadata={"unit_id": "player", "battle_state": battle_state}
        )

        if attack_buff.can_trigger(context):
            result = await attack_buff.execute(context)
            # 攻击力+50，持续3回合
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.FIRST_TURN,
        effect=EffectType.BUFF_ATTACK,
        value=attack_increase,
        chance=1.0,
        duration=duration,
        description=f"攻击力+{attack_increase}（{duration}回合）"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"attack_buff_{effect_id_suffix}"
    )


# 示例3: 护盾效果（FIRST_TURN触发）
def create_shield_bridge(
    shield_value: int = 100,
    duration: int = 1,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建护盾效果桥接器

    效果：战斗开始时获得X点护盾值

    Args:
        shield_value: 护盾值
        duration: 持续回合数
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 护盾效果桥接器

    示例：
        ```python
        # 创建100点护盾
        shield = create_shield_bridge(100, 1, "灵影之甲")

        # 战斗开始时触发
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_BATTLE_START,
            session=session,
            metadata={"unit_id": "player", "battle_state": battle_state}
        )

        if shield.can_trigger(context):
            result = await shield.execute(context)
            # 获得100点护盾
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.FIRST_TURN,
        effect=EffectType.SHIELD,
        value=shield_value,
        chance=1.0,
        duration=duration,
        description=f"护盾 {shield_value}点"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"shield_{effect_id_suffix}"
    )


# 示例4: 伤害反弹（ON_ATTACKED触发）
def create_reflect_bridge(
    reflect_percent: float = 0.3,
    trigger_chance: float = 1.0,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建伤害反弹效果桥接器

    效果：受到攻击时反弹X%伤害

    Args:
        reflect_percent: 反弹百分比（0.3 = 30%）
        trigger_chance: 触发概率
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 伤害反弹效果桥接器

    示例：
        ```python
        # 创建30%伤害反弹
        reflect = create_reflect_bridge(0.3, 1.0, "镜怨之衣")

        # 受到攻击时触发
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_DAMAGED,
            session=session,
            attacker=attacker,
            damage_dealt=100,
            metadata={"unit_id": "player", "battle_state": battle_state}
        )

        if reflect.can_trigger(context):
            result = await reflect.execute(context)
            # 反弹30点伤害（100 * 0.3）
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.ON_ATTACKED,
        effect=EffectType.REFLECT,
        value=reflect_percent,
        chance=trigger_chance,
        duration=0,  # 瞬时效果
        description=f"反弹伤害 {int(reflect_percent * 100)}%"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"reflect_{effect_id_suffix}"
    )


# 示例5: 恐惧效果（ON_CRITICAL触发，带概率）
def create_fear_bridge(
    fear_duration: int = 1,
    trigger_chance: float = 0.2,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建恐惧效果桥接器

    效果：暴击时有X%概率令目标恐惧Y回合（无法行动）

    Args:
        fear_duration: 恐惧持续回合数
        trigger_chance: 触发概率（0.2 = 20%）
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 恐惧效果桥接器

    示例：
        ```python
        # 创建20%概率恐惧1回合
        fear = create_fear_bridge(1, 0.2, "恐惧之刃")

        # 暴击时触发
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_CRITICAL,
            session=session,
            is_critical=True,
            target=enemy,
            metadata={"unit_id": "player", "battle_state": battle_state}
        )

        if fear.can_trigger(context):
            result = await fear.execute(context)
            # 目标恐惧1回合
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.ON_CRITICAL,
        effect=EffectType.FEAR,
        value=1,  # 恐惧值（通常为1）
        chance=trigger_chance,
        duration=fear_duration,
        description=f"恐惧 {fear_duration}回合（{int(trigger_chance * 100)}%概率）"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"fear_{effect_id_suffix}"
    )


# 示例6: 带条件的效果（低血量触发）
def create_low_hp_damage_boost_bridge(
    damage_boost_percent: float = 0.5,
    hp_threshold: float = 0.3,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建低血量伤害提升效果桥接器

    效果：当血量低于X%时，伤害提升Y%

    Args:
        damage_boost_percent: 伤害提升百分比（0.5 = 50%）
        hp_threshold: 血量阈值（0.3 = 30%）
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 低血量伤害提升效果桥接器

    示例：
        ```python
        # 创建血量<30%时伤害+50%
        boost = create_low_hp_damage_boost_bridge(0.5, 0.3, "绝境")

        # 攻击时检查
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_ATTACK,
            session=session,
            metadata={
                "unit_id": "player",
                "battle_state": battle_state
            }
        )

        # 只有在低血量时才触发
        if boost.can_trigger(context):
            result = await boost.execute(context)
            # 伤害提升50%
        ```
    """
    trigger_config = TriggerConfig(
        trigger=TriggerType.LOW_HP,
        effect=EffectType.DAMAGE_BOOST,
        value=damage_boost_percent,
        chance=1.0,
        duration=0,  # 被动效果
        condition={"low_hp": True, "threshold": hp_threshold},
        description=f"低血量伤害+{int(damage_boost_percent * 100)}%"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"low_hp_boost_{effect_id_suffix}"
    )


# 示例7: 带环境限制的效果（特定区域生效）
def create_region_restricted_buff_bridge(
    attack_increase: int = 100,
    allowed_regions: list = None,
    effect_id_suffix: str = "default"
) -> BattleEffectBridge:
    """
    创建带区域限制的增益效果桥接器

    效果：仅在特定区域生效的攻击力提升

    Args:
        attack_increase: 攻击力提升值
        allowed_regions: 允许生效的区域列表（如["诡域", "妖魔林"]）
        effect_id_suffix: 效果ID后缀

    Returns:
        BattleEffectBridge: 带区域限制的增益效果桥接器

    示例：
        ```python
        # 创建仅在"诡域"生效的攻击力+100
        region_buff = create_region_restricted_buff_bridge(
            100,
            ["诡域"],
            "诡域霸主"
        )

        # 战斗开始时检查
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_BATTLE_START,
            session=session,
            metadata={
                "unit_id": "player",
                "battle_state": battle_state,
                "region": "诡域"  # 当前区域
            }
        )

        # 只有在"诡域"时才触发
        if region_buff.can_trigger(context):
            result = await region_buff.execute(context)
            # 攻击力+100
        ```
    """
    if allowed_regions is None:
        allowed_regions = ["诡域"]

    trigger_config = TriggerConfig(
        trigger=TriggerType.FIRST_TURN,
        effect=EffectType.BUFF_ATTACK,
        value=attack_increase,
        chance=1.0,
        duration=99,  # 持续整场战斗
        region_whitelist=allowed_regions,
        description=f"攻击力+{attack_increase}（{','.join(allowed_regions)}）"
    )

    return create_bridge_for_trigger_config(
        trigger_config,
        base_effect_id=f"region_buff_{effect_id_suffix}"
    )


# 示例集合：创建所有示例桥接器
def create_all_example_bridges() -> dict:
    """
    创建所有示例桥接器

    Returns:
        dict: 桥接器映射 {effect_id: BattleEffectBridge}
    """
    examples = {
        "lifesteal_default": create_lifesteal_bridge(0.15, "default"),
        "attack_buff_default": create_attack_buff_bridge(50, 3, "default"),
        "shield_default": create_shield_bridge(100, 1, "default"),
        "reflect_default": create_reflect_bridge(0.3, 1.0, "default"),
        "fear_default": create_fear_bridge(1, 0.2, "default"),
        "low_hp_boost_default": create_low_hp_damage_boost_bridge(0.5, 0.3, "default"),
        "region_buff_default": create_region_restricted_buff_bridge(100, ["诡域"], "default"),
    }

    return {bridge.effect_id: bridge for bridge in examples.values()}
