"""
属性来源实现模块

提供各种属性来源的具体实现：装备、buff、丹药、VIP等
"""

from .buff_source import BuffAttributeSource
from .equipment_source import EquipmentAttributeSource

__all__ = [
    "BuffAttributeSource",
    "EquipmentAttributeSource",
]
