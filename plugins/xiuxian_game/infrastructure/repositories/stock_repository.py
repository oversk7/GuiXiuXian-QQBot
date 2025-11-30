"""
StockRepository - 股票数据访问层

提供股票相关的数据库操作
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ...models.stock import Stock, StockPriceHistory
from ...domain.repositories.base import IRepository


class StockRepository(IRepository[Stock]):
    """股票仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[Stock]:
        """根据ID获取股票"""
        return await self._session.get(Stock, entity_id)

    async def add(self, entity: Stock) -> Stock:
        """添加股票"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: Stock) -> Stock:
        """更新股票"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: Stock):
        """删除股票"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[Stock]:
        """列出所有股票"""
        stmt = select(Stock)
        if filters.get("is_active") is not None:
            stmt = stmt.where(Stock.is_active == filters["is_active"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计股票数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(Stock)
        if filters.get("is_active") is not None:
            stmt = stmt.where(Stock.is_active == filters["is_active"])
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """
        检查股票是否存在

        Args:
            entity_id: 股票ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 股票特定方法 ====================

    async def get_by_symbol(self, symbol: str) -> Optional[Stock]:
        """
        根据股票代码获取股票

        Args:
            symbol: 股票代码

        Returns:
            股票对象，如果不存在则返回None
        """
        stmt = select(Stock).where(Stock.symbol == symbol)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_active_stocks(self) -> List[Stock]:
        """
        获取所有活跃股票

        Returns:
            活跃股票列表
        """
        stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_updated_stock(self) -> Optional[Stock]:
        """
        获取最近更新的股票（用于判断是否需要更新价格）

        Returns:
            最近更新的股票，如果没有则返回None
        """
        stmt = (
            select(Stock)
            .where(Stock.is_active == True)
            .order_by(Stock.updated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_all_active_with_price_history(
        self, days: int = 7
    ) -> List[tuple[Stock, List[StockPriceHistory]]]:
        """
        获取所有活跃股票及其价格历史（解决N+1查询）

        Args:
            days: 查询最近N天的价格历史

        Returns:
            (Stock, List[StockPriceHistory])元组列表
        """
        # 查询活跃股票
        stock_stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
        stock_result = await self._session.execute(stock_stmt)
        stocks = list(stock_result.scalars().all())

        if not stocks:
            return []

        # 批量查询价格历史
        stock_ids = [stock.id for stock in stocks]
        cutoff_date = datetime.now() - timedelta(days=days)

        history_stmt = (
            select(StockPriceHistory)
            .where(
                and_(
                    StockPriceHistory.stock_id.in_(stock_ids),
                    StockPriceHistory.recorded_at >= cutoff_date
                )
            )
            .order_by(StockPriceHistory.stock_id, StockPriceHistory.recorded_at.desc())
        )
        history_result = await self._session.execute(history_stmt)
        histories = list(history_result.scalars().all())

        # 按stock_id分组
        history_map = {}
        for history in histories:
            if history.stock_id not in history_map:
                history_map[history.stock_id] = []
            history_map[history.stock_id].append(history)

        # 组合结果
        return [(stock, history_map.get(stock.id, [])) for stock in stocks]

    async def update_prices_batch(self, stocks: List[Stock]) -> None:
        """
        批量更新股票价格

        Args:
            stocks: 股票列表
        """
        for stock in stocks:
            self._session.add(stock)
        await self._session.flush()
