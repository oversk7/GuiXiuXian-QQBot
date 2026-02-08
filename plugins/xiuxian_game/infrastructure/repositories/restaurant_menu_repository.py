"""
餐厅菜单仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..domain.repositories.base import IRepository
from ...models.restaurant import RestaurantMenu


class RestaurantMenuRepository(IRepository[RestaurantMenu]):
    """
    餐厅菜单仓储实现

    提供餐厅营业菜单的数据访问方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化餐厅菜单仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, menu_id: int) -> Optional[RestaurantMenu]:
        """
        根据ID获取菜单记录

        Args:
            menu_id: 菜单记录ID

        Returns:
            菜单记录对象,不存在则返回None
        """
        return await self._session.get(RestaurantMenu, menu_id)

    async def add(self, entity: RestaurantMenu) -> RestaurantMenu:
        """
        添加新菜单记录

        Args:
            entity: 菜单记录对象

        Returns:
            添加后的菜单记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: RestaurantMenu) -> RestaurantMenu:
        """
        更新菜单记录

        Args:
            entity: 菜单记录对象

        Returns:
            更新后的菜单记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: RestaurantMenu):
        """
        删除菜单记录

        Args:
            entity: 菜单记录对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, menu_id: int) -> bool:
        """
        检查菜单记录是否存在

        Args:
            menu_id: 菜单记录ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(menu_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计菜单记录总数

        Returns:
            菜单记录总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(RestaurantMenu.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_restaurant(self, restaurant_id: int) -> List[RestaurantMenu]:
        """
        获取餐厅的所有菜单(包括未激活的)

        Args:
            restaurant_id: 餐厅ID

        Returns:
            菜单记录列表
        """
        stmt = select(RestaurantMenu).where(
            RestaurantMenu.restaurant_id == restaurant_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_active_menu(self, restaurant_id: int) -> List[RestaurantMenu]:
        """
        获取餐厅的当前激活菜单

        Args:
            restaurant_id: 餐厅ID

        Returns:
            激活的菜单记录列表
        """
        stmt = select(RestaurantMenu).where(
            RestaurantMenu.restaurant_id == restaurant_id,
            RestaurantMenu.is_active == True
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def clear_menu(self, restaurant_id: int):
        """
        清除餐厅的所有菜单

        Args:
            restaurant_id: 餐厅ID
        """
        stmt = sql_delete(RestaurantMenu).where(
            RestaurantMenu.restaurant_id == restaurant_id
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def deactivate_all(self, restaurant_id: int):
        """
        停用餐厅的所有菜单(设置is_active=False)

        Args:
            restaurant_id: 餐厅ID
        """
        menus = await self.get_by_restaurant(restaurant_id)
        for menu in menus:
            menu.is_active = False
            await self.update(menu)
