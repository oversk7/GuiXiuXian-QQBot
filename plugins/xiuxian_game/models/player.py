from sqlalchemy import Integer, String, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..data.db import Base
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
    position: Mapped[str] = mapped_column(String(32), default="主城", server_default='主城', comment="位置")
    hp: Mapped[int] = mapped_column(Integer, default=100, server_default='100', comment="生命值")
    max_hp: Mapped[int] = mapped_column(Integer, default=100, server_default='100', comment="最大生命值")
    mp: Mapped[int] = mapped_column(Integer, default=100, server_default='100', comment="理智值")
    max_mp: Mapped[int] = mapped_column(Integer, default=100, server_default='100', comment="最大理智值")
    attack: Mapped[int] = mapped_column(Integer, default=25, server_default='25', comment="攻击力")
    defense: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="物抗")
    fear_resistance: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="恐惧抗性/魔抗")
    agility: Mapped[int] = mapped_column(Integer, default=5, server_default='5', comment="敏捷")
    stamina: Mapped[int] = mapped_column(Integer, default=100, server_default='100', comment="体力")
    luck: Mapped[int] = mapped_column(Integer, default=10, server_default='10', comment="运气")
    
    vip: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="VIP等级")
    gold: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="货币")
    gold2: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="稀有货币")
    
    last_sign: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次签到日期")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    last_cultivation: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="上次修炼时间")

    inventory_capacity: Mapped[int] = mapped_column(Integer, default=10, server_default='10', nullable=False, comment="背包容量")
    is_secluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default='False', comment="是否闭关")
    seclusion_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="闭关开始时间")

    battle_mode: Mapped[str] = mapped_column(String(16), default="SOLO", comment="战斗模式，SOLO，TEAM")

    
async def get_player_by_uid(uid: str):
    from sqlalchemy import select
    from ..data.db import get_session
    
    async with get_session() as session:
        result = await session.execute(select(Player).where(Player.uid == uid))
        return result.scalars().first()