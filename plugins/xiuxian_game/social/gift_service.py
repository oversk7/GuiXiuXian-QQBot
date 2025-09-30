from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple, Optional

from ..models.player import Player
from ..models.inventory import ItemInstance, ItemType
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

        # 检查物品类型的送礼限制
        if item_config.type == ItemType.MATERIAL:
            return False, "禁止送材料类物品"

        if item_config.type == ItemType.GOODS:
            if gift_type == GiftType.MENTORSHIP:
                return False, "师徒之间禁止送商品类物品"

        # 只允许送消耗品，夫妻间还可以送商品（但商品会被消耗转换为恩爱值）
        if item_config.type not in [ItemType.CONSUMABLE, ItemType.GOODS]:
            return False, "只能送消耗品类物品"

        # 检查并扣除发送者的物品（只处理消耗品和商品）
        try:
            await ItemInstance.consume_item(session, sender_id, item_config.item_id, quantity)
        except ValueError:
            return False, f"你没有足够的「{item_name}」"

        # 计算礼物总价值
        total_value = item_config.price * quantity

        # 给接收者添加物品（夫妻送商品时不给物品）
        is_marriage_goods = (gift_type == GiftType.MARRIAGE and item_config.type == ItemType.GOODS)

        if not is_marriage_goods:
            # 统一使用 ItemInstance.add_item 方法处理物品添加，确保正确处理叠加限制
            try:
                await ItemInstance.add_item(session, receiver.id, item_config.item_id, quantity)
            except ValueError as e:
                return False, f"添加物品失败：{e}"
        
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
            # 夫妻间送礼，所有物品都按价值的1%转换为恩爱值
            love_value = max(1, total_value // 100)  # 至少增加1点恩爱值
            await MarriageService.update_gift_value(session, sender_id, receiver.id, love_value)
        
        await session.commit()

        # 根据情况返回不同的消息
        if gift_type == GiftType.MARRIAGE:
            # 夫妻间送礼，统一显示恩爱值增加
            love_value = max(1, total_value // 100)
            if is_marriage_goods:
                return True, f"成功向配偶 {receiver.nickname} 送出 {quantity}个「{item_name}」，增加恩爱值 {love_value}（商品已消耗）"
            else:
                return True, f"成功向配偶 {receiver.nickname} 送出 {quantity}个「{item_name}」，增加恩爱值 {love_value}"
        else:
            # 师徒间送礼或其他情况
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
