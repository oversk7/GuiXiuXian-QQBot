from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class NavigationTask(Base):
    """玩家自动导航状态，持久化避免重启丢失。"""

    __tablename__ = "navigation_task"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="玩家ID")
    target_x: Mapped[int] = mapped_column(Integer, comment="目标X")
    target_y: Mapped[int] = mapped_column(Integer, comment="目标Y")
    last_update: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="上次位置更新时间")