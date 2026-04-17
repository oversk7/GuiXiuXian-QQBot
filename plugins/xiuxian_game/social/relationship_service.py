"""
玩家关系服务

管理玩家间的好感度、送礼、魅力值等社交功能
"""
from typing import Tuple, Optional, List
from datetime import datetime, date
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.player_relationship import PlayerRelationship, RelationshipType
from ..models.inventory import ItemInstance, ItemType
from ..config import config


class RelationshipService:
    """
    玩家关系服务

    核心功能:
    - 送好感度礼物(远程,消耗型)
    - 当面送礼(物品转移)
    - 查询魅力榜
    - 查询好感度

    设计要点:
    - 双向好感度: A-B关系是双向的,只有一条记录
    - 每日上限: 每人对另一人每天最多获得30好感度
    - 魅力值: 只有接收者增加魅力值(与好感度1:1)
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        relationship_repo: PlayerRelationshipRepository,
        item_repo: ItemRepository,
        uow: UnitOfWork
    ):
        """
        初始化关系服务

        Args:
            player_repo: 玩家仓储
            relationship_repo: 关系仓储
            item_repo: 物品仓储
            uow: 工作单元
        """
        self._player_repo = player_repo
        self._relationship_repo = relationship_repo
        self._item_repo = item_repo
        self._uow = uow

    async def send_gift_favorability(
        self,
        sender_id: str,
        receiver_uid: int,
        item_name: str,
        quantity: int,
        daily_limit: int = 500
    ) -> Tuple[bool, str]:
        """
        送好感度礼物(远程,消耗型)

        规则:
        1. 物品类型必须是GIFT
        2. 物品被消耗(不转移)
        3. 增加双向好感度
        4. 增加接收者魅力值(与好感度1:1)
        5. 每人对另一人每天最多获得daily_limit好感度

        Args:
            sender_id: 发送者ID
            receiver_uid: 接收者UID
            item_name: 礼物名称
            quantity: 数量
            daily_limit: 每日好感度上限(默认500)

        Returns:
            (是否成功, 提示信息)
        """
        # 1. 获取发送者
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "发送者不存在"

        # 2. 获取接收者
        receiver = await self._player_repo.get_by_uid(receiver_uid)
        if not receiver:
            return False, f"未找到UID为{receiver_uid}的玩家"

        if sender_id == receiver.id:
            return False, "不能给自己送礼"

        # 3. 获取物品配置
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            return False, f"物品「{item_name}」不存在"

        # 4. 检查物品类型
        if item_config.type != ItemType.GIFT:
            return False, "该命令只能送好感度礼物,请使用【当面送礼】命令转移其他物品"

        # 5. 检查背包数量
        has_item = await self._item_repo.has_item(sender_id, item_config.item_id, quantity)
        if not has_item:
            return False, f"你没有足够的「{item_name}」"

        # 6. 获取或创建关系
        relationship = await self._relationship_repo.get_or_create_relationship(
            sender_id, receiver.id
        )

        # 7. 检查每日上限
        today = date.today()
        need_reset = (
            relationship.last_gift_date is None or
            relationship.last_gift_date.date() < today
        )

        if need_reset:
            # 新的一天,重置计数
            relationship.today_favorability_gain = 0
            relationship.last_gift_date = datetime.now()

        # 8. 计算好感度增加量
        favorability_per_item = getattr(item_config, 'favorability', 0)
        total_favorability = favorability_per_item * quantity

        # 检查是否超过每日上限
        if relationship.today_favorability_gain + total_favorability > daily_limit:
            remaining = daily_limit - relationship.today_favorability_gain
            if remaining <= 0:
                return False, f"今日对{receiver.nickname}的好感度已达上限({daily_limit}),请明天再送"
            else:
                # 计算实际可送数量
                max_quantity = remaining // favorability_per_item
                if max_quantity == 0:
                    return False, f"今日对{receiver.nickname}的好感度已达上限({daily_limit}),请明天再送"
                return False, f"今日对{receiver.nickname}的好感度即将达上限,最多只能送{max_quantity}个「{item_name}」"

        # 9. 消耗物品
        success = await self._item_repo.consume_item(sender_id, item_config.item_id, quantity)
        if not success:
            return False, f"你没有足够的「{item_name}」"

        # 10. 增加双向好感度
        old_favorability = relationship.favorability
        relationship.favorability = min(10000, relationship.favorability + total_favorability)
        relationship.today_favorability_gain += total_favorability
        relationship.total_gifts += quantity
        relationship.last_interaction_date = datetime.now()

        # 11. 增加接收者魅力值(1:1)
        receiver.charm += total_favorability

        # 12. 返回成功消息
        actual_gain = relationship.favorability - old_favorability
        return (
            True,
            f"成功向{receiver.nickname}送出{quantity}个「{item_name}」\n"
            f"好感度: {old_favorability} → {relationship.favorability} (+{actual_gain})\n"
            f"{receiver.nickname}魅力值: +{total_favorability}\n"
            f"今日已获得: {relationship.today_favorability_gain}/{daily_limit}"
        )

    async def send_gift_face_to_face(
        self,
        sender_id: str,
        receiver_uid: int,
        item_name: str,
        quantity: int
    ) -> Tuple[bool, str]:
        """
        当面送礼(物品转移)

        规则:
        1. 必须在同一坐标(x,y完全相同)
        2. 不能转移跑商商品(GOODS类型)
        3. 可以转移材料、装备、好感度礼物(GIFT类型不消耗)
        4. 物品实际转移到接收者背包,不增加好感度
        5. 装备类型需要选择具体实例(如果有多件)

        Args:
            sender_id: 发送者ID
            receiver_uid: 接收者UID
            item_name: 物品名称
            quantity: 数量

        Returns:
            (是否成功, 提示信息)
        """
        # 1. 获取发送者
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "发送者不存在"

        # 2. 获取接收者
        receiver = await self._player_repo.get_by_uid(receiver_uid)
        if not receiver:
            return False, f"未找到UID为{receiver_uid}的玩家"

        if sender_id == receiver.id:
            return False, "不能给自己送东西"

        # 3. 检查地理约束(同一坐标)
        # 使用精确坐标判断
        sender_x, sender_y = sender.get_current_coordinates()
        receiver_x, receiver_y = receiver.get_current_coordinates()

        # 检查是否在同一坐标
        if sender_x != receiver_x or sender_y != receiver_y:
            sender_region = sender.get_current_region()
            receiver_region = receiver.get_current_region()
            return False, f"必须和{receiver.nickname}在同一坐标才能当面送礼\n你的位置: {sender_region}({sender_x},{sender_y})\n对方位置: {receiver_region}({receiver_x},{receiver_y})"

        # 4. 获取物品配置
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            return False, f"物品「{item_name}」不存在"

        # 5. 检查物品类型
        if item_config.type == ItemType.GOODS:
            return False, f"禁止转移跑商商品类物品"

        # 5.1 VIP定制装备禁止转移
        VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren", "vip_pendant_fuze", "vip_huihai_xinyuan"}
        if item_config.item_id in VIP_EQUIPMENT_IDS:
            return False, "VIP定制装备为专属装备，不可转移"

        # 6. 特殊处理: 装备/铭文类型需要返回信息供Command处理（实例交易）
        if item_config.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
            # 获取玩家实例列表
            instance_list = await self._item_repo.get_player_equipment_list(
                sender_id, item_config.item_id, equipped=False
            )

            if not instance_list:
                return False, f"你没有可转移的「{item_name}」"

            # 返回特殊标记,通知Command需要处理实例选择
            return (
                False,
                f"__EQUIPMENT_SELECTION__:{item_config.item_id}:{item_config.name}:{len(instance_list)}"
            )

        # 7. 普通物品处理流程
        # 注意: 允许转移GIFT类型,但不消耗也不加好感度(仅物理转移)

        # 检查背包数量
        has_item = await self._item_repo.has_item(sender_id, item_config.item_id, quantity)
        if not has_item:
            return False, f"你没有足够的「{item_name}」"

        # 扣除发送者物品
        success = await self._item_repo.consume_item(sender_id, item_config.item_id, quantity)
        if not success:
            return False, f"你没有足够的「{item_name}」"

        # 添加到接收者背包(自动检查背包空间)
        try:
            await self._item_repo.add_item(receiver.id, item_config.item_id, quantity)
        except ValueError as e:
            # 背包空间不足,退还物品给发送者
            await self._item_repo.add_item(sender_id, item_config.item_id, quantity)
            return False, f"{receiver.nickname}的背包已满,无法接收物品"

        # 返回成功消息
        return (
            True,
            f"成功向{receiver.nickname}当面送出{quantity}个「{item_name}」"
        )

    async def transfer_equipment_face_to_face(
        self,
        sender_id: str,
        receiver_uid: int,
        equipment_instance_id: int
    ) -> Tuple[bool, str]:
        """
        当面转移装备(选择具体实例后调用)

        规则:
        1. 必须在同一坐标(x,y完全相同)
        2. 使用 transfer_equipment 方法转移装备实例
        3. 不增加好感度

        Args:
            sender_id: 发送者ID
            receiver_uid: 接收者UID
            equipment_instance_id: 装备实例ID

        Returns:
            (是否成功, 提示信息)
        """
        from ..economy.equipment_trade_service import EquipmentTradeService

        # 1. 获取发送者和接收者
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "发送者不存在"

        receiver = await self._player_repo.get_by_uid(receiver_uid)
        if not receiver:
            return False, f"未找到UID为{receiver_uid}的玩家"

        # 2. 获取物品实例（装备或铭文）
        equipment = await self._item_repo.get_by_id(equipment_instance_id)
        if not equipment:
            return False, "物品不存在"

        if equipment.player_id != sender_id:
            return False, "该物品不属于你"

        if equipment.is_equipment and equipment.equipped:
            return False, "不能转移已装备的装备,请先卸下"

        # 3. 检查地理约束(同一坐标)
        sender_x, sender_y = sender.get_current_coordinates()
        receiver_x, receiver_y = receiver.get_current_coordinates()

        if sender_x != receiver_x or sender_y != receiver_y:
            sender_region = sender.get_current_region()
            receiver_region = receiver.get_current_region()
            type_name = "装备" if equipment.is_equipment else "铭文"
            return False, f"必须和{receiver.nickname}在同一坐标才能当面转移{type_name}\n你的位置: {sender_region}({sender_x},{sender_y})\n对方位置: {receiver_region}({receiver_x},{receiver_y})"

        # 4. 转移实例
        success = await EquipmentTradeService.transfer_equipment(
            self._uow.session, equipment, receiver.id
        )

        if not success:
            return False, "转移物品失败"

        # 5. 返回成功消息
        from ..economy.equipment_trade_service_new import EquipmentTradeService as ETSNew
        summary = ETSNew.generate_instance_summary(equipment)
        type_name = "装备" if equipment.is_equipment else "铭文"
        return (
            True,
            f"成功向{receiver.nickname}转移{type_name}: {summary}"
        )

    async def get_favorability(
        self,
        player_id: str,
        target_id: str
    ) -> Tuple[int, str]:
        """
        查询与另一个玩家的好感度

        Args:
            player_id: 玩家A的ID
            target_id: 玩家B的ID

        Returns:
            (好感度值, 关系描述)
        """
        relationship = await self._relationship_repo.get_relationship(player_id, target_id)

        if relationship is None:
            return 0, "陌生人"

        favorability = relationship.favorability

        # 根据好感度返回关系描述
        if favorability < 20:
            relation_desc = "陌生人"
        elif favorability < 40:
            relation_desc = "熟识"
        elif favorability < 60:
            relation_desc = "友好"
        elif favorability < 80:
            relation_desc = "亲密"
        else:
            relation_desc = "知心"

        return favorability, relation_desc

    async def get_charm_ranking(
        self,
        limit: int = 100
    ) -> list:
        """
        获取魅力值排行榜

        Args:
            limit: 返回记录数

        Returns:
            [(玩家昵称, 魅力值, 排名), ...]
        """
        from sqlalchemy import desc
        from ..models.player import Player

        result = await self._uow.session.execute(
            select(Player.nickname, Player.charm)
            .order_by(desc(Player.charm))
            .limit(limit)
        )

        ranking = []
        for idx, (nickname, charm) in enumerate(result.all(), start=1):
            ranking.append((nickname, charm, idx))

        return ranking

    # ==================== 关系建立方法 ====================

    async def can_establish_relationship(
        self,
        player_id: str,
        target_uid: int,
        relationship_type: RelationshipType
    ) -> Tuple[bool, str]:
        """
        检查是否可以建立指定关系

        Args:
            player_id: 玩家A的ID
            target_uid: 玩家B的UID
            relationship_type: 关系类型

        Returns:
            (是否可以, 提示信息)
        """
        # 获取目标玩家
        target = await self._player_repo.get_by_uid(target_uid)
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"

        if player_id == target.id:
            return False, "不能与自己建立关系"

        # 获取或创建关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            player_id, target.id
        )

        # 检查当前关系类型
        if relationship.relationship_type != RelationshipType.NONE.value:
            current_type = relationship.relationship_type
            if relationship_type.value == current_type:
                return False, f"你们已经是{self._get_relationship_name(relationship_type)}关系了"
            else:
                return False, f"你们已有{self._get_relationship_name(RelationshipType(current_type))}关系,无法建立{self._get_relationship_name(relationship_type)}关系"

        # 检查好感度要求
        favorability = relationship.favorability
        min_favorability = self._get_min_favorability(relationship_type)

        if favorability < min_favorability:
            return False, f"好感度不足！{self._get_relationship_name(relationship_type)}需要{min_favorability}好感度,当前{favorability}"

        # 检查地理位置
        player = await self._player_repo.get_by_id(player_id)
        if player.region != target.region:
            return False, f"必须与对方在同一地点才能建立关系\n当前位置: {player.region}\n对方位置: {target.region}"

        return True, ""

    async def establish_marriage(
        self,
        player_id: str,
        target_uid: int
    ) -> Tuple[bool, str]:
        """
        建立婚姻关系

        Args:
            player_id: 玩家ID
            target_uid: 配偶UID

        Returns:
            (是否成功, 提示信息)
        """
        # 检查是否可以建立婚姻关系
        can, msg = await self.can_establish_relationship(
            player_id, target_uid, RelationshipType.MARRIAGE
        )
        if not can:
            return False, msg

        target = await self._player_repo.get_by_uid(target_uid)

        # 建立婚姻关系
        relationship = await self._relationship_repo.get_relationship(
            player_id, target.id
        )

        if relationship:
            relationship.relationship_type = RelationshipType.MARRIAGE.value
            relationship.established_at = datetime.now()

            return True, f"恭喜！你与{target.nickname}喜结连理,成为夫妻！"
        else:
            return False, "关系记录不存在"

    # ==================== 婚姻申请方法 ====================

    # 婚姻申请配置常量
    MARRIAGE_REQUEST_EXPIRE_DAYS = 7  # 申请7天未处理自动过期
    MARRIAGE_REQUEST_REJECT_COOLDOWN_HOURS = 24  # 被拒绝后24小时内不能再次申请

    async def submit_marriage_proposal(
        self,
        proposer_id: str,
        target_uid: int
    ) -> Tuple[bool, str]:
        """
        发起求婚申请

        Args:
            proposer_id: 求婚者ID
            target_uid: 对方UID

        Returns:
            (是否成功, 消息)
        """
        from datetime import timedelta

        # 获取求婚者和对方
        proposer = await self._player_repo.get_by_id(proposer_id)
        target = await self._player_repo.get_by_uid(target_uid)

        if not proposer:
            return False, "玩家不存在"
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"
        if proposer.id == target.id:
            return False, "不能向自己求婚"

        # 检查是否可以建立婚姻关系
        can, msg = await self.can_establish_relationship(
            proposer_id, target_uid, RelationshipType.MARRIAGE
        )
        if not can:
            return False, msg

        # 获取或创建关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            proposer.id, target.id
        )

        # 检查是否已有待处理的申请
        if relationship.marriage_request_status == "pending":
            # 检查是谁发起的申请
            if relationship.marriage_proposer_id == proposer_id:
                return False, f"你已经向【{target.nickname}】发起过求婚申请，请等待对方处理"
            else:
                return False, f"【{target.nickname}】已向你发起求婚申请，请先处理该申请"

        # 检查被拒绝后的冷却期
        if relationship.marriage_reject_time:
            cooldown_end = relationship.marriage_reject_time + timedelta(hours=self.MARRIAGE_REQUEST_REJECT_COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                remaining_hours = (cooldown_end - datetime.now()).total_seconds() / 3600
                return False, f"求婚被拒绝后需要等待24小时才能再次申请，剩余{remaining_hours:.1f}小时"

        # 创建申请
        relationship.marriage_request_status = "pending"
        relationship.marriage_request_time = datetime.now()
        relationship.marriage_reject_time = None
        relationship.marriage_proposer_id = proposer.id

        return True, (
            f"✅ 已向【{target.nickname}】(UID: {target.uid})发起求婚申请！\n"
            f"━━━━━━━━━━━━━\n"
            f"对方可通过【交互 月老 求婚申请】查看\n"
            f"申请将在7天后自动过期"
        )

    async def get_marriage_proposals(
        self,
        player_id: str
    ) -> List[dict]:
        """
        查询收到的求婚申请列表

        Args:
            player_id: 玩家ID

        Returns:
            申请列表
        """
        from datetime import timedelta

        # 查询所有与该玩家相关的待处理求婚申请
        stmt = select(PlayerRelationship).where(
            and_(
                PlayerRelationship.marriage_request_status == "pending",
                PlayerRelationship.marriage_proposer_id != player_id,  # 不是自己发起的
                # 该玩家是关系的一方
                (PlayerRelationship.player_id == player_id) | (PlayerRelationship.target_id == player_id)
            )
        )
        result = await self._uow.session.execute(stmt)
        relationships = result.scalars().all()

        proposals = []
        for rel in relationships:
            # 检查申请是否过期
            if rel.marriage_request_time:
                expire_time = rel.marriage_request_time + timedelta(days=self.MARRIAGE_REQUEST_EXPIRE_DAYS)
                if datetime.now() > expire_time:
                    # 过期了，清除申请状态（保留申请时间作为历史记录）
                    rel.marriage_request_status = None
                    # rel.marriage_request_time 保留不清空
                    rel.marriage_proposer_id = None
                    continue

            # 获取求婚者信息
            proposer = await self._player_repo.get_by_id(rel.marriage_proposer_id)
            if proposer:
                proposals.append({
                    "proposer_uid": proposer.uid,
                    "proposer_name": proposer.nickname,
                    "request_time": rel.marriage_request_time
                })

        return proposals

    async def approve_marriage_proposal(
        self,
        responder_id: str,
        proposer_uid: int
    ) -> Tuple[bool, str]:
        """
        同意求婚申请

        Args:
            responder_id: 被求婚者ID
            proposer_uid: 求婚者UID

        Returns:
            (是否成功, 消息)
        """
        from datetime import timedelta

        # 获取双方
        responder = await self._player_repo.get_by_id(responder_id)
        proposer = await self._player_repo.get_by_uid(proposer_uid)

        if not responder:
            return False, "玩家不存在"
        if not proposer:
            return False, f"未找到UID为{proposer_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            responder.id, proposer.id
        )

        # 检查申请状态
        if relationship.marriage_request_status != "pending":
            return False, f"【{proposer.nickname}】没有向你发起求婚申请"

        if relationship.marriage_proposer_id != proposer.id:
            return False, f"该求婚申请不是【{proposer.nickname}】发起的"

        # 检查申请是否过期
        if relationship.marriage_request_time:
            expire_time = relationship.marriage_request_time + timedelta(days=self.MARRIAGE_REQUEST_EXPIRE_DAYS)
            if datetime.now() > expire_time:
                # 过期了，清除申请状态（保留申请时间作为历史记录）
                relationship.marriage_request_status = None
                # relationship.marriage_request_time 保留不清空
                relationship.marriage_proposer_id = None
                return False, "申请已过期"

        # 再次检查是否可以建立婚姻关系（可能状态已变化）
        can, msg = await self.can_establish_relationship(
            responder_id, proposer_uid, RelationshipType.MARRIAGE
        )
        if not can:
            # 清除申请状态（保留申请时间作为历史记录）
            relationship.marriage_request_status = None
            # relationship.marriage_request_time 保留不清空
            relationship.marriage_proposer_id = None
            return False, f"无法建立婚姻关系：{msg}"

        # 建立婚姻关系
        relationship.relationship_type = RelationshipType.MARRIAGE.value
        relationship.established_at = datetime.now()

        # 清除申请状态（保留申请时间作为历史记录）
        relationship.marriage_request_status = None
        # relationship.marriage_request_time 保留不清空
        relationship.marriage_proposer_id = None
        relationship.marriage_reject_time = None

        return True, (
            f"🎉 恭喜！你与【{proposer.nickname}】喜结连理，成为夫妻！\n"
            f"━━━━━━━━━━━━━\n"
            f"愿你们白头偕老，永结同心！"
        )

    async def reject_marriage_proposal(
        self,
        responder_id: str,
        proposer_uid: int
    ) -> Tuple[bool, str]:
        """
        拒绝求婚申请

        Args:
            responder_id: 被求婚者ID
            proposer_uid: 求婚者UID

        Returns:
            (是否成功, 消息)
        """
        # 获取双方
        responder = await self._player_repo.get_by_id(responder_id)
        proposer = await self._player_repo.get_by_uid(proposer_uid)

        if not responder:
            return False, "玩家不存在"
        if not proposer:
            return False, f"未找到UID为{proposer_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            responder.id, proposer.id
        )

        # 检查申请状态
        if relationship.marriage_request_status != "pending":
            return False, f"【{proposer.nickname}】没有向你发起求婚申请"

        if relationship.marriage_proposer_id != proposer.id:
            return False, f"该求婚申请不是【{proposer.nickname}】发起的"

        # 拒绝申请（保留申请时间作为历史记录）
        relationship.marriage_request_status = None
        # relationship.marriage_request_time 保留不清空
        relationship.marriage_proposer_id = None
        relationship.marriage_reject_time = datetime.now()

        return True, f"已拒绝【{proposer.nickname}】的求婚申请"

    async def cancel_marriage_proposal(
        self,
        proposer_id: str,
        target_uid: int
    ) -> Tuple[bool, str]:
        """
        撤销求婚申请

        Args:
            proposer_id: 求婚者ID
            target_uid: 对方UID

        Returns:
            (是否成功, 消息)
        """
        # 获取双方
        proposer = await self._player_repo.get_by_id(proposer_id)
        target = await self._player_repo.get_by_uid(target_uid)

        if not proposer:
            return False, "玩家不存在"
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            proposer.id, target.id
        )

        # 检查申请状态
        if relationship.marriage_request_status != "pending":
            return False, f"你没有向【{target.nickname}】发起求婚申请"

        if relationship.marriage_proposer_id != proposer_id:
            return False, f"该求婚申请不是你发起的"

        # 撤销申请（保留申请时间作为历史记录）
        relationship.marriage_request_status = None
        # relationship.marriage_request_time 保留不清空
        relationship.marriage_proposer_id = None

        return True, f"已撤销向【{target.nickname}】的求婚申请"

    async def establish_sworn(
        self,
        player_id: str,
        target_uids: List[int]
    ) -> Tuple[bool, str]:
        """
        建立结义关系

        Args:
            player_id: 发起者ID
            target_uids: 其他结义者的UID列表(2-4人总数)

        Returns:
            (是否成功, 提示信息)
        """
        # 检查人数
        total_people = len(target_uids) + 1  # 包括发起者
        if total_people < 2:
            return False, "结义至少需要2人"
        if total_people > 4:
            return False, "结义最多支持4人"

        # 获取所有玩家
        players = [await self._player_repo.get_by_id(player_id)]
        player_names = [players[0].nickname]

        for uid in target_uids:
            p = await self._player_repo.get_by_uid(uid)
            if not p:
                return False, f"未找到UID为{uid}的玩家"
            players.append(p)
            player_names.append(p.nickname)

        # 检查所有玩家是否在同一地点
        first_region = players[0].region
        for p in players[1:]:
            if p.region != first_region:
                return False, f"所有人必须在同一地点才能结义\n{p.nickname}在{p.region}"

        # 检查所有两两之间的关系
        for i, p1 in enumerate(players):
            for p2 in players[i+1:]:
                # 检查是否可以建立结义关系
                can, msg = await self.can_establish_relationship(
                    p1.id, int(p2.uid), RelationshipType.SWORN
                )
                if not can:
                    # 特殊处理：如果只是好感度不足，给出更友好的提示
                    if "好感度不足" in msg:
                        relationship = await self._relationship_repo.get_relationship(
                            p1.id, p2.id
                        )
                        favorability = relationship.favorability if relationship else 0
                        return False, f"{p1.nickname}与{p2.nickname}的好感度不足(需要5000,当前{favorability})"
                    return False, msg

        # 建立所有两两之间的结义关系
        for i, p1 in enumerate(players):
            for p2 in players[i+1:]:
                relationship = await self._relationship_repo.get_relationship(
                    p1.id, p2.id
                )
                if relationship:
                    relationship.relationship_type = RelationshipType.SWORN.value
                    relationship.established_at = datetime.now()

        names_str = "、".join(player_names)
        return True, f"恭喜！{names_str}在上京城结为异姓兄弟，从此有福同享，有难同当！"

    # ==================== 结义申请方法(2人) ====================

    # 结义申请配置常量
    SWORN_REQUEST_EXPIRE_DAYS = 7  # 申请7天未处理自动过期
    SWORN_REQUEST_REJECT_COOLDOWN_HOURS = 24  # 被拒绝后24小时内不能再次申请

    async def submit_sworn_proposal(
        self,
        proposer_id: str,
        target_uid: int
    ) -> Tuple[bool, str]:
        """
        发起结义申请(仅支持2人结义)

        Args:
            proposer_id: 发起者ID
            target_uid: 对方UID

        Returns:
            (是否成功, 消息)
        """
        from datetime import timedelta

        # 获取发起者和对方
        proposer = await self._player_repo.get_by_id(proposer_id)
        target = await self._player_repo.get_by_uid(target_uid)

        if not proposer:
            return False, "玩家不存在"
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"
        if proposer.id == target.id:
            return False, "不能与自己结义"

        # 检查是否可以建立结义关系
        can, msg = await self.can_establish_relationship(
            proposer_id, target_uid, RelationshipType.SWORN
        )
        if not can:
            return False, msg

        # 获取或创建关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            proposer.id, target.id
        )

        # 检查是否已有待处理的申请
        if relationship.sworn_request_status == "pending":
            # 检查是谁发起的申请
            if relationship.sworn_proposer_id == proposer_id:
                return False, f"你已经向【{target.nickname}】发起过结义申请，请等待对方处理"
            else:
                return False, f"【{target.nickname}】已向你发起结义申请，请先处理该申请"

        # 检查被拒绝后的冷却期
        if relationship.sworn_reject_time:
            cooldown_end = relationship.sworn_reject_time + timedelta(hours=self.SWORN_REQUEST_REJECT_COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                remaining_hours = (cooldown_end - datetime.now()).total_seconds() / 3600
                return False, f"结义被拒绝后需要等待24小时才能再次申请，剩余{remaining_hours:.1f}小时"

        # 创建申请
        relationship.sworn_request_status = "pending"
        relationship.sworn_request_time = datetime.now()
        relationship.sworn_reject_time = None
        relationship.sworn_proposer_id = proposer.id

        return True, (
            f"✅ 已向【{target.nickname}】(UID: {target.uid})发起结义申请！\n"
            f"━━━━━━━━━━━━━\n"
            f"对方可通过【交互 结义使者 结义申请】查看\n"
            f"申请将在7天后自动过期\n"
            f"💡 提示: 3-4人结义仍需所有人在场使用【结义 UID1 UID2...】"
        )

    async def get_sworn_proposals(
        self,
        player_id: str
    ) -> List[dict]:
        """
        查询收到的结义申请列表

        Args:
            player_id: 玩家ID

        Returns:
            申请列表
        """
        from datetime import timedelta

        # 查询所有与该玩家相关的待处理结义申请
        stmt = select(PlayerRelationship).where(
            and_(
                PlayerRelationship.sworn_request_status == "pending",
                PlayerRelationship.sworn_proposer_id != player_id,  # 不是自己发起的
                # 该玩家是关系的一方
                (PlayerRelationship.player_id == player_id) | (PlayerRelationship.target_id == player_id)
            )
        )
        result = await self._uow.session.execute(stmt)
        relationships = result.scalars().all()

        proposals = []
        for rel in relationships:
            # 检查申请是否过期
            if rel.sworn_request_time:
                expire_time = rel.sworn_request_time + timedelta(days=self.SWORN_REQUEST_EXPIRE_DAYS)
                if datetime.now() > expire_time:
                    # 过期了，清除申请状态（保留申请时间作为历史记录）
                    rel.sworn_request_status = None
                    # rel.sworn_request_time 保留不清空
                    rel.sworn_proposer_id = None
                    continue

            # 获取发起者信息
            proposer = await self._player_repo.get_by_id(rel.sworn_proposer_id)
            if proposer:
                proposals.append({
                    "proposer_uid": proposer.uid,
                    "proposer_name": proposer.nickname,
                    "request_time": rel.sworn_request_time
                })

        return proposals

    async def approve_sworn_proposal(
        self,
        responder_id: str,
        proposer_uid: int
    ) -> Tuple[bool, str]:
        """
        同意结义申请

        Args:
            responder_id: 被邀请者ID
            proposer_uid: 发起者UID

        Returns:
            (是否成功, 消息)
        """
        from datetime import timedelta

        # 获取双方
        responder = await self._player_repo.get_by_id(responder_id)
        proposer = await self._player_repo.get_by_uid(proposer_uid)

        if not responder:
            return False, "玩家不存在"
        if not proposer:
            return False, f"未找到UID为{proposer_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            responder.id, proposer.id
        )

        # 检查申请状态
        if relationship.sworn_request_status != "pending":
            return False, f"【{proposer.nickname}】没有向你发起结义申请"

        if relationship.sworn_proposer_id != proposer.id:
            return False, f"该结义申请不是【{proposer.nickname}】发起的"

        # 检查申请是否过期
        if relationship.sworn_request_time:
            expire_time = relationship.sworn_request_time + timedelta(days=self.SWORN_REQUEST_EXPIRE_DAYS)
            if datetime.now() > expire_time:
                # 过期了，清除申请状态（保留申请时间作为历史记录）
                relationship.sworn_request_status = None
                # relationship.sworn_request_time 保留不清空
                relationship.sworn_proposer_id = None
                return False, "申请已过期"

        # 再次检查是否可以建立结义关系（可能状态已变化）
        can, msg = await self.can_establish_relationship(
            responder_id, proposer_uid, RelationshipType.SWORN
        )
        if not can:
            # 清除申请状态（保留申请时间作为历史记录）
            relationship.sworn_request_status = None
            # relationship.sworn_request_time 保留不清空
            relationship.sworn_proposer_id = None
            return False, f"无法建立结义关系：{msg}"

        # 建立结义关系
        relationship.relationship_type = RelationshipType.SWORN.value
        relationship.established_at = datetime.now()

        # 清除申请状态（保留申请时间作为历史记录）
        relationship.sworn_request_status = None
        # relationship.sworn_request_time 保留不清空
        relationship.sworn_proposer_id = None
        relationship.sworn_reject_time = None

        return True, (
            f"🎉 恭喜！你与【{proposer.nickname}】结为异姓兄弟！\n"
            f"━━━━━━━━━━━━━\n"
            f"有福同享，有难同当！江湖义气永存！"
        )

    async def reject_sworn_proposal(
        self,
        responder_id: str,
        proposer_uid: int
    ) -> Tuple[bool, str]:
        """
        拒绝结义申请

        Args:
            responder_id: 被邀请者ID
            proposer_uid: 发起者UID

        Returns:
            (是否成功, 消息)
        """
        # 获取双方
        responder = await self._player_repo.get_by_id(responder_id)
        proposer = await self._player_repo.get_by_uid(proposer_uid)

        if not responder:
            return False, "玩家不存在"
        if not proposer:
            return False, f"未找到UID为{proposer_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            responder.id, proposer.id
        )

        # 检查申请状态
        if relationship.sworn_request_status != "pending":
            return False, f"【{proposer.nickname}】没有向你发起结义申请"

        if relationship.sworn_proposer_id != proposer.id:
            return False, f"该结义申请不是【{proposer.nickname}】发起的"

        # 拒绝申请（保留申请时间作为历史记录）
        relationship.sworn_request_status = None
        # relationship.sworn_request_time 保留不清空
        relationship.sworn_proposer_id = None
        relationship.sworn_reject_time = datetime.now()

        return True, f"已拒绝【{proposer.nickname}】的结义申请"

    async def cancel_sworn_proposal(
        self,
        proposer_id: str,
        target_uid: int
    ) -> Tuple[bool, str]:
        """
        撤销结义申请

        Args:
            proposer_id: 发起者ID
            target_uid: 对方UID

        Returns:
            (是否成功, 消息)
        """
        # 获取双方
        proposer = await self._player_repo.get_by_id(proposer_id)
        target = await self._player_repo.get_by_uid(target_uid)

        if not proposer:
            return False, "玩家不存在"
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            proposer.id, target.id
        )

        # 检查申请状态
        if relationship.sworn_request_status != "pending":
            return False, f"你没有向【{target.nickname}】发起结义申请"

        if relationship.sworn_proposer_id != proposer_id:
            return False, f"该结义申请不是你发起的"

        # 撤销申请（保留申请时间作为历史记录）
        relationship.sworn_request_status = None
        # relationship.sworn_request_time 保留不清空
        relationship.sworn_proposer_id = None

        return True, f"已撤销向【{target.nickname}】的结义申请"

    async def establish_mentorship(
        self,
        player_id: str,
        target_uid: int,
        is_master: bool
    ) -> Tuple[bool, str]:
        """
        建立师徒关系

        Args:
            player_id: 玩家ID
            target_uid: 对方UID
            is_master: True表示当前玩家是师父,False表示是徒弟

        Returns:
            (是否成功, 提示信息)
        """
        # 检查是否可以建立师徒关系
        can, msg = await self.can_establish_relationship(
            player_id, target_uid, RelationshipType.MENTORSHIP
        )
        if not can:
            return False, msg

        target = await self._player_repo.get_by_uid(target_uid)
        player = await self._player_repo.get_by_id(player_id)

        # 建立师徒关系
        relationship = await self._relationship_repo.get_relationship(
            player_id, target.id
        )

        if relationship:
            relationship.relationship_type = RelationshipType.MENTORSHIP.value
            relationship.established_at = datetime.now()

            if is_master:
                return True, f"恭喜！{target.nickname}正式拜你为师,成为你的徒弟"
            else:
                return True, f"恭喜！你正式拜{target.nickname}为师,成为其徒弟"
        else:
            return False, "关系记录不存在"

    # ==================== 关系解除方法 ====================

    async def divorce(
        self,
        player_id: str,
        cost: int = 100000
    ) -> Tuple[bool, str]:
        """
        离婚(单方面,需要支付高额金币)

        Args:
            player_id: 玩家ID
            cost: 离婚费用(默认10万金币)

        Returns:
            (是否成功, 提示信息)
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        # 检查金币
        if player.money < cost:
            return False, f"金币不足！离婚需要{cost}金币,你当前只有{player.money}金币"

        # 查找婚姻关系
        from sqlalchemy import or_
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id
                ),
                PlayerRelationship.relationship_type == RelationshipType.MARRIAGE.value
            )
        )
        result = await self._uow.session.execute(stmt)
        relationship = result.scalar_one_or_none()

        if not relationship:
            return False, "你当前没有婚姻关系"

        # 扣除金币
        player.money -= cost

        # 解除婚姻关系
        relationship.relationship_type = RelationshipType.NONE.value
        relationship.established_at = None

        # 获取配偶ID
        spouse_id = relationship.target_id if relationship.player_id == player_id else relationship.player_id
        spouse = await self._player_repo.get_by_id(spouse_id)

        return True, f"你支付了{cost}金币,与{spouse.nickname if spouse else '对方'}离婚了"

    async def break_sworn(
        self,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        断义(解除结义关系)

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 提示信息)
        """
        # 查找所有结义关系
        from sqlalchemy import or_
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id
                ),
                PlayerRelationship.relationship_type == RelationshipType.SWORN.value
            )
        )
        result = await self._uow.session.execute(stmt)
        relationships = result.scalars().all()

        if not relationships:
            return False, "你当前没有结义关系"

        # 解除所有结义关系
        count = 0
        for rel in relationships:
            rel.relationship_type = RelationshipType.NONE.value
            rel.established_at = None
            count += 1

        return True, f"你已断义,解除了{count}段结义关系"

    # ==================== 辅助方法 ====================

    def _get_relationship_name(self, relationship_type: RelationshipType) -> str:
        """获取关系类型的中文名称"""
        names = {
            RelationshipType.NONE: "陌生人",
            RelationshipType.MENTORSHIP: "师徒",
            RelationshipType.SWORN: "结义",
            RelationshipType.MARRIAGE: "夫妻"
        }
        return names.get(relationship_type, "未知")

    def _get_min_favorability(self, relationship_type: RelationshipType) -> int:
        """获取建立关系所需的最小好感度"""
        requirements = {
            RelationshipType.MENTORSHIP: 0,      # 拜师不需要好感度
            RelationshipType.SWORN: 5000,        # 结义需要5000好感度
            RelationshipType.MARRIAGE: 5000      # 结婚需要5000好感度
        }
        return requirements.get(relationship_type, 0)
