"""
每日任务仓储实现

基于 REFACTORING_PLAN_v4.md 的DI架构重构
"""

from typing import List, Optional
from datetime import date
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.daily_task import DailyTask, TaskStatus


class DailyTaskRepository(IRepository[DailyTask]):
    """
    每日任务仓储实现

    提供每日任务数据的访问和查询方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化每日任务仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    # ==================== 核心查询方法 ====================

    async def find_by_id(self, task_id: int) -> Optional[DailyTask]:
        """
        按ID查询任务

        Args:
            task_id: 任务唯一标识

        Returns:
            DailyTask对象，如果不存在则返回None
        """
        stmt = select(DailyTask).where(DailyTask.id == task_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_player_and_date(
        self,
        player_id: str,
        task_date: date
    ) -> Optional[DailyTask]:
        """
        查询玩家指定日期的第一个任务

        Args:
            player_id: 玩家ID
            task_date: 任务日期

        Returns:
            DailyTask对象，如果不存在则返回None
        """
        stmt = (
            select(DailyTask)
            .where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.task_date == task_date
                )
            )
            .order_by(DailyTask.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all_by_player_and_date(
        self,
        player_id: str,
        task_date: date
    ) -> List[DailyTask]:
        """
        查询玩家指定日期的所有任务

        Args:
            player_id: 玩家ID
            task_date: 任务日期

        Returns:
            DailyTask列表
        """
        stmt = (
            select(DailyTask)
            .where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.task_date == task_date
                )
            )
            .order_by(DailyTask.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_weekly_completed(
        self,
        player_id: str,
        week_start: date
    ) -> int:
        """
        统计本周完成任务数

        Args:
            player_id: 玩家ID
            week_start: 本周开始日期（周一）

        Returns:
            本周完成任务数量
        """
        stmt = select(func.count(DailyTask.id)).where(
            and_(
                DailyTask.player_id == player_id,
                DailyTask.status == TaskStatus.COMPLETED,
                DailyTask.task_date >= week_start
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_total_completed(self, player_id: str) -> int:
        """
        统计总完成任务数

        Args:
            player_id: 玩家ID

        Returns:
            历史累计完成任务数量
        """
        stmt = select(func.count(DailyTask.id)).where(
            and_(
                DailyTask.player_id == player_id,
                DailyTask.status == TaskStatus.COMPLETED
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def find_expired_tasks(self, today: date) -> List[DailyTask]:
        """
        查询昨天及之前未完成的任务

        Args:
            today: 今天的日期

        Returns:
            过期任务列表
        """
        stmt = select(DailyTask).where(
            and_(
                DailyTask.task_date < today,
                DailyTask.status.in_([TaskStatus.AVAILABLE, TaskStatus.ACCEPTED])
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ==================== 写入方法 ====================

    async def add(self, task: DailyTask) -> DailyTask:
        """
        添加新任务

        Args:
            task: DailyTask实体对象

        Returns:
            添加后的DailyTask对象
        """
        self._session.add(task)
        await self._session.flush()
        return task

    async def update(self, task: DailyTask) -> DailyTask:
        """
        更新任务

        Args:
            task: DailyTask实体对象

        Returns:
            更新后的DailyTask对象
        """
        self._session.add(task)
        return task

    async def bulk_update_status(
        self,
        tasks: List[DailyTask],
        status: TaskStatus
    ) -> int:
        """
        批量更新任务状态

        Args:
            tasks: DailyTask列表
            status: 新状态

        Returns:
            更新的任务数量
        """
        for task in tasks:
            task.status = status
        return len(tasks)
