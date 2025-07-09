from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base

class PurchaseRequest(Base):
    __tablename__ = "purchase_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requester_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer, comment="剩余需求数量")
    price: Mapped[int] = mapped_column(Integer, comment="单价")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now()) 