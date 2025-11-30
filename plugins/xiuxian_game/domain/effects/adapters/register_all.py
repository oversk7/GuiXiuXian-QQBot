"""
批量注册物品效果适配器

在启动时自动将所有旧的物品效果包装为适配器并注册到新系统
"""

from nonebot import logger
from typing import Dict, Type

from ..registry import register_effect
from .item_effect_adapter import create_adapter_for_all_legacy_effects, ItemEffectAdapter


# 全局变量，存储所有注册的适配器
_registered_adapters: Dict[str, Type[ItemEffectAdapter]] = {}


def register_all_item_effect_adapters() -> Dict[str, Type[ItemEffectAdapter]]:
    """
    批量注册所有物品效果适配器

    该函数会：
    1. 自动扫描item_effects.py中的所有注册效果
    2. 为每个效果创建适配器类
    3. 注册到EffectRegistry

    Returns:
        Dict[effect_id, AdapterClass]: 已注册的适配器映射

    使用示例:
    ```python
    # 在插件启动时调用
    from domain.effects.adapters.register_all import register_all_item_effect_adapters

    adapters = register_all_item_effect_adapters()
    logger.info(f"成功注册 {len(adapters)} 个物品效果适配器")
    ```
    """
    global _registered_adapters

    # 如果已经注册过，直接返回
    if _registered_adapters:
        logger.debug(f"[AdapterRegistry] 适配器已注册，跳过重复注册")
        return _registered_adapters

    logger.info("[AdapterRegistry] 开始批量注册物品效果适配器...")

    # 创建所有适配器
    adapters = create_adapter_for_all_legacy_effects()

    # 注册到EffectRegistry
    for effect_id, adapter_class in adapters.items():
        try:
            # 使用装饰器注册
            register_effect(effect_id)(adapter_class)
            _registered_adapters[effect_id] = adapter_class
            logger.debug(f"[AdapterRegistry] 注册适配器: {effect_id}")
        except Exception as e:
            logger.error(f"[AdapterRegistry] 注册适配器 {effect_id} 失败: {e}")

    logger.info(f"[AdapterRegistry] 成功注册 {len(_registered_adapters)} 个物品效果适配器")

    # 打印注册清单（DEBUG级别）
    if _registered_adapters:
        logger.debug("[AdapterRegistry] 注册清单:")
        for idx, effect_id in enumerate(_registered_adapters.keys(), 1):
            logger.debug(f"  {idx:2d}. {effect_id}")

    return _registered_adapters


def get_registered_adapters() -> Dict[str, Type[ItemEffectAdapter]]:
    """
    获取已注册的适配器映射

    Returns:
        Dict[effect_id, AdapterClass]: 已注册的适配器映射
    """
    return _registered_adapters.copy()


def is_effect_registered(effect_id: str) -> bool:
    """
    检查指定效果是否已注册

    Args:
        effect_id: 效果ID

    Returns:
        bool: 是否已注册
    """
    return effect_id in _registered_adapters
