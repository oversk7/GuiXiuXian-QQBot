from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from enum import Enum as PyEnum

class ItemType(str,PyEnum):
    CONSUMABLE = "CONSUMABLE"
    MATERIAL = "MATERIAL"
    EQUIPMENT = "EQUIPMENT"

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "RESTORE_HP" 
    RESTORE_MP = "RESTORE_MP"
    BUFF = "BUFF"
    REVIVE = "REVIVE"
    # 以下类型不使用 apply_effect 处理
    CHANGE_NAME = "CHANGE_NAME"
    TELEPORT = "TELEPORT"
    APPOINT_PRESIDENT = "APPOINT_PRESIDENT"

class ItemConfig:
    def __init__(self, data: dict):
        self.item_id = data["item_id"]
        self.name = data["name"]
        self.type = ItemType(data["type"])
        self.description = data["description"]
        self.effect_type = ItemEffectType(data.get("effect_type", "BUFF"))
        self.effect_params = data.get("effect_params", {})
        self.price = data.get("price", 0)
        self.durability = data.get("durability", 0)
        self.attr_bonus = data.get("attr_bonus", {})
        self.attr_ratio = data.get("attr_ratio", {})
        # 部分材料可拥有怨念值，用于献祭
        self.grudge_value = data.get("grudge_value", 0)
        # 装备锻造配方：{"materials": {"item_id": qty, ...}, "gold": 1000}
        self.recipe = data.get("recipe")
        # 装备修复单价（每 1 点耐久消耗金币数），若为空则默认按 price/durability 计算
        self.repair_cost = data.get("repair_cost")
        

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