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
]
