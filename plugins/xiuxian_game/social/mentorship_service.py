from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple, List
from datetime import datetime

from ..models.player import Player
from ..models.mentorship import Mentorship
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus


class MentorshipService:
    """师徒系统服务类"""
    
    @staticmethod
    async def get_master(session: AsyncSession, disciple_id: str) -> Optional[Player]:
        """获取徒弟的师父"""
        stmt = select(Mentorship).where(Mentorship.disciple_id == disciple_id)
        mentorship = (await session.execute(stmt)).scalars().first()
        if not mentorship:
            return None
        return await session.get(Player, mentorship.master_id)
    
    @staticmethod
    async def get_disciples(session: AsyncSession, master_id: str) -> List[Player]:
        """获取师父的所有徒弟"""
        stmt = select(Mentorship).where(Mentorship.master_id == master_id)
        mentorships = (await session.execute(stmt)).scalars().all()

        disciples = []
        for mentorship in mentorships:
            disciple = await session.get(Player, mentorship.disciple_id)
            if disciple:
                disciples.append(disciple)
        return disciples

    @staticmethod
    async def get_disciples_count(session: AsyncSession, master_id: str) -> int:
        """获取师父的徒弟数量"""
        stmt = select(func.count(Mentorship.id)).where(Mentorship.master_id == master_id)
        result = await session.execute(stmt)
        return result.scalar() or 0
    
    @staticmethod
    async def get_mentorship(session: AsyncSession, master_id: str, disciple_id: str) -> Optional[Mentorship]:
        """获取师徒关系"""
        stmt = select(Mentorship).where(
            and_(Mentorship.master_id == master_id, Mentorship.disciple_id == disciple_id)
        )
        return (await session.execute(stmt)).scalars().first()
    
    @staticmethod
    async def has_master(session: AsyncSession, player_id: str) -> bool:
        """检查玩家是否有师父"""
        master = await MentorshipService.get_master(session, player_id)
        return master is not None
    
    @staticmethod
    async def can_become_disciple(session: AsyncSession, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """检查是否可以拜师"""
        if applicant_id == master_id:
            return False, "不能拜自己为师"
        
        # 检查申请人是否已有师父
        if await MentorshipService.has_master(session, applicant_id):
            return False, "你已经有师父了"
        
        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await MentorshipService.get_mentorship(session, applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"
        
        # 检查是否已有待处理的拜师申请
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.target_id == master_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        existing_app = (await session.execute(stmt)).scalars().first()
        if existing_app:
            return False, "你已经向对方发送过拜师申请了，请等待回复"
        
        return True, ""
    
    @staticmethod
    async def create_mentorship_application(session: AsyncSession, applicant_id: str, master_id: str) -> SocialApplication:
        """创建拜师申请"""
        application = SocialApplication(
            applicant_id=applicant_id,
            target_id=master_id,
            application_type=ApplicationType.MENTORSHIP
        )
        session.add(application)
        await session.commit()
        return application
    
    @staticmethod
    async def get_pending_mentorship_applications(session: AsyncSession, master_id: str) -> List[SocialApplication]:
        """获取师父收到的待处理拜师申请"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.target_id == master_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def accept_mentorship_application(session: AsyncSession, application_id: int, master_id: str) -> Tuple[bool, str]:
        """接受拜师申请（通过申请ID）"""
        # 获取申请
        application = await session.get(SocialApplication, application_id)
        if not application or application.target_id != master_id:
            return False, "申请不存在或无权限"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == master_id:
            return False, "不能拜自己为师"

        # 检查申请人是否已有师父
        if await MentorshipService.has_master(session, application.applicant_id):
            return False, "该玩家已经有师父了"

        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await MentorshipService.get_mentorship(session, application.applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"

        # 检查师父的徒弟数量限制
        disciples_count = await MentorshipService.get_disciples_count(session, master_id)
        if disciples_count >= 5:
            return False, "你的徒弟已达上限（5人），请先让一名徒弟出师"
        
        # 获取徒弟当前等级
        disciple = await session.get(Player, application.applicant_id)
        if not disciple:
            return False, "徒弟不存在"
        
        # 创建师徒关系
        mentorship = Mentorship(
            master_id=master_id,
            disciple_id=application.applicant_id,
            disciple_start_level=disciple.level
        )
        session.add(mentorship)
        
        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        
        # 拒绝该徒弟的其他拜师申请
        await MentorshipService._reject_other_mentorship_applications(session, application.applicant_id)
        
        await session.commit()
        return True, "师徒关系建立成功！"
    
    @staticmethod
    async def accept_mentorship_application_by_uid(session: AsyncSession, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """通过UID接受拜师申请"""
        # 查找对应的申请
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.target_id == master_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        application = (await session.execute(stmt)).scalars().first()

        if not application:
            return False, "未找到该玩家的拜师申请"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == master_id:
            return False, "不能拜自己为师"

        # 检查申请人是否已有师父
        if await MentorshipService.has_master(session, application.applicant_id):
            return False, "该玩家已经有师父了"

        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await MentorshipService.get_mentorship(session, application.applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"

        # 检查师父的徒弟数量限制
        disciples_count = await MentorshipService.get_disciples_count(session, master_id)
        if disciples_count >= 5:
            return False, "你的徒弟已达上限（5人），请先让一名徒弟出师"
        
        # 获取徒弟当前等级
        disciple = await session.get(Player, application.applicant_id)
        if not disciple:
            return False, "徒弟不存在"
        
        # 创建师徒关系
        mentorship = Mentorship(
            master_id=master_id,
            disciple_id=application.applicant_id,
            disciple_start_level=disciple.level
        )
        session.add(mentorship)
        
        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        
        # 拒绝该徒弟的其他拜师申请
        await MentorshipService._reject_other_mentorship_applications(session, application.applicant_id)
        
        await session.commit()
        return True, "师徒关系建立成功！"
    
    @staticmethod
    async def reject_mentorship_application(session: AsyncSession, application_id: int, master_id: str) -> Tuple[bool, str]:
        """拒绝拜师申请（通过申请ID）"""
        application = await session.get(SocialApplication, application_id)
        if not application or application.target_id != master_id:
            return False, "申请不存在或无权限"
        
        if not application.is_pending():
            return False, "申请已被处理"
        
        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        await session.commit()
        return True, "已拒绝拜师申请"
    
    @staticmethod
    async def reject_mentorship_application_by_uid(session: AsyncSession, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """通过UID拒绝拜师申请"""
        # 查找对应的申请
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == applicant_id,
                SocialApplication.target_id == master_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        application = (await session.execute(stmt)).scalars().first()
        
        if not application:
            return False, "未找到该玩家的拜师申请"
        
        if not application.is_pending():
            return False, "申请已被处理"
        
        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        await session.commit()
        return True, "已拒绝拜师申请"
    
    @staticmethod
    async def dismiss_disciple(session: AsyncSession, master_id: str, disciple_uid: int, is_graduation: bool = False) -> Tuple[bool, str]:
        """逐出徒弟或让徒弟出师"""
        # 根据UID查找徒弟
        disciple = (await session.execute(select(Player).where(Player.uid == disciple_uid))).scalars().first()
        if not disciple:
            return False, "未找到该UID的玩家"

        # 检查师徒关系
        mentorship = await MentorshipService.get_mentorship(session, master_id, disciple.id)
        if not mentorship:
            return False, "该玩家不是你的徒弟"

        await session.delete(mentorship)
        await session.commit()

        if is_graduation:
            return True, f"恭喜 {disciple.nickname} 出师！愿你前程似锦，修行路上勇猛精进！"
        else:
            return True, f"已将 {disciple.nickname} 逐出师门"
    
    @staticmethod
    async def leave_master(session: AsyncSession, disciple_id: str) -> Tuple[bool, str]:
        """脱离师父"""
        stmt = select(Mentorship).where(Mentorship.disciple_id == disciple_id)
        mentorship = (await session.execute(stmt)).scalars().first()
        if not mentorship:
            return False, "你还没有师父"
        
        await session.delete(mentorship)
        await session.commit()
        return True, "已脱离师门"
    
    @staticmethod
    async def update_mentor_points(session: AsyncSession, disciple_id: str, level_increase: int):
        """更新恩师点数（当徒弟升级时调用）"""
        stmt = select(Mentorship).where(Mentorship.disciple_id == disciple_id)
        mentorship = (await session.execute(stmt)).scalars().first()
        if mentorship:
            mentorship.mentor_points += level_increase
            await session.commit()
    
    @staticmethod
    async def get_mentor_points_ranking(session: AsyncSession, limit: int = 10) -> List[Tuple[Player, int]]:
        """获取恩师点数排行榜"""
        stmt = select(Mentorship.master_id, func.sum(Mentorship.mentor_points).label('total_points')).group_by(
            Mentorship.master_id
        ).order_by(func.sum(Mentorship.mentor_points).desc()).limit(limit)
        
        result = await session.execute(stmt)
        rankings = []
        for master_id, total_points in result:
            master = await session.get(Player, master_id)
            if master:
                rankings.append((master, total_points))
        
        return rankings
    
    @staticmethod
    async def _reject_other_mentorship_applications(session: AsyncSession, disciple_id: str):
        """拒绝该徒弟的其他拜师申请"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == disciple_id,
                SocialApplication.application_type == ApplicationType.MENTORSHIP,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        applications = (await session.execute(stmt)).scalars().all()
        for app in applications:
            app.status = ApplicationStatus.REJECTED
            app.processed_at = datetime.now()

