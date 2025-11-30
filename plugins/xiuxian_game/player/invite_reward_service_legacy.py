"""
邀请奖励服务 - 处理分级奖励逻辑
"""
from typing import Tuple, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from ..models.player import Player
from ..models.invite_reward import InviteReward


class InviteRewardService:
    """邀请奖励服务类"""
    
    # 分级奖励配置
    LEVEL_REWARDS = {
        1: {
            "inviter_gold": 3000,
            "inviter_items": [],  # 可以添加道具奖励
            "invitee_gold": 1000,
            "invitee_items": [],
            "description": "1级奖励"
        },
        10: {
            "inviter_gold": 8000,
            "inviter_items": [],
            "invitee_gold": 3000,
            "invitee_items": [],
            "description": "10级奖励"
        },
        50: {
            "inviter_gold": 20000,
            "inviter_items": [],
            "invitee_gold": 8000,
            "invitee_items": [],
            "description": "50级奖励"
        }
    }
    
    @classmethod
    async def create_invite_record(cls, session: AsyncSession, invitee_uid: int, inviter_uid: int) -> InviteReward:
        """创建邀请记录"""
        invite_record = InviteReward(
            invitee_uid=invitee_uid,
            inviter_uid=inviter_uid
        )
        session.add(invite_record)
        await session.flush()  # 获取ID
        return invite_record
    
    @classmethod
    async def check_and_grant_level_rewards(cls, session: AsyncSession, player_id: str, new_level: int) -> List[str]:
        """检查并发放等级奖励"""
        # 获取玩家信息
        player = await session.get(Player, player_id)
        if not player:
            return []
        
        # 查找该玩家的邀请记录
        stmt = select(InviteReward).where(InviteReward.invitee_uid == player.uid)
        result = await session.execute(stmt)
        invite_record = result.scalars().first()
        
        if not invite_record:
            return []  # 没有邀请记录
        
        # 获取邀请者信息
        inviter_stmt = select(Player).where(Player.uid == invite_record.inviter_uid)
        inviter_result = await session.execute(inviter_stmt)
        inviter = inviter_result.scalars().first()
        
        if not inviter:
            return []  # 邀请者不存在
        
        messages = []
        
        # 检查各级奖励
        for level_threshold in [1, 10, 50]:
            if new_level >= level_threshold:
                reward_granted = await cls._grant_level_reward(
                    session, invite_record, inviter, player, level_threshold
                )
                if reward_granted:
                    messages.append(reward_granted)
        
        return messages
    
    @classmethod
    async def _grant_level_reward(cls, session: AsyncSession, invite_record: InviteReward, 
                                 inviter: Player, invitee: Player, level: int) -> str:
        """发放指定等级的奖励"""
        # 检查是否已经发放过该等级奖励
        if level == 1 and invite_record.level_1_rewarded:
            return ""
        elif level == 10 and invite_record.level_10_rewarded:
            return ""
        elif level == 50 and invite_record.level_50_rewarded:
            return ""
        
        reward_config = cls.LEVEL_REWARDS.get(level)
        if not reward_config:
            return ""
        
        # 发放奖励
        inviter.gold += reward_config["inviter_gold"]
        invitee.gold += reward_config["invitee_gold"]
        
        # 标记奖励已发放
        now = datetime.now()
        if level == 1:
            invite_record.level_1_rewarded = True
            invite_record.level_1_rewarded_at = now
        elif level == 10:
            invite_record.level_10_rewarded = True
            invite_record.level_10_rewarded_at = now
        elif level == 50:
            invite_record.level_50_rewarded = True
            invite_record.level_50_rewarded_at = now
        
        session.add(invite_record)
        session.add(inviter)
        session.add(invitee)
        
        return (f"🎉 邀请奖励发放！\n"
                f"📈 {invitee.nickname} 达到{level}级\n"
                f"🎁 邀请者 {inviter.nickname} 获得 💰{reward_config['inviter_gold']} 金币\n"
                f"🎁 被邀请者 {invitee.nickname} 获得 💰{reward_config['invitee_gold']} 金币")
    
    @classmethod
    async def get_invite_status(cls, session: AsyncSession, player_uid: int) -> Dict:
        """获取邀请状态信息"""
        # 查找作为邀请者的记录
        inviter_stmt = select(InviteReward).where(InviteReward.inviter_uid == player_uid)
        inviter_result = await session.execute(inviter_stmt)
        inviter_records = inviter_result.scalars().all()
        
        # 查找作为被邀请者的记录
        invitee_stmt = select(InviteReward).where(InviteReward.invitee_uid == player_uid)
        invitee_result = await session.execute(invitee_stmt)
        invitee_record = invitee_result.scalars().first()
        
        return {
            "invited_count": len(inviter_records),
            "inviter_records": inviter_records,
            "invitee_record": invitee_record
        }
    
    @classmethod
    async def get_pending_rewards_info(cls, session: AsyncSession, inviter_uid: int) -> List[Dict]:
        """获取待发放奖励信息"""
        stmt = select(InviteReward).where(InviteReward.inviter_uid == inviter_uid)
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        pending_rewards = []
        
        for record in records:
            # 获取被邀请者当前等级
            invitee_stmt = select(Player).where(Player.uid == record.invitee_uid)
            invitee_result = await session.execute(invitee_stmt)
            invitee = invitee_result.scalars().first()
            
            if not invitee:
                continue
            
            # 检查各级奖励状态
            for level in [1, 10, 50]:
                if invitee.level >= level:
                    rewarded = (
                        (level == 1 and record.level_1_rewarded) or
                        (level == 10 and record.level_10_rewarded) or
                        (level == 50 and record.level_50_rewarded)
                    )
                    if not rewarded:
                        reward_config = cls.LEVEL_REWARDS.get(level)
                        pending_rewards.append({
                            "invitee_name": invitee.nickname,
                            "invitee_level": invitee.level,
                            "reward_level": level,
                            "inviter_gold": reward_config["inviter_gold"],
                            "invitee_gold": reward_config["invitee_gold"]
                        })
        
        return pending_rewards
