"""NPC好感度仓储实现"""
from typing import Optional, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.npc_favorability import NPCFavorability


class NPCFavorabilityRepository(IRepository[NPCFavorability]):
    """NPC好感度仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, favorability_id: int) -> Optional[NPCFavorability]:
        """按ID查询好感度记录"""
        stmt = select(NPCFavorability).where(NPCFavorability.id == favorability_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_npc_and_player(
        self,
        npc_id: int,
        player_id: str
    ) -> Optional[NPCFavorability]:
        """
        获取特定NPC与玩家的好感度记录

        Args:
            npc_id: NPC ID
            player_id: 玩家ID

        Returns:
            好感度记录，不存在返回None
        """
        stmt = select(NPCFavorability).where(
            and_(
                NPCFavorability.npc_id == npc_id,
                NPCFavorability.player_id == player_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        npc_id: int,
        player_id: str,
        initial_favorability: int = 50
    ) -> NPCFavorability:
        """
        获取或创建好感度记录

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            initial_favorability: 初始好感度，默认50

        Returns:
            好感度记录
        """
        record = await self.get_by_npc_and_player(npc_id, player_id)
        if record is None:
            record = NPCFavorability(
                npc_id=npc_id,
                player_id=player_id,
                current_favorability=initial_favorability
            )
            self._session.add(record)
            await self._session.flush()
        return record

    async def save(self, favorability: NPCFavorability) -> NPCFavorability:
        """保存好感度记录"""
        self._session.add(favorability)
        await self._session.flush()
        return favorability

    async def get_player_favorabilities(
        self,
        player_id: str,
        min_favorability: int = None
    ) -> List[NPCFavorability]:
        """
        获取玩家与所有NPC的好感度记录

        Args:
            player_id: 玩家ID
            min_favorability: 可选，最小好感度筛选

        Returns:
            好感度记录列表（按好感度降序）
        """
        stmt = select(NPCFavorability).where(
            NPCFavorability.player_id == player_id
        )

        if min_favorability is not None:
            stmt = stmt.where(NPCFavorability.current_favorability >= min_favorability)

        stmt = stmt.order_by(desc(NPCFavorability.current_favorability))

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_npc_favorabilities(
        self,
        npc_id: int,
        min_favorability: int = None
    ) -> List[NPCFavorability]:
        """
        获取NPC与所有玩家的好感度记录

        Args:
            npc_id: NPC ID
            min_favorability: 可选，最小好感度筛选

        Returns:
            好感度记录列表（按好感度降序）
        """
        stmt = select(NPCFavorability).where(
            NPCFavorability.npc_id == npc_id
        )

        if min_favorability is not None:
            stmt = stmt.where(NPCFavorability.current_favorability >= min_favorability)

        stmt = stmt.order_by(desc(NPCFavorability.current_favorability))

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_relationship_level(self, favorability: NPCFavorability):
        """更新关系等级（基于当前好感度）"""
        favorability.relationship_level = favorability.get_relationship_level()
        await self._session.flush()

    async def get_followers(self, player_id: str) -> List[NPCFavorability]:
        """获取跟随玩家的NPC列表"""
        stmt = select(NPCFavorability).where(
            and_(
                NPCFavorability.player_id == player_id,
                NPCFavorability.is_follower == True
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
