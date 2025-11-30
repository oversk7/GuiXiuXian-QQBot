from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player

class BankAccount(Base):
    __tablename__ = "bank_account"

    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("players.id"), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    last_interest: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # 关联到Player（用于预加载优化）
    player: Mapped["Player"] = relationship("Player", lazy="raise") 