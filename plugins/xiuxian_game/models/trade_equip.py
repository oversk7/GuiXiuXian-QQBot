from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from .player import Player
from .equipment import EquipmentInstance

class TradeEquip(Base):
    """装备交易市场挂牌信息
    id: 自增主键
    equip_id: 对应 EquipmentInstance.id
    seller_id: 玩家平台ID
    price: 单价（金币）
    created_at: 上架时间
    """
    __tablename__ = "trade_equips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equip_id: Mapped[int] = mapped_column(Integer, ForeignKey("equipment_instances.id"), index=True)
    seller_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    equip: Mapped["EquipmentInstance"] = relationship("EquipmentInstance")
    seller: Mapped["Player"] = relationship("Player") 