from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple, Optional
from datetime import datetime

from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.gift_record import GiftRecord, GiftType
from ..config import config
from .marriage_service import MarriageService
from .mentorship_service import MentorshipService


class GiftService:
    """礼物系统服务类"""
    
    @staticmethod
    async def can_send_gift(session: AsyncSession, sender_id: str, receiver_id: str) -> Tuple[bool, str, Optional[GiftType]]:
        """检查是否可以送礼"""
        if sender_id == receiver_id:
            return False, "不能给自己送礼", None
        
        # 检查是否为夫妻关系
        marriage = await MarriageService.get_marriage(session, sender_id)
        if marriage and marriage.involves_player(receiver_id):
            return True, "", GiftType.MARRIAGE
        
        # 检查是否为师徒关系
        mentorship = await MentorshipService.get_mentorship(session, sender_id, receiver_id)
        if mentorship:
            return True, "", GiftType.MENTORSHIP
        
        # 检查反向师徒关系
        mentorship = await MentorshipService.get_mentorship(session, receiver_id, sender_id)
        if mentorship:
            return True, "", GiftType.MENTORSHIP
        
        return False, "只能向配偶或师父/徒弟送礼", None
    
    @staticmethod
    async def send_gift(session: AsyncSession, sender_id: str, receiver_uid: int, item_name: str, quantity: int) -> Tuple[bool, str]:
        """送礼"""
        # 获取发送者
        sender = await session.get(Player, sender_id)
        if not sender:
            return False, "发送者不存在"
        
        # 根据UID获取接收者
        receiver = (await session.execute(select(Player).where(Player.uid == receiver_uid))).scalars().first()
        if not receiver:
            return False, "未找到该UID的玩家"
        
        # 检查是否可以送礼
        can_send, reason, gift_type = await GiftService.can_send_gift(session, sender_id, receiver.id)
        if not can_send:
            return False, reason
        
        # 获取物品配置
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            return False, f"物品「{item_name}」不存在"
        
        # 检查发送者是否有足够的物品
        stmt = select(ItemInstance).where(
            and_(
                ItemInstance.player_id == sender_id,
                ItemInstance.item_id == item_config.item_id,
                ItemInstance.quantity >= quantity
            )
        )
        sender_item = (await session.execute(stmt)).scalars().first()
        if not sender_item:
            return False, f"你没有足够的「{item_name}」"
        
        # 计算礼物总价值
        total_value = item_config.price * quantity
        
        # 扣除发送者的物品
        if sender_item.quantity == quantity:
            await session.delete(sender_item)
        else:
            sender_item.quantity -= quantity
        
        # 给接收者添加物品
        stmt = select(ItemInstance).where(
            and_(
                ItemInstance.player_id == receiver.id,
                ItemInstance.item_id == item_config.item_id
            )
        )
        receiver_item = (await session.execute(stmt)).scalars().first()
        
        if receiver_item:
            receiver_item.quantity += quantity
        else:
            new_item = ItemInstance(
                player_id=receiver.id,
                item_id=item_config.item_id,
                quantity=quantity
            )
            session.add(new_item)
        
        # 记录礼物
        gift_record = GiftRecord(
            sender_id=sender_id,
            receiver_id=receiver.id,
            item_id=item_config.item_id,
            item_name=item_name,
            quantity=quantity,
            total_value=total_value,
            gift_type=gift_type
        )
        session.add(gift_record)
        
        # 更新相关系统的数值
        if gift_type == GiftType.MARRIAGE:
            await MarriageService.update_gift_value(session, sender_id, receiver.id, total_value)
        
        await session.commit()
        
        return True, f"成功向 {receiver.nickname} 送出 {quantity}个「{item_name}」，价值 {total_value} 金币"
    
    @staticmethod
    async def get_gift_history(session: AsyncSession, player_id: str, limit: int = 10) -> list[GiftRecord]:
        """获取玩家的送礼历史"""
        stmt = select(GiftRecord).where(
            GiftRecord.sender_id == player_id
        ).order_by(GiftRecord.sent_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_received_gifts(session: AsyncSession, player_id: str, limit: int = 10) -> list[GiftRecord]:
        """获取玩家收到的礼物历史"""
        stmt = select(GiftRecord).where(
            GiftRecord.receiver_id == player_id
        ).order_by(GiftRecord.sent_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
