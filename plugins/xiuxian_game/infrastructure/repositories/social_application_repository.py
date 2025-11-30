"""
社交申请仓储实现

提供社交申请（求婚、拜师、公会入会等）的数据访问抽象
"""

from typing import List, Optional
from sqlalchemy import select, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ...domain.repositories.base import IRepository
from ...models.social_application import SocialApplication, ApplicationType, ApplicationStatus


class SocialApplicationRepository(IRepository[SocialApplication]):
    """社交申请仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化社交申请仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, application_id: int) -> Optional[SocialApplication]:
        """
        根据ID获取申请记录

        Args:
            application_id: 申请ID

        Returns:
            申请记录实例，不存在返回None
        """
        stmt = select(SocialApplication).where(SocialApplication.id == application_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_application_by_player_and_guild(
        self, player_id: str, guild_id: int
    ) -> Optional[SocialApplication]:
        """
        获取玩家在指定公会的待处理申请

        Args:
            player_id: 玩家ID
            guild_id: 公会ID

        Returns:
            待处理的申请记录，不存在返回None

        对应原代码:
            guild_application_service.py Line 32-40
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == player_id,
                SocialApplication.guild_id == guild_id,
                SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_guild_applications(
        self, guild_id: int
    ) -> List[SocialApplication]:
        """
        获取公会的所有待处理申请

        Args:
            guild_id: 公会ID

        Returns:
            待处理申请列表（按申请时间升序）

        对应原代码:
            guild_application_service.py Line 71-82
        """
        stmt = (
            select(SocialApplication)
            .where(
                and_(
                    SocialApplication.guild_id == guild_id,
                    SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                    SocialApplication.status == ApplicationStatus.PENDING
                )
            )
            .order_by(SocialApplication.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_player_applications(
        self, player_id: str, application_type: ApplicationType = None
    ) -> List[SocialApplication]:
        """
        获取玩家的申请历史

        Args:
            player_id: 玩家ID
            application_type: 申请类型（可选，不指定则返回所有类型）

        Returns:
            申请记录列表（按申请时间降序）

        对应原代码:
            guild_application_service.py Line 165-175
        """
        conditions = [SocialApplication.applicant_id == player_id]
        if application_type:
            conditions.append(SocialApplication.application_type == application_type)

        stmt = (
            select(SocialApplication)
            .where(and_(*conditions))
            .order_by(SocialApplication.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, application: SocialApplication) -> SocialApplication:
        """
        添加申请记录

        Args:
            application: 申请记录实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            guild_application_service.py Line 58-68
        """
        self._session.add(application)
        await self._session.flush()  # 刷新以获取生成的ID
        return application

    async def update(self, application: SocialApplication) -> SocialApplication:
        """
        更新申请记录

        Args:
            application: 申请记录实例

        Returns:
            更新后的记录
        """
        self._session.add(application)
        return application

    async def approve_application(
        self, application: SocialApplication
    ) -> SocialApplication:
        """
        批准申请

        Args:
            application: 申请记录实例

        Returns:
            更新后的记录

        对应原代码:
            guild_application_service.py Line 135-136
        """
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        self._session.add(application)
        return application

    async def reject_application(
        self, application: SocialApplication
    ) -> SocialApplication:
        """
        拒绝申请

        Args:
            application: 申请记录实例

        Returns:
            更新后的记录

        对应原代码:
            guild_application_service.py Line 158-160
        """
        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        self._session.add(application)
        return application

    async def reject_other_pending_applications(
        self, player_id: str, exclude_application_id: int
    ) -> int:
        """
        拒绝玩家其他待处理的公会申请

        Args:
            player_id: 玩家ID
            exclude_application_id: 要排除的申请ID（当前被批准的申请）

        Returns:
            被拒绝的申请数量

        对应原代码:
            guild_application_service.py Line 138-150

        Note:
            当玩家加入一个公会时，其他公会的待处理申请应该自动拒绝
        """
        stmt = (
            update(SocialApplication)
            .where(
                and_(
                    SocialApplication.applicant_id == player_id,
                    SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                    SocialApplication.status == ApplicationStatus.PENDING,
                    SocialApplication.id != exclude_application_id
                )
            )
            .values(status=ApplicationStatus.REJECTED, processed_at=datetime.now())
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def delete(self, application_id: int) -> bool:
        """
        删除申请记录

        Args:
            application_id: 申请ID

        Returns:
            是否成功删除
        """
        application = await self.get_by_id(application_id)
        if application:
            await self._session.delete(application)
            return True
        return False

    async def exists(self, application_id: int) -> bool:
        """
        检查申请记录是否存在

        Args:
            application_id: 申请ID

        Returns:
            是否存在
        """
        application = await self.get_by_id(application_id)
        return application is not None

    async def count(self) -> int:
        """
        获取申请记录总数

        Returns:
            记录总数
        """
        stmt = select(SocialApplication)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def get_pending_mentorship_applications_by_target(
        self, target_id: str
    ) -> List[SocialApplication]:
        """
        获取指定师父收到的所有待处理拜师申请

        Args:
            target_id: 师父ID

        Returns:
            待处理拜师申请列表

        对应原代码:
            mentorship_service.py Line 100-110
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.target_id == target_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_mentorship_application_by_applicant_and_target(
        self, applicant_id: str, target_id: str
    ) -> Optional[SocialApplication]:
        """
        获取指定申请人向指定师父发起的待处理拜师申请

        Args:
            applicant_id: 申请人ID
            target_id: 师父ID

        Returns:
            待处理拜师申请，如果不存在则返回None

        对应原代码:
            mentorship_service.py Line 73-83
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.target_id == target_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_pending_mentorship_applications_by_applicant(
        self, applicant_id: str
    ) -> List[SocialApplication]:
        """
        获取指定申请人的所有待处理拜师申请

        Args:
            applicant_id: 申请人ID

        Returns:
            待处理拜师申请列表

        对应原代码:
            mentorship_service.py Line 324-336
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_marriage_proposals_by_target(
        self, target_id: str
    ) -> List[SocialApplication]:
        """
        获取目标玩家收到的待处理求婚申请

        Args:
            target_id: 目标玩家ID

        Returns:
            待处理求婚申请列表

        对应原代码:
            marriage_service.py Line 84-94
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.target_id == target_id,
                SocialApplication.application_type == ApplicationType.MARRIAGE,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_marriage_proposal_by_applicant_and_target(
        self, applicant_id: str, target_id: str
    ) -> Optional[SocialApplication]:
        """
        获取特定的待处理求婚申请

        Args:
            applicant_id: 申请人ID
            target_id: 目标玩家ID

        Returns:
            待处理求婚申请，如果不存在则返回None

        对应原代码:
            marriage_service.py Line 57-67
        """
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.target_id == target_id,
                SocialApplication.application_type == ApplicationType.MARRIAGE,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_pending_marriage_proposals_for_players(
        self, player1_id: str, player2_id: str
    ) -> List[SocialApplication]:
        """
        获取两个玩家相关的所有待处理求婚申请（用于_reject_other_proposals）

        Args:
            player1_id: 玩家1 ID
            player2_id: 玩家2 ID

        Returns:
            待处理求婚申请列表

        对应原代码:
            marriage_service.py Line 238-250
        """
        stmt = select(SocialApplication).where(
            and_(
                or_(
                    and_(SocialApplication.applicant_id == player1_id, SocialApplication.target_id != player2_id),
                    and_(SocialApplication.applicant_id == player2_id, SocialApplication.target_id != player1_id),
                    and_(SocialApplication.target_id == player1_id, SocialApplication.applicant_id != player2_id),
                    and_(SocialApplication.target_id == player2_id, SocialApplication.applicant_id != player1_id)
                ),
                SocialApplication.application_type == ApplicationType.MARRIAGE,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
