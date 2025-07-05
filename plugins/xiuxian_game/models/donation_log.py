from sqlalchemy import Integer, String, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

class PlayerDonationLog(Base):
    """记录玩家每日金币捐献额度，用于限额校验"""

    __tablename__ = "player_donation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    donate_date: Mapped[Date] = mapped_column(Date, index=True, server_default=func.current_date())
    amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0") 