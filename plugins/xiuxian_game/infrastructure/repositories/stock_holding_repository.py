"""
StockHoldingRepository - 股票持仓数据访问层

提供股票持仓相关的数据库操作，解决N+1查询问题
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ...models.stock import StockHolding, Stock
from ...domain.repositories.base import IRepository


class StockHoldingRepository(IRepository[StockHolding]):
    """股票持仓仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[StockHolding]:
        """根据ID获取持仓"""
        return await self._session.get(StockHolding, entity_id)

    async def add(self, entity: StockHolding) -> StockHolding:
        """添加持仓"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: StockHolding) -> StockHolding:
        """更新持仓"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: StockHolding):
        """删除持仓"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[StockHolding]:
        """列出所有持仓"""
        stmt = select(StockHolding)
        if filters.get("player_id"):
            stmt = stmt.where(StockHolding.player_id == filters["player_id"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计持仓数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(StockHolding)
        if filters.get("player_id"):
            stmt = stmt.where(StockHolding.player_id == filters["player_id"])
        result = await self._session.execute(stmt)
        return result.scalar()

    # ==================== 持仓特定方法 ====================

    async def get_by_player_and_stock(
        self, player_id: str, stock_id: int
    ) -> Optional[StockHolding]:
        """
        根据玩家ID和股票ID获取持仓

        Args:
            player_id: 玩家ID
            stock_id: 股票ID

        Returns:
            持仓对象，如果不存在则返回None
        """
        stmt = select(StockHolding).where(
            and_(
                StockHolding.player_id == player_id,
                StockHolding.stock_id == stock_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_player_holdings_with_stock(
        self, player_id: str
    ) -> List[StockHolding]:
        """
        获取玩家所有持仓并预加载股票信息（解决N+1查询）

        Args:
            player_id: 玩家ID

        Returns:
            持仓列表（已预加载Stock关联）
        """
        stmt = (
            select(StockHolding)
            .options(selectinload(StockHolding.stock))
            .where(StockHolding.player_id == player_id)
            .order_by(StockHolding.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_holding(self, holding: StockHolding) -> None:
        """
        删除持仓记录

        Args:
            holding: 持仓对象
        """
        await self._session.delete(holding)
        await self._session.flush()

    async def get_total_shares_by_player_and_stock(
        self, player_id: str, stock_id: int
    ) -> int:
        """
        获取玩家持有某股票的总股数

        Args:
            player_id: 玩家ID
            stock_id: 股票ID

        Returns:
            总股数，如果不存在返回0
        """
        holding = await self.get_by_player_and_stock(player_id, stock_id)
        return holding.shares if holding else 0
