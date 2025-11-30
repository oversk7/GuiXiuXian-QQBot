"""
师徒关系仓储实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计
"""

from typing import Optional, List, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.mentorship import Mentorship
from ...models.player import Player


class MentorshipRepository(IRepository[Mentorship]):
    """
    师徒关系仓储实现

    提供师徒关系数据的访问和查询方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化师徒关系仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    # ==================== 基础CRUD方法 ====================

    async def get_by_id(self, mentorship_id: int) -> Optional[Mentorship]:
        """
        根据ID获取师徒关系

        Args:
            mentorship_id: 师徒关系ID

        Returns:
            师徒关系对象，如果不存在则返回 None
        """
        stmt = select(Mentorship).where(Mentorship.id == mentorship_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, mentorship: Mentorship) -> Mentorship:
        """
        添加师徒关系

        Args:
            mentorship: 师徒关系对象

        Returns:
            添加后的师徒关系（包含生成的ID）
        """
        self._session.add(mentorship)
        await self._session.flush()  # 获取自增ID
        return mentorship

    async def update(self, mentorship: Mentorship) -> Mentorship:
        """
        更新师徒关系

        Args:
            mentorship: 师徒关系对象

        Returns:
            更新后的师徒关系
        """
        self._session.add(mentorship)
        return mentorship

    async def delete(self, mentorship_id: int) -> bool:
        """
        删除师徒关系

        Args:
            mentorship_id: 师徒关系ID

        Returns:
            是否删除成功
        """
        mentorship = await self.get_by_id(mentorship_id)
        if mentorship:
            await self._session.delete(mentorship)
            return True
        return False

    async def exists(self, mentorship_id: int) -> bool:
        """
        检查师徒关系是否存在

        Args:
            mentorship_id: 师徒关系ID

        Returns:
            是否存在
        """
        stmt = select(func.count()).select_from(Mentorship).where(Mentorship.id == mentorship_id)
        result = await self._session.execute(stmt)
        count = result.scalar()
        return count > 0

    async def count(self) -> int:
        """
        统计师徒关系总数

        Returns:
            师徒关系数量
        """
        stmt = select(func.count()).select_from(Mentorship)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== 业务查询方法 ====================

    async def get_by_disciple_id(self, disciple_id: str) -> Optional[Mentorship]:
        """
        根据徒弟ID获取师徒关系（一个徒弟只能有一个师父）

        Args:
            disciple_id: 徒弟ID

        Returns:
            师徒关系对象，如果不存在则返回 None
        """
        stmt = select(Mentorship).where(Mentorship.disciple_id == disciple_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_master_and_disciple(
        self, master_id: str, disciple_id: str
    ) -> Optional[Mentorship]:
        """
        根据师父ID和徒弟ID获取师徒关系

        Args:
            master_id: 师父ID
            disciple_id: 徒弟ID

        Returns:
            师徒关系对象，如果不存在则返回 None
        """
        stmt = select(Mentorship).where(
            and_(
                Mentorship.master_id == master_id,
                Mentorship.disciple_id == disciple_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_master_id(self, master_id: str) -> List[Mentorship]:
        """
        获取师父的所有徒弟关系

        Args:
            master_id: 师父ID

        Returns:
            师徒关系列表
        """
        stmt = select(Mentorship).where(Mentorship.master_id == master_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_disciples_count(self, master_id: str) -> int:
        """
        获取师父的徒弟数量

        Args:
            master_id: 师父ID

        Returns:
            徒弟数量
        """
        stmt = (
            select(func.count())
            .select_from(Mentorship)
            .where(Mentorship.master_id == master_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== N+1优化方法 ====================

    async def get_disciples_with_players(
        self, master_id: str
    ) -> List[Tuple[Mentorship, Player]]:
        """
        获取师父的所有徒弟关系，并预加载徒弟Player对象

        使用join预加载，避免N+1查询问题

        Args:
            master_id: 师父ID

        Returns:
            (Mentorship, Player) 元组列表，其中Mentorship是师徒关系，Player是徒弟信息
        """
        stmt = (
            select(Mentorship, Player)
            .join(Player, Mentorship.disciple_id == Player.id)
            .where(Mentorship.master_id == master_id)
        )
        result = await self._session.execute(stmt)
        return [(mentorship, player) for mentorship, player in result]

    async def get_mentor_points_ranking(self, limit: int = 10) -> List[Tuple[str, int]]:
        """
        获取恩师点数排行榜（仅返回master_id和总点数）

        不在Repository中查询Player，由Service层批量查询

        Args:
            limit: 排行榜数量限制，默认10

        Returns:
            (master_id, total_points) 元组列表，按点数降序排列
        """
        stmt = (
            select(Mentorship.master_id, func.sum(Mentorship.mentor_points).label("total_points"))
            .group_by(Mentorship.master_id)
            .order_by(func.sum(Mentorship.mentor_points).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(master_id, int(total_points or 0)) for master_id, total_points in result]

    # ==================== 批量更新方法 ====================

    async def update_mentor_points(self, disciple_id: str, points_increase: int) -> bool:
        """
        更新恩师点数（当徒弟升级时调用）

        根据徒弟ID查找对应的师徒关系，并增加恩师点数

        Args:
            disciple_id: 徒弟ID
            points_increase: 增加的点数

        Returns:
            是否成功更新
        """
        mentorship = await self.get_by_disciple_id(disciple_id)
        if not mentorship:
            return False
        mentorship.mentor_points += points_increase
        await self.update(mentorship)
        return True
