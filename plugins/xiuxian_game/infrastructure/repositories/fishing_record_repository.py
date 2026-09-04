"""
钓鱼记录仓储实现

提供钓鱼记录的数据访问抽象
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.fishing_record import FishingRecord


class FishingRecordRepository(IRepository[FishingRecord]):
    """钓鱼记录仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化钓鱼记录仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础CRUD方法 ====================

    async def get_by_id(self, record_id: int) -> Optional[FishingRecord]:
        """
        根据ID获取钓鱼记录

        Args:
            record_id: 记录ID

        Returns:
            钓鱼记录实例，不存在返回None
        """
        return await self._session.get(FishingRecord, record_id)

    async def add(self, fishing_record: FishingRecord) -> FishingRecord:
        """
        添加钓鱼记录

        Args:
            fishing_record: 钓鱼记录实例

        Returns:
            添加后的钓鱼记录（包含生成的ID）
        """
        self._session.add(fishing_record)
        await self._session.flush()
        return fishing_record

    async def update(self, fishing_record: FishingRecord) -> FishingRecord:
        """
        更新钓鱼记录

        Args:
            fishing_record: 钓鱼记录实例

        Returns:
            更新后的钓鱼记录
        """
        self._session.add(fishing_record)
        await self._session.flush()
        return fishing_record

    async def delete(self, record_id: int) -> bool:
        """
        删除钓鱼记录

        Args:
            record_id: 记录ID

        Returns:
            是否成功删除
        """
        fishing_record = await self.get_by_id(record_id)
        if not fishing_record:
            return False
        await self._session.delete(fishing_record)
        await self._session.flush()
        return True

    async def exists(self, record_id: int) -> bool:
        """
        检查钓鱼记录是否存在

        Args:
            record_id: 记录ID

        Returns:
            是否存在
        """
        fishing_record = await self.get_by_id(record_id)
        return fishing_record is not None

    async def count(self) -> int:
        """
        统计钓鱼记录总数

        Returns:
            记录总数
        """
        stmt = select(func.count(FishingRecord.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== 业务查询方法 ====================

    async def can_fishing(self, player_id: str, cooldown_minutes: int) -> bool:
        """
        检查玩家是否过了钓鱼冷却时间

        Args:
            player_id: 玩家ID
            cooldown_minutes: 冷却时间（分钟）

        Returns:
            是否可以钓鱼

        对应原代码:
            fishing_record.py Line 82-96
        """
        last_time = await self.get_last_fishing_time(player_id)
        if not last_time:
            return True

        cooldown_delta = timedelta(minutes=cooldown_minutes)
        return datetime.now() >= last_time + cooldown_delta

    async def get_last_fishing_time(self, player_id: str) -> Optional[datetime]:
        """
        获取玩家最后一次钓鱼时间

        Args:
            player_id: 玩家ID

        Returns:
            最后钓鱼时间，如果没有记录则返回None

        对应原代码:
            fishing_record.py Line 98-105
        """
        stmt = (
            select(FishingRecord.fishing_time)
            .where(FishingRecord.player_id == player_id)
            .order_by(FishingRecord.fishing_time.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar()

    async def get_today_fishing_count(self, player_id: str) -> int:
        """获取玩家今日钓鱼次数。"""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(FishingRecord.id)).where(
            FishingRecord.player_id == player_id,
            FishingRecord.fishing_time >= today_start,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def get_player_fishing_stats(self, player_id: str) -> Dict:
        """
        获取玩家钓鱼统计信息

        Args:
            player_id: 玩家ID

        Returns:
            统计信息字典，包含：
            - today_fishing_count: 今日钓鱼次数
            - total_fishing_count: 总钓鱼次数
            - total_fish_caught: 总钓鱼数量

        对应原代码:
            fishing_record.py Line 42-70
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(
            func.count(FishingRecord.id),
            func.coalesce(func.sum(FishingRecord.quantity), 0),
            func.coalesce(
                func.sum(case((FishingRecord.fishing_time >= today_start, 1), else_=0)),
                0,
            ),
        ).where(FishingRecord.player_id == player_id)
        total_count, total_fish, today_count = (
            await self._session.execute(stmt)
        ).one()

        return {
            "today_fishing_count": int(today_count),
            "total_fishing_count": int(total_count),
            "total_fish_caught": int(total_fish),
        }

    async def record_fishing(
        self,
        player_id: str,
        fish_id: str,
        quantity: int,
        location_x: int,
        location_y: int,
        dungeon_level: int = 0
    ) -> FishingRecord:
        """
        记录钓鱼活动

        Args:
            player_id: 玩家ID
            fish_id: 鱼类物品ID
            quantity: 数量
            location_x: X坐标
            location_y: Y坐标
            dungeon_level: 钓鱼时诡域层级（0=现实世界）

        Returns:
            创建的钓鱼记录

        对应原代码:
            fishing_record.py Line 28-39
        """
        fishing_record = FishingRecord(
            player_id=player_id,
            fish_id=fish_id,
            quantity=quantity,
            location_x=location_x,
            location_y=location_y,
            dungeon_level=dungeon_level,
            fishing_time=datetime.now()
        )
        return await self.add(fishing_record)

    # ==================== 辅助方法 ====================

    async def get_player_records(self, player_id: str, limit: int = 10) -> List[FishingRecord]:
        """
        获取玩家的钓鱼记录

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            钓鱼记录列表，按时间倒序排列

        对应原代码:
            fishing_record.py Line 72-79
        """
        stmt = (
            select(FishingRecord)
            .where(FishingRecord.player_id == player_id)
            .order_by(FishingRecord.fishing_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
