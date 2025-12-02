"""
StockEventRepository - 股票事件数据访问层

提供黑天鹅事件相关的数据库操作
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from ...models.stock import StockEvent, Stock
from ...domain.repositories.base import IRepository


class StockEventRepository(IRepository[StockEvent]):
    """股票事件仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """返回session供Service使用"""
        return self._session

    async def get_by_id(self, entity_id: int) -> Optional[StockEvent]:
        """根据ID获取事件"""
        return await self._session.get(StockEvent, entity_id)

    async def add(self, entity: StockEvent) -> StockEvent:
        """添加事件"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: StockEvent) -> StockEvent:
        """更新事件"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: StockEvent):
        """删除事件"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[StockEvent]:
        """列出所有事件"""
        stmt = select(StockEvent)
        if filters.get("is_active") is not None:
            stmt = stmt.where(StockEvent.is_active == filters["is_active"])
        if filters.get("affected_stock_id"):
            stmt = stmt.where(StockEvent.affected_stock_id == filters["affected_stock_id"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_events(self, limit: int = 10) -> List[StockEvent]:
        """获取最近的事件"""
        stmt = (
            select(StockEvent)
            .options(selectinload(StockEvent.stock))
            .order_by(desc(StockEvent.trigger_date))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_events_by_stock(self, stock_id: int, limit: int = 5) -> List[StockEvent]:
        """获取指定股票的历史事件"""
        stmt = (
            select(StockEvent)
            .where(StockEvent.affected_stock_id == stock_id)
            .order_by(desc(StockEvent.trigger_date))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
