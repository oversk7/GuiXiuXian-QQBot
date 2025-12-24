from sqlalchemy import Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class PlayerBan(Base):
    """全局玩家封禁模型"""
    __tablename__ = "player_ban"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="ID")
    player_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, comment="被封禁玩家ID"
    )
    admin_id: Mapped[str] = mapped_column(String(32), index=True, comment="操作管理员ID")
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="封禁原因")
    ban_type: Mapped[str] = mapped_column(
        String(20), default="permanent", server_default="permanent",
        comment="封禁类型：permanent(永久) | temporary(临时)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间（NULL表示永久封禁）"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default='1', index=True, comment="是否生效中"
    )

    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.ban_type == "permanent" or self.expires_at is None:
            return False  # 永久封禁永不过期
        return datetime.now() > self.expires_at

    def get_remaining_time(self) -> str | None:
        """获取剩余封禁时间描述"""
        if self.ban_type == "permanent" or self.expires_at is None:
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

    def get_ban_info(self) -> str:
        """获取封禁信息摘要"""
        remaining = self.get_remaining_time()
        return f"封禁状态：{'生效中' if self.is_active else '已解封'}\n原因：{self.reason or '无'}\n剩余时间：{remaining}"
