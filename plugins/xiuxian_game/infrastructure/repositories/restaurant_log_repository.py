"""
餐厅日志仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from ...domain.repositories.base import IRepository
from ...models.restaurant_log import RestaurantLog


class RestaurantLogRepository(IRepository[RestaurantLog]):
    """
    餐厅日志仓储实现

    提供餐厅日志数据访问方法,支持按餐厅ID和时间范围查询
    """

    def __init__(self, session: AsyncSession):
        """
        初始化餐厅日志仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, log_id: int) -> Optional[RestaurantLog]:
        """
        根据ID获取日志

        Args:
            log_id: 日志ID

        Returns:
            日志对象,不存在则返回None
        """
        return await self._session.get(RestaurantLog, log_id)

    async def add(self, entity: RestaurantLog) -> RestaurantLog:
        """
        添加新日志

        Args:
            entity: 日志对象

        Returns:
            添加后的日志对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: RestaurantLog) -> RestaurantLog:
        """
        更新日志

        Args:
            entity: 日志对象

        Returns:
            更新后的日志对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: RestaurantLog):
        """
        删除日志

        Args:
            entity: 日志对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, log_id: int) -> bool:
        """
        检查日志是否存在

        Args:
            log_id: 日志ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(log_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计日志总数

        Returns:
            日志总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(RestaurantLog.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_restaurant_id(
        self,
        restaurant_id: int,
        limit: int = 24
    ) -> List[RestaurantLog]:
        """
        根据餐厅ID获取最近的日志

        Args:
            restaurant_id: 餐厅ID
            limit: 返回数量限制(默认24小时)

        Returns:
            日志列表(按时间倒序)
        """
        stmt = (
            select(RestaurantLog)
            .where(RestaurantLog.restaurant_id == restaurant_id)
            .order_by(RestaurantLog.period_start.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_time_range(
        self,
        restaurant_id: int,
        start_time: datetime,
        end_time: datetime
    ) -> List[RestaurantLog]:
        """
        根据时间范围获取日志

        Args:
            restaurant_id: 餐厅ID
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            日志列表
        """
        stmt = (
            select(RestaurantLog)
            .where(
                and_(
                    RestaurantLog.restaurant_id == restaurant_id,
                    RestaurantLog.period_start >= start_time,
                    RestaurantLog.period_end <= end_time
                )
            )
            .order_by(RestaurantLog.period_start.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_recent_stats(
        self,
        restaurant_id: int,
        hours: int = 24
    ) -> dict:
        """
        获取最近N小时的统计数据

        Args:
            restaurant_id: 餐厅ID
            hours: 小时数

        Returns:
            统计数据字典
        """
        from sqlalchemy import func
        start_time = datetime.now() - timedelta(hours=hours)

        stmt = (
            select(
                func.sum(RestaurantLog.income).label("total_income"),
                func.sum(RestaurantLog.expense).label("total_expense"),
                func.sum(RestaurantLog.customers).label("total_customers"),
                func.sum(RestaurantLog.dishes_made).label("total_dishes_made"),
                func.sum(RestaurantLog.dishes_failed).label("total_dishes_failed"),
                func.sum(RestaurantLog.reputation_change).label("total_reputation_change")
            )
            .where(
                and_(
                    RestaurantLog.restaurant_id == restaurant_id,
                    RestaurantLog.period_start >= start_time
                )
            )
        )
        result = await self._session.execute(stmt)
        row = result.one()

        return {
            "total_income": row.total_income or 0,
            "total_expense": row.total_expense or 0,
            "total_customers": row.total_customers or 0,
            "total_dishes_made": row.total_dishes_made or 0,
            "total_dishes_failed": row.total_dishes_failed or 0,
            "total_reputation_change": row.total_reputation_change or 0,
            "net_profit": (row.total_income or 0) - (row.total_expense or 0)
        }

    async def clear_old_logs(self, days: int = 7) -> int:
        """
        清理超过指定天数的旧日志

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        expire_time = datetime.now() - timedelta(days=days)
        stmt = delete(RestaurantLog).where(RestaurantLog.created_at < expire_time)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
