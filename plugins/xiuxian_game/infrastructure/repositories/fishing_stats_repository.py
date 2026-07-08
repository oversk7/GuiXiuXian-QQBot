"""
钓鱼统计仓储实现
"""
from typing import Optional, List, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.fishing_record import FishingStats
from ...models.player import Player


class FishingStatsRepository(IRepository[FishingStats]):
    """钓鱼统计仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ==================== 基础CRUD方法 ====================

    async def get_by_id(self, stats_id: int) -> Optional[FishingStats]:
        """根据ID获取统计记录"""
        return await self._session.get(FishingStats, stats_id)

    async def add(self, fishing_stats: FishingStats) -> FishingStats:
        """添加统计记录"""
        self._session.add(fishing_stats)
        await self._session.flush()
        return fishing_stats

    async def update(self, fishing_stats: FishingStats) -> FishingStats:
        """更新统计记录"""
        self._session.add(fishing_stats)  # 必须先标记对象为需要更新
        await self._session.flush()
        return fishing_stats

    async def delete(self, stats_id: int) -> bool:
        """删除统计记录"""
        fishing_stats = await self.get_by_id(stats_id)
        if not fishing_stats:
            return False
        await self._session.delete(fishing_stats)
        await self._session.flush()
        return True

    async def exists(self, stats_id: int) -> bool:
        """检查统计记录是否存在"""
        fishing_stats = await self.get_by_id(stats_id)
        return fishing_stats is not None

    async def count(self) -> int:
        """统计记录总数"""
        stmt = select(func.count(FishingStats.player_id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== 业务查询方法 ====================

    async def get_by_player_id(self, player_id: str) -> Optional[FishingStats]:
        """
        根据玩家ID获取统计记录

        Args:
            player_id: 玩家ID

        Returns:
            统计记录，如果不存在则返回None
        """
        stmt = select(FishingStats).where(FishingStats.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_or_create(self, player_id: str) -> FishingStats:
        """
        获取或创建玩家的统计记录

        Args:
            player_id: 玩家ID

        Returns:
            统计记录（已存在或新创建）
        """
        stats = await self.get_by_player_id(player_id)
        if not stats:
            stats = FishingStats(player_id=player_id)
            await self.add(stats)
        return stats

    async def update_stats(
        self,
        stats: FishingStats,
        fish_value: int,
        rarity: str,
        quantity: int,
        dungeon_level: int = 0
    ) -> FishingStats:
        """
        更新钓鱼统计数据

        Args:
            stats: 统计记录对象
            fish_value: 本次钓鱼价值
            rarity: 鱼类稀有度（white/green/blue/purple/orange）
            quantity: 数量
            dungeon_level: 钓鱼时所处诡域层级（0=现实世界）

        Returns:
            更新后的统计记录
        """
        # 更新最深诡域钓鱼层级（成就用）
        if dungeon_level > (stats.max_fishing_dungeon_level or 0):
            stats.max_fishing_dungeon_level = dungeon_level

        # 更新总次数
        stats.total_fishing_count += 1

        # 更新总捕鱼数量
        stats.total_fish_caught += quantity

        # 更新总价值
        stats.total_fish_value += fish_value

        # 更新稀有鱼统计（紫色及以上）
        if rarity in ["purple", "orange"]:
            stats.rare_fish_caught += quantity

        # 更新传说鱼统计（橙色）
        if rarity == "orange":
            stats.legendary_fish_caught += quantity

        # 更新最高单次价值
        if fish_value > stats.best_fish_value:
            stats.best_fish_value = fish_value

        await self.update(stats)
        return stats

    async def get_leaderboard(self, limit: int = 10, server_id: int = 1) -> List[Tuple[FishingStats, str, int]]:
        """
        获取钓鱼排行榜（预加载Player信息，按区服隔离）

        Args:
            limit: 返回数量限制
            server_id: 区服ID

        Returns:
            排行榜列表，每项为 (FishingStats, nickname, uid)
        """
        stmt = (
            select(FishingStats, Player.nickname, Player.uid)
            .join(Player, FishingStats.player_id == Player.id)
            .where(Player.server_id == server_id)
            .order_by(desc(FishingStats.total_fish_value))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(stats, nickname, uid) for stats, nickname, uid in result]
