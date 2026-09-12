"""
餐厅日志数据模型

记录餐厅经营的详细日志
"""
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class RestaurantLog(Base):
    """餐厅经营日志模型

    记录每小时的经营详情
    """
    __tablename__ = "restaurant_log"

    __table_args__ = (
        Index("ix_restaurant_log_restaurant_period", "restaurant_id", "period_start"),
        Index("ix_restaurant_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("restaurant.id", ondelete="CASCADE"),
        index=True,
        comment="所属餐厅ID"
    )
    period_start: Mapped[datetime] = mapped_column(DateTime, comment="时段开始")
    period_end: Mapped[datetime] = mapped_column(DateTime, comment="时段结束")
    income: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="本时段收入")
    expense: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="本时段支出")
    customers: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="顾客数")
    dishes_made: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="制作菜品数")
    dishes_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="失败数")
    details_json: Mapped[str] = mapped_column(Text, comment="JSON详细日志")
    reputation_change: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="声望变化")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="创建时间"
    )
