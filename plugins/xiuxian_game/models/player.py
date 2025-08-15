from sqlalchemy import Integer, BigInteger, String, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
    nickname: Mapped[str] = mapped_column(String(24))
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="等级")
    sex: Mapped[Gender] = mapped_column(String(8), default=Gender.MALE, server_default='男', comment="性别")
    exp: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="经验")
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
    hp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="生命值")
    max_hp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="最大生命值")
    mp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="理智值")
    max_mp: Mapped[int] = mapped_column(Integer, default=20, server_default='20', comment="最大理智值")
    attack: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="攻击力")
    defense: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="防御")
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
    counter_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="反击率(百分比)")
    dodge_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="闪避率(百分比)")
    accuracy_rate: Mapped[int] = mapped_column(Integer, default=80, server_default='80', comment="命中率(百分比)")
    skill_crit_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="灵爆率(百分比)")
    penetration_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="穿透率(百分比)")
    anti_crit_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="抗暴率(百分比)")
    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属公会ID")
    guild_contribution: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会贡献值")
    
    vip: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="VIP等级")
    gold: Mapped[int] = mapped_column(BigInteger, default=1000, server_default='1000', comment="货币")
    gold2: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="积分")
    
    last_sign: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次签到日期")
    sign_streak: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连续签到天数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    last_cultivation: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次修炼时间")

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
        """检查是否可以进入指定层级诡域"""
        if level <= 0:
            return False
        if level == 1:
            return True  # 第1层总是可以进入
        return level <= (self.max_dungeon_level or 0) + 1  # 只能进入已通过层级+1

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

    inventory_capacity: Mapped[int] = mapped_column(Integer, default=50, server_default='50', nullable=False, comment="背包容量")
    is_secluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default='False', comment="是否闭关")
    seclusion_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="闭关开始时间")
    last_message_board_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看留言板时间")

    monthly_cards: Mapped[list["MonthlyCard"]] = relationship("MonthlyCard", back_populates="player")
    
    async def get_effective_inventory_capacity(self, session) -> int:
        """获取有效背包容量（包含月卡加成）"""
        from .monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, self.id)
        return self.inventory_capacity + benefits["inventory_bonus"]

    def get_effective_battle_attributes(self, session=None) -> dict:
        """获取有效战斗属性（包含装备加成）

        返回格式化后的战斗属性字典，数值为百分比形式
        """
        # 基础属性值
        base_attrs = {
            "critical_rate": self.critical_rate,
            "critical_power": self.critical_power,
            "combo_rate": self.combo_rate,
            "counter_rate": self.counter_rate,
            "dodge_rate": self.dodge_rate,
            "accuracy_rate": self.accuracy_rate,
            "skill_crit_rate": self.skill_crit_rate,
            "penetration_rate": self.penetration_rate,
            "anti_crit_rate": self.anti_crit_rate
        }

        # TODO: 后续添加装备加成计算
        # if session:
        #     equipment_bonus = await self._get_equipment_battle_bonus(session)
        #     for attr, bonus in equipment_bonus.items():
        #         base_attrs[attr] = min(base_attrs[attr] + bonus, self._get_attr_cap(attr))

        return base_attrs

    def _get_attr_cap(self, attr_name: str) -> int:
        """获取属性上限值"""
        caps = {
            "critical_rate": 75,
            "combo_rate": 60,
            "counter_rate": 80,
            "dodge_rate": 85,
            "accuracy_rate": 95,
            "skill_crit_rate": 70,
            "penetration_rate": 70,
            "anti_crit_rate": 80
        }
        return caps.get(attr_name, 100)

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