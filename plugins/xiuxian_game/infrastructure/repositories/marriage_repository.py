"""
婚姻关系仓储实现
"""
from typing import Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.marriage import Marriage


class MarriageRepository(IRepository[Marriage]):
    """婚姻关系仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ==================== 基础CRUD方法 ====================

    async def get_by_id(self, marriage_id: int) -> Optional[Marriage]:
        """根据ID获取婚姻记录"""
        return await self._session.get(Marriage, marriage_id)

    async def add(self, marriage: Marriage) -> Marriage:
        """添加婚姻记录"""
        self._session.add(marriage)
        await self._session.flush()
        return marriage

    async def update(self, marriage: Marriage) -> Marriage:
        """更新婚姻记录"""
        await self._session.flush()
        return marriage

    async def delete(self, marriage_id: int) -> bool:
        """删除婚姻记录"""
        marriage = await self.get_by_id(marriage_id)
        if not marriage:
            return False
        await self._session.delete(marriage)
        await self._session.flush()
        return True

    async def exists(self, marriage_id: int) -> bool:
        """检查婚姻记录是否存在"""
        marriage = await self.get_by_id(marriage_id)
        return marriage is not None

    async def count(self) -> int:
        """统计婚姻记录总数"""
        stmt = select(func.count(Marriage.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== 业务查询方法 ====================

    async def get_by_player_id(self, player_id: str) -> Optional[Marriage]:
        """
        获取玩家的婚姻关系

        Args:
            player_id: 玩家ID

        Returns:
            玩家的婚姻记录，如果未结婚则返回None

        Note:
            查询player1_id或player2_id匹配的记录
        """
        stmt = select(Marriage).where(
            or_(Marriage.player1_id == player_id, Marriage.player2_id == player_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def is_married(self, player_id: str) -> bool:
        """检查玩家是否已婚"""
        marriage = await self.get_by_player_id(player_id)
        return marriage is not None

    async def update_gift_value(self, player_id: str, value_increase: int) -> bool:
        """
        更新玩家婚姻的礼物总价值

        Args:
            player_id: 玩家ID
            value_increase: 增加的价值

        Returns:
            是否更新成功
        """
        marriage = await self.get_by_player_id(player_id)
        if not marriage:
            return False
        marriage.total_gift_value += value_increase
        await self.update(marriage)
        return True

    # ==================== 辅助方法 ====================

    async def delete_by_player_id(self, player_id: str) -> bool:
        """
        删除玩家的婚姻关系

        Args:
            player_id: 玩家ID

        Returns:
            是否删除成功
        """
        marriage = await self.get_by_player_id(player_id)
        if not marriage:
            return False
        await self._session.delete(marriage)
        await self._session.flush()
        return True
