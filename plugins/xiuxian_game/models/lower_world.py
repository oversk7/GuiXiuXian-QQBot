"""
下位世界·天灾山寨数据模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class LowerWorldStronghold(Base):
    """玩家天灾山寨"""
    __tablename__ = "lower_world_stronghold"

    player_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="玩家ID"
    )
    calamity_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="天灾点（专属货币）"
    )
    wave_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="当前波次"
    )
    next_wave_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="下一波英雄抵达时间"
    )
    pending_hero: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="待挑战英雄数据（JSON）"
    )
    sealed_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="封印截止时间（失败后24小时）"
    )
    total_waves_won: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="历史总胜场"
    )
    best_wave: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="历史最高波次"
    )
    last_battle_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最后一次迎战时间（战斗冷却用）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="首次降临时间"
    )
