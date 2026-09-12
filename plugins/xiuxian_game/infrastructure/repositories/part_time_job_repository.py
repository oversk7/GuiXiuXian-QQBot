"""
PartTimeJobRepository - 打工记录数据访问层

提供打工记录相关的数据库操作
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ...models.part_time_job import PartTimeJob
from ...domain.repositories.base import IRepository


class PartTimeJobRepository(IRepository[PartTimeJob]):
    """打工记录仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[PartTimeJob]:
        """根据ID获取打工记录"""
        return await self._session.get(PartTimeJob, entity_id)

    async def add(self, entity: PartTimeJob) -> PartTimeJob:
        """添加打工记录"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PartTimeJob) -> PartTimeJob:
        """更新打工记录"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PartTimeJob):
        """删除打工记录"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[PartTimeJob]:
        """列出所有打工记录"""
        stmt = select(PartTimeJob)
        if filters.get("player_id"):
            stmt = stmt.where(PartTimeJob.player_id == filters["player_id"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计打工记录数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(PartTimeJob)
        if filters.get("player_id"):
            stmt = stmt.where(PartTimeJob.player_id == filters["player_id"])
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """
        检查打工记录是否存在

        Args:
            entity_id: 打工记录ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 打工记录特定方法 ====================

    async def get_current_working_job(self, player_id: str) -> Optional[PartTimeJob]:
        """
        获取玩家当前正在进行的工作

        Args:
            player_id: 玩家ID

        Returns:
            正在进行的打工记录，如果不存在则返回None
        """
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player_id,
                PartTimeJob.is_working == True
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_current_working_job_with_lock(self, player_id: str) -> Optional[PartTimeJob]:
        """
        获取玩家当前正在进行的工作并加行锁（防止竞态条件）

        Args:
            player_id: 玩家ID

        Returns:
            正在进行的打工记录，如果不存在则返回None

        Note:
            使用SELECT FOR UPDATE进行行级锁，防止并发领取
        """
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player_id,
                PartTimeJob.is_working == True
            )
        ).with_for_update().execution_options(populate_existing=True)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_completed_jobs(
        self, player_id: str, limit: int = 10
    ) -> List[PartTimeJob]:
        """
        获取玩家已完成的打工记录

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            已完成的打工记录列表（按完成时间倒序）
        """
        stmt = (
            select(PartTimeJob)
            .where(
                and_(
                    PartTimeJob.player_id == player_id,
                    PartTimeJob.is_working == False
                )
            )
            .order_by(PartTimeJob.completed_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
