"""
效果系统领域模块

提供统一的效果接口和注册机制，用于统一物品效果和战斗效果
"""

from .interfaces import (
    IEffect,
    BaseItemEffect,
    BaseBattleEffect,
    EffectContext,
    EffectResult,
    TriggerType,
)

__all__ = [
    # 核心接口
    "IEffect",
    "BaseItemEffect",
    "BaseBattleEffect",

    # 数据结构
    "EffectContext",
    "EffectResult",
    "TriggerType",
]
