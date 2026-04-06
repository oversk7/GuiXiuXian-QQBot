from sqlalchemy import Integer, String, DateTime, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class MarketTradeLog(Base):
    """玩家交易市场成交记录"""
    __tablename__ = "market_trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_id: Mapped[str] = mapped_column(String(32), index=True, comment="买家ID")
    seller_id: Mapped[str] = mapped_column(String(32), index=True, comment="卖家ID")
    buyer_name: Mapped[str] = mapped_column(String(24), comment="买家昵称")
    seller_name: Mapped[str] = mapped_column(String(24), comment="卖家昵称")
    item_id: Mapped[str] = mapped_column(String(64), index=True, comment="物品ID")
    item_name: Mapped[str] = mapped_column(String(64), comment="物品名称")
    quantity: Mapped[int] = mapped_column(Integer, comment="成交数量")
    unit_price: Mapped[int] = mapped_column(BigInteger, comment="成交单价")
    total_amount: Mapped[int] = mapped_column(BigInteger, comment="成交总额")
    tax: Mapped[int] = mapped_column(BigInteger, default=0, comment="税收")
    is_equipment: Mapped[bool] = mapped_column(Integer, default=False, server_default="0", comment="是否装备交易")
    trade_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), index=True, comment="成交时间"
    )
