from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import BaseModel
from .player import Player
from .inventory import ItemConfig

class TradeItem(BaseModel):
    __tablename__ = "trade_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    
    seller: Mapped["Player"] = relationship("Player") 

    @property
    def item(self) -> ItemConfig:
        from ..config import config
        return config.items_config["by_id"].get(self.item_id) 