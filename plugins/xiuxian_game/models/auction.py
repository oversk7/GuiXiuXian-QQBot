"""
拍卖行数据模型

拍卖品表：记录所有拍卖条目，包括上架信息、出价信息、结算状态。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .db import Base


class AuctionItem(Base):
    """拍卖条目

    一件物品（或装备）在拍卖行中的竞价记录。
    - 普通物品：上架时从背包扣除，流拍/撤拍时退回
    - 装备实例：上架时设置 _frozen_for_auction 标记，成交后转移所有权
    """

    __tablename__ = "auction_item"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ==================== 卖家信息 ====================
    seller_id: Mapped[str] = mapped_column(
        String(32), index=True, comment="卖家平台ID（player.id）"
    )

    # ==================== 物品信息 ====================
    item_id: Mapped[str] = mapped_column(
        String(64), comment="物品模板ID（items.yaml）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="数量（装备固定为1）"
    )
    is_instance_trade: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否为装备实例交易"
    )
    item_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="装备实例ID（仅装备交易时有效）"
    )
    equipment_summary: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="装备摘要文本（如：⭐+5阶 [💎2/3] 耐久160/160）"
    )

    # ==================== 价格信息 ====================
    start_price: Mapped[int] = mapped_column(
        BigInteger, comment="起拍价（金币）"
    )
    current_price: Mapped[int] = mapped_column(
        BigInteger, comment="当前最高出价（初始=起拍价）"
    )
    buyout_price: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="一口价（NULL表示不设置）"
    )

    # ==================== 竞价信息 ====================
    current_bidder_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="当前最高出价人ID（NULL表示无人出价）"
    )
    bid_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="总出价次数"
    )

    # ==================== 时间信息 ====================
    start_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), comment="拍卖开始时间"
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime, comment="拍卖结束时间"
    )
    reminded_30min: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否已发送30分钟提醒"
    )

    # ==================== 状态 ====================
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active",
        index=True,
        comment="状态: active(进行中) / sold(已成交) / cancelled(已撤拍) / expired(流拍)"
    )

    def __repr__(self) -> str:
        return (
            f"<AuctionItem id={self.id} item_id={self.item_id} "
            f"current_price={self.current_price} status={self.status}>"
        )

    @property
    def is_active(self) -> bool:
        """是否仍在竞价中"""
        return self.status == "active"

    @property
    def has_bidder(self) -> bool:
        """是否有人出价"""
        return self.current_bidder_id is not None

    @property
    def min_next_bid(self) -> int:
        """下一次出价的最低金额（当前价 × 1.05，向上取整，最低 +1）"""
        if not self.has_bidder:
            return self.start_price
        return max(self.current_price + 1, int(self.current_price * 1.05))
