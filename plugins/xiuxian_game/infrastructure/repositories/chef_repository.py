"""
厨师仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from ..domain.repositories.base import IRepository
from ...models.chef import Chef, ChefCandidate


class ChefRepository(IRepository[Chef]):
    """
    厨师仓储实现

    提供厨师数据访问方法,支持按餐厅ID查询厨师
    """

    def __init__(self, session: AsyncSession):
        """
        初始化厨师仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, chef_id: int) -> Optional[Chef]:
        """
        根据ID获取厨师

        Args:
            chef_id: 厨师ID

        Returns:
            厨师对象,不存在则返回None
        """
        return await self._session.get(Chef, chef_id)

    async def add(self, entity: Chef) -> Chef:
        """
        添加新厨师

        Args:
            entity: 厨师对象

        Returns:
            添加后的厨师对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: Chef) -> Chef:
        """
        更新厨师

        Args:
            entity: 厨师对象

        Returns:
            更新后的厨师对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: Chef):
        """
        删除厨师

        Args:
            entity: 厨师对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, chef_id: int) -> bool:
        """
        检查厨师是否存在

        Args:
            chef_id: 厨师ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(chef_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计厨师总数

        Returns:
            厨师总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(Chef.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_restaurant_id(self, restaurant_id: int) -> List[Chef]:
        """
        根据餐厅ID获取所有厨师

        Args:
            restaurant_id: 餐厅ID

        Returns:
            厨师列表
        """
        stmt = select(Chef).where(Chef.restaurant_id == restaurant_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_name(self, restaurant_id: int, name: str) -> Optional[Chef]:
        """
        根据餐厅ID和名字获取厨师

        Args:
            restaurant_id: 餐厅ID
            name: 厨师名字

        Returns:
            厨师对象,不存在则返回None
        """
        stmt = select(Chef).where(
            and_(
                Chef.restaurant_id == restaurant_id,
                Chef.name == name
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_restaurant(self, restaurant_id: int) -> int:
        """
        统计餐厅的厨师数量

        Args:
            restaurant_id: 餐厅ID

        Returns:
            厨师数量
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(Chef.id)).where(Chef.restaurant_id == restaurant_id)
        )
        return result.scalar_one()


class ChefCandidateRepository(IRepository[ChefCandidate]):
    """
    厨师候选仓储实现

    提供厨师候选数据访问方法,支持按玩家ID查询和清理过期候选
    """

    def __init__(self, session: AsyncSession):
        """
        初始化厨师候选仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, candidate_id: int) -> Optional[ChefCandidate]:
        """
        根据ID获取厨师候选

        Args:
            candidate_id: 候选ID

        Returns:
            候选对象,不存在则返回None
        """
        return await self._session.get(ChefCandidate, candidate_id)

    async def add(self, entity: ChefCandidate) -> ChefCandidate:
        """
        添加新候选

        Args:
            entity: 候选对象

        Returns:
            添加后的候选对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: ChefCandidate) -> ChefCandidate:
        """
        更新候选

        Args:
            entity: 候选对象

        Returns:
            更新后的候选对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: ChefCandidate):
        """
        删除候选

        Args:
            entity: 候选对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, candidate_id: int) -> bool:
        """
        检查候选是否存在

        Args:
            candidate_id: 候选ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(candidate_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计候选总数

        Returns:
            候选总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(ChefCandidate.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_player_id(self, player_id: str) -> List[ChefCandidate]:
        """
        根据玩家ID获取所有候选

        Args:
            player_id: 玩家ID

        Returns:
            候选列表
        """
        stmt = select(ChefCandidate).where(ChefCandidate.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def clear_by_player(self, player_id: str) -> int:
        """
        清除玩家的所有候选

        Args:
            player_id: 玩家ID

        Returns:
            删除的记录数
        """
        stmt = delete(ChefCandidate).where(ChefCandidate.player_id == player_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def clear_expired(self, hours: int = 24) -> int:
        """
        清除过期的候选(超过指定小时数)

        Args:
            hours: 过期时间(小时)

        Returns:
            删除的记录数
        """
        expire_time = datetime.now() - timedelta(hours=hours)
        stmt = delete(ChefCandidate).where(ChefCandidate.created_at < expire_time)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
