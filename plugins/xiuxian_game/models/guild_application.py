from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class GuildApplication(Base):
    __tablename__ = "guild_application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default='PENDING')  # PENDING/APPROVED/REJECTED
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now()) 