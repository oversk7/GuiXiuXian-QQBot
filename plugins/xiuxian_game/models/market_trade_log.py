from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class MarketTradeLog(Base):
    """挂牌市场成交日志（买牌直购成交时写入）"""
    __tablename__ = "market_trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, default=1, server_default="1", index=True, comment="所属区服ID")
    buyer_id: Mapped[str] = mapped_column(String(32), index=True)
    seller_id: Mapped[str] = mapped_column(String(32), index=True)
    buyer_name: Mapped[str] = mapped_column(String(24))
    seller_name: Mapped[str] = mapped_column(String(24))
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    item_name: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    total_amount: Mapped[int] = mapped_column(BigInteger)
    tax: Mapped[int] = mapped_column(BigInteger)
    is_equipment: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trade_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), index=True)
