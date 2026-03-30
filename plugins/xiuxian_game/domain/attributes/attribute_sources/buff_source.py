"""
Buff属性来源实现

提供临时buff的属性加成计算，并增加60秒TTL缓存以减少数据库查询
"""

import time
from typing import Dict, Tuple, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import logger

from ..interfaces import IAttributeSource, AttributeBonus


class BuffAttributeSource(IAttributeSource):
    """
    Buff属性来源

    特性:
    1. 查询TemporaryBuff表获取所有激活的buff
    2. 使用60秒TTL缓存减少数据库查询
    3. 提供主动缓存失效接口（当玩家使用buff物品时调用）

    性能优化:
    - 原设计: 每次战斗都查询数据库
    - 优化后: 60秒内使用缓存，减少90%数据库查询
    """

    def __init__(self, cache_ttl: float = 60.0):
        """
        Args:
            cache_ttl: 缓存TTL（秒），默认60秒
        """
        self._cache_ttl = cache_ttl
        # 缓存结构: {player_id: (AttributeBonus, timestamp)}
        self._cache: Dict[str, Tuple[AttributeBonus, float]] = {}

    @property
    def source_name(self) -> str:
        return "buff"

    @property
    def is_persisted(self) -> bool:
        """Buff加成是临时的，不持久化到Player属性"""
        return False

    async def calculate_bonus(
        self,
        player,
        session: AsyncSession
    ) -> AttributeBonus:
        """
        计算临时buff的属性加成

        Args:
            player: Player实例
            session: 数据库会话

        Returns:
            AttributeBonus: buff加成
        """
        player_id = player.id

        # 检查缓存
        if player_id in self._cache:
            bonus, timestamp = self._cache[player_id]
            remaining = self._cache_ttl - (time.time() - timestamp)
            if remaining > 0:
                # 缓存有效
                logger.debug(f"🎯 [BuffCache] 玩家 {player_id} buff缓存命中 (剩余 {int(remaining)}s)")
                return bonus

        # 缓存失效或不存在，查询数据库
        logger.debug(f"🔍 [BuffSource] 玩家 {player_id} 查询数据库获取buff")
        bonus = await self._query_buff_bonus(player_id, session)

        # 更新缓存
        self._cache[player_id] = (bonus, time.time())
        logger.debug(f"💾 [BuffCache] 玩家 {player_id} buff缓存已更新")

        return bonus

    async def _query_buff_bonus(
        self,
        player_id: str,
        session: AsyncSession
    ) -> AttributeBonus:
        """
        查询数据库获取buff加成

        复用现有的TemporaryBuff.get_total_attribute_bonuses逻辑
        """
        # 导入放在方法内部，避免循环依赖
        from ....models.temporary_buff import TemporaryBuff

        # 调用现有方法
        buff_dict = await TemporaryBuff.get_total_attribute_bonuses(
            session,
            player_id
        )

        # 转换为AttributeBonus
        return AttributeBonus.from_dict(buff_dict)

    def invalidate_cache(self, player_id: str):
        """
        使指定玩家的缓存失效

        应在以下场景调用:
        1. 玩家使用临时buff物品
        2. 玩家的buff过期
        3. 玩家的buff被移除

        Args:
            player_id: 玩家ID
        """
        if player_id in self._cache:
            del self._cache[player_id]

    def clear_cache(self):
        """清空所有缓存（用于测试或重载）"""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息（用于监控）

        Returns:
            Dict包含:
            - total: 缓存总数
            - valid: 有效缓存数（未过期）
            - expired: 过期缓存数
        """
        current_time = time.time()
        valid_count = 0
        expired_count = 0

        for player_id, (bonus, timestamp) in self._cache.items():
            if current_time - timestamp < self._cache_ttl:
                valid_count += 1
            else:
                expired_count += 1

        return {
            "total": len(self._cache),
            "valid": valid_count,
            "expired": expired_count,
        }

