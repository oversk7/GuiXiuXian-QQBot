from sqlalchemy import Integer, BigInteger, String, DateTime, Float, func, Boolean, Index, text, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime
from .db import Base
from enum import Enum as PyEnum


class Gender(str, PyEnum):
    MALE = "男"
    FEMALE = "女"

class Player(Base):
    __tablename__ = "player"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True, comment="平台ID")
    uid: Mapped[int] = mapped_column(Integer, unique=True, comment="自增UID")
    server_id: Mapped[int] = mapped_column(Integer, default=1, server_default='1', index=True, comment="所属区服ID")
    nickname: Mapped[str] = mapped_column(String(24))
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="等级")
    sex: Mapped[Gender] = mapped_column(String(8), default=Gender.MALE, server_default='男', comment="性别")
    exp: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="经验")
    attribute_points: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="可分配属性点")
    region: Mapped[str] = mapped_column(String(32), default="大都会", server_default='大都会', comment="区域")
    x: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="坐标X")
    y: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="坐标Y")

    # 双层坐标系统字段
    real_world_x: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="现实世界X坐标")
    real_world_y: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="现实世界Y坐标")
    dungeon_level: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="当前诡域层级(0=现实世界)")
    dungeon_x: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="诡域内小坐标X(-5到5)")
    dungeon_y: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="诡域内小坐标Y(-5到5)")
    max_dungeon_level: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="到达过的最高诡域层级")

    # 里界系统字段
    inner_realm: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="当前所在里界(None=不在里界)")

    hp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="生命值")
    max_hp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="最大生命值")
    mp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="理智值")
    max_mp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="最大理智值")
    attack: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="攻击力")
    defense: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="防御")
    agility: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="敏捷")
    stamina: Mapped[int] = mapped_column(Integer, default=10, server_default='10', comment="咒抗")
    luck: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="运气")
    resentment: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="怨念值")
    reincarnation_level: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="转数")
    breakthrough_fail_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="当前连续突破失败次数")

    # 新增特殊属性
    critical_rate: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="暴击率(百分比)")
    critical_power: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="暴击力(每点增加0.1倍伤害)")
    combo_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连击率(百分比)")
    counter_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="反击率/反弹率(百分比)")
    dodge_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="闪避率(百分比)")
    accuracy_rate: Mapped[int] = mapped_column(Integer, default=80, server_default='80', comment="命中率(百分比)")
    skill_crit_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="灵爆率(百分比)")
    penetration_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="穿透率(百分比)")
    anti_crit_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="抗暴率(百分比)")

    # 增强战斗属性
    lifesteal_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="吸血率(百分比)")
    immobilize_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="定身率(百分比)")
    true_damage_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="真伤率(百分比)")
    regen_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="回血率(百分比)")

    # 战斗统计
    total_battles: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总战斗次数")
    total_wins: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总胜利次数")
    total_damage_dealt: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总造成伤害")

    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属公会ID")
    guild_contribution: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会贡献值")
    
    vip: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="VIP等级")
    gold: Mapped[int] = mapped_column(BigInteger, default=1000, server_default='1000', comment="货币")
    gold2: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="积分")
    gui_zhu: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="诡烛(氪金专属货币)")
    mini_game_score: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="小游戏积分")
    demon_coins: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="恶魔币(恶魔轮盘排行积分)")
    charm: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="魅力值(通过收礼获得)")
    
    last_sign: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次签到日期")
    sign_streak: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连续签到天数")
    completed_trials: Mapped[str | None] = mapped_column(Text, nullable=True, comment="已通关的试炼列表(JSON数组)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    last_cultivation: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次修炼时间")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后活跃时间(灵田偷菜判定用)")

    # 焚金充能系统
    fenjin_charge: Mapped[float] = mapped_column(Float, default=0, server_default='0', comment="焚金充能百分比(0-100)")
    fenjin_last_update: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="焚金充能最后更新时间")
    fenjin_last_charge: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="焚金最后充值时间(衰减速率)")

    # 双层坐标系统辅助方法
    def is_in_dungeon(self) -> bool:
        """判断是否在诡域中"""
        return (self.dungeon_level or 0) > 0

    def get_current_coordinates(self) -> tuple[int, int]:
        """获取当前活跃坐标"""
        if self.is_in_dungeon():
            return (self.dungeon_x or 0, self.dungeon_y or 0)
        else:
            return (self.real_world_x or 0, self.real_world_y or 0)

    def get_current_region(self) -> str:
        """获取当前区域名称"""
        if self.is_in_dungeon():
            return f"{self.dungeon_level or 0}层诡域"
        else:
            return "大都会"

    def get_completed_trials(self) -> list:
        """获取已通关的试炼列表"""
        import json
        if self.completed_trials:
            try:
                return json.loads(self.completed_trials)
            except:
                return []
        return []

    def is_trial_completed(self, trial_id: str) -> bool:
        """检查指定试炼是否已通关"""
        return trial_id in self.get_completed_trials()

    def add_completed_trial(self, trial_id: str):
        """记录试炼通关"""
        import json
        completed = self.get_completed_trials()
        if trial_id not in completed:
            completed.append(trial_id)
            self.completed_trials = json.dumps(completed, ensure_ascii=False)

    def enter_dungeon(self, level: int):
        """进入指定层级诡域"""
        # 保存现实世界坐标
        if not self.is_in_dungeon():
            # 从现实世界进入副本：保存当前现实世界坐标
            self.real_world_x = self.real_world_x or self.x or 0
            self.real_world_y = self.real_world_y or self.y or 0
        # 如果已经在副本中，不要修改real_world坐标，保持原有的现实世界位置

        # 设置诡域信息
        self.dungeon_level = level
        self.dungeon_x = 0
        self.dungeon_y = 0

        # 更新兼容字段
        self.region = f"{level}层诡域"
        self.x = 0
        self.y = 0

    def exit_dungeon(self):
        """退出诡域，返回现实世界"""
        # 恢复现实世界坐标
        self.x = self.real_world_x or 0
        self.y = self.real_world_y or 0

        # 清除诡域信息
        self.dungeon_level = 0
        self.dungeon_x = 0
        self.dungeon_y = 0

        # 更新兼容字段
        self.region = "大都会"

    def move_in_current_world(self, dx: int, dy: int):
        """在当前世界移动"""
        if self.is_in_dungeon():
            # 诡域内移动，限制范围-5到5
            current_x = self.dungeon_x or 0
            current_y = self.dungeon_y or 0
            new_x = max(-5, min(5, current_x + dx))
            new_y = max(-5, min(5, current_y + dy))
            self.dungeon_x = new_x
            self.dungeon_y = new_y
            self.x = new_x
            self.y = new_y
        else:
            # 现实世界移动，无限制
            current_x = self.real_world_x or 0
            current_y = self.real_world_y or 0
            self.real_world_x = current_x + dx
            self.real_world_y = current_y + dy
            self.x = self.real_world_x
            self.y = self.real_world_y

    def can_enter_dungeon_level(self, level: int) -> bool:
        """检查是否可以进入指定层级诡域

        规则:
        - 第1层总是可以进入
        - 可以进入所有已解锁的层级(1 到 max_dungeon_level)
        - 可以进入下一层(max_dungeon_level + 1)用于逐层探索
        - 超过 max_dungeon_level + 1 的层不能进入(需要逐层解锁)
        """
        if level <= 0:
            return False
        if level == 1:
            return True  # 第1层总是可以进入

        max_level = self.max_dungeon_level or 0
        # 可以进入所有已解锁的层级 + 下一层(用于逐层探索)
        return level <= max_level + 1

    def unlock_next_dungeon_level(self):
        """解锁下一层诡域（击败当前层怪物后调用）"""
        if self.is_in_dungeon():
            current_level = self.dungeon_level or 0
            max_level = self.max_dungeon_level or 0
            if current_level > max_level:
                self.max_dungeon_level = current_level

    def get_accessible_dungeon_levels(self) -> list[int]:
        """获取可访问的诡域层级列表"""
        max_level = self.max_dungeon_level or 0
        return list(range(1, max_level + 2))  # 1到最高层+1

    def get_available_explorer_chest_levels(self) -> list[int]:
        """获取可以领取深渊探索者宝箱的层级列表"""
        max_level = self.max_dungeon_level or 0
        # 每10层可以领取一个宝箱，从第10层开始
        available_levels = []
        for level in range(10, max_level + 1, 10):
            available_levels.append(level)
        return available_levels

    inventory_capacity: Mapped[int] = mapped_column(Integer, default=80, server_default='80', nullable=False, comment="背包容量")
    is_secluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="是否闭关")
    seclusion_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="闭关开始时间")
    last_message_board_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看世界留言时间")
    last_private_message_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看私信时间")
    last_system_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看系统公告时间")
    last_guild_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看公会消息时间")
    last_group_openid: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最近活跃QQ群openid")
    last_group_member_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最近活跃QQ群成员ID(用于@)")
    last_group_username: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最近活跃QQ群昵称(用于@展示)")
    daily_gift_purchases: Mapped[str | None] = mapped_column(Text, nullable=True, comment="每日礼物购买记录(JSON格式)")

    # 阴宅系统
    mansion_level: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="阴宅等级(0表示未拥有)")
    mansion_x: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="阴宅X坐标")
    mansion_y: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="阴宅Y坐标")
    mansion_usage_fee: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="阴宅使用费用(其他玩家使用需支付的金币)")
    mansion_allow_others: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text('1'), comment="是否允许其他玩家使用阴宅")
    mansion_willing_to_pay: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text('1'), comment="是否愿意支付费用使用他人阴宅")

    # 师徒系统
    incense: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="香火点数")
    max_apprentice_slots: Mapped[int] = mapped_column(Integer, default=3, server_default='3', comment="最大徒弟位")
    mentor_cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="师徒操作冷却结束时间")

    # [已废弃] 加点分配追踪 - 永久加成已改为从 ElixirUsageLog 精确累加，
    # 加点部分通过残差推导，此字段不再使用。保留列定义避免迁移问题。
    allocated_attrs: Mapped[dict | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
        default=None,
        comment="[废弃] 加点分配追踪JSON - 已改用ElixirUsageLog"
    )

    # 扩展数据(活动、特殊系统等)
    extra_attrs: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="扩展数据JSON(活动数据、特殊系统数据等)"
    )

    # VIP装备专属数据
    vip_equipment_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="VIP装备专属数据(锚点坐标、快照等)"
    )
    vip_skill_cooldown: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="VIP技能冷却时间戳"
    )

    monthly_cards: Mapped[list["MonthlyCard"]] = relationship("MonthlyCard", back_populates="player")

    # 表约束
    __table_args__ = (
        # 阴宅位置唯一约束：同一位置只能有一个阴宅
        Index(
            'idx_mansion_location_unique',
            'server_id', 'mansion_x', 'mansion_y',
            unique=True,
            postgresql_where=text('mansion_level > 0 AND mansion_x IS NOT NULL AND mansion_y IS NOT NULL'),
            sqlite_where=text('mansion_level > 0 AND mansion_x IS NOT NULL AND mansion_y IS NOT NULL')
        ),
    )

    async def get_effective_inventory_capacity(self, session) -> int:
        """获取有效背包容量（包含月卡加成和VIP装备加成）"""
        from .monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, self.id)
        bonus = benefits["inventory_bonus"]

        # VIP装备背包加成（龙影闪: +200格，再额外+10%）
        from sqlalchemy import select
        from .inventory import ItemInstance
        stmt = select(ItemInstance.id).where(
            ItemInstance.player_id == self.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id == "vip_longying_flash"
        )
        result = await session.execute(stmt)
        if result.scalars().first():
            bonus += 200 + int((self.inventory_capacity + 200) * 0.10)

        return self.inventory_capacity + bonus

    async def get_effective_attributes(self, session=None) -> dict:
        """获取有效属性（包含装备加成、丹药加成、临时buff加成和宠物加成）

        返回包含所有属性的字典，这是玩家的最终有效属性
        注意：装备加成已经通过_persist_bonus机制直接应用到玩家属性上
        """
        # 当前属性值（已包含装备加成和永久丹药加成）
        base_attrs = {
            "max_hp": self.max_hp,
            "max_mp": self.max_mp,
            "attack": self.attack,
            "defense": self.defense,
            "agility": self.agility,
            "luck": self.luck,
            "critical_rate": self.critical_rate,
            "critical_power": self.critical_power,
            "combo_rate": self.combo_rate,
            "counter_rate": self.counter_rate,
            "dodge_rate": self.dodge_rate,
            "accuracy_rate": self.accuracy_rate,
            "skill_crit_rate": self.skill_crit_rate,
            "penetration_rate": self.penetration_rate,
            "anti_crit_rate": self.anti_crit_rate,
            # 增强战斗属性
            "lifesteal_rate": self.lifesteal_rate,
            "immobilize_rate": self.immobilize_rate,
            "true_damage_rate": self.true_damage_rate,
            "regen_rate": self.regen_rate,
        }

        if session:
            # 添加临时buff加成
            from .temporary_buff import TemporaryBuff
            buff_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, self.id)
            for attr, bonus in buff_bonuses.items():
                if attr in base_attrs:
                    base_attrs[attr] += bonus

            # 添加宠物属性加成（宠物加成未持久化，需动态计算）
            from ..domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory
            AttributeCalculatorFactory.get_instance()  # 确保工厂已初始化
            pet_source = AttributeCalculatorFactory._pet_source
            if pet_source:
                pet_full = await pet_source.calculate_full_bonus(self, session)
                for attr_key, val in pet_full.items():
                    if attr_key in base_attrs:
                        base_attrs[attr_key] += val

        return base_attrs

    async def get_effective_battle_attributes(self, session=None) -> dict:
        """获取有效战斗属性（仅包含战斗相关属性）

        返回格式化后的战斗属性字典，用于战斗系统
        这是get_effective_attributes的子集，只包含战斗相关属性
        """
        # 获取完整的有效属性
        all_attrs = await self.get_effective_attributes(session)

        # 只返回战斗相关属性
        battle_attrs = {
            "critical_rate": all_attrs["critical_rate"],
            "critical_power": all_attrs["critical_power"],
            "combo_rate": all_attrs["combo_rate"],
            "counter_rate": all_attrs["counter_rate"],
            "dodge_rate": all_attrs["dodge_rate"],
            "accuracy_rate": all_attrs["accuracy_rate"],
            "skill_crit_rate": all_attrs["skill_crit_rate"],
            "penetration_rate": all_attrs["penetration_rate"],
            "anti_crit_rate": all_attrs["anti_crit_rate"],
            # 增强战斗属性
            "lifesteal_rate": all_attrs["lifesteal_rate"],
            "immobilize_rate": all_attrs["immobilize_rate"],
            "true_damage_rate": all_attrs["true_damage_rate"],
            "regen_rate": all_attrs["regen_rate"],
        }

        return battle_attrs

    # 角色创建时的初始属性值（与Player模型default一致）
    INIT_ATTRS = {
        "max_hp": 20, "max_mp": 20, "attack": 1, "defense": 0,
        "agility": 5, "luck": 1,
        "critical_rate": 5, "critical_power": 0, "combo_rate": 0,
        "counter_rate": 0, "dodge_rate": 0, "accuracy_rate": 80,
        "skill_crit_rate": 0, "penetration_rate": 0, "anti_crit_rate": 0,
        "lifesteal_rate": 0, "immobilize_rate": 0, "true_damage_rate": 0, "regen_rate": 0,
    }

    async def get_attribute_breakdown(self, session=None) -> dict:
        """获取属性来源分解

        返回格式：
        {
            "base": {...},         # 基础属性（初始值 + 加点，残差推导）
            "equipment": {...},    # 装备加成
            "permanent": {...},    # 永久加成（从 ElixirUsageLog 精确累加）
            "vip_equipment": {...},# VIP装备永久加成
            "pet": {...},          # 宠物伙伴加成
            "temporary": {...},    # 临时buff加成
            "total": {...}         # 最终有效属性
        }

        permanent 从 ElixirUsageLog 获取（source of truth），
        base = 存储值 - permanent - equipment - vip（残差，包含 INIT + 加点）。
        """
        from ..config import config as gcfg
        from sqlalchemy import select

        INIT = self.INIT_ATTRS

        # ---- 装备加成（精确：直接读取 _persist_bonus）----
        equipment_bonus = {k: 0 for k in INIT}
        if session:
            from ..models.inventory import ItemInstance
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == self.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
            )
            for eq in (await session.execute(stmt)).scalars().all():
                for k, v in ((eq.extra_attrs or {}).get("_persist_bonus", {})).items():
                    if k in equipment_bonus:
                        equipment_bonus[k] += int(v)

        # ---- VIP装备永久加成（精确）----
        vip_equipment_bonus = {k: 0 for k in INIT}
        if session:
            from .vip_equipment_bonus import VIPEquipmentBonus
            stmt = select(VIPEquipmentBonus).where(VIPEquipmentBonus.player_id == self.id)
            vip_record = (await session.execute(stmt)).scalars().first()
            if vip_record:
                for attr, value in vip_record.get_total_bonus().items():
                    if attr in vip_equipment_bonus:
                        vip_equipment_bonus[attr] = int(value)

        # ---- 临时buff加成（精确）----
        temporary_bonus = {k: 0 for k in INIT}
        if session:
            from .temporary_buff import TemporaryBuff
            buff_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, self.id)
            for attr, bonus in buff_bonuses.items():
                if attr in temporary_bonus:
                    temporary_bonus[attr] = bonus

        # ---- 宠物加成（精确）----
        pet_bonus_dict = {k: 0 for k in INIT}
        if session:
            from ..domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory
            AttributeCalculatorFactory.get_instance()
            pet_source = AttributeCalculatorFactory._pet_source
            if pet_source:
                pet_full = await pet_source.calculate_full_bonus(self, session)
                for attr_key, val in pet_full.items():
                    if attr_key in pet_bonus_dict:
                        pet_bonus_dict[attr_key] = val

        # ---- 永久加成（从 ElixirUsageLog 精确累加）----
        permanent_bonus = {k: 0 for k in INIT}
        if session:
            from .elixir_usage import ElixirUsageLog
            permanent_total = await ElixirUsageLog.get_total_attribute_changes(session, self.id)
            for attr, value in permanent_total.items():
                if attr in permanent_bonus:
                    permanent_bonus[attr] = value

        # ---- 基础属性（残差 = 存储值 - permanent - equipment - vip）----
        base_attrs = {}
        for attr in INIT:
            current = getattr(self, attr, INIT[attr])
            base_attrs[attr] = current - permanent_bonus[attr] - equipment_bonus[attr] - vip_equipment_bonus[attr]

        # ---- 计算最终属性 ----
        total_attrs = {}
        for attr in INIT:
            total_attrs[attr] = (
                base_attrs[attr] +
                permanent_bonus[attr] +
                equipment_bonus[attr] +
                vip_equipment_bonus[attr] +
                temporary_bonus[attr] +
                pet_bonus_dict[attr]
            )

        return {
            "base": base_attrs,
            "equipment": equipment_bonus,
            "permanent": permanent_bonus,
            "vip_equipment": vip_equipment_bonus,
            "temporary": temporary_bonus,
            "pet": pet_bonus_dict,
            "total": total_attrs
        }

    def format_battle_attributes(self) -> str:
        """格式化显示战斗属性"""
        attrs = self.get_effective_battle_attributes()

        # 计算暴击倍数显示（基础1.5倍 + 暴击力*0.1倍）
        crit_multiplier = 1.5 + (attrs['critical_power'] * 0.1)

        lines = [
            "⚔️ 战斗属性 ⚔️",
            f"💥 暴击率: {attrs['critical_rate']}%",
            f"💢 暴击力: {crit_multiplier:.1f}倍",
            f"🔄 连击率: {attrs['combo_rate']}%",
            f"🛡️ 反击率: {attrs['counter_rate']}%",
            f"⚡ 闪避率: {attrs['dodge_rate']}%",
            f"🎯 命中率: {attrs['accuracy_rate']}%",
            f"✨ 灵爆率: {attrs['skill_crit_rate']}%",
            f"🗡️ 穿透率: {attrs['penetration_rate']}%",
            f"🛡️ 抗暴率: {attrs['anti_crit_rate']}%"
        ]

        return "\n".join(lines)




async def get_player_by_uid(uid: str):
    from sqlalchemy import select
    from .db import get_session
    
    async with get_session() as session:
        result = await session.execute(select(Player).where(Player.uid == uid))
        return result.scalars().first()
