from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple
from datetime import datetime

from ..models.player import Player
from ..models.marriage import Marriage
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..models.gift_record import GiftRecord, GiftType


class MarriageService:
    """婚姻系统服务类"""
    
    @staticmethod
    async def get_marriage(session: AsyncSession, player_id: str) -> Optional[Marriage]:
        """获取玩家的婚姻关系"""
        stmt = select(Marriage).where(
            or_(Marriage.player1_id == player_id, Marriage.player2_id == player_id)
        )
        result = await session.execute(stmt)
        return result.scalars().first()
    
    @staticmethod
    async def get_spouse(session: AsyncSession, player_id: str) -> Optional[Player]:
        """获取玩家的配偶"""
        marriage = await MarriageService.get_marriage(session, player_id)
        if not marriage:
            return None
        
        spouse_id = marriage.get_spouse_id(player_id)
        if not spouse_id:
            return None
            
        return await session.get(Player, spouse_id)
    
    @staticmethod
    async def is_married(session: AsyncSession, player_id: str) -> bool:
        """检查玩家是否已婚"""
        marriage = await MarriageService.get_marriage(session, player_id)
        return marriage is not None
    
    @staticmethod
    async def can_propose(session: AsyncSession, proposer_id: str, target_id: str) -> Tuple[bool, str]:
        """检查是否可以求婚"""
        if proposer_id == target_id:
            return False, "不能向自己求婚"
        
        # 检查双方是否已婚
        if await MarriageService.is_married(session, proposer_id):
            return False, "你已经结婚了"
        
        if await MarriageService.is_married(session, target_id):
            return False, "对方已经结婚了"
        
        # 检查是否已有待处理的求婚申请
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.applicant_id == proposer_id,
                SocialApplication.target_id == target_id,
                SocialApplication.application_type == ApplicationType.MARRIAGE,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        existing_app = (await session.execute(stmt)).scalars().first()
        if existing_app:
            return False, "你已经向对方求过婚了，请等待回复"
        
        return True, ""
    
    @staticmethod
    async def create_proposal(session: AsyncSession, proposer_id: str, target_id: str) -> SocialApplication:
        """创建求婚申请"""
        application = SocialApplication(
            applicant_id=proposer_id,
            target_id=target_id,
            application_type=ApplicationType.MARRIAGE
        )
        session.add(application)
        await session.commit()
        return application
    
    @staticmethod
    async def get_pending_proposals(session: AsyncSession, player_id: str) -> list[SocialApplication]:
        """获取玩家收到的待处理求婚申请"""
        stmt = select(SocialApplication).where(
            and_(
                SocialApplication.target_id == player_id,
                SocialApplication.application_type == ApplicationType.MARRIAGE,
                SocialApplication.status == ApplicationStatus.PENDING
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def accept_proposal(session: AsyncSession, application_id: int, target_id: str) -> Tuple[bool, str]:
        """接受求婚申请"""
        # 获取申请
        application = await session.get(SocialApplication, application_id)
        if not application or application.target_id != target_id:
            return False, "申请不存在或无权限"
        
        if not application.is_pending():
            return False, "申请已被处理"
        
        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == target_id:
            return False, "不能向自己求婚"
        
        # 检查双方是否已婚
        if await MarriageService.is_married(session, application.applicant_id):
            return False, "对方已经结婚了"
        
        if await MarriageService.is_married(session, target_id):
            return False, "你已经结婚了"
        
        # 创建婚姻关系
        marriage = Marriage(
            player1_id=application.applicant_id,
            player2_id=target_id
        )
        session.add(marriage)
        
        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        
        # 拒绝其他相关的求婚申请
        await MarriageService._reject_other_proposals(session, application.applicant_id, target_id)
        
        await session.commit()
        return True, "恭喜你们结为夫妻！"
    
    @staticmethod
    async def reject_proposal(session: AsyncSession, application_id: int, target_id: str) -> Tuple[bool, str]:
        """拒绝求婚申请"""
        application = await session.get(SocialApplication, application_id)
        if not application or application.target_id != target_id:
            return False, "申请不存在或无权限"
        
        if not application.is_pending():
            return False, "申请已被处理"
        
        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        await session.commit()
        return True, "已拒绝求婚申请"
    
    @staticmethod
    async def divorce(session: AsyncSession, player_id: str) -> Tuple[bool, str]:
        """离婚"""
        marriage = await MarriageService.get_marriage(session, player_id)
        if not marriage:
            return False, "你还没有结婚"
        
        await session.delete(marriage)
        await session.commit()
        return True, "离婚成功"
    
    @staticmethod
    async def _reject_other_proposals(session: AsyncSession, player1_id: str, player2_id: str):
        """拒绝其他相关的求婚申请"""
        # 拒绝这两个玩家的所有其他待处理求婚申请
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
        applications = (await session.execute(stmt)).scalars().all()
        for app in applications:
            app.status = ApplicationStatus.REJECTED
            app.processed_at = datetime.now()
    
    @staticmethod
    async def update_gift_value(session: AsyncSession, player1_id: str, player2_id: str, value: int):
        """更新夫妻间礼物总价值"""
        marriage = await MarriageService.get_marriage(session, player1_id)
        if marriage and marriage.involves_player(player2_id):
            marriage.total_gift_value += value
            await session.commit()

