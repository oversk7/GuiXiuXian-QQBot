"""
阴宅仓库物品数据模型

存储玩家个人阴宅仓库中的物品堆叠记录
"""
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class MansionWarehouseItem(Base):
    """阴宅仓库物品表"""
    __tablename__ = "mansion_warehouse_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    item_id: Mapped[str] = mapped_column(String(64), comment="物品模板ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    deposited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="存入时间")

    __table_args__ = (
        {"comment": "阴宅仓库物品表"}
    )
