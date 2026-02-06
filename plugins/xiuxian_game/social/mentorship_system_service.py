"""
师徒系统服务层

核心功能：
1. 拜师/收徒
2. 香火计算和发放
3. 叛师/逐出师门处理
4. 正常出师处理
5. 香火商店

规则说明：
- 徒弟要求：注册≥24小时
- 师父要求：境界≥徒弟+50 或 转数>徒弟
- 师父初始3个徒弟位，可用香火购买更多
- 每名徒弟使师父修炼效率-1%
- 徒弟升级时师父获得香火（按升级所需经验计算）
- 叛师：徒弟扣除属性，师父扣除香火，双方进入冷却
- 逐出/出师：双方进入冷却
"""
import math
import random
from datetime import datetime, timedelta
from typing import Tuple, List, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.player_relationship import PlayerRelationship, RelationshipType
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
from ..utils import calculate_level_up_exp


# ==================== 配置常量 ====================

# 冷却时间配置（天）
COOLDOWN_BETRAY = 7  # 叛师/被逐出后的冷却
COOLDOWN_NORMAL = 3  # 正常出师后的冷却

# 拜师申请配置
REQUEST_EXPIRE_DAYS = 7  # 申请7天未处理自动过期
REQUEST_REJECT_COOLDOWN_HOURS = 24  # 被拒绝后24小时内不能再次申请同一师父

# 香火计算配置
INCENSE_DIVISOR = 5000  # 香火 = ceil(升级经验 / 5000)
POST_REINCARNATION_INCENSE = 15  # 一转后每级固定贡献香火

# 叛师惩罚配置
BETRAY_ATTRIBUTE_LOSS_MIN = 0.10  # 叛师最小属性损失比例
BETRAY_ATTRIBUTE_LOSS_MAX = 0.20  # 叛师最大属性损失比例
BETRAY_INCENSE_LOSS_RATE = 0.50  # 师父损失该徒弟贡献香火的比例

# 徒弟位配置
INITIAL_APPRENTICE_SLOTS = 3  # 初始徒弟位
SLOT_PURCHASE_COST = 500  # 购买一个徒弟位的香火成本

# 修炼效率惩罚
CULTIVATION_PENALTY_PER_APPRENTICE = 0.01  # 每个徒弟减少1%修炼效率


class MentorshipSystemService:
    """师徒系统服务"""

    def __init__(
        self,
        player_repo: PlayerRepository,
        relationship_repo: PlayerRelationshipRepository,
        session: AsyncSession
    ):
        self._player_repo = player_repo
        self._relationship_repo = relationship_repo
        self._session = session

    # ==================== 核心查询方法 ====================

    async def get_master(self, player_id: str) -> Optional[Player]:
        """获取玩家的师父"""
        # 查找师徒关系，当前玩家不是master_id的记录
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id
                ),
                PlayerRelationship.relationship_type == RelationshipType.MENTORSHIP.value,
                PlayerRelationship.master_id != player_id  # 玩家不是师父，即是徒弟
            )
        )
        result = await self._session.execute(stmt)
        relationship = result.scalar_one_or_none()

        if relationship and relationship.master_id:
            return await self._player_repo.get_by_id(relationship.master_id)
        return None

    async def get_apprentices(self, player_id: str) -> List[Tuple[Player, PlayerRelationship]]:
        """获取玩家的所有徒弟"""
        # 查找师徒关系，当前玩家是master_id的记录
        stmt = select(PlayerRelationship).where(
            and_(
                PlayerRelationship.master_id == player_id,
                PlayerRelationship.relationship_type == RelationshipType.MENTORSHIP.value
            )
        )
        result = await self._session.execute(stmt)
        relationships = result.scalars().all()

        apprentices = []
        for rel in relationships:
            # 徒弟是关系中不是master_id的那个
            apprentice_id = rel.player_id if rel.player_id != player_id else rel.target_id
            apprentice = await self._player_repo.get_by_id(apprentice_id)
            if apprentice:
                apprentices.append((apprentice, rel))

        return apprentices

    async def get_apprentice_count(self, player_id: str) -> int:
        """获取当前徒弟数量"""
        apprentices = await self.get_apprentices(player_id)
        return len(apprentices)

    async def get_mentorship_relationship(self, player_id: str) -> Optional[PlayerRelationship]:
        """获取玩家参与的师徒关系"""
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id
                ),
                PlayerRelationship.relationship_type == RelationshipType.MENTORSHIP.value
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ==================== 资格检查方法 ====================

    async def can_become_apprentice(self, player: Player) -> Tuple[bool, str]:
        """
        检查玩家是否可以拜师

        要求：
        1. 注册≥24小时
        2. 当前无师父
        3. 不在冷却期
        """
        # 检查注册时间
        if not player.created_at:
            return False, "无法获取注册时间"

        hours_since_register = (datetime.now() - player.created_at).total_seconds() / 3600
        if hours_since_register < 24:
            remaining_hours = 24 - hours_since_register
            return False, f"注册时间不足24小时，还需等待{remaining_hours:.1f}小时"

        # 检查是否已有师父
        master = await self.get_master(player.id)
        if master:
            return False, f"你已有师父【{master.nickname}】，需先脱离师门才能拜新师"

        # 检查冷却期
        if player.mentor_cooldown_until and player.mentor_cooldown_until > datetime.now():
            remaining = player.mentor_cooldown_until - datetime.now()
            days = remaining.days
            hours = remaining.seconds // 3600
            return False, f"你正处于师徒冷却期，还需等待{days}天{hours}小时"

        return True, "可以拜师"

    async def can_accept_apprentice(
        self,
        master: Player,
        apprentice: Player
    ) -> Tuple[bool, str]:
        """
        检查是否可以收徒

        要求：
        1. 师父境界≥徒弟+50 或 转数>徒弟
        2. 师父有空闲徒弟位
        3. 师父不在冷却期
        """
        # 检查境界或转数要求
        level_diff = master.level - apprentice.level
        reincarnation_diff = master.reincarnation_level - apprentice.reincarnation_level

        if level_diff < 50 and reincarnation_diff <= 0:
            return False, f"收徒条件不满足：需要境界高于徒弟50级(当前差{level_diff}级)或转数更高(当前差{reincarnation_diff}转)"

        # 检查徒弟位
        current_apprentice_count = await self.get_apprentice_count(master.id)
        max_slots = master.max_apprentice_slots or INITIAL_APPRENTICE_SLOTS

        if current_apprentice_count >= max_slots:
            return False, f"徒弟位已满({current_apprentice_count}/{max_slots})，可用香火购买更多徒弟位"

        # 检查冷却期
        if master.mentor_cooldown_until and master.mentor_cooldown_until > datetime.now():
            remaining = master.mentor_cooldown_until - datetime.now()
            days = remaining.days
            hours = remaining.seconds // 3600
            return False, f"你正处于师徒冷却期，还需等待{days}天{hours}小时"

        return True, "可以收徒"

    # ==================== 核心业务方法 ====================

    async def establish_mentorship(
        self,
        master_id: str,
        apprentice_uid: int
    ) -> Tuple[bool, str]:
        """
        建立师徒关系

        Args:
            master_id: 师父ID
            apprentice_uid: 徒弟UID

        Returns:
            (是否成功, 消息)
        """
        # 获取师父和徒弟
        master = await self._player_repo.get_by_id(master_id)
        apprentice = await self._player_repo.get_by_uid(apprentice_uid)

        if not master:
            return False, "师父不存在"
        if not apprentice:
            return False, f"未找到UID为{apprentice_uid}的玩家"
        if master.id == apprentice.id:
            return False, "不能收自己为徒"

        # 检查徒弟资格
        can_be_apprentice, msg = await self.can_become_apprentice(apprentice)
        if not can_be_apprentice:
            return False, f"徒弟条件不满足：{msg}"

        # 检查师父资格
        can_accept, msg = await self.can_accept_apprentice(master, apprentice)
        if not can_accept:
            return False, f"师父条件不满足：{msg}"

        # 获取或创建关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            master.id, apprentice.id
        )

        # 检查是否已有其他关系
        if relationship.relationship_type != RelationshipType.NONE.value:
            current_type = relationship.relationship_type
            type_names = {
                RelationshipType.MENTORSHIP.value: "师徒",
                RelationshipType.SWORN.value: "结义",
                RelationshipType.MARRIAGE.value: "夫妻"
            }
            return False, f"你们已有{type_names.get(current_type, '其他')}关系"

        # 建立师徒关系
        relationship.relationship_type = RelationshipType.MENTORSHIP.value
        relationship.master_id = master.id
        relationship.apprentice_level_at_start = apprentice.level
        relationship.total_incense_contributed = 0
        relationship.established_at = datetime.now()

        return True, f"恭喜！【{apprentice.nickname}】正式拜【{master.nickname}】为师！\n徒弟当前等级：Lv.{apprentice.level}"
    # ==================== 拜师申请方法 ====================

    # 拜师申请配置常量
    REQUEST_EXPIRE_DAYS = 7  # 申请7天未处理自动过期
    REQUEST_REJECT_COOLDOWN_HOURS = 24  # 被拒绝后24小时内不能再次申请同一师父

    async def submit_mentorship_request(
        self,
        apprentice_id: str,
        master_uid: int
    ) -> Tuple[bool, str]:
        """
        徒弟发起拜师申请

        Args:
            apprentice_id: 徒弟ID
            master_uid: 师父UID

        Returns:
            (是否成功, 消息)
        """
        # 获取徒弟和师父
        apprentice = await self._player_repo.get_by_id(apprentice_id)
        master = await self._player_repo.get_by_uid(master_uid)

        if not apprentice:
            return False, "玩家不存在"
        if not master:
            return False, f"未找到UID为{master_uid}的玩家"
        if master.id == apprentice.id:
            return False, "不能拜自己为师"

        # 检查徒弟资格
        can_be_apprentice, msg = await self.can_become_apprentice(apprentice)
        if not can_be_apprentice:
            return False, msg

        # 检查师父资格
        can_accept, msg = await self.can_accept_apprentice(master, apprentice)
        if not can_accept:
            return False, msg

        # 获取或创建关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            apprentice.id, master.id
        )

        # 检查是否已有其他关系
        if relationship.relationship_type != RelationshipType.NONE.value:
            current_type = relationship.relationship_type
            type_names = {
                RelationshipType.MENTORSHIP.value: "师徒",
                RelationshipType.SWORN.value: "结义",
                RelationshipType.MARRIAGE.value: "夫妻"
            }
            return False, f"你们已有{type_names.get(current_type, '其他')}关系"

        # 检查是否有待处理的申请
        if relationship.mentorship_request_status == "pending":
            return False, f"你已经向【{master.nickname}】发起过拜师申请，请等待处理"

        # 检查被拒绝后的冷却期
        if relationship.mentorship_reject_time:
            cooldown_end = relationship.mentorship_reject_time + timedelta(hours=REQUEST_REJECT_COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                remaining_hours = (cooldown_end - datetime.now()).total_seconds() / 3600
                return False, f"你的申请被拒绝后需要等待24小时才能再次申请，剩余{remaining_hours:.1f}小时"

        # 创建申请
        relationship.mentorship_request_status = "pending"
        relationship.mentorship_request_time = datetime.now()
        relationship.mentorship_reject_time = None
        relationship.master_id = master.id  # 暂时标记一下谁是师父

        return True, (
            f"✅ 已向【{master.nickname}】(UID: {master.uid})发起拜师申请！\n"
            f"━━━━━━━━━━━━━\n"
            f"对方可通过【交互 师徒使者 拜师申请】查看\n"
            f"申请将在7天后自动过期"
        )


    async def get_pending_requests(self, master_id: str) -> List[Tuple[Player, PlayerRelationship]]:
        """
        获取师父收到的待处理拜师申请列表

        Returns:
            [(徒弟Player对象, 关系记录), ...]
        """
        # 查询所有pending状态的申请，且master_id匹配
        stmt = select(PlayerRelationship).where(
            and_(
                PlayerRelationship.mentorship_request_status == "pending",
                PlayerRelationship.master_id == master_id
            )
        )
        result = await self._session.execute(stmt)
        relationships = list(result.scalars().all())

        # 过滤过期申请并获取徒弟信息
        valid_requests = []
        now = datetime.now()

        for rel in relationships:
            # 检查是否过期
            if rel.mentorship_request_time:
                expire_time = rel.mentorship_request_time + timedelta(days=REQUEST_EXPIRE_DAYS)
                if now > expire_time:
                    # 过期了，清除申请状态
                    rel.mentorship_request_status = None
                    rel.mentorship_request_time = None
                    rel.master_id = None
                    continue

            # 获取徒弟信息
            apprentice_id = rel.player_id if rel.target_id == master_id else rel.target_id
            apprentice = await self._player_repo.get_by_id(apprentice_id)
            if apprentice:
                valid_requests.append((apprentice, rel))

        return valid_requests


    async def approve_mentorship_request(
        self,
        master_id: str,
        apprentice_uid: int
    ) -> Tuple[bool, str]:
        """
        师父同意拜师申请

        Args:
            master_id: 师父ID
            apprentice_uid: 徒弟UID

        Returns:
            (是否成功, 消息)
        """
        # 获取师父和徒弟
        master = await self._player_repo.get_by_id(master_id)
        apprentice = await self._player_repo.get_by_uid(apprentice_uid)

        if not master:
            return False, "玩家不存在"
        if not apprentice:
            return False, f"未找到UID为{apprentice_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            apprentice.id, master.id
        )

        # 检查申请状态
        if relationship.mentorship_request_status != "pending":
            return False, f"【{apprentice.nickname}】没有向你发起拜师申请"

        if relationship.master_id != master_id:
            return False, f"申请的师父不是你"

        # 检查申请是否过期
        if relationship.mentorship_request_time:
            expire_time = relationship.mentorship_request_time + timedelta(days=REQUEST_EXPIRE_DAYS)
            if datetime.now() > expire_time:
                # 过期了，清除申请
                relationship.mentorship_request_status = None
                relationship.mentorship_request_time = None
                relationship.master_id = None
                return False, "申请已过期"

        # 再次检查师父资格（可能状态已变化）
        can_accept, msg = await self.can_accept_apprentice(master, apprentice)
        if not can_accept:
            # 清除申请状态
            relationship.mentorship_request_status = None
            relationship.mentorship_request_time = None
            relationship.master_id = None
            return False, f"收徒条件不满足：{msg}"

        # 建立师徒关系
        relationship.relationship_type = RelationshipType.MENTORSHIP.value
        relationship.master_id = master.id
        relationship.apprentice_level_at_start = apprentice.level
        relationship.total_incense_contributed = 0
        relationship.established_at = datetime.now()

        # 清除申请状态
        relationship.mentorship_request_status = None
        relationship.mentorship_request_time = None

        return True, (
            f"🎉 恭喜！【{apprentice.nickname}】正式拜你为师！\n"
            f"━━━━━━━━━━━━━\n"
            f"徒弟当前等级：Lv.{apprentice.level}\n"
            f"徒弟一转前升级将贡献香火\n"
            f"师徒缘分，传承不息！"
        )


    async def reject_mentorship_request(
        self,
        master_id: str,
        apprentice_uid: int
    ) -> Tuple[bool, str]:
        """
        师父拒绝拜师申请

        Args:
            master_id: 师父ID
            apprentice_uid: 徒弟UID

        Returns:
            (是否成功, 消息)
        """
        # 获取师父和徒弟
        master = await self._player_repo.get_by_id(master_id)
        apprentice = await self._player_repo.get_by_uid(apprentice_uid)

        if not master:
            return False, "玩家不存在"
        if not apprentice:
            return False, f"未找到UID为{apprentice_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            apprentice.id, master.id
        )

        # 检查申请状态
        if relationship.mentorship_request_status != "pending":
            return False, f"【{apprentice.nickname}】没有向你发起拜师申请"

        if relationship.master_id != master_id:
            return False, f"申请的师父不是你"

        # 拒绝申请
        relationship.mentorship_request_status = None
        relationship.mentorship_request_time = None
        relationship.mentorship_reject_time = datetime.now()  # 记录拒绝时间，用于冷却
        relationship.master_id = None

        return True, (
            f"已拒绝【{apprentice.nickname}】的拜师申请\n"
            f"对方24小时内不能再次申请"
        )


    async def cancel_mentorship_request(
        self,
        apprentice_id: str,
        master_uid: int
    ) -> Tuple[bool, str]:
        """
        徒弟撤销拜师申请

        Args:
            apprentice_id: 徒弟ID
            master_uid: 师父UID

        Returns:
            (是否成功, 消息)
        """
        # 获取徒弟和师父
        apprentice = await self._player_repo.get_by_id(apprentice_id)
        master = await self._player_repo.get_by_uid(master_uid)

        if not apprentice:
            return False, "玩家不存在"
        if not master:
            return False, f"未找到UID为{master_uid}的玩家"

        # 查找关系记录
        relationship = await self._relationship_repo.get_or_create_relationship(
            apprentice.id, master.id
        )

        # 检查申请状态
        if relationship.mentorship_request_status != "pending":
            return False, f"你没有向【{master.nickname}】发起拜师申请"

        if relationship.master_id != master.id:
            return False, "申请记录异常"

        # 撤销申请
        relationship.mentorship_request_status = None
        relationship.mentorship_request_time = None
        relationship.master_id = None

        return True, f"已撤销向【{master.nickname}】的拜师申请"



    async def betray_master(self, apprentice_id: str) -> Tuple[bool, str]:
        """
        徒弟叛师（主动脱离师门，有惩罚）

        惩罚：
        1. 徒弟随机扣除10-20%总属性点
        2. 师父扣除该徒弟贡献的50%香火
        3. 双方进入7天冷却期
        """
        # 获取徒弟
        apprentice = await self._player_repo.get_by_id(apprentice_id)
        if not apprentice:
            return False, "玩家不存在"

        # 获取师父
        master = await self.get_master(apprentice_id)
        if not master:
            return False, "你当前没有师父"

        # 获取师徒关系（直接查询两个人之间的关系，避免多条记录问题）
        relationship = await self._relationship_repo.get_relationship(apprentice_id, master.id)
        if not relationship:
            return False, "师徒关系记录不存在"
        master_name = master.nickname if master else "未知"

        # 计算徒弟属性惩罚
        loss_rate = random.uniform(BETRAY_ATTRIBUTE_LOSS_MIN, BETRAY_ATTRIBUTE_LOSS_MAX)
        attrs_to_punish = ["attack", "defense", "agility", "stamina", "max_hp", "max_mp"]
        total_loss = 0

        punishment_details = []
        for attr in attrs_to_punish:
            current_value = getattr(apprentice, attr, 0)
            if current_value > 10:  # 保留最低10点
                loss = int(current_value * loss_rate)
                new_value = max(10, current_value - loss)
                actual_loss = current_value - new_value
                if actual_loss > 0:
                    setattr(apprentice, attr, new_value)
                    total_loss += actual_loss
                    attr_names = {
                        "attack": "攻击", "defense": "防御", "agility": "敏捷",
                        "stamina": "咒抗", "max_hp": "生命", "max_mp": "理智"
                    }
                    punishment_details.append(f"{attr_names.get(attr, attr)}-{actual_loss}")

        # 计算师父香火损失
        incense_loss = int(relationship.total_incense_contributed * BETRAY_INCENSE_LOSS_RATE)
        if master and incense_loss > 0:
            master.incense = max(0, (master.incense or 0) - incense_loss)

        # 设置冷却期
        cooldown_until = datetime.now() + timedelta(days=COOLDOWN_BETRAY)
        apprentice.mentor_cooldown_until = cooldown_until
        if master:
            master.mentor_cooldown_until = cooldown_until

        # 解除师徒关系
        relationship.relationship_type = RelationshipType.NONE.value
        relationship.master_id = None
        relationship.apprentice_level_at_start = 0
        relationship.total_incense_contributed = 0
        relationship.established_at = None

        # 构建消息
        punishment_str = "、".join(punishment_details) if punishment_details else "无"
        msg = (
            f"你已叛出【{master_name}】的师门！\n"
            f"━━━━━━━━━━━━━\n"
            f"叛师惩罚：\n"
            f"  属性损失({int(loss_rate*100)}%)：{punishment_str}\n"
            f"  冷却期：{COOLDOWN_BETRAY}天\n"
            f"师父损失香火：{incense_loss}\n"
            f"━━━━━━━━━━━━━\n"
            f"背叛师门者，天道不容！"
        )

        return True, msg

    async def expel_apprentice(
        self,
        master_id: str,
        apprentice_uid: int
    ) -> Tuple[bool, str]:
        """
        师父逐出徒弟（无惩罚，但有冷却）
        """
        # 获取师父和徒弟
        master = await self._player_repo.get_by_id(master_id)
        apprentice = await self._player_repo.get_by_uid(apprentice_uid)

        if not master:
            return False, "玩家不存在"
        if not apprentice:
            return False, f"未找到UID为{apprentice_uid}的徒弟"

        # 获取师徒关系（直接查询两个人之间的关系，避免多条记录问题）
        relationship = await self._relationship_repo.get_relationship(apprentice.id, master_id)
        if not relationship or relationship.master_id != master_id:
            return False, f"【{apprentice.nickname}】不是你的徒弟"

        # 设置冷却期
        cooldown_until = datetime.now() + timedelta(days=COOLDOWN_NORMAL)
        master.mentor_cooldown_until = cooldown_until
        apprentice.mentor_cooldown_until = cooldown_until

        # 记录徒弟贡献的香火（用于消息显示）
        contributed_incense = relationship.total_incense_contributed

        # 解除师徒关系
        relationship.relationship_type = RelationshipType.NONE.value
        relationship.master_id = None
        relationship.apprentice_level_at_start = 0
        relationship.total_incense_contributed = 0
        relationship.established_at = None

        msg = (
            f"你已将【{apprentice.nickname}】逐出师门\n"
            f"━━━━━━━━━━━━━\n"
            f"徒弟累计贡献香火：{contributed_incense}\n"
            f"双方冷却期：{COOLDOWN_NORMAL}天\n"
            f"━━━━━━━━━━━━━\n"
            f"师徒缘尽，各自珍重"
        )

        return True, msg

    async def graduate_apprentice(
        self,
        master_id: str,
        apprentice_uid: int
    ) -> Tuple[bool, str]:
        """
        徒弟正常出师（荣誉毕业，无惩罚）
        """
        # 获取师父和徒弟
        master = await self._player_repo.get_by_id(master_id)
        apprentice = await self._player_repo.get_by_uid(apprentice_uid)

        if not master:
            return False, "玩家不存在"
        if not apprentice:
            return False, f"未找到UID为{apprentice_uid}的徒弟"

        # 获取师徒关系（直接查询两个人之间的关系，避免多条记录问题）
        relationship = await self._relationship_repo.get_relationship(apprentice.id, master_id)
        if not relationship or relationship.master_id != master_id:
            return False, f"【{apprentice.nickname}】不是你的徒弟"

        # 设置冷却期
        cooldown_until = datetime.now() + timedelta(days=COOLDOWN_NORMAL)
        master.mentor_cooldown_until = cooldown_until
        apprentice.mentor_cooldown_until = cooldown_until

        # 记录徒弟信息
        contributed_incense = relationship.total_incense_contributed
        start_level = relationship.apprentice_level_at_start
        current_level = apprentice.level
        level_growth = current_level - start_level

        # 解除师徒关系
        relationship.relationship_type = RelationshipType.NONE.value
        relationship.master_id = None
        relationship.apprentice_level_at_start = 0
        relationship.total_incense_contributed = 0
        relationship.established_at = None

        msg = (
            f"【{apprentice.nickname}】学有所成，正式出师！\n"
            f"━━━━━━━━━━━━━\n"
            f"入门等级：Lv.{start_level}\n"
            f"出师等级：Lv.{current_level}\n"
            f"成长：+{level_growth}级\n"
            f"累计贡献香火：{contributed_incense}\n"
            f"双方冷却期：{COOLDOWN_NORMAL}天\n"
            f"━━━━━━━━━━━━━\n"
            f"师恩浩荡，前程似锦！"
        )

        return True, msg

    # ==================== 香火系统 ====================

    @staticmethod
    def calculate_incense_reward(level: int) -> int:
        """
        计算升级时师父获得的香火

        公式：香火 = ceil(升级所需经验 / 5000)
        """
        exp_needed = calculate_level_up_exp(level - 1)  # 升到当前级别所需的经验
        return max(1, math.ceil(exp_needed / INCENSE_DIVISOR))

    async def grant_incense_on_level_up(
        self,
        apprentice_id: str,
        old_level: int,
        new_level: int
    ) -> Optional[str]:
        """
        徒弟升级时给师父发放香火

        规则：
        - 徒弟一转前：根据升级经验计算香火（公式：ceil(经验/5000)）
        - 徒弟一转后：每级固定贡献少量香火（鼓励师父让徒弟出师，收新徒弟）

        Returns:
            奖励消息（如果有师父），否则返回None
        """
        # 获取徒弟的师父
        master = await self.get_master(apprentice_id)
        if not master:
            return None

        # 获取师徒关系（直接查询两个人之间的关系，避免多条记录问题）
        relationship = await self._relationship_repo.get_relationship(apprentice_id, master.id)
        if not relationship:
            return None

        # 获取徒弟信息，检查转数
        apprentice = await self._player_repo.get_by_id(apprentice_id)
        if not apprentice:
            return None

        # 计算总香火（可能一次升多级）
        total_incense = 0
        level_count = new_level - old_level

        if apprentice.reincarnation_level >= 1:
            # 一转后：每级固定少量香火
            total_incense = POST_REINCARNATION_INCENSE * level_count
            incense_type = "（一转后固定）"
        else:
            # 一转前：根据经验计算
            for level in range(old_level + 1, new_level + 1):
                total_incense += self.calculate_incense_reward(level)
            incense_type = "（升级奖励）"

        # 发放香火
        master.incense = (master.incense or 0) + total_incense
        relationship.total_incense_contributed = (relationship.total_incense_contributed or 0) + total_incense

        # 构建消息
        msg = f"师父【{master.nickname}】获得香火 +{total_incense}{incense_type}"

        # 一转后提示出师
        if apprentice.reincarnation_level >= 1:
            msg += f"\n💡 徒弟【{apprentice.nickname}】已一转，建议让其出师收新徒获取更多香火"

        return msg

    async def purchase_apprentice_slot(self, player_id: str) -> Tuple[bool, str]:
        """
        用香火购买额外徒弟位
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        current_incense = player.incense or 0
        if current_incense < SLOT_PURCHASE_COST:
            return False, f"香火不足！购买徒弟位需要{SLOT_PURCHASE_COST}香火，当前{current_incense}香火"

        # 扣除香火
        player.incense = current_incense - SLOT_PURCHASE_COST

        # 增加徒弟位
        current_slots = player.max_apprentice_slots or INITIAL_APPRENTICE_SLOTS
        player.max_apprentice_slots = current_slots + 1

        return True, f"购买成功！消耗{SLOT_PURCHASE_COST}香火\n徒弟位：{current_slots} → {current_slots + 1}"

    # ==================== 修炼效率相关 ====================

    async def get_cultivation_penalty(self, player_id: str) -> float:
        """
        获取因徒弟数量导致的修炼效率惩罚

        Returns:
            惩罚比例（如0.02表示减少2%）
        """
        apprentice_count = await self.get_apprentice_count(player_id)
        return apprentice_count * CULTIVATION_PENALTY_PER_APPRENTICE

    # ==================== 信息查询 ====================

    async def get_mentorship_info(self, player_id: str) -> str:
        """获取玩家的师徒信息"""
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return "玩家不存在"

        lines = [
            "🎓 师徒信息",
            "━━━━━━━━━━━━━"
        ]

        # 香火信息
        incense = player.incense or 0
        max_slots = player.max_apprentice_slots or INITIAL_APPRENTICE_SLOTS
        lines.append(f"🔥 香火：{incense}")
        lines.append(f"📋 徒弟位：{max_slots}")

        # 冷却信息
        if player.mentor_cooldown_until and player.mentor_cooldown_until > datetime.now():
            remaining = player.mentor_cooldown_until - datetime.now()
            days = remaining.days
            hours = remaining.seconds // 3600
            lines.append(f"⏰ 冷却中：{days}天{hours}小时")

        # 师父信息
        master = await self.get_master(player_id)
        if master:
            # 获取师徒关系（直接查询两个人之间的关系，避免多条记录问题）
            relationship = await self._relationship_repo.get_relationship(player_id, master.id)
            lines.append("")
            lines.append("👨‍🏫 我的师父")
            lines.append(f"  {master.nickname} [UID:{master.uid}]")
            lines.append(f"  等级：Lv.{master.level} | 转数：{master.reincarnation_level}")
            if relationship:
                lines.append(f"  拜师时等级：Lv.{relationship.apprentice_level_at_start}")
                lines.append(f"  累计贡献香火：{relationship.total_incense_contributed}")

        # 徒弟信息
        apprentices = await self.get_apprentices(player_id)
        current_count = len(apprentices)

        lines.append("")
        lines.append(f"👨‍🎓 我的徒弟 ({current_count}/{max_slots})")

        if apprentices:
            for apprentice, rel in apprentices:
                level_growth = apprentice.level - (rel.apprentice_level_at_start or 0)
                lines.append(f"  • {apprentice.nickname} [UID:{apprentice.uid}]")
                lines.append(f"    Lv.{apprentice.level}(+{level_growth}) | 贡献香火：{rel.total_incense_contributed}")
        else:
            lines.append("  暂无徒弟")

        # 修炼效率惩罚
        if current_count > 0:
            penalty = current_count * CULTIVATION_PENALTY_PER_APPRENTICE * 100
            lines.append("")
            lines.append(f"⚠️ 修炼效率惩罚：-{penalty:.0f}%")

        lines.append("━━━━━━━━━━━━━")

        return "\n".join(lines)
