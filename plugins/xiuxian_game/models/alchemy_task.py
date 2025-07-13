from datetime import datetime, timedelta
from sqlalchemy import Integer, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class AlchemyTask(Base):
    """定时炼丹任务"""

    __tablename__ = "alchemy_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    furnace_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("inventory.id", ondelete="SET NULL"))

    recipe_key: Mapped[str] = mapped_column(String(64))
    qty: Mapped[int] = mapped_column(Integer)
    success_rate: Mapped[float] = mapped_column(Float)

    produce_item_id: Mapped[str] = mapped_column(String(32))
    produce_per: Mapped[int] = mapped_column(Integer)

    finish_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=datetime.now) 