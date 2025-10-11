"""
抽奖系统数据模型
"""
from sqlalchemy import Integer, String, DateTime, Boolean, Text, func, BigInteger, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base
from enum import Enum as PyEnum


class LotteryType(str, PyEnum):
    """抽奖类型"""
    ITEM = "物品"
    EQUIPMENT = "装备"
    GOLD = "金币"


class LotteryStatus(str, PyEnum):
    """抽奖状态"""
    PENDING = "进行中"
    FINISHED = "已开奖"
    CANCELLED = "已取消"


class Lottery(Base):
    """抽奖活动表"""
    __tablename__ = "lottery"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="抽奖ID")
    creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="发起人ID")
    creator_uid: Mapped[int] = mapped_column(Integer, nullable=False, comment="发起人UID")
    creator_name: Mapped[str] = mapped_column(String(24), nullable=False, comment="发起人昵称")
    
    lottery_type: Mapped[LotteryType] = mapped_column(SQLEnum(LotteryType, values_callable=lambda x: [e.value for e in x]), nullable=False, comment="抽奖类型")
    item_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="物品/装备ID")
    item_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="奖品名称")

    # 奖品配置
    winner_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="中奖人数")
    prize_per_winner: Mapped[int] = mapped_column(Integer, nullable=False, comment="每人奖品数量")
    total_prize: Mapped[int] = mapped_column(Integer, nullable=False, comment="奖品总数")

    # 参与条件
    min_level: Mapped[int] = mapped_column(Integer, default=1, comment="最低等级要求")
    max_level: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最高等级要求")

    # 状态
    status: Mapped[LotteryStatus] = mapped_column(SQLEnum(LotteryStatus, values_callable=lambda x: [e.value for e in x]), default=LotteryStatus.PENDING, comment="抽奖状态")

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="开奖时间")

    # 群组信息（用于判断是否在同一个群）
    group_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="群组ID")


class LotteryParticipant(Base):
    """抽奖参与者表"""
    __tablename__ = "lottery_participant"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lottery_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="抽奖ID")
    player_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="玩家ID")
    player_uid: Mapped[int] = mapped_column(Integer, nullable=False, comment="玩家UID")
    player_name: Mapped[str] = mapped_column(String(24), nullable=False, comment="玩家昵称")
    
    # 中奖信息
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否中奖")
    prize_received: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已领奖")
    
    # 时间
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="参与时间")
    won_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="中奖时间")

