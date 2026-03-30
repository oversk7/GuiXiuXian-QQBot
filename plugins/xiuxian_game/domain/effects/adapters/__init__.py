"""
效果适配器模块

将旧的效果实现适配到新的IEffect接口
"""

# 物品效果适配器
from .item_effect_adapter import ItemEffectAdapter, wrap_legacy_item_effect
from .register_all import (
    register_all_item_effect_adapters,
    get_registered_adapters,
    is_effect_registered
)
from .integration import (
    apply_effect_v2,
    apply_effect_with_fallback,
    USE_NEW_EFFECT_SYSTEM
)

# 战斗效果桥接器
from .battle_effect_bridge import BattleEffectBridge, create_bridge_for_trigger_config
from .battle_effect_register import (
    register_all_battle_effect_bridges,
    get_equipment_bridge_mapping,
)

__all__ = [
    # 物品效果适配器
    "ItemEffectAdapter",
    "wrap_legacy_item_effect",
    "register_all_item_effect_adapters",
    "get_registered_adapters",
    "is_effect_registered",
    "apply_effect_v2",
    "apply_effect_with_fallback",
    "USE_NEW_EFFECT_SYSTEM",

    # 战斗效果桥接器
    "BattleEffectBridge",
    "create_bridge_for_trigger_config",
    "register_all_battle_effect_bridges",
    "get_equipment_bridge_mapping",
]
