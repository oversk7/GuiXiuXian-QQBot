from sqlalchemy import select, and_, func as _func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple, List
from datetime import datetime

from ..models.player import Player
from ..models.guild import Guild
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus


class GuildApplicationService:
    """公会申请系统服务类"""
    
    @staticmethod
    async def can_apply_guild(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """检查是否可以申请加入公会"""
        # 获取玩家信息
        player = await session.get(Player, player_id)
        if not player:
            return False, "玩家不存在"
        
        # 检查玩家是否已加入公会
        if player.guild_id is not None:
            return False, "你已经加入公会，无法再次加入"
        
        # 检查公会是否存在
        guild = await session.get(Guild, guild_id)
        if not guild:
            return False, "未找到该公会"
        
        # 检查是否已有待处理的申请
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == player_id,
                SocialApplication.guild_id == guild_id,
                SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        existing_app = (await session.execute(stmt)).scalars().first()
        if existing_app:
            return False, "你已提交申请，请等待会长审核"
        
        # 检查公会容量
        def _capacity(lv: int) -> int:
            return 10 + (lv - 1) * 5
        
        member_count = (await session.execute(
            select(_func.count(Player.id)).where(Player.guild_id == guild_id)
        )).scalar_one()
        
        if member_count >= _capacity(guild.level):
            return False, "该公会人数已满，无法申请"
        
        return True, ""
    
    @staticmethod
    async def create_guild_application(session: AsyncSession, player_id: str, guild_id: int) -> SocialApplication:
        """创建公会申请"""
        application = SocialApplication(
            applicant_id=player_id,
            target_id="",  # 公会申请不需要 target_id
            guild_id=guild_id,
            application_type=ApplicationType.GUILD_JOIN
        )
        session.add(application)
        await session.commit()
        return application
    
    @staticmethod
    async def get_pending_applications(session: AsyncSession, guild_id: int) -> List[SocialApplication]:
        """获取公会的待处理申请列表"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.guild_id == guild_id,
                SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        ).order_by(SocialApplication.created_at.asc())
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_application_by_player_and_guild(
        session: AsyncSession, 
        player_id: str, 
        guild_id: int
    ) -> Optional[SocialApplication]:
        """根据玩家ID和公会ID获取待处理申请"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == player_id,
                SocialApplication.guild_id == guild_id,
                SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await session.execute(stmt)
        return result.scalars().first()
    
    @staticmethod
    async def approve_application(
        session: AsyncSession, 
        application: SocialApplication,
        guild: Guild
    ) -> Tuple[bool, str]:
        """批准公会申请"""
        # 再次检查公会容量（防止并发问题）
        def _capacity(lv: int) -> int:
            return 10 + (lv - 1) * 5
        
        member_count = (await session.execute(
            select(_func.count(Player.id)).where(Player.guild_id == guild.id)
        )).scalar_one()
        
        if member_count >= _capacity(guild.level):
            return False, "公会人数已满，无法同意"
        
        # 获取申请人
        applicant = await session.get(Player, application.applicant_id)
        if not applicant:
            return False, "申请人不存在"
        
        # 检查申请人是否已加入其他公会
        if applicant.guild_id is not None and applicant.guild_id != guild.id:
            application.status = ApplicationStatus.REJECTED
            application.processed_at = datetime.now()
            session.add(application)
            await session.commit()
            return False, "该玩家已加入其他公会，无法同意"
        
        # 批准申请
        applicant.guild_id = guild.id
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        
        # 将该玩家其他待处理的公会申请全部标记为拒绝
        await session.execute(
            SocialApplication.__table__.update()
            .where(
                and_(
                    SocialApplication.applicant_id == applicant.id,
                    SocialApplication.application_type == ApplicationType.GUILD_JOIN,
                    SocialApplication.status == ApplicationStatus.PENDING,
                    SocialApplication.id != application.id
                )
            )
            .values(status=ApplicationStatus.REJECTED, processed_at=datetime.now())
        )
        
        session.add_all([applicant, application])
        await session.commit()
        return True, "申请已批准"
    
    @staticmethod
    async def reject_application(session: AsyncSession, application: SocialApplication) -> None:
        """拒绝公会申请"""
        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        session.add(application)
        await session.commit()
    
    @staticmethod
    async def get_player_applications(session: AsyncSession, player_id: str) -> List[SocialApplication]:
        """获取玩家的公会申请历史"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == player_id,
                SocialApplication.application_type == ApplicationType.GUILD_JOIN
            )
        ).order_by(SocialApplication.created_at.desc())
        
        result = await session.execute(stmt)
        return result.scalars().all()
