"""
Player属性计算集成模块

将AttributeCalculator集成到Player模型，保持向后兼容
"""

from typing import Dict
from .attribute_calculator_factory import AttributeCalculatorFactory
from nonebot import logger


async def get_effective_attributes_v2(player, session) -> Dict[str, int | float]:
    """
    使用AttributeCalculator v2计算有效属性

    这是新实现，使用统一的AttributeCalculator框架
    包含60秒TTL buff缓存优化

    Args:
        player: Player实例
        session: 数据库会话

    Returns:
        Dict: 有效属性字典（与旧版本格式兼容）
    """
    logger.debug(f"⚡ [AttributeCalculator v2] 开始计算玩家 {player.id} 的属性")

    # 获取AttributeCalculator单例
    calculator = AttributeCalculatorFactory.get_instance()

    # 计算最终属性
    attrs_bonus = await calculator.calculate_simple(player, session)

    logger.debug(f"✨ [AttributeCalculator v2] 玩家 {player.id} 属性计算完成: attack={attrs_bonus.attack}, defense={attrs_bonus.defense}")

    # 转换为dict（保持向后兼容）
    return attrs_bonus.to_dict()


def invalidate_player_buff_cache(player_id: str):
    """
    使指定玩家的buff缓存失效

    应在以下场景调用:
    - 玩家使用临时buff物品
    - 玩家的buff过期
    - 玩家的buff被移除

    使用示例:
    ```python
    from domain.attributes.player_attributes_integration import invalidate_player_buff_cache

    # 玩家使用buff物品后
    invalidate_player_buff_cache(player.id)
    ```

    Args:
        player_id: 玩家ID
    """
    AttributeCalculatorFactory.invalidate_buff_cache(player_id)


def get_attribute_calculator_stats() -> dict:
    """
    获取AttributeCalculator统计信息（用于监控）

    Returns:
        Dict: 缓存统计信息
    """
    return AttributeCalculatorFactory.get_cache_stats()
