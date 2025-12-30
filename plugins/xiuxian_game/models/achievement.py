"""
成就系统数据模型
"""
from sqlalchemy import String, Integer, Boolean, DateTime, BigInteger, func, Index, ForeignKey, text, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base
from typing import Optional


class PlayerAchievement(Base):
    """玩家成就关联表"""
    __tablename__ = "player_achievement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), nullable=False, comment="玩家ID")
    achievement_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="成就ID")

    # 完成信息
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="解锁时间")
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="当前进度")
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="是否已完成")
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="是否已领取奖励")

    # 索引
    __table_args__ = (
        Index("idx_player_achievement", "player_id", "achievement_id", unique=True),
        Index("idx_player_completed", "player_id", "is_completed"),
    )

    def __repr__(self):
        return f"<PlayerAchievement player_id={self.player_id} achievement_id={self.achievement_id} progress={self.progress}>"


class PlayerStats(Base):
    """玩家统计数据表（用于成就进度追踪）"""
    __tablename__ = "player_stats"

    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), primary_key=True, comment="玩家ID")

    # 修炼统计
    cultivation_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="累计修炼次数")

    # 战斗统计
    total_battles: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总战斗次数")
    total_wins: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总胜利次数")
    total_kills: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总击杀数")

    # 财富统计
    gold_earned_total: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="累计获得金币")
    gold_spent_total: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="累计花费金币")

    # 探索统计
    locations_visited: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="探索过的地点数")
    locations_visited_list: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="探索过的地点列表(逗号分隔)")

    # 装备统计
    equipment_obtained: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="获得过的装备数")

    # 登录统计
    last_login_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后登录日期")
    consecutive_login_days: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="连续登录天数")
    total_login_days: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="总登录天数")

    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<PlayerStats player_id={self.player_id} cultivation_count={self.cultivation_count}>"
