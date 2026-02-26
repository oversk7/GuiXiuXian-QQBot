"""
恶魔轮盘 PvE 人机模式游戏仓储

提供 RussianRoulettePvEGame 实体的数据访问层，支持：
1. 玩家活跃游戏查询
2. 标准 CRUD 操作
"""

from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.russian_roulette import RussianRoulettePvEGame


class RussianRoulettePvERepository(IRepository[RussianRoulettePvEGame]):
    """恶魔轮盘 PvE 人机模式游戏仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ==================== 基础查询 ====================

    async def get_by_id(self, entity_id: int) -> Optional[RussianRoulettePvEGame]:
        """根据主键ID查询游戏"""
        return await self._session.get(RussianRoulettePvEGame, entity_id)

    # ==================== 业务查询 ====================

    async def find_active_by_player_id(self, player_id: str) -> Optional[RussianRoulettePvEGame]:
        """
        查询玩家的活跃 PvE 游戏（playing 或 won 状态）

        Args:
            player_id: 玩家ID

        Returns:
            活跃游戏实体，不存在返回 None
        """
        stmt = select(RussianRoulettePvEGame).where(
            RussianRoulettePvEGame.player_id == player_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== CRUD 操作 ====================

    async def add(self, entity: RussianRoulettePvEGame) -> RussianRoulettePvEGame:
        """创建新 PvE 游戏"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: RussianRoulettePvEGame) -> RussianRoulettePvEGame:
        """更新 PvE 游戏状态"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: int) -> bool:
        """删除 PvE 游戏记录"""
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        return False

    async def delete_entity(self, entity: RussianRoulettePvEGame) -> None:
        """直接删除已加载的实体（避免额外查询）"""
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, entity_id: int) -> bool:
        """检查游戏是否存在"""
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        """获取游戏总数"""
        stmt = select(func.count()).select_from(RussianRoulettePvEGame)
        result = await self._session.execute(stmt)
        return result.scalar()
