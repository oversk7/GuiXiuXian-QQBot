"""
属性来源实现模块

宠物加成未持久化到 Player 字段，由 Player.get_effective_attributes 动态叠加
"""

from .pet_source import PetAttributeSource, get_pet_source, invalidate_pet_cache

__all__ = [
    "PetAttributeSource",
    "get_pet_source",
    "invalidate_pet_cache",
]
