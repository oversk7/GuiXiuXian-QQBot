"""
灵田系统数据模型

包含:
- SpiritField: 灵田(每玩家一块)
- SpiritFieldPlot: 灵壤/地块
- SpiritFieldStealLog: 偷菜记录
"""
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class SpiritField(Base):
    """灵田模型

    每个玩家只能拥有一块灵田
    """
    __tablename__ = "spirit_field"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id"),
        unique=True,
        index=True,
        comment="所属玩家ID"
    )
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="灵田等级(1-9)")
    guardian_beast_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="守田诡兽物品ID(items.yaml)"
    )
    guardian_fed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="诡兽上次喂食时间"
    )
    total_harvested: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="累计收菜次数"
    )
    total_stolen_from: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="被偷次数"
    )
    total_stolen_by_me: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="偷他人次数"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2026-02-19 00:00:00",
        comment="创建时间"
    )


class SpiritFieldPlot(Base):
    """灵壤/地块模型

    每块灵壤种一株作物
    """
    __tablename__ = "spirit_field_plot"

    __table_args__ = (
        Index("ix_spirit_field_plot_field_index", "field_id", "plot_index", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("spirit_field.id", ondelete="CASCADE"),
        index=True,
        comment="所属灵田ID"
    )
    plot_index: Mapped[int] = mapped_column(Integer, comment="地块编号(从1开始)")
    crop_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="作物ID(crops.yaml中的crop_id)"
    )
    planted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="种植时间"
    )
    mature_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="成熟时间"
    )
    is_mature: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否已成熟"
    )
    water_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="今日灌溉次数"
    )
    last_water_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="上次灌溉时间"
    )
    yield_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="预计产量"
    )
    stolen_quantity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="被偷数量"
    )


class SpiritFieldStealLog(Base):
    """偷菜记录模型"""
    __tablename__ = "spirit_field_steal_log"

    __table_args__ = (
        Index("ix_steal_log_thief_date", "thief_id", "steal_date"),
        Index("ix_steal_log_victim_date", "victim_id", "steal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thief_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id"),
        index=True,
        comment="偷菜者ID"
    )
    victim_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id"),
        index=True,
        comment="被偷者ID"
    )
    crop_id: Mapped[str] = mapped_column(String(32), comment="被偷作物ID")
    quantity: Mapped[int] = mapped_column(Integer, comment="偷取数量")
    was_caught: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否被诡兽拦截"
    )
    penalty_gold: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="被拦截时罚金"
    )
    steal_date: Mapped[str] = mapped_column(
        String(10), comment="偷菜日期(YYYY-MM-DD)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2026-02-19 00:00:00",
        comment="创建时间"
    )
