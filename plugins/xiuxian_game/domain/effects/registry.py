"""
效果注册中心

提供统一的效果注册和管理机制，支持装饰器注册和实例创建
"""

from typing import Dict, Type, Optional, List, Callable
from .interfaces import IEffect, TriggerType


class EffectRegistry:
    """
    统一的效果注册中心

    设计原则：
    1. 支持装饰器注册效果类
    2. 支持按效果ID或触发类型查找
    3. 支持效果实例的创建和缓存
    4. 向后兼容旧的注册表系统
    """

    def __init__(self):
        # 效果类注册表：effect_id -> Effect类
        self._registry: Dict[str, Type[IEffect]] = {}

        # 触发类型索引：trigger_type -> List[effect_id]
        self._trigger_index: Dict[TriggerType, List[str]] = {}

        # 效果实例缓存（用于单例效果）
        self._instances: Dict[str, IEffect] = {}

    def register(self, effect_id: str, singleton: bool = False):
        """
        装饰器：注册效果类

        Args:
            effect_id: 效果唯一标识
            singleton: 是否单例（复用同一个实例）

        Returns:
            装饰器函数

        Example:
            @effect_registry.register("item_restore_hp")
            class RestoreHPEffect(BaseItemEffect):
                ...
        """
        def decorator(cls: Type[IEffect]):
            self._registry[effect_id] = cls

            # 如果是单例，立即创建实例
            if singleton:
                self._instances[effect_id] = cls(effect_id)

            return cls

        return decorator

    def register_class(self, effect_id: str, effect_class: Type[IEffect], singleton: bool = False):
        """
        直接注册效果类（不使用装饰器）

        Args:
            effect_id: 效果唯一标识
            effect_class: 效果类
            singleton: 是否单例
        """
        self._registry[effect_id] = effect_class

        if singleton:
            self._instances[effect_id] = effect_class(effect_id)

    def get_class(self, effect_id: str) -> Optional[Type[IEffect]]:
        """
        获取效果类

        Args:
            effect_id: 效果ID

        Returns:
            效果类，如果不存在返回None
        """
        return self._registry.get(effect_id)

    def create(self, effect_id: str, **kwargs) -> IEffect:
        """
        创建效果实例

        Args:
            effect_id: 效果ID
            **kwargs: 传递给效果类构造函数的参数

        Returns:
            IEffect: 效果实例

        Raises:
            ValueError: 如果效果ID不存在
        """
        # 如果是单例，直接返回缓存的实例
        if effect_id in self._instances:
            return self._instances[effect_id]

        # 获取效果类
        effect_class = self._registry.get(effect_id)
        if not effect_class:
            raise ValueError(f"Unknown effect ID: {effect_id}")

        # 创建新实例
        return effect_class(**kwargs)

    def get_by_trigger(self, trigger_type: TriggerType) -> List[str]:
        """
        按触发类型获取效果ID列表

        Args:
            trigger_type: 触发类型

        Returns:
            List[str]: 效果ID列表
        """
        return self._trigger_index.get(trigger_type, [])

    def index_by_trigger(self, effect_id: str, trigger_type: TriggerType):
        """
        为效果建立触发类型索引

        Args:
            effect_id: 效果ID
            trigger_type: 触发类型
        """
        if trigger_type not in self._trigger_index:
            self._trigger_index[trigger_type] = []

        if effect_id not in self._trigger_index[trigger_type]:
            self._trigger_index[trigger_type].append(effect_id)

    def list_all(self) -> List[str]:
        """
        列出所有已注册的效果ID

        Returns:
            List[str]: 效果ID列表
        """
        return list(self._registry.keys())

    def clear(self):
        """清空注册表（主要用于测试）"""
        self._registry.clear()
        self._trigger_index.clear()
        self._instances.clear()


# 全局单例注册中心
_global_registry: Optional[EffectRegistry] = None


def get_effect_registry() -> EffectRegistry:
    """
    获取全局效果注册中心（单例）

    Returns:
        EffectRegistry: 全局注册中心实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = EffectRegistry()
    return _global_registry


def register_effect(effect_id: str, singleton: bool = False):
    """
    全局装饰器：注册效果到全局注册中心

    Example:
        @register_effect("item_restore_hp")
        class RestoreHPEffect(BaseItemEffect):
            ...
    """
    return get_effect_registry().register(effect_id, singleton)
