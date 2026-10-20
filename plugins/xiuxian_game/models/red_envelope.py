"""
红包数据模型

支持群聊发红包/抢红包功能：
- 每群同时只有一个活跃红包
- 双倍均值随机分配机制
- 阶梯散财税

领取由 Redis Lua 判断资格并扣减份额，入账消息经 Redis Stream 异步写入
red_envelope_grab，由唯一约束保证一人一次、消息重复也只入账一次。
"""

from enum import Enum
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class RedEnvelopeStatus(str, Enum):
    """红包状态枚举"""
    ACTIVE = "active"        # 活跃中，可以抢
    FINISHED = "finished"    # 已抢完
    EXPIRED = "expired"      # 已过期


class ReconcileState(int, Enum):
    """红包关闭后的对账结果；改造前的旧红包为 NULL，不参与对账"""
    PENDING = 0       # 未对账
    CONSISTENT = 1    # 已领总额 + 退款 = 实发金额
    COMPENSATED = 2   # 有领取未入账，差额已退给发送者
    OVERPAID = 3      # 已领总额 + 退款 > 实发金额，需人工处理


class RedEnvelope(Base):
    """红包表"""
    __tablename__ = "red_envelope"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, default=1, index=True, comment="所属区服ID")
    group_id: Mapped[str] = mapped_column(String(32), index=True, comment="群ID")
    sender_id: Mapped[str] = mapped_column(String(32), index=True, comment="发送者玩家ID")

    # 金额信息
    total_gold: Mapped[int] = mapped_column(BigInteger, comment="总金额(税前)")
    tax_amount: Mapped[int] = mapped_column(BigInteger, default=0, comment="税收金额")
    actual_gold: Mapped[int] = mapped_column(BigInteger, comment="实际红包金额(税后)")

    # 份数信息（进行中的剩余以 Redis 为准，关闭时回写最终值）
    total_count: Mapped[int] = mapped_column(Integer, comment="总份数")
    remaining_gold: Mapped[int] = mapped_column(BigInteger, comment="剩余金额")
    remaining_count: Mapped[int] = mapped_column(Integer, comment="剩余份数")

    # 状态
    status: Mapped[str] = mapped_column(String(16), default=RedEnvelopeStatus.ACTIVE.value, comment="红包状态")
    message: Mapped[str] = mapped_column(String(128), nullable=True, comment="红包留言")
    refund_gold: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", comment="已退还发送者的金额",
    )
    reconcile_state: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=ReconcileState.PENDING.value,
        comment="对账结果 0未对账/1一致/2已补偿/3超发，旧红包为空",
    )

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="过期时间")

    # 改造前旧红包的领取记录与最佳手气，新红包不再写入
    grab_records: Mapped[str] = mapped_column(Text, default="[]", comment="抢红包记录(JSON，旧数据)")
    best_luck_player_id: Mapped[str] = mapped_column(String(32), nullable=True, comment="最佳手气玩家ID(旧数据)")
    best_luck_amount: Mapped[int] = mapped_column(BigInteger, default=0, comment="最佳手气金额(旧数据)")


class RedEnvelopeGrab(Base):
    """领取记录：一条入账消息落库一行。"""
    __tablename__ = "red_envelope_grab"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    envelope_id: Mapped[int] = mapped_column(Integer, comment="红包ID")
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="领取者玩家ID")
    nickname: Mapped[str] = mapped_column(String(64), default="", comment="领取时的昵称")
    amount: Mapped[int] = mapped_column(BigInteger, comment="领取金额")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="入账时间")

    __table_args__ = (
        UniqueConstraint("envelope_id", "player_id", name="uq_red_envelope_grab"),
    )
