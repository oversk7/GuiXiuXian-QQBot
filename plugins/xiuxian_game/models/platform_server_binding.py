"""平台账号区服绑定模型。

一个真实 QQ/platform 账号只能绑定一个游戏区服。该表是跨账号转让、
小号绑定和注册时的 source of truth。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PlatformServerBinding(Base):
    """QQ/platform 账号到区服的唯一绑定。"""

    __tablename__ = "platform_server_binding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_platform_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="平台ID（QQ号等）",
    )
    server_id: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default='1',
        nullable=False,
        index=True,
        comment="绑定区服ID",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("owner_platform_id", name="uq_platform_server_binding_owner"),
    )
