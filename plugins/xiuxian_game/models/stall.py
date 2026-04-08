"""
个人摊位数据模型

PlayerStall: 玩家的摊位信息（1个玩家同时只能有1个摊位）
StallItem: 摊位上的商品条目
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .db import Base


class PlayerStall(Base):
    """玩家摊位

    每个玩家同时只能开设一个摊位，消耗摊位令开摊，持续24小时。
    """

    __tablename__ = "player_stall"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ==================== 摊主信息 ====================
    player_id: Mapped[str] = mapped_column(
        String(32), index=True, comment="摊主平台ID（player.id）"
    )
    player_uid: Mapped[int] = mapped_column(
        Integer, comment="摊主游戏UID"
    )
    player_name: Mapped[str] = mapped_column(
        String(64), comment="摊主昵称快照"
    )

    # ==================== 摊位信息 ====================
    city_name: Mapped[str] = mapped_column(
        String(32), comment="所在城镇名称"
    )
    stall_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="摊位名称（玩家自定义）"
    )
    shout_text: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="吆喝语"
    )

    # ==================== 时间信息 ====================
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
        comment="开摊时间"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, comment="到期时间"
    )

    # ==================== 状态 ====================
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active",
        index=True,
        comment="状态: active(营业中) / closed(已收摊) / expired(已过期)"
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class StallItem(Base):
    """摊位商品条目

    摊位上架的单个商品，支持普通物品和装备实例。
    """

    __tablename__ = "stall_item"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ==================== 关联信息 ====================
    stall_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="所属摊位ID"
    )
    seller_id: Mapped[str] = mapped_column(
        String(32), index=True, comment="摊主player_id（冗余，方便查询）"
    )

    # ==================== 物品信息 ====================
    item_id: Mapped[str] = mapped_column(
        String(64), comment="物品模板ID（items.yaml）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, comment="数量（装备固定为1）"
    )
    unit_price: Mapped[int] = mapped_column(
        BigInteger, comment="单价（金币）- 玩家自由定价"
    )
    is_instance_trade: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0",
        comment="是否为装备/铭文实例交易"
    )
    item_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="装备实例ID（仅装备交易时有效）"
    )
    equipment_summary: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="装备摘要文本"
    )

    # ==================== 时间 ====================
    listed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
        comment="上架时间"
    )
