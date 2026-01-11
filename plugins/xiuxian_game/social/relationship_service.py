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
        daily_limit: int = 30
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
            daily_limit: 每日好感度上限(默认30)

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
        relationship.favorability = min(100, relationship.favorability + total_favorability)
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
        1. 必须在同一市集(region)
        2. 不能转移跑商商品(GOODS类型)
        3. 可以转移材料、装备、好感度礼物(GIFT类型不消耗)
        4. 物品实际转移到接收者背包,不增加好感度

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

        # 3. 检查地理约束(同一市集)
        # 使用region字段判断(市场位置)
        if sender.region != receiver.region:
            return False, f"必须和{receiver.nickname}在同一地点才能当面送礼\n当前位置: {sender.region}\n对方位置: {receiver.region}"

        # 4. 获取物品配置
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            return False, f"物品「{item_name}」不存在"

        # 5. 检查物品类型
        if item_config.type == ItemType.GOODS:
            return False, f"禁止转移跑商商品类物品"

        # 注意: 允许转移GIFT类型,但不消耗也不加好感度(仅物理转移)

        # 6. 检查背包数量
        has_item = await self._item_repo.has_item(sender_id, item_config.item_id, quantity)
        if not has_item:
            return False, f"你没有足够的「{item_name}」"

        # 7. 检查接收者背包空间
        # 获取接收者已使用的背包格数
        receiver_items = await self._item_repo.get_all_non_equipment_non_fish(receiver.id)
        used_slots = len(receiver_items)

        # 获取接收者的有效背包容量
        effective_capacity = await receiver.get_effective_inventory_capacity(self._uow.session)

        available_space = effective_capacity - used_slots

        if available_space <= 0:
            return False, f"{receiver.nickname}的背包已满,无法接收物品"

        # 8. 计算实际可转移数量(考虑背包限制)
        # 如果物品可堆叠且已有相同物品,可以全部转移
        # 否则受限于可用格数
        max_addable = quantity  # 默认可以全部转移

        # 检查接收者是否已有该物品
        existing_items = await self._item_repo.get_items_by_item_id(receiver.id, item_config.item_id)
        if not existing_items:
            # 没有该物品,需要占用新格子
            max_addable = min(quantity, available_space)

        # 9. 扣除发送者物品
        success = await self._item_repo.consume_item(sender_id, item_config.item_id, max_addable)
        if not success:
            return False, f"你没有足够的「{item_name}」"

        # 10. 添加到接收者背包
        try:
            await self._item_repo.add_item(receiver.id, item_config.item_id, max_addable)
        except ValueError as e:
            # 理论上不会发生(已预估容量),兜底:返还给发送者
            await self._item_repo.add_item(sender_id, item_config.item_id, max_addable)
            return False, f"送礼失败,物品已退还:{str(e)}"

        # 11. 返回成功消息
        if max_addable < quantity:
            leftover = quantity - max_addable
            return (
                True,
                f"成功向{receiver.nickname}当面送出{max_addable}个「{item_name}」\n"
                f"(剩余{leftover}个因背包空间不足未送出)"
            )
        else:
            return (
                True,
                f"成功向{receiver.nickname}当面送出{max_addable}个「{item_name}」"
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
                        return False, f"{p1.nickname}与{p2.nickname}的好感度不足(需要60,当前{favorability})"
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

    async def end_mentorship(
        self,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        结束师徒关系

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 提示信息)
        """
        # 查找师徒关系
        from sqlalchemy import or_
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id
                ),
                PlayerRelationship.relationship_type == RelationshipType.MENTORSHIP.value
            )
        )
        result = await self._uow.session.execute(stmt)
        relationship = result.scalar_one_or_none()

        if not relationship:
            return False, "你当前没有师徒关系"

        # 获取师/徒ID
        other_id = relationship.target_id if relationship.player_id == player_id else relationship.player_id
        other = await self._player_repo.get_by_id(other_id)

        # 解除师徒关系
        relationship.relationship_type = RelationshipType.NONE.value
        relationship.established_at = None

        role = "师父" if relationship.player_id == player_id else "徒弟"
        return True, f"你已与{other.nickname if other else '对方'}解除师徒关系"

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
            RelationshipType.MENTORSHIP: 40,
            RelationshipType.SWORN: 60,
            RelationshipType.MARRIAGE: 80
        }
        return requirements.get(relationship_type, 0)
