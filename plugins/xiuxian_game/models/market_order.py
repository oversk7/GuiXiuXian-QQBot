from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, Enum as SAEnum, ForeignKey, func, Boolean
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
    price: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    # 装备实例交易扩展字段
    item_instance_id: Mapped[int] = mapped_column(Integer, nullable=True, comment="装备实例ID，仅装备交易使用")
    is_instance_trade: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否为装备实例交易")
    equipment_summary: Mapped[str] = mapped_column(String(500), nullable=True, comment="装备摘要信息，用于显示")

    player: Mapped["Player"] = relationship("Player")

    @property
    def item(self) -> ItemConfig | None:
        from ..config import config
        return config.items_config["by_id"].get(self.item_id)

    @property
    def is_equipment_trade(self) -> bool:
        """判断是否为装备交易"""
        return self.is_instance_trade and self.item_instance_id is not None

    def get_display_name(self) -> str:
        """获取订单显示名称"""
        if self.is_equipment_trade:
            return self.equipment_summary or f"{self.item.name if self.item else self.item_id} (装备)"
        else:
            item_name = self.item.name if self.item else self.item_id
            return f"{item_name} x{self.quantity}" if self.quantity > 1 else item_name