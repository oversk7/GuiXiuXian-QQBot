"""斗法天梯数据模型

提供天梯系统所需的三张表：
- LadderRating: 玩家天梯档案（评分、段位、魂晶、统计）
- LadderMatchLog: 对战日志
- LadderSeason: 赛季管理
"""
from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import (
    String, Integer, BigInteger, Boolean, DateTime, Date, Index, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func
from .db import Base


class LadderRating(Base):
    """玩家天梯档案

    存储玩家在斗法天梯中的 ELO 评分、段位、统计数据与魂晶余额。
    采用懒加载创建：玩家首次访问天梯命令时自动创建。
    """

    __tablename__ = "ladder_rating"

    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("player.id"), primary_key=True, comment="玩家ID"
    )

    # ELO 与段位
    rating: Mapped[int] = mapped_column(
        Integer, default=1000, server_default="1000", comment="ELO评分"
    )
    rank_tier: Mapped[str] = mapped_column(
        String(16), default="九品", server_default="九品", comment="当前段位（缓存）"
    )

    # 战绩统计
    matches_played: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="总场次"
    )
    wins: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="胜场"
    )
    losses: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="负场"
    )
    draws: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="平局"
    )
    win_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="当前连胜"
    )
    best_rating: Mapped[int] = mapped_column(
        Integer, default=1000, server_default="1000", comment="历史最高积分"
    )
    season_id: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True, comment="当前赛季ID"
    )

    # 每日计数器
    daily_matches: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="今日已用匹配次数（攻方）"
    )
    daily_defense_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="今日被匹配次数（守方保护用）"
    )
    daily_extra_matches: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="今日通过斗法令额外购买的次数"
    )
    daily_reset_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次重置日期"
    )
    daily_first_win_claimed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="今日首胜奖励是否已领"
    )
    daily_shop_purchases: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="今日商店购买计数 {item_name: count}"
    )

    # 设置与货币
    matchmaking_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", comment="是否参与匹配池"
    )
    soul_crystals: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", comment="魂晶余额（PvP专属货币）"
    )
    last_match_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="上次对战时间（防匹配间隔）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<LadderRating player={self.player_id} rating={self.rating} "
            f"tier={self.rank_tier} wins={self.wins}>"
        )


# 排行榜查询索引
Index("idx_ladder_rating_value", LadderRating.rating.desc())
Index("idx_ladder_season_rating", LadderRating.season_id, LadderRating.rating.desc())


class LadderMatchLog(Base):
    """斗法天梯对战记录

    每场天梯对战写入一条记录，用于：
    - 玩家战绩查询
    - 守方离线推送（defender_notified 字段）
    - 反作弊审计（同对手冷却查询）
    """

    __tablename__ = "ladder_match_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, index=True, comment="赛季ID")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="对战时间"
    )

    # 双方信息（快照保存）
    attacker_id: Mapped[str] = mapped_column(String(32), index=True)
    defender_id: Mapped[str] = mapped_column(String(32), index=True)
    attacker_uid: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    defender_uid: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attacker_name: Mapped[str] = mapped_column(String(32), default="", server_default="")
    defender_name: Mapped[str] = mapped_column(String(32), default="", server_default="")

    # 结果与积分变化
    result: Mapped[str] = mapped_column(
        String(16), comment="attacker_win / defender_win / draw"
    )
    attacker_rating_before: Mapped[int] = mapped_column(Integer)
    attacker_rating_after: Mapped[int] = mapped_column(Integer)
    attacker_rating_change: Mapped[int] = mapped_column(Integer)
    defender_rating_before: Mapped[int] = mapped_column(Integer)
    defender_rating_after: Mapped[int] = mapped_column(Integer)
    defender_rating_change: Mapped[int] = mapped_column(Integer)

    defender_notified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", index=True,
        comment="守方是否已通过钩子收到推送"
    )

    def __repr__(self) -> str:
        return (
            f"<LadderMatchLog #{self.id} {self.attacker_name} vs "
            f"{self.defender_name} {self.result}>"
        )


# 战绩查询索引
Index("idx_ladder_match_attacker_ts", LadderMatchLog.attacker_id, LadderMatchLog.timestamp.desc())
Index("idx_ladder_match_defender_ts", LadderMatchLog.defender_id, LadderMatchLog.timestamp.desc())
Index("idx_ladder_match_pair_ts", LadderMatchLog.attacker_id, LadderMatchLog.defender_id, LadderMatchLog.timestamp.desc())


class LadderSeason(Base):
    """斗法天梯赛季

    每月一赛季。采用懒加载创建：访问任意天梯命令时检查并自动开新赛季 / 结算上赛季。
    """

    __tablename__ = "ladder_season"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_number: Mapped[int] = mapped_column(
        Integer, unique=True, comment="赛季序号（第N赛季）"
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, comment="赛季开始时间")
    end_at: Mapped[datetime] = mapped_column(DateTime, comment="赛季结束时间")
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active",
        comment="active / settling / ended"
    )
    rewards_distributed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="奖励是否已发放"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<LadderSeason #{self.season_number} {self.status} "
            f"{self.start_at:%Y-%m-%d}~{self.end_at:%Y-%m-%d}>"
        )
