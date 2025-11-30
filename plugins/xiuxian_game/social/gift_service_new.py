"""
礼物系统服务模块 (DI架构版本)

改造说明:
- 从静态方法改为实例方法
- 通过构造函数注入5个Repository/Service依赖
- 移除所有session参数，通过self._xxx_repo/self._xxx_service访问数据
- 移除所有内部commit()调用(2处)，由调用方控制事务边界
- 保持业务逻辑完全一致
- 移除Feature Flag逻辑，直接使用注入的DI版本Service
"""
from typing import Tuple, Optional, List
from sqlalchemy import select

from ..models.player import Player
from ..models.inventory import ItemInstance, ItemType, STACK_SIZE
from ..models.gift_record import GiftRecord, GiftType
from ..config import config
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.gift_record_repository import GiftRecordRepository
from ..infrastructure.repositories.item_repository import ItemRepository
# Service依赖（注入DI版本）
from .marriage_service_new import MarriageService
from .mentorship_service_new import MentorshipService


class GiftService:
    """
    礼物系统服务类 (DI版本)

    依赖注入:
        - player_repo: PlayerRepository
        - marriage_service: MarriageService (DI版本)
        - mentorship_service: MentorshipService (DI版本)
        - gift_record_repo: GiftRecordRepository
        - item_repo: ItemRepository
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        marriage_service: MarriageService,
        mentorship_service: MentorshipService,
        gift_record_repo: GiftRecordRepository,
        item_repo: ItemRepository
    ):
        """
        初始化礼物服务

        Args:
            player_repo: 玩家仓储
            marriage_service: 婚姻服务 (DI版本)
            mentorship_service: 师徒服务 (DI版本)
            gift_record_repo: 礼物记录仓储
            item_repo: 物品仓储
        """
        self._player_repo = player_repo
        self._marriage_service = marriage_service
        self._mentorship_service = mentorship_service
        self._gift_record_repo = gift_record_repo
        self._item_repo = item_repo

    async def can_send_gift(self, sender_id: str, receiver_id: str) -> Tuple[bool, str, Optional[GiftType]]:
        """
        检查是否可以送礼

        Args:
            sender_id: 发送者ID
            receiver_id: 接收者ID

        Returns:
            (是否可以送礼, 提示信息, 礼物类型)

        对应原代码:
            gift_service.py Line 21-68
        """
        if sender_id == receiver_id:
            return False, "不能给自己送礼", None

        # 检查是否为夫妻关系
        marriage = await self._marriage_service.get_marriage(sender_id)
        if marriage and marriage.involves_player(receiver_id):
            return True, "", GiftType.MARRIAGE

        # 检查是否为师徒关系
        mentorship = await self._mentorship_service.get_mentorship(sender_id, receiver_id)
        if mentorship:
            return True, "", GiftType.MENTORSHIP

        # 检查反向师徒关系
        mentorship = await self._mentorship_service.get_mentorship(receiver_id, sender_id)
        if mentorship:
            return True, "", GiftType.MENTORSHIP

        return False, "只能向配偶或师父/徒弟送礼", None

    async def send_gift(self, sender_id: str, receiver_uid: int, item_name: str, quantity: int) -> Tuple[bool, str]:
        """
        送礼

        Args:
            sender_id: 发送者ID
            receiver_uid: 接收者UID
            item_name: 物品名称
            quantity: 数量

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            gift_service.py Line 70-206

        P0修复:
            移除Line 128和Line 192的commit()
        """
        # 获取发送者
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "发送者不存在"

        # 根据UID获取接收者
        receiver = await self._player_repo.get_by_uid(receiver_uid)
        if not receiver:
            return False, "未找到该UID的玩家"

        receiver_name = receiver.nickname

        # 检查是否可以送礼
        can_send, reason, gift_type = await self.can_send_gift(sender_id, receiver.id)
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
            # 消耗发送者的物品
            success = await self._item_repo.consume_item(sender_id, item_config.item_id, quantity)
            if not success:
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
            await self._gift_record_repo.add(gift_record)
            love_value = max(1, total_value // 100)
            await self._marriage_service.update_gift_value(sender_id, receiver.id, love_value)
            # P0修复: 移除commit() - 由调用方控制事务
            return True, f"成功向配偶 {receiver.nickname} 送出 {quantity}个「{item_name}」，增加恩爱值 {love_value}（商品已消耗）"

        # 非"夫妻送商品"的情况：支持部分转入，剩余不扣除，避免'全丢失'
        # 计算接收者可接收的最大数量（叠堆+新格子）
        # 查询接收者所有背包物品以计算已用格数
        receiver_all_items = await self._item_repo.get_all_non_equipment_non_fish(receiver.id)
        used_slots = len(receiver_all_items)
        effective_capacity = await receiver.get_effective_inventory_capacity(self._item_repo._session)
        free_slots = max(0, effective_capacity - used_slots)

        # 查询接收者该物品的现有堆叠，计算可在原堆中继续叠加的空间
        same_item_stacks = await self._item_repo.get_items_by_item_id(receiver.id, item_config.item_id)
        existing_stack_room = sum(max(0, STACK_SIZE - inv.quantity) for inv in same_item_stacks)
        max_addable = min(quantity, existing_stack_room + free_slots * STACK_SIZE)

        if max_addable <= 0:
            return False, f"{receiver_name}的背包空间不足，送礼失败"

        # 仅扣除将要成功转入的数量
        success = await self._item_repo.consume_item(sender_id, item_config.item_id, max_addable)
        if not success:
            return False, f"你没有足够的「{item_name}」"

        # 实际添加到接收者背包
        try:
            await self._item_repo.add_item(receiver.id, item_config.item_id, max_addable)
        except ValueError:
            # 理论上不会发生（已预估容量），兜底：返还给发送者
            try:
                await self._item_repo.add_item(sender_id, item_config.item_id, max_addable)
            except ValueError:
                # 这里无法直接rollback，因为由调用方控制事务
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
        await self._gift_record_repo.add(gift_record)

        # 婚姻关系但非"商品"的情况：也计入恩爱值（沿用原逻辑按1%）
        if gift_type == GiftType.MARRIAGE:
            love_value = max(1, total_value // 100)
            await self._marriage_service.update_gift_value(sender_id, receiver.id, love_value)

        # P0修复: 移除commit() - 由调用方控制事务

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

    async def get_gift_history(self, player_id: str, limit: int = 10) -> List[GiftRecord]:
        """
        获取玩家的送礼历史

        Args:
            player_id: 玩家ID
            limit: 返回数量限制

        Returns:
            礼物记录列表

        对应原代码:
            gift_service.py Line 208-216
        """
        return await self._gift_record_repo.get_gift_history(player_id, limit)

    async def get_received_gifts(self, player_id: str, limit: int = 10) -> List[GiftRecord]:
        """
        获取玩家收到的礼物历史

        Args:
            player_id: 玩家ID
            limit: 返回数量限制

        Returns:
            礼物记录列表

        对应原代码:
            gift_service.py Line 218-226
        """
        return await self._gift_record_repo.get_received_gifts(player_id, limit)
