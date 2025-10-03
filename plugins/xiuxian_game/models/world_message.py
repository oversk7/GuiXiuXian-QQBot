from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class WorldMessage(Base):
    __tablename__ = "world_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="发送者平台ID")
    recipient_id: Mapped[str | None] = mapped_column(
        String(32), index=True, nullable=True, comment="收信人平台ID (NULL 表示世界频道)"
    )
    content: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
