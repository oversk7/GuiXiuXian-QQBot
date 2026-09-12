from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from .db import Base

class NavigationTask(Base):
    """玩家自动导航状态，持久化避免重启丢失。"""

    __tablename__ = "navigation_task"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="玩家ID")
    target_x: Mapped[int] = mapped_column(Integer, comment="目标X")
    target_y: Mapped[int] = mapped_column(Integer, comment="目标Y")
    last_update: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="上次位置更新时间")
    initial_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="初始总距离（用于进度计算）")
    supernatural_events_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="已处理的导航灵异事件数")