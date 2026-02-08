"""
餐厅仓储实现
"""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.restaurant import Restaurant


class RestaurantRepository(IRepository[Restaurant]):
    """
    餐厅仓储实现

    提供餐厅数据访问方法,支持按玩家ID查询餐厅
    """

    def __init__(self, session: AsyncSession):
        """
        初始化餐厅仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, restaurant_id: int) -> Optional[Restaurant]:
        """
        根据ID获取餐厅

        Args:
            restaurant_id: 餐厅ID

        Returns:
            餐厅对象,不存在则返回None
        """
        return await self._session.get(Restaurant, restaurant_id)

    async def add(self, entity: Restaurant) -> Restaurant:
        """
        添加新餐厅

        Args:
            entity: 餐厅对象

        Returns:
            添加后的餐厅对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: Restaurant) -> Restaurant:
        """
        更新餐厅

        Args:
            entity: 餐厅对象

        Returns:
            更新后的餐厅对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: Restaurant):
        """
        删除餐厅

        Args:
            entity: 餐厅对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, restaurant_id: int) -> bool:
        """
        检查餐厅是否存在

        Args:
            restaurant_id: 餐厅ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(restaurant_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计餐厅总数

        Returns:
            餐厅总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(Restaurant.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_player_id(self, player_id: str) -> Optional[Restaurant]:
        """
        根据玩家ID获取餐厅

        Args:
            player_id: 玩家ID

        Returns:
            餐厅对象,不存在则返回None
        """
        stmt = select(Restaurant).where(Restaurant.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_open_restaurants(self) -> List[Restaurant]:
        """
        获取所有营业中的餐厅

        Returns:
            营业中的餐厅列表
        """
        stmt = select(Restaurant).where(Restaurant.is_open == True)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_top_by_reputation(self, limit: int = 10) -> List[Restaurant]:
        """
        获取声望排行榜

        Args:
            limit: 返回数量限制

        Returns:
            按声望排序的餐厅列表
        """
        stmt = (
            select(Restaurant)
            .order_by(Restaurant.reputation.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
