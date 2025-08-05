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

    # 新增战斗属性
    critical_rate: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="暴击率(百分比)")
    combo_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连击率(百分比)")
    counter_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="反击率(百分比)")
    dodge_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="闪避率(百分比)")
    accuracy_rate: Mapped[int] = mapped_column(Integer, default=80, server_default='80', comment="命中率(百分比)")
    skill_crit_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="灵爆率(百分比)")
    penetration_rate: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="穿透率(百分比)")
    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属公会ID")
    guild_contribution: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会贡献值")
    
    vip: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="VIP等级")
    gold: Mapped[int] = mapped_column(BigInteger, default=1000, server_default='1000', comment="货币")
    gold2: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="积分")
    
    last_sign: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次签到日期")
    sign_streak: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连续签到天数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    last_cultivation: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次修炼时间")

    inventory_capacity: Mapped[int] = mapped_column(Integer, default=30, server_default='30', nullable=False, comment="背包容量")
    is_secluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default='False', comment="是否闭关")
    seclusion_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="闭关开始时间")
    last_message_board_check: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后查看留言板时间")

    # 关联关系
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
            "combo_rate": self.combo_rate,
            "counter_rate": self.counter_rate,
            "dodge_rate": self.dodge_rate,
            "accuracy_rate": self.accuracy_rate,
            "skill_crit_rate": self.skill_crit_rate,
            "penetration_rate": self.penetration_rate
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
            "penetration_rate": 70
        }
        return caps.get(attr_name, 100)

    def format_battle_attributes(self) -> str:
        """格式化显示战斗属性"""
        attrs = self.get_effective_battle_attributes()

        lines = [
            "⚔️ 战斗属性 ⚔️",
            f"💥 暴击率: {attrs['critical_rate']}%",
            f"🔄 连击率: {attrs['combo_rate']}%",
            f"🛡️ 反击率: {attrs['counter_rate']}%",
            f"⚡ 闪避率: {attrs['dodge_rate']}%",
            f"🎯 命中率: {attrs['accuracy_rate']}%",
            f"✨ 灵爆率: {attrs['skill_crit_rate']}%",
            f"🗡️ 穿透率: {attrs['penetration_rate']}%"
        ]

        return "\n".join(lines)


async def get_player_by_uid(uid: str):
    from sqlalchemy import select
    from .db import get_session
    
    async with get_session() as session:
        result = await session.execute(select(Player).where(Player.uid == uid))
        return result.scalars().first()