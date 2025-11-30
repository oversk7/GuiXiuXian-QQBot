"""
属性计算领域模块

提供统一的属性计算接口和实现
"""

from .interfaces import IAttributeSource, AttributeBonus, AttributeBreakdown
from .attribute_calculator import AttributeCalculator
from .attribute_calculator_factory import AttributeCalculatorFactory
from .player_attributes_integration import (
    get_effective_attributes_v2,
    get_attribute_breakdown_v2,
    invalidate_player_buff_cache,
    get_attribute_calculator_stats,
    USE_ATTRIBUTE_CALCULATOR_V2,
)

__all__ = [
    # 核心接口和数据类
    "IAttributeSource",
    "AttributeBonus",
    "AttributeBreakdown",
    "AttributeCalculator",
    # 工厂和集成
    "AttributeCalculatorFactory",
    "get_effective_attributes_v2",
    "get_attribute_breakdown_v2",
    "invalidate_player_buff_cache",
    "get_attribute_calculator_stats",
    "USE_ATTRIBUTE_CALCULATOR_V2",
]
