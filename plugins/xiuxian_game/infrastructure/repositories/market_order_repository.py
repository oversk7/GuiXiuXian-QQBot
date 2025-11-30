"""
市场订单仓储

提供MarketOrder实体的数据访问层，支持：
1. 订单ID查询
2. 装备实例关联查询
3. 订单状态管理
"""

from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.market_order import MarketOrder


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

    async def update(self, order: MarketOrder) -> None:
        """
        更新订单信息

        Args:
            order: 订单实体
        """
        self._session.add(order)
        await self._session.flush()

    async def delete(self, order: MarketOrder) -> None:
        """
        删除订单

        Args:
            order: 订单实体
        """
        await self._session.delete(order)
        await self._session.flush()
