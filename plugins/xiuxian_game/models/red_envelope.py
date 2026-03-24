"""
红包数据模型

支持群聊发红包/抢红包功能：
- 每群同时只有一个活跃红包
- 双倍均值随机分配机制
- 阶梯散财税
"""

from enum import Enum
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class RedEnvelopeStatus(str, Enum):
    """红包状态枚举"""
    ACTIVE = "active"        # 活跃中，可以抢
    FINISHED = "finished"    # 已抢完
    EXPIRED = "expired"      # 已过期


class RedEnvelope(Base):
    """红包表"""
    __tablename__ = "red_envelope"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(32), index=True, comment="群ID")
    sender_id: Mapped[str] = mapped_column(String(32), index=True, comment="发送者玩家ID")

    # 金额信息
    total_gold: Mapped[int] = mapped_column(BigInteger, comment="总金额(税前)")
    tax_amount: Mapped[int] = mapped_column(BigInteger, default=0, comment="税收金额")
    actual_gold: Mapped[int] = mapped_column(BigInteger, comment="实际红包金额(税后)")

    # 份数信息
    total_count: Mapped[int] = mapped_column(Integer, comment="总份数")
    remaining_gold: Mapped[int] = mapped_column(BigInteger, comment="剩余金额")
    remaining_count: Mapped[int] = mapped_column(Integer, comment="剩余份数")

    # 状态
    status: Mapped[str] = mapped_column(String(16), default=RedEnvelopeStatus.ACTIVE.value, comment="红包状态")
    message: Mapped[str] = mapped_column(String(128), nullable=True, comment="红包留言")

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="过期时间")

    # 抢红包记录 (JSON格式: [{player_id, nickname, amount, is_lucky}])
    grab_records: Mapped[str] = mapped_column(Text, default="[]", comment="抢红包记录(JSON)")

    # 最佳手气
    best_luck_player_id: Mapped[str] = mapped_column(String(32), nullable=True, comment="最佳手气玩家ID")
    best_luck_amount: Mapped[int] = mapped_column(BigInteger, default=0, comment="最佳手气金额")
