"""
账号所有权模型

记录玩家拥有哪些游戏账号，支持：
1. 一个玩家（platform_id）拥有多个游戏账号（Player）
2. 账号切换（激活不同的账号）
3. 账号转让（买卖/赠送）
"""

from sqlalchemy import String, DateTime, Boolean, Integer, func, Index, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base


class AccountOwnership(Base):
    """账号所有权表"""
    __tablename__ = "account_ownership"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 拥有者信息
    owner_platform_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="拥有者的平台ID（真实玩家）"
    )

    # 游戏账号信息
    player_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('player.id', ondelete='CASCADE'),
        comment="拥有的游戏账号ID"
    )

    # 关系定义
    player: Mapped["Player"] = relationship("Player", foreign_keys=[player_id], lazy="joined")

    # 状态信息
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default='0',
        comment="是否是当前激活使用的账号"
    )

    # 账号备注
    display_name: Mapped[str] = mapped_column(
        String(32),
        nullable=True,
        comment="账号备注名（如'主号'、'小号'、'买来的'）"
    )

    # 转让密钥
    transfer_key: Mapped[str] = mapped_column(
        String(16),
        nullable=True,
        comment="账号转让密钥（6位数字，NULL表示未生成）"
    )

    transfer_key_created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        comment="转让密钥生成时间"
    )

    # 借号权（一次性买断的串行共享）
    master_platform_id: Mapped[str] = mapped_column(
        String(64),
        nullable=True,
        comment="主切权人平台ID（买断借号权的真实主人，NULL=未开通借号权）"
    )

    delegate_platform_id: Mapped[str] = mapped_column(
        String(64),
        nullable=True,
        comment="被授权借用人平台ID（换借用人需重新付费）"
    )

    # 获得方式
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="获得此账号的时间"
    )

    acquired_type: Mapped[str] = mapped_column(
        String(16),
        default="created",
        server_default="created",
        comment="获得方式：created/transferred/purchased/gift"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="记录创建时间"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="记录更新时间"
    )

    # 约束
    __table_args__ = (
        # 每个游戏账号只能有一个拥有者
        UniqueConstraint('player_id', name='uq_account_ownership_player_id'),
        # 索引：快速查找某个玩家拥有的所有账号
        Index('idx_account_ownership_owner', 'owner_platform_id'),
        # 索引：快速查找激活的账号
        Index('idx_account_ownership_active', 'owner_platform_id', 'is_active'),
    )

    def is_lent_out(self) -> bool:
        """是否处于借出状态（使用权在被授权人手里）"""
        return bool(self.master_platform_id) and self.owner_platform_id != self.master_platform_id

    def is_transfer_key_valid(self) -> bool:
        """检查转让密钥是否有效（永久有效直到使用）"""
        return bool(self.transfer_key)

    def clear_transfer_key(self):
        """清除转让密钥"""
        self.transfer_key = None
        self.transfer_key_created_at = None
        self.updated_at = datetime.now()
