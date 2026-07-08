"""
公会镇诡（公会Boss）数据模型

设计文档：llmdoc/design/specs/2026-07-08-guild-boss-design.md
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class GuildBossInstance(Base):
    """公会镇诡场次（一次开坛引诡）"""
    __tablename__ = "guild_boss_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, index=True, comment="公会ID")
    boss_name: Mapped[str] = mapped_column(String(32), comment="诡异名称")
    boss_title: Mapped[str] = mapped_column(String(64), comment="诡异称号")
    boss_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="凶戾度（开坛时快照）")
    hp_max: Mapped[int] = mapped_column(BigInteger, comment="总血量")
    hp_left: Mapped[int] = mapped_column(BigInteger, comment="剩余血量")
    atk_snapshot: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="开坛时全会有效攻击力总和（审计用）")
    summoned_by: Mapped[str] = mapped_column(String(32), comment="开坛者玩家ID")
    summoned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="开坛时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="超时时间（开坛+48小时）")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", comment="active/subdued/expired")
    settled: Mapped[bool] = mapped_column(Integer, default=0, server_default="0", comment="是否已结算发奖")
    final_blow_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="封棺一击玩家ID")

    def __repr__(self) -> str:
        return f"<GuildBossInstance guild={self.guild_id} {self.boss_name} {self.hp_left}/{self.hp_max}>"


class GuildBossDamage(Base):
    """成员对公会诡异的出力记录"""
    __tablename__ = "guild_boss_damage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, index=True, comment="场次ID")
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    total_damage: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="累计伤害（按实际扣血计，溢出不算）")
    attacks_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="已出手次数")
    last_attack_ts: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="上次攻击UNIX秒（冷却用）")

    __table_args__ = (
        UniqueConstraint("instance_id", "player_id", name="uq_gboss_instance_player"),
    )

    def __repr__(self) -> str:
        return f"<GuildBossDamage inst={self.instance_id} player={self.player_id} dmg={self.total_damage}>"
