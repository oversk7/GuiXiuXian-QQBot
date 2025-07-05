from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class BankAccount(Base):
    __tablename__ = "bank_account"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    last_interest: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now()) 