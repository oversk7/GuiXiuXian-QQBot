"""
餐厅仓库仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.restaurant import RestaurantStorage


class RestaurantStorageRepository(IRepository[RestaurantStorage]):
    """
    餐厅仓库仓储实现

    提供餐厅食材仓库的数据访问方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化餐厅仓库仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, storage_id: int) -> Optional[RestaurantStorage]:
        """
        根据ID获取仓库记录

        Args:
            storage_id: 仓库记录ID

        Returns:
            仓库记录对象,不存在则返回None
        """
        return await self._session.get(RestaurantStorage, storage_id)

    async def add(self, entity: RestaurantStorage) -> RestaurantStorage:
        """
        添加新仓库记录

        Args:
            entity: 仓库记录对象

        Returns:
            添加后的仓库记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: RestaurantStorage) -> RestaurantStorage:
        """
        更新仓库记录

        Args:
            entity: 仓库记录对象

        Returns:
            更新后的仓库记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: RestaurantStorage):
        """
        删除仓库记录

        Args:
            entity: 仓库记录对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, storage_id: int) -> bool:
        """
        检查仓库记录是否存在

        Args:
            storage_id: 仓库记录ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(storage_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计仓库记录总数

        Returns:
            仓库记录总数
        """
        result = await self._session.execute(
            select(func.count(RestaurantStorage.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_restaurant_and_item(
        self,
        restaurant_id: int,
        item_id: str
    ) -> Optional[RestaurantStorage]:
        """
        根据餐厅ID和物品ID获取仓库记录

        Args:
            restaurant_id: 餐厅ID
            item_id: 物品ID

        Returns:
            仓库记录对象,不存在则返回None
        """
        stmt = select(RestaurantStorage).where(
            RestaurantStorage.restaurant_id == restaurant_id,
            RestaurantStorage.item_id == item_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_restaurant(self, restaurant_id: int) -> List[RestaurantStorage]:
        """
        获取餐厅的所有仓库记录

        Args:
            restaurant_id: 餐厅ID

        Returns:
            仓库记录列表
        """
        stmt = select(RestaurantStorage).where(
            RestaurantStorage.restaurant_id == restaurant_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_total_quantity_by_restaurant(self, restaurant_id: int) -> int:
        """
        获取餐厅仓库的总物品数量

        Args:
            restaurant_id: 餐厅ID

        Returns:
            总数量
        """
        stmt = select(func.sum(RestaurantStorage.quantity)).where(
            RestaurantStorage.restaurant_id == restaurant_id
        )
        result = await self._session.execute(stmt)
        total = result.scalar_one_or_none()
        return total if total is not None else 0

    async def consume_ingredient(
        self,
        restaurant_id: int,
        item_id: str,
        quantity: int
    ) -> bool:
        """
        消耗食材(从仓库扣除)

        Args:
            restaurant_id: 餐厅ID
            item_id: 物品ID
            quantity: 消耗数量

        Returns:
            是否成功(库存不足返回False)
        """
        storage = await self.get_by_restaurant_and_item(restaurant_id, item_id)
        if not storage or storage.quantity < quantity:
            return False

        storage.quantity -= quantity
        if storage.quantity == 0:
            await self.delete(storage)
        else:
            await self.update(storage)

        return True
