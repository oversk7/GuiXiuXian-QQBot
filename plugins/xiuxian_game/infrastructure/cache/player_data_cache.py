"""
玩家数据 LRU 缓存

缓存 player_id → Player 列数据（dict），避免活跃玩家每条指令都 SELECT。

策略：
- Write-through：UoW commit 成功后自动更新缓存
- LRU 淘汰：超过 maxsize 时淘汰最久未访问的条目
- TTL 过期：超过 ttl 秒的条目视为过期，下次访问时淘汰
- last_active_at 节流：60秒内不重复写入 DB
"""
import time
import logging
from collections import OrderedDict
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class PlayerDataCache:
    """player_id → Player 列数据的进程内 LRU 缓存"""

    def __init__(self, maxsize: int = 64, ttl: int = 120):
        """
        Args:
            maxsize: 最大缓存条目数（活跃玩家不多，64 足够）
            ttl: 缓存过期时间（秒），默认 120 秒
        """
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, player_id: str) -> Optional[Dict[str, Any]]:
        """查缓存，返回列数据 dict 或 None。"""
        if player_id not in self._cache:
            self._misses += 1
            return None

        # TTL 检查
        if time.monotonic() - self._timestamps[player_id] > self._ttl:
            self._evict(player_id)
            self._misses += 1
            return None

        self._hits += 1
        self._cache.move_to_end(player_id)
        return self._cache[player_id]

    def put(self, player_id: str, column_data: Dict[str, Any]) -> None:
        """写入/更新缓存。"""
        if player_id in self._cache:
            self._cache.move_to_end(player_id)
        self._cache[player_id] = column_data
        self._timestamps[player_id] = time.monotonic()

        # LRU 淘汰
        while len(self._cache) > self._maxsize:
            oldest_key, _ = self._cache.popitem(last=False)
            self._timestamps.pop(oldest_key, None)

    def put_from_player(self, player) -> None:
        """从 SQLAlchemy Player 对象提取列数据并缓存。"""
        from ...models.player import Player
        column_data = {}
        for col in Player.__table__.columns:
            column_data[col.key] = getattr(player, col.key, None)
        self.put(player.id, column_data)

    def invalidate(self, player_id: str) -> None:
        """使指定玩家的缓存失效。"""
        self._evict(player_id)

    def _evict(self, player_id: str) -> None:
        self._cache.pop(player_id, None)
        self._timestamps.pop(player_id, None)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
        }


# 全局单例
player_data_cache = PlayerDataCache()
