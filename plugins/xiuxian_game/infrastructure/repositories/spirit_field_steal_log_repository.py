"""
偷菜记录仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.spirit_field import SpiritFieldStealLog


class SpiritFieldStealLogRepository(IRepository[SpiritFieldStealLog]):
    """偷菜记录仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, log_id: int) -> Optional[SpiritFieldStealLog]:
        return await self._session.get(SpiritFieldStealLog, log_id)

    async def add(self, entity: SpiritFieldStealLog) -> SpiritFieldStealLog:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: SpiritFieldStealLog) -> SpiritFieldStealLog:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: SpiritFieldStealLog):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, log_id: int) -> bool:
        entity = await self.get_by_id(log_id)
        return entity is not None

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count(SpiritFieldStealLog.id))
        )
        return result.scalar_one()

    async def get_today_steal_count(self, thief_id: str, today: str) -> int:
        """获取今日偷菜总次数"""
        result = await self._session.execute(
            select(func.count(SpiritFieldStealLog.id)).where(
                SpiritFieldStealLog.thief_id == thief_id,
                SpiritFieldStealLog.steal_date == today
            )
        )
        return result.scalar_one()

    async def has_stolen_from_today(self, thief_id: str, victim_id: str, today: str) -> bool:
        """今日是否已偷过该玩家"""
        result = await self._session.execute(
            select(func.count(SpiritFieldStealLog.id)).where(
                SpiritFieldStealLog.thief_id == thief_id,
                SpiritFieldStealLog.victim_id == victim_id,
                SpiritFieldStealLog.steal_date == today
            )
        )
        return result.scalar_one() > 0

    async def get_recent_logs_for_victim(self, victim_id: str, limit: int = 10) -> List[SpiritFieldStealLog]:
        """获取被偷记录(最近N条)"""
        stmt = (
            select(SpiritFieldStealLog)
            .where(SpiritFieldStealLog.victim_id == victim_id)
            .order_by(SpiritFieldStealLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_logs_for_thief(self, thief_id: str, limit: int = 10) -> List[SpiritFieldStealLog]:
        """获取偷菜记录(最近N条)"""
        stmt = (
            select(SpiritFieldStealLog)
            .where(SpiritFieldStealLog.thief_id == thief_id)
            .order_by(SpiritFieldStealLog.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_steal_time(self, thief_id: str) -> Optional[SpiritFieldStealLog]:
        """获取最后一次偷菜记录(用于冷却判定)"""
        stmt = (
            select(SpiritFieldStealLog)
            .where(SpiritFieldStealLog.thief_id == thief_id)
            .order_by(SpiritFieldStealLog.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
