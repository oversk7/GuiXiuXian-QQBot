"""
账号转让历史记录模型

记录所有账号转让操作，用于：
1. 审计追踪
2. 防止欺诈
3. 统计分析
"""

from sqlalchemy import String, DateTime, Integer, func, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class AccountTransferLog(Base):
    """账号转让历史记录表"""
    __tablename__ = "account_transfer_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 转让的账号
    player_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('player.id', ondelete='CASCADE'),
        index=True,
        comment="被转让的游戏账号ID"
    )

    # 转让双方
    from_platform_id: Mapped[str] = mapped_column(
        String(64),
        comment="原拥有者的平台ID"
    )

    to_platform_id: Mapped[str] = mapped_column(
        String(64),
        comment="新拥有者的平台ID"
    )

    # 转让类型
    transfer_type: Mapped[str] = mapped_column(
        String(16),
        comment="转让类型：sale（买卖）/gift（赠送）/admin（管理员操作）"
    )

    # 转让时间
    transfer_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="转让完成时间"
    )

    # 转让密钥（用于追踪）
    transfer_key_used: Mapped[str] = mapped_column(
        String(16),
        nullable=True,
        comment="使用的转让密钥"
    )

    # 备注
    notes: Mapped[str] = mapped_column(
        String(256),
        nullable=True,
        comment="转让备注"
    )

    # 索引
    __table_args__ = (
        # 快速查找某个账号的转让历史
        Index('idx_transfer_log_player', 'player_id', 'transfer_time'),
        # 快速查找某个用户的转让历史（买入或卖出）
        Index('idx_transfer_log_from', 'from_platform_id', 'transfer_time'),
        Index('idx_transfer_log_to', 'to_platform_id', 'transfer_time'),
    )
