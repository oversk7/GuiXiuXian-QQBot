"""
战斗效果桥接器

将现有的TriggerConfig包装为IEffect接口，提供统一的效果访问层
采用桥接模式而非适配器模式，保留现有BattleEffectManager的优秀设计
"""

import random
from typing import Optional, Dict, Any
from nonebot import logger

from ..interfaces import IEffect, EffectContext, EffectResult, TriggerType
from plugins.xiuxian_game.battle.battle_effects import (
    BattleEffect,
    TriggerConfig,
    BattleEffectManager,
    TriggerType as BattleTriggerType,
)


# 触发类型映射：IEffect的TriggerType → BattleEffect的TriggerType
_TRIGGER_TYPE_MAPPING = {
    TriggerType.ON_ATTACK: BattleTriggerType.ON_ATTACK,
    TriggerType.ON_DEFENSE: BattleTriggerType.ON_DEFENSE,
    TriggerType.ON_CRITICAL: BattleTriggerType.ON_CRITICAL,
    TriggerType.ON_DODGE: BattleTriggerType.ON_DODGE,
    TriggerType.ON_HIT: BattleTriggerType.ON_HIT,
    TriggerType.ON_KILL: BattleTriggerType.ON_KILL,
    TriggerType.ON_ROUND_START: BattleTriggerType.EACH_TURN,  # 映射：回合开始
    TriggerType.ON_ROUND_END: BattleTriggerType.EACH_TURN,  # 映射：回合结束
    TriggerType.ON_BATTLE_START: BattleTriggerType.FIRST_TURN,  # 映射：战斗开始
    TriggerType.ON_DAMAGED: BattleTriggerType.ON_ATTACKED,  # 映射：受到伤害
}


class BattleEffectBridge(IEffect):
    """
    战斗效果桥接器 - 将TriggerConfig桥接到IEffect接口

    设计原则：
    1. 保留现有的BattleEffect和BattleEffectManager
    2. 提供IEffect接口的访问层
    3. 委托触发检查给原有逻辑
    4. 返回BattleEffect对象而非直接应用效果

    使用场景：
    - 统一物品效果和战斗效果的接口
    - 支持通过效果注册中心访问战斗效果
    - 保持向后兼容，新旧系统并存

    示例：
        ```python
        # 创建TriggerConfig
        trigger_config = TriggerConfig(
            trigger=BattleTriggerType.ON_HIT,
            effect=EffectType.LIFESTEAL,
            value=0.15,
            chance=1.0,
            description="吸血 15%"
        )

        # 创建桥接器
        bridge = BattleEffectBridge(
            effect_id="battle_lifesteal",
            trigger_config=trigger_config
        )

        # 使用IEffect接口
        context = EffectContext(
            player=player,
            trigger_type=TriggerType.ON_HIT,
            session=session,
            metadata={"unit_id": "player", "battle_state": battle_state}
        )

        if bridge.can_trigger(context):
            result = await bridge.execute(context)
            battle_effect = result.extra_data["battle_effect"]
            # 添加到BattleEffectManager
            effect_manager.add_effect("player", battle_effect)
        ```
    """

    def __init__(
        self,
        effect_id: str,
        trigger_config: TriggerConfig,
        effect_manager: Optional[BattleEffectManager] = None
    ):
        """
        初始化桥接器

        Args:
            effect_id: 效果唯一标识（如"battle_lifesteal_斩龙闪"）
            trigger_config: 触发配置对象（来自装备配置）
            effect_manager: 效果管理器实例（可选，用于直接操作）
        """
        self._effect_id = effect_id
        self._trigger_config = trigger_config
        self._effect_manager = effect_manager

    @property
    def effect_id(self) -> str:
        """效果唯一标识"""
        return self._effect_id

    @property
    def trigger_config(self) -> TriggerConfig:
        """暴露原始TriggerConfig供兼容性使用"""
        return self._trigger_config

    def can_trigger(self, context: EffectContext) -> bool:
        """
        判断是否可以触发

        委托给原有的TriggerConfig判断逻辑：
        1. 检查触发类型匹配
        2. 检查概率
        3. 检查条件（低血量、理智上限等）
        4. 检查环境条件（区域白名单、周主题白名单）

        Args:
            context: 效果执行上下文

        Returns:
            bool: 是否可以触发
        """
        # 1. 检查触发类型匹配
        battle_trigger_type = _TRIGGER_TYPE_MAPPING.get(context.trigger_type)
        if battle_trigger_type is None:
            # 不支持的触发类型
            return False

        if self._trigger_config.trigger != battle_trigger_type:
            return False

        # 2. 检查概率
        if self._trigger_config.chance < 1.0:
            if random.random() > self._trigger_config.chance:
                logger.debug(
                    f"[BattleEffectBridge] {self._effect_id} 概率判定失败 "
                    f"(概率: {self._trigger_config.chance})"
                )
                return False

        # 3. 检查条件
        if self._trigger_config.condition:
            if not self._check_condition(context):
                logger.debug(
                    f"[BattleEffectBridge] {self._effect_id} 条件检查失败"
                )
                return False

        # 4. 检查环境条件
        if not self._check_environment(context):
            logger.debug(
                f"[BattleEffectBridge] {self._effect_id} 环境条件检查失败"
            )
            return False

        return True

    async def execute(self, context: EffectContext) -> EffectResult:
        """
        执行效果 - 返回应该添加的BattleEffect

        注意：此方法不直接修改战斗状态，而是返回效果描述
        实际的效果应用由EnhancedBattleEngine完成

        Args:
            context: 效果执行上下文

        Returns:
            EffectResult: 效果执行结果，包含BattleEffect对象在extra_data中
        """
        logger.debug(
            f"[BattleEffectBridge] 执行效果: {self._effect_id} "
            f"(类型: {self._trigger_config.effect.value}, "
            f"值: {self._trigger_config.value})"
        )

        # 创建BattleEffect实例
        effect = BattleEffect(
            effect_type=self._trigger_config.effect,
            value=self._trigger_config.value,
            duration=self._trigger_config.duration,
            max_stacks=self._trigger_config.max_stacks,
            stackable=self._trigger_config.stackable,
            source_unit_id=context.metadata.get("unit_id", "unknown"),
            description=self._trigger_config.description
        )

        # 如果提供了effect_manager，可以直接添加效果
        if self._effect_manager and "unit_id" in context.metadata:
            unit_id = context.metadata["unit_id"]
            self._effect_manager.add_effect(unit_id, effect)
            logger.debug(
                f"[BattleEffectBridge] 效果已添加到管理器: "
                f"unit_id={unit_id}, effect={self._trigger_config.effect.value}"
            )

        # 返回效果结果
        return EffectResult(
            success=True,
            message=f"触发效果: {self._trigger_config.description}",
            extra_data={
                "battle_effect": effect,  # 返回BattleEffect对象
                "apply_to_manager": True,  # 标记需要添加到管理器
                "trigger_config": self._trigger_config,  # 返回原始配置
            }
        )

    def _check_condition(self, context: EffectContext) -> bool:
        """
        检查条件（如低血量、理智上限）

        Args:
            context: 效果执行上下文

        Returns:
            bool: 条件是否满足
        """
        condition = self._trigger_config.condition
        if not condition:
            return True

        # 获取战斗状态和单位信息
        battle_state = context.metadata.get("battle_state")
        unit_id = context.metadata.get("unit_id")

        # 低血量检查
        if "low_hp" in condition:
            threshold = condition.get("threshold", 0.3)

            # 尝试从context.player获取
            if hasattr(context.player, "current_hp") and hasattr(context.player, "max_hp"):
                if context.player.current_hp > context.player.max_hp * threshold:
                    return False
            # 尝试从battle_state获取
            elif battle_state and unit_id:
                unit = getattr(battle_state, "get_unit", lambda x: None)(unit_id)
                if unit and hasattr(unit, "current_hp") and hasattr(unit, "max_hp"):
                    if unit.current_hp > unit.max_hp * threshold:
                        return False
                else:
                    logger.warning(
                        f"[BattleEffectBridge] 无法获取单位血量信息: unit_id={unit_id}"
                    )
                    return False

        # 理智上限检查
        if "mp_cap" in condition:
            required_mp = condition.get("min_mp", 0)

            # 尝试从context.player获取
            if hasattr(context.player, "max_mp"):
                if context.player.max_mp < required_mp:
                    return False
            # 尝试从battle_state获取
            elif battle_state and unit_id:
                unit = getattr(battle_state, "get_unit", lambda x: None)(unit_id)
                if unit and hasattr(unit, "max_mp"):
                    if unit.max_mp < required_mp:
                        return False
                else:
                    logger.warning(
                        f"[BattleEffectBridge] 无法获取单位理智信息: unit_id={unit_id}"
                    )
                    return False

        return True

    def _check_environment(self, context: EffectContext) -> bool:
        """
        检查环境条件（区域白名单、周主题白名单）

        Args:
            context: 效果执行上下文

        Returns:
            bool: 环境条件是否满足
        """
        # 区域白名单检查
        region_whitelist = self._trigger_config.region_whitelist
        if region_whitelist:
            current_region = context.metadata.get("region")
            if current_region not in region_whitelist:
                logger.debug(
                    f"[BattleEffectBridge] 区域不在白名单: "
                    f"current={current_region}, whitelist={region_whitelist}"
                )
                return False

        # 周主题白名单检查
        week_theme_whitelist = self._trigger_config.week_theme_whitelist
        if week_theme_whitelist:
            current_week_theme = context.metadata.get("week_theme")
            if current_week_theme not in week_theme_whitelist:
                logger.debug(
                    f"[BattleEffectBridge] 周主题不在白名单: "
                    f"current={current_week_theme}, whitelist={week_theme_whitelist}"
                )
                return False

        return True


def create_bridge_for_trigger_config(
    trigger_config: TriggerConfig,
    base_effect_id: str,
    effect_manager: Optional[BattleEffectManager] = None
) -> BattleEffectBridge:
    """
    为单个TriggerConfig创建桥接器

    Args:
        trigger_config: 触发配置对象
        base_effect_id: 基础效果ID（如"斩龙闪_吸血"）
        effect_manager: 效果管理器实例（可选）

    Returns:
        BattleEffectBridge: 桥接器实例
    """
    effect_id = f"battle_{trigger_config.effect.value}_{base_effect_id}"
    return BattleEffectBridge(
        effect_id=effect_id,
        trigger_config=trigger_config,
        effect_manager=effect_manager
    )
