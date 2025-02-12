from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from ..data.db import Base
from enum import Enum as PyEnum

class ItemType(str,PyEnum):
    CONSUMABLE = "CONSUMABLE"
    MATERIAL = "MATERIAL"
    EQUIPMENT = "EQUIPMENT"

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "RESTORE_HP"
    RESTORE_MP = "RESTORE_MP"
    BUFF = "BUFF"
    SPECIAL = "SPECIAL"
    REVIVE = "REVIVE"

class ItemConfig:
    def __init__(self, data: dict):
        self.item_id = data["item_id"]
        self.name = data["name"]
        self.type = ItemType(data["type"])
        self.description = data["description"]
        self.effect_type = ItemEffectType(data.get("effect_type", "BUFF"))
        self.effect_params = data.get("effect_params", {})
        self.price = data.get("price", 0)
        

class Inventory(Base):
    __tablename__ = "inventory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    
    @property
    def config(self) -> ItemConfig:
        from ..config import config
        return config.items_config["by_id"].get(self.item_id) 