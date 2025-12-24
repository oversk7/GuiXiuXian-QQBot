from sqlalchemy import Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class MessageBoardBlacklist(Base):
    """留言板黑名单模型"""
    __tablename__ = "message_board_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="ID")
    target_player_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, comment="被禁言玩家ID"
    )
    admin_id: Mapped[str] = mapped_column(String(32), index=True, comment="操作管理员ID")
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="禁言原因")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间（NULL表示永久禁言）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default='1', index=True, comment="是否生效中"
    )

    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False  # 永久禁言永不过期
        return datetime.now() > self.expires_at

    def get_remaining_time(self) -> str | None:
        """获取剩余禁言时间描述"""
        if self.expires_at is None:
            return "永久"

        if self.is_expired():
            return "已过期"

        delta = self.expires_at - datetime.now()
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60

        if days > 0:
            return f"{days}天{hours}小时"
        elif hours > 0:
            return f"{hours}小时{minutes}分钟"
        else:
            return f"{minutes}分钟"
