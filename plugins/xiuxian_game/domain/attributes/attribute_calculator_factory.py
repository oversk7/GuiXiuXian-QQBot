"""
AttributeCalculator工厂类

提供AttributeCalculator的单例创建和配置
"""

from typing import Optional
from .attribute_calculator import AttributeCalculator
from .attribute_sources.buff_source import BuffAttributeSource
from .attribute_sources.equipment_source import EquipmentAttributeSource


class AttributeCalculatorFactory:
    """
    AttributeCalculator工厂类

    职责:
    1. 创建并配置AttributeCalculator实例
    2. 注册所有AttributeSource
    3. 提供单例访问（全局共享，复用缓存）

    使用示例:
    ```python
    calculator = AttributeCalculatorFactory.get_instance()
    attrs = await calculator.calculate_simple(player, session)
    ```
    """

    _instance: Optional[AttributeCalculator] = None
    _buff_source: Optional[BuffAttributeSource] = None
    _pet_source: Optional['PetAttributeSource'] = None

    @classmethod
    def get_instance(cls, cache_ttl: float = 60.0) -> AttributeCalculator:
        """
        获取AttributeCalculator单例

        Args:
            cache_ttl: Buff缓存TTL（秒），默认60秒

        Returns:
            AttributeCalculator实例（全局单例）
        """
        if cls._instance is None:
            cls._create_instance(cache_ttl)

        return cls._instance

    @classmethod
    def _create_instance(cls, cache_ttl: float = 60.0):
        """创建并配置AttributeCalculator实例"""
        calculator = AttributeCalculator()

        # 创建BuffAttributeSource（全局单例，共享缓存）
        cls._buff_source = BuffAttributeSource(cache_ttl=cache_ttl)
        calculator.add_source(cls._buff_source)

        # 创建EquipmentAttributeSource
        equipment_source = EquipmentAttributeSource()
        calculator.add_source(equipment_source)

        # 宠物伴侣属性来源
        from .attribute_sources.pet_source import PetAttributeSource
        cls._pet_source = PetAttributeSource(cache_ttl=cache_ttl)
        calculator.add_source(cls._pet_source)

        cls._instance = calculator

    @classmethod
    def invalidate_buff_cache(cls, player_id: str):
        """
        使指定玩家的buff缓存失效

        应在以下场景调用:
        - 玩家使用临时buff物品
        - 玩家的buff过期
        - 玩家的buff被移除

        Args:
            player_id: 玩家ID
        """
        if cls._buff_source:
            cls._buff_source.invalidate_cache(player_id)

    @classmethod
    def clear_buff_cache(cls):
        """清空所有Buff缓存（用于全量状态变更后的兜底一致性）"""
        if cls._buff_source:
            cls._buff_source.clear_cache()

    @classmethod
    def invalidate_pet_cache(cls, player_id: str):
        """使指定玩家的宠物属性缓存失效"""
        if cls._pet_source:
            cls._pet_source.invalidate_cache(player_id)

    @classmethod
    def get_cache_stats(cls) -> dict:
        """
        获取缓存统计信息（用于监控）

        Returns:
            Dict包含buff缓存统计
        """
        if cls._buff_source:
            return {
                "buff_cache": cls._buff_source.get_cache_stats()
            }
        return {}

    @classmethod
    def reset(cls):
        """
        重置工厂（用于测试）

        清空单例实例和缓存
        """
        if cls._buff_source:
            cls._buff_source.clear_cache()
        if cls._pet_source:
            cls._pet_source.clear_cache()
        cls._instance = None
        cls._buff_source = None
        cls._pet_source = None
