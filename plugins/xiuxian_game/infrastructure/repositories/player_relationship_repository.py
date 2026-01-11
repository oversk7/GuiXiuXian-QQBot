"""
玩家关系仓储实现

提供玩家间关系数据的CRUD操作和领域查询
"""
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from ...domain.repositories.base import IRepository
from ...models.player_relationship import PlayerRelationship, RelationshipType


class PlayerRelationshipRepository(IRepository[PlayerRelationship]):
    """
    玩家关系仓储

    提供玩家间关系数据访问层,包括:
    - 标准CRUD操作
    - 获取双向关系(自动排序ID确保唯一性)
    - 查询今日好感度增益
    - 按关系类型查询
    """

    def __init__(self, session: AsyncSession):
        """
        初始化仓储

        Args:
            session: SQLAlchemy异步会话
        """
        super().__init__(session)
        self._session = session

    async def get_by_id(self, relationship_id: int) -> Optional[PlayerRelationship]:
        """
        根据ID获取关系记录

        Args:
            relationship_id: 关系记录ID

        Returns:
            关系记录,不存在则返回None
        """
        result = await self._session.execute(
            select(PlayerRelationship).where(PlayerRelationship.id == relationship_id)
        )
        return result.scalar_one_or_none()

    async def add(self, relationship: PlayerRelationship) -> None:
        """
        添加新的关系记录

        Args:
            relationship: 关系实体
        """
        self._session.add(relationship)

    async def update(self, relationship: PlayerRelationship) -> None:
        """
        更新关系记录

        Args:
            relationship: 关系实体
        """
        # SQLAlchemy会自动跟踪修改,无需显式操作
        pass

    async def delete(self, relationship_id: int) -> None:
        """
        删除关系记录

        Args:
            relationship_id: 关系记录ID
        """
        relationship = await self.get_by_id(relationship_id)
        if relationship:
            await self._session.delete(relationship)

    async def exists(self, relationship_id: int) -> bool:
        """
        检查关系记录是否存在

        Args:
            relationship_id: 关系记录ID

        Returns:
            存在返回True,否则返回False
        """
        result = await self._session.execute(
            select(func.count(PlayerRelationship.id)).where(PlayerRelationship.id == relationship_id)
        )
        return result.scalar() > 0

    async def count(self) -> int:
        """
        获取关系记录总数

        Returns:
            总记录数
        """
        result = await self._session.execute(
            select(func.count(PlayerRelationship.id))
        )
        return result.scalar()

    # ==================== 领域查询方法 ====================

    async def get_relationship(
        self,
        player_id: str,
        target_id: str
    ) -> Optional[PlayerRelationship]:
        """
        获取两个玩家之间的关系(双向)

        设计要点:
        - 通过排序player_id和target_id确保唯一性
        - 无论传入(player_a, player_b)还是(player_b, player_a)都返回同一记录

        Args:
            player_id: 玩家A的ID
            target_id: 玩家B的ID

        Returns:
            关系记录,不存在则返回None
        """
        # 排序确保双向查询返回同一记录
        sorted_ids = sorted([player_id, target_id])
        p1, p2 = sorted_ids[0], sorted_ids[1]

        result = await self._session.execute(
            select(PlayerRelationship).where(
                and_(
                    PlayerRelationship.player_id == p1,
                    PlayerRelationship.target_id == p2
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_relationship(
        self,
        player_id: str,
        target_id: str
    ) -> PlayerRelationship:
        """
        获取或创建两个玩家之间的关系

        Args:
            player_id: 玩家A的ID
            target_id: 玩家B的ID

        Returns:
            关系记录(已存在则返回,不存在则创建)
        """
        relationship = await self.get_relationship(player_id, target_id)

        if relationship is None:
            # 排序确保唯一性
            sorted_ids = sorted([player_id, target_id])

            relationship = PlayerRelationship(
                player_id=sorted_ids[0],
                target_id=sorted_ids[1],
                favorability=0,
                today_favorability_gain=0,
                total_gifts=0,
                relationship_type=RelationshipType.NONE.value
            )
            self._session.add(relationship)
            # 刷新以获取生成的ID
            await self._session.flush()

        return relationship

    async def get_players_by_relationship_type(
        self,
        player_id: str,
        relationship_type: RelationshipType
    ) -> List[PlayerRelationship]:
        """
        获取玩家指定类型的所有关系

        Args:
            player_id: 玩家ID
            relationship_type: 关系类型

        Returns:
            关系列表
        """
        result = await self._session.execute(
            select(PlayerRelationship).where(
                and_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.relationship_type == relationship_type.value
                )
            )
        )
        return list(result.scalars().all())

    async def update_favorability(
        self,
        player_id: str,
        target_id: str,
        delta: int,
        max_favorability: int = 100
    ) -> Optional[PlayerRelationship]:
        """
        更新两个玩家的好感度

        Args:
            player_id: 玩家A的ID
            target_id: 玩家B的ID
            delta: 好感度变化量
            max_favorability: 最大好感度值(默认100)

        Returns:
            更新后的关系记录,关系不存在则返回None
        """
        relationship = await self.get_relationship(player_id, target_id)

        if relationship:
            # 限制在0-100范围内
            relationship.favorability = max(0, min(max_favorability, relationship.favorability + delta))
            relationship.last_interaction_date = func.now()

        return relationship

    async def get_top_by_favorability(
        self,
        limit: int = 100
    ) -> List[PlayerRelationship]:
        """
        获取好感度最高的关系列表

        Args:
            limit: 返回记录数

        Returns:
            关系列表(按好感度降序)
        """
        result = await self._session.execute(
            select(PlayerRelationship)
            .order_by(PlayerRelationship.favorability.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def reset_daily_gift_limit(
        self,
        player_id: str,
        target_id: str
    ) -> None:
        """
        重置两个玩家之间的每日送礼限制

        Args:
            player_id: 玩家A的ID
            target_id: 玩家B的ID
        """
        relationship = await self.get_relationship(player_id, target_id)

        if relationship:
            relationship.today_favorability_gain = 0
            relationship.last_gift_date = None
