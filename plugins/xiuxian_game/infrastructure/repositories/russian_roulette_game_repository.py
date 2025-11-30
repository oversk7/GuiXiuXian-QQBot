"""
俄罗斯轮盘游戏状态仓储

提供RussianRouletteGame实体的数据访问层，支持：
1. 游戏ID查询
2. 房间ID关联查询
3. 活跃游戏查询
4. CRUD操作
"""

from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.repositories.base import IRepository
from ...models.russian_roulette import RussianRouletteGame, GameStatus


class RussianRouletteGameRepository(IRepository[RussianRouletteGame]):
    """俄罗斯轮盘游戏状态仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化游戏仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础查询 ====================

    async def find_by_id(self, id: int) -> Optional[RussianRouletteGame]:
        """
        通过主键ID查询游戏

        Args:
            id: 游戏主键ID

        Returns:
            游戏实体，不存在返回None
        """
        return await self._session.get(RussianRouletteGame, id)

    # ==================== 业务查询 ====================

    async def find_by_room_id(
        self,
        room_id: str,
        status: Optional[List[str]] = None
    ) -> Optional[RussianRouletteGame]:
        """
        通过房间ID查询游戏，可选状态过滤

        Args:
            room_id: 房间ID
            status: 游戏状态列表（可选），如[GameStatus.PLAYING.value]

        Returns:
            符合条件的游戏，不存在返回None
        """
        conditions = [RussianRouletteGame.room_id == room_id]

        if status is not None:
            conditions.append(RussianRouletteGame.status.in_(status))

        stmt = select(RussianRouletteGame).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_active_game_by_room(self, room_id: str) -> Optional[RussianRouletteGame]:
        """
        查询房间的活跃游戏（PLAYING状态）

        Args:
            room_id: 房间ID

        Returns:
            活跃游戏实体，不存在返回None
        """
        return await self.find_by_room_id(
            room_id,
            status=[GameStatus.PLAYING.value]
        )

    # ==================== CRUD操作 ====================

    async def create(self, game: RussianRouletteGame) -> RussianRouletteGame:
        """
        创建新游戏

        Args:
            game: 游戏实体

        Returns:
            创建后的游戏实体（包含生成的ID）
        """
        self._session.add(game)
        await self._session.flush()  # 刷新以获取生成的ID
        return game

    async def update(self, game: RussianRouletteGame) -> None:
        """
        更新游戏状态

        Args:
            game: 游戏实体
        """
        self._session.add(game)
        await self._session.flush()

    async def delete(self, game: RussianRouletteGame) -> None:
        """
        删除游戏

        Args:
            game: 游戏实体
        """
        await self._session.delete(game)
        await self._session.flush()
