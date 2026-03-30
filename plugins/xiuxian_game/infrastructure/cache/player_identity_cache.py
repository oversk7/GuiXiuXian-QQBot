"""
玩家身份映射缓存

缓存 platform_id → player_id 的映射关系，避免每条指令都做
AccountOwnership JOIN Player 的数据库查询。

该映射几乎不变（仅在账号切换/转让时变化），因此采用纯失效策略，
不设 TTL。失效入口统一收敛到 invalidate() 方法。
"""
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PlayerIdentityCache:
    """platform_id → player_id 的进程内映射缓存"""

    def __init__(self):
        self._map: Dict[str, Optional[str]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, platform_id: str) -> Optional[str]:
        """查缓存。返回 player_id 或 None（未缓存）。

        注意：返回 None 表示缓存未命中，不代表该用户没有角色。
        若用户确实没有角色，缓存中会存储一个特殊的 sentinel 值。
        """
        if platform_id in self._map:
            self._hits += 1
            return self._map[platform_id]
        self._misses += 1
        return None

    def has(self, platform_id: str) -> bool:
        """是否已缓存该 platform_id（包括缓存了"无角色"的情况）"""
        return platform_id in self._map

    def put(self, platform_id: str, player_id: Optional[str]) -> None:
        """写入缓存。player_id 为 None 表示该用户无角色。"""
        self._map[platform_id] = player_id

    def invalidate(self, platform_id: str) -> None:
        """使指定用户的缓存失效。账号切换/转让时调用。"""
        self._map.pop(platform_id, None)

    def invalidate_all(self) -> None:
        """清空全部缓存。一般用于调试或热重载。"""
        self._map.clear()
        logger.info("[PlayerIdentityCache] 全部缓存已清空")

    @property
    def stats(self) -> dict:
        """缓存命中统计，用于监控。"""
        total = self._hits + self._misses
        return {
            "size": len(self._map),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
        }


# 全局单例
player_identity_cache = PlayerIdentityCache()
