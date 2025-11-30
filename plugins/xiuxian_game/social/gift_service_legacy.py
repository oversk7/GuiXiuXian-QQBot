from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple, Optional

from ..models.player import Player
from ..models.inventory import ItemInstance, ItemType
from ..models.gift_record import GiftRecord, GiftType
from ..config import config
from .marriage_service import MarriageService
from .mentorship_service import MentorshipService

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的MentorshipService，False使用旧版本
USE_NEW_MENTORSHIP_SERVICE = True
# =====================================================


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
        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            mentorship = await service.get_mentorship(sender_id, receiver_id)
        else:
            mentorship = await MentorshipService.get_mentorship(session, sender_id, receiver_id)
        if mentorship:
            return True, "", GiftType.MENTORSHIP
        
        # 检查反向师徒关系
        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            mentorship = await service.get_mentorship(receiver_id, sender_id)
        else:
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

        receiver_name = receiver.nickname
        
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

        # 夫妻送商品：直接消耗转化为恩爱值，不占用接收者背包
        is_marriage_goods = (gift_type == GiftType.MARRIAGE and item_config.type == ItemType.GOODS)
        if is_marriage_goods:
            try:
                await ItemInstance.consume_item(session, sender_id, item_config.item_id, quantity)
            except ValueError:
                return False, f"你没有足够的「{item_name}」"
            total_value = item_config.price * quantity
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
            love_value = max(1, total_value // 100)
            await MarriageService.update_gift_value(session, sender_id, receiver.id, love_value)
            await session.commit()
            return True, f"成功向配偶 {receiver.nickname} 送出 {quantity}个「{item_name}」，增加恩爱值 {love_value}（商品已消耗）"

        # 非“夫妻送商品”的情况：支持部分转入，剩余不扣除，避免‘全丢失’
        # 计算接收者可接收的最大数量（叠堆+新格子）
        from ..models.inventory import STACK_SIZE
        # 查询接收者所有背包物品以计算已用格数
        result_all = await session.execute(select(ItemInstance).where(ItemInstance.player_id == receiver.id))
        receiver_all_items = result_all.scalars().all()
        used_slots = sum(1 for it in receiver_all_items if not it.is_equipment and not it.is_fish)
        effective_capacity = await receiver.get_effective_inventory_capacity(session)
        free_slots = max(0, effective_capacity - used_slots)
        # 查询接收者该物品的现有堆叠，计算可在原堆中继续叠加的空间
        result_same = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == receiver.id, ItemInstance.item_id == item_config.item_id)
            .order_by(ItemInstance.id)
        )
        same_item_stacks = result_same.scalars().all()
        existing_stack_room = sum(max(0, STACK_SIZE - inv.quantity) for inv in same_item_stacks)
        max_addable = min(quantity, existing_stack_room + free_slots * STACK_SIZE)

        if max_addable <= 0:
            return False, f"{receiver_name}的背包空间不足，送礼失败"

        # 仅扣除将要成功转入的数量
        try:
            await ItemInstance.consume_item(session, sender_id, item_config.item_id, max_addable)
        except ValueError:
            return False, f"你没有足够的「{item_name}」"

        # 实际添加到接收者背包
        try:
            await ItemInstance.add_item(session, receiver.id, item_config.item_id, max_addable)
        except ValueError:
            # 理论上不会发生（已预估容量），兜底：返还给发送者
            try:
                await ItemInstance.add_item(session, sender_id, item_config.item_id, max_addable)
            except ValueError:
                await session.rollback()
                return False, "送礼失败，物品返还异常，请稍后再试"
            return False, f"{receiver_name}的背包空间不足，送礼失败，物品已退还"

        # 计算礼物总价值（按实际送出的数量）
        actual_qty = max_addable
        total_value = item_config.price * actual_qty

        # 记录礼物
        gift_record = GiftRecord(
            sender_id=sender_id,
            receiver_id=receiver.id,
            item_id=item_config.item_id,
            item_name=item_name,
            quantity=actual_qty,
            total_value=total_value,
            gift_type=gift_type
        )
        session.add(gift_record)

        # 婚姻关系但非“商品”的情况：也计入恩爱值（沿用原逻辑按1%）
        if gift_type == GiftType.MARRIAGE:
            love_value = max(1, total_value // 100)
            await MarriageService.update_gift_value(session, sender_id, receiver.id, love_value)

        await session.commit()

        # 返回提示（区分是否部分送达）
        if actual_qty < quantity:
            leftover = quantity - actual_qty
            if gift_type == GiftType.MARRIAGE:
                return True, f"成功向配偶 {receiver.nickname} 送出 {actual_qty}个「{item_name}」（剩余{leftover}个因背包不足未送出）"
            else:
                return True, f"成功向 {receiver.nickname} 送出 {actual_qty}个「{item_name}」（剩余{leftover}个因背包不足未送出）"
        else:
            if gift_type == GiftType.MARRIAGE:
                love_value = max(1, total_value // 100)
                return True, f"成功向配偶 {receiver.nickname} 送出 {actual_qty}个「{item_name}」，增加恩爱值 {love_value}"
            else:
                return True, f"成功向 {receiver.nickname} 送出 {actual_qty}个「{item_name}」，价值 {total_value} 金币"
    
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
