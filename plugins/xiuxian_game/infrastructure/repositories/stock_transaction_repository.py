"""
StockTransactionRepository - 股票交易记录数据访问层

提供股票交易记录相关的数据库操作
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...models.stock import StockTransaction
from ...domain.repositories.base import IRepository


class StockTransactionRepository(IRepository[StockTransaction]):
    """股票交易记录仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[StockTransaction]:
        """根据ID获取交易记录"""
        return await self._session.get(StockTransaction, entity_id)

    async def add(self, entity: StockTransaction) -> StockTransaction:
        """添加交易记录"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: StockTransaction) -> StockTransaction:
        """更新交易记录（通常不需要更新历史交易记录）"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: StockTransaction):
        """删除交易记录（通常不删除历史记录）"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[StockTransaction]:
        """列出所有交易记录"""
        stmt = select(StockTransaction)
        if filters.get("player_id"):
            stmt = stmt.where(StockTransaction.player_id == filters["player_id"])
        if filters.get("stock_id"):
            stmt = stmt.where(StockTransaction.stock_id == filters["stock_id"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计交易记录数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(StockTransaction)
        if filters.get("player_id"):
            stmt = stmt.where(StockTransaction.player_id == filters["player_id"])
        if filters.get("stock_id"):
            stmt = stmt.where(StockTransaction.stock_id == filters["stock_id"])
        result = await self._session.execute(stmt)
        return result.scalar()

    # ==================== 交易记录特定方法 ====================

    async def get_player_transactions_with_stock(
        self, player_id: str, limit: int = 20
    ) -> List[StockTransaction]:
        """
        获取玩家交易记录并预加载股票信息（解决N+1查询）

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            交易记录列表（已预加载Stock关联）
        """
        stmt = (
            select(StockTransaction)
            .options(selectinload(StockTransaction.stock))
            .where(StockTransaction.player_id == player_id)
            .order_by(StockTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stock_transactions_with_players(
        self, stock_id: int, limit: int = 50
    ) -> List[StockTransaction]:
        """
        获取某股票的交易记录并预加载玩家信息

        Args:
            stock_id: 股票ID
            limit: 返回记录数量限制

        Returns:
            交易记录列表（已预加载Player关联）
        """
        stmt = (
            select(StockTransaction)
            .options(selectinload(StockTransaction.player))
            .where(StockTransaction.stock_id == stock_id)
            .order_by(StockTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_transaction(
        self,
        player_id: str,
        stock_id: int,
        transaction_type: str,
        shares: int,
        price: int,
        total_amount: int,
        commission: int = 0
    ) -> StockTransaction:
        """
        创建交易记录

        Args:
            player_id: 玩家ID
            stock_id: 股票ID
            transaction_type: 交易类型（BUY/SELL）
            shares: 交易股数
            price: 交易价格（金币/股）
            total_amount: 交易总金额（金币）
            commission: 手续费（金币）

        Returns:
            创建的交易记录
        """
        transaction = StockTransaction(
            player_id=player_id,
            stock_id=stock_id,
            transaction_type=transaction_type,
            shares=shares,
            price=price,
            total_amount=total_amount,
            commission=commission
        )
        return await self.add(transaction)
