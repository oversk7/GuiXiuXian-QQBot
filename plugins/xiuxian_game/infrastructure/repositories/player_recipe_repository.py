"""
玩家食谱仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..domain.repositories.base import IRepository
from ...models.player_recipe import PlayerRecipe


class PlayerRecipeRepository(IRepository[PlayerRecipe]):
    """
    玩家食谱仓储实现

    提供玩家食谱数据访问方法,支持按玩家ID查询已学会的食谱
    """

    def __init__(self, session: AsyncSession):
        """
        初始化玩家食谱仓储

        Args:
            session: 数据库会话(由UnitOfWork注入)
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, recipe_record_id: int) -> Optional[PlayerRecipe]:
        """
        根据ID获取食谱记录

        Args:
            recipe_record_id: 记录ID

        Returns:
            食谱记录对象,不存在则返回None
        """
        return await self._session.get(PlayerRecipe, recipe_record_id)

    async def add(self, entity: PlayerRecipe) -> PlayerRecipe:
        """
        添加新食谱记录

        Args:
            entity: 食谱记录对象

        Returns:
            添加后的食谱记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PlayerRecipe) -> PlayerRecipe:
        """
        更新食谱记录

        Args:
            entity: 食谱记录对象

        Returns:
            更新后的食谱记录对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PlayerRecipe):
        """
        删除食谱记录

        Args:
            entity: 食谱记录对象
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, recipe_record_id: int) -> bool:
        """
        检查食谱记录是否存在

        Args:
            recipe_record_id: 记录ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(recipe_record_id)
        return entity is not None

    async def count(self) -> int:
        """
        统计食谱记录总数

        Returns:
            食谱记录总数
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(PlayerRecipe.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_player_id(self, player_id: str) -> List[PlayerRecipe]:
        """
        根据玩家ID获取所有已学会的食谱

        Args:
            player_id: 玩家ID

        Returns:
            食谱记录列表
        """
        stmt = (
            select(PlayerRecipe)
            .where(PlayerRecipe.player_id == player_id)
            .order_by(PlayerRecipe.learned_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_recipe_ids_by_player(self, player_id: str) -> List[str]:
        """
        获取玩家已学会的所有食谱ID列表

        Args:
            player_id: 玩家ID

        Returns:
            食谱ID列表
        """
        stmt = (
            select(PlayerRecipe.recipe_id)
            .where(PlayerRecipe.player_id == player_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def has_recipe(self, player_id: str, recipe_id: str) -> bool:
        """
        检查玩家是否已学会指定食谱

        Args:
            player_id: 玩家ID
            recipe_id: 食谱ID

        Returns:
            是否已学会
        """
        stmt = select(PlayerRecipe).where(
            and_(
                PlayerRecipe.player_id == player_id,
                PlayerRecipe.recipe_id == recipe_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_player_and_recipe(
        self,
        player_id: str,
        recipe_id: str
    ) -> Optional[PlayerRecipe]:
        """
        根据玩家ID和食谱ID获取记录

        Args:
            player_id: 玩家ID
            recipe_id: 食谱ID

        Returns:
            食谱记录对象,不存在则返回None
        """
        stmt = select(PlayerRecipe).where(
            and_(
                PlayerRecipe.player_id == player_id,
                PlayerRecipe.recipe_id == recipe_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_player(self, player_id: str) -> int:
        """
        统计玩家已学会的食谱数量

        Args:
            player_id: 玩家ID

        Returns:
            食谱数量
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(PlayerRecipe.id)).where(PlayerRecipe.player_id == player_id)
        )
        return result.scalar_one()

    async def remove_recipe(self, player_id: str, recipe_id: str) -> bool:
        """
        移除玩家的指定食谱

        Args:
            player_id: 玩家ID
            recipe_id: 食谱ID

        Returns:
            是否成功移除
        """
        stmt = delete(PlayerRecipe).where(
            and_(
                PlayerRecipe.player_id == player_id,
                PlayerRecipe.recipe_id == recipe_id
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0
