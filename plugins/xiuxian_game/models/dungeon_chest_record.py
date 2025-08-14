"""
深渊探索者宝箱领取记录模型

记录玩家在每十层诡域领取深渊探索者宝箱的情况
"""

from sqlalchemy import Integer, String, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from .db import Base


class DungeonChestRecord(Base):
    """深渊探索者宝箱领取记录表"""
    __tablename__ = "dungeon_chest_record"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    dungeon_level: Mapped[int] = mapped_column(Integer, index=True, comment="诡域层级")
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="领取时间")
    
    # 确保每个玩家在每个层级只能领取一次宝箱
    __table_args__ = (
        UniqueConstraint('player_id', 'dungeon_level', name='uq_player_dungeon_chest'),
    )
