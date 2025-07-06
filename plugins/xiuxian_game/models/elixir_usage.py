from datetime import date
from sqlalchemy import Integer, String, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class ElixirUsageLog(Base):
    """记录玩家每日服用丹药数量"""
    __tablename__ = "elixir_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32))
    use_date: Mapped[Date] = mapped_column(Date, index=True, default=date.today)
    quantity: Mapped[int] = mapped_column(Integer, default=0) 