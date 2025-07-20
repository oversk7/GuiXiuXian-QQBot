from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, date
from .db import Base


class GhostInvasion(Base):
    """鬼怪入侵事件表
    
    记录每日生成的鬼怪入侵事件，包括位置、状态等信息
    """
    __tablename__ = "ghost_invasion"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ghost_id: Mapped[str] = mapped_column(String(32), index=True, comment="鬼怪ID，对应Ghost表")
    
    # 位置信息
    region: Mapped[str] = mapped_column(String(32), default="大都会", comment="入侵区域")
    x: Mapped[int] = mapped_column(Integer, comment="入侵坐标X")
    y: Mapped[int] = mapped_column(Integer, comment="入侵坐标Y")
    
    # 状态信息
    is_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已被镇压")
    suppressed_by: Mapped[str] = mapped_column(String(32), nullable=True, comment="镇压者玩家ID")
    suppressed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="镇压时间")
    
    # 时间信息
    invasion_date: Mapped[date] = mapped_column(default=date.today, comment="入侵日期")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    
    def is_available_for_suppression(self) -> bool:
        """检查是否可以被镇压"""
        return not self.is_suppressed
    
    def suppress(self, player_id: str) -> None:
        """标记为已镇压"""
        self.is_suppressed = True
        self.suppressed_by = player_id
        self.suppressed_at = datetime.now()
    
    @property
    def location_str(self) -> str:
        """获取位置字符串"""
        return f"{self.region}({self.x},{self.y})"
