from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Enum as SAEnum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum as PyEnum
from .db import Base
from .player import Player
from .inventory import ItemConfig

class OrderSide(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"

class MarketOrder(Base):
    """市场挂牌订单（买/卖）统一模型"""
    __tablename__ = "market_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    player: Mapped["Player"] = relationship("Player")
    @property
    def item(self) -> ItemConfig | None:
        from ..config import config
        return config.items_config["by_id"].get(self.item_id) 