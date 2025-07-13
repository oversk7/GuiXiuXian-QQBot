from sqlalchemy import Integer, String, DateTime, func, Boolean
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
    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属公会ID")
    guild_contribution: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="公会贡献值")
    
    vip: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="VIP等级")
    gold: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="货币")
    gold2: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="积分")
    
    last_sign: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次签到日期")
    sign_streak: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连续签到天数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    last_cultivation: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次修炼时间")

    inventory_capacity: Mapped[int] = mapped_column(Integer, default=30, server_default='30', nullable=False, comment="背包容量")
    is_secluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default='False', comment="是否闭关")
    seclusion_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="闭关开始时间")


async def get_player_by_uid(uid: str):
    from sqlalchemy import select
    from .db import get_session
    
    async with get_session() as session:
        result = await session.execute(select(Player).where(Player.uid == uid))
        return result.scalars().first()