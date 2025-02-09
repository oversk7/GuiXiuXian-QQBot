from sqlalchemy import JSON, String, Integer, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import BaseModel
from enum import Enum as PyEnum

class ItemType(str, PyEnum):
    CONSUMABLE = "消耗品"
    MATERIAL = "材料"
    EQUIPMENT = "装备"

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "恢复生命"
    RESTORE_MP = "恢复理智"
    BUFF = "增益效果"

class Item(BaseModel):
    __tablename__ = "items"
    
    item_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="物品唯一ID")
    name: Mapped[str] = mapped_column(String(24), unique=True, comment="物品名称")
    description: Mapped[str] = mapped_column(String(128), nullable=True, comment="物品描述")
    type: Mapped[ItemType] = mapped_column(Enum(ItemType), comment="物品类型")
    effect_type: Mapped[ItemEffectType] = mapped_column(Enum(ItemEffectType), nullable=True, comment="效果类型")
    effect_params: Mapped[dict] = mapped_column(JSON, nullable=True, comment="效果参数")
    max_stack: Mapped[int] = mapped_column(Integer, default=99, server_default='99', comment="最大堆叠数量")

class Inventory(BaseModel):
    __tablename__ = "inventory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(32), ForeignKey("items.item_id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="数量")
    
    item: Mapped[Item] = relationship("Item", lazy="joined") 