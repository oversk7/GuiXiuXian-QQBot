"""
市场订单仓储

提供MarketOrder实体的数据访问层，支持：
1. 订单ID查询
2. 装备实例关联查询
3. 订单状态管理
"""

from dataclasses import dataclass
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.market_order import MarketOrder, OrderSide
from ..locking import lock_row, lock_rows


@dataclass(frozen=True)
class MatchingCandidate:
    id: int
    player_id: str
    quantity: int


class MarketOrderRepository(IRepository[MarketOrder]):
    """市场订单仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化市场订单仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础查询 ====================

    async def find_by_id(self, order_id: int) -> Optional[MarketOrder]:
        """
        通过主键ID查询订单

        Args:
            order_id: 订单主键ID

        Returns:
            订单实体，不存在返回None
        """
        return await self._session.get(MarketOrder, order_id)

    async def get_by_id(self, entity_id: int) -> Optional[MarketOrder]:
        """get_by_id别名，调用find_by_id以符合IRepository接口"""
        return await self.find_by_id(entity_id)

    async def lock_by_id(self, order_id: int) -> Optional[MarketOrder]:
        return await lock_row(self._session, MarketOrder, order_id)

    @staticmethod
    def matching_conditions(order: MarketOrder, same_price_only: bool):
        opposite = OrderSide.SELL if order.side == OrderSide.BUY else OrderSide.BUY
        price = MarketOrder.price == order.price
        if not same_price_only:
            price = (MarketOrder.price <= order.price) if order.side == OrderSide.BUY else (MarketOrder.price >= order.price)
        return (
            MarketOrder.item_id == order.item_id,
            MarketOrder.side == opposite,
            MarketOrder.server_id == order.server_id,
            MarketOrder.quantity > 0,
            price,
        )

    async def matching_candidates(self, order: MarketOrder, same_price_only: bool):
        # 快照只用于确定锁集合；数量和有效性以随后锁定的当前行为准。
        price_order = MarketOrder.price.asc() if order.side == OrderSide.BUY else MarketOrder.price.desc()
        with self._session.no_autoflush:
            result = await self._session.execute(
                select(MarketOrder.id, MarketOrder.player_id, MarketOrder.quantity).where(
                    *self.matching_conditions(order, same_price_only)
                ).order_by(price_order, MarketOrder.created_at, MarketOrder.id)
            )
        return [MatchingCandidate(*row) for row in result.all()]

    async def lock_candidates(self, order: MarketOrder, candidates, same_price_only: bool):
        owners = {candidate.id: candidate.player_id for candidate in candidates}
        orders = await lock_rows(self._session, MarketOrder, owners)
        valid = [
            other for other in orders
            if other.player_id == owners[other.id]
            and other.server_id == order.server_id
            and other.item_id == order.item_id
            and other.side != order.side
            and other.quantity > 0
            and (
                other.price == order.price if same_price_only else
                other.price <= order.price if order.side == OrderSide.BUY else
                other.price >= order.price
            )
        ]
        return sorted(valid, key=lambda other: (
            other.price if order.side == OrderSide.BUY else -other.price,
            other.created_at, other.id,
        ))

    # ==================== 装备实例关联查询 ====================

    async def find_by_equipment_instance(self, instance_id: int) -> Optional[MarketOrder]:
        """
        通过装备实例ID查询关联的市场订单

        用于检查装备是否已在交易中

        Args:
            instance_id: 装备实例ID

        Returns:
            关联的订单，不存在返回None
        """
        stmt = select(MarketOrder).where(
            and_(
                MarketOrder.item_instance_id == instance_id,
                MarketOrder.is_instance_trade == True
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def exists_by_equipment_instance(self, instance_id: int) -> bool:
        """
        检查装备实例是否存在关联的市场订单

        Args:
            instance_id: 装备实例ID

        Returns:
            True表示存在关联订单，False表示不存在
        """
        order = await self.find_by_equipment_instance(instance_id)
        return order is not None

    # ==================== CRUD操作 ====================

    async def create(self, order: MarketOrder) -> MarketOrder:
        """
        创建新订单

        Args:
            order: 订单实体

        Returns:
            创建后的订单实体（包含生成的ID）
        """
        self._session.add(order)
        await self._session.flush()  # 刷新以获取生成的ID
        return order

    async def add(self, entity: MarketOrder) -> MarketOrder:
        """add别名，调用create以符合IRepository接口"""
        return await self.create(entity)

    async def update(self, order: MarketOrder) -> MarketOrder:
        """
        更新订单信息

        Args:
            order: 订单实体

        Returns:
            更新后的订单实体
        """
        self._session.add(order)
        await self._session.flush()
        return order

    async def delete(self, entity_id: int) -> bool:
        """
        删除订单

        Args:
            entity_id: 订单ID

        Returns:
            是否删除成功
        """
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        return False

    async def exists(self, entity_id: int) -> bool:
        """
        检查订单是否存在

        Args:
            entity_id: 订单ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        """
        获取订单总数

        Returns:
            订单数量
        """
        from sqlalchemy import func
        stmt = select(func.count()).select_from(MarketOrder)
        result = await self._session.execute(stmt)
        return result.scalar()
