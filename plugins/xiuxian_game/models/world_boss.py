from __future__ import annotations

from sqlalchemy import String, Integer, DateTime, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from .db import Base


class WorldBossCycle(Base):
    """世界BOSS周期信息

    说明：
    - 懒加载刷新：当任意相关指令被触发时检查是否到达刷新点（周三/周六20:00）。
    - 旧周期在刷新时进行结算，并创建新周期。
    """

    __tablename__ = "world_boss_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_key: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="周期键，如 2025W10_SAT_20")
    boss_name: Mapped[str] = mapped_column(String(32), comment="BOSS名称")
    boss_title: Mapped[str] = mapped_column(String(64), comment="BOSS称号/副标题")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="开始时间")
    next_refresh_at: Mapped[datetime] = mapped_column(DateTime, comment="下次刷新时间（周三/六 20:00）")
    settled: Mapped[bool] = mapped_column(Integer, default=0, server_default="0", comment="是否已结算旧周期")

    def __repr__(self) -> str:
        return f"<WorldBossCycle {self.cycle_key} {self.boss_name}>"


class WorldBossDamage(Base):
    """玩家在某个周期内对世界BOSS造成的累计伤害与状态

    attacks_today / attacks_reset_date 用于实现每日3次上限（自然日）。
    last_attack_ts 用于1秒冷却。
    """

    __tablename__ = "world_boss_damage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    total_damage: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="累计伤害")
    last_attack_ts: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="上次攻击的UNIX秒")
    attacks_today: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="今日已攻击次数")
    attacks_reset_date: Mapped[str] = mapped_column(String(10), default="", server_default="", comment="YYYY-MM-DD")

    __table_args__ = (
        UniqueConstraint('cycle_id', 'player_id', name='uq_cycle_player'),
    )

    def __repr__(self) -> str:
        return f"<WorldBossDamage cycle={self.cycle_id} player={self.player_id} dmg={self.total_damage}>"


