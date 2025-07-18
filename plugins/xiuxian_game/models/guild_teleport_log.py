from sqlalchemy import Integer, String, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from .db import Base

class GuildTeleportLog(Base):
    """记录玩家每日公会传送使用次数，用于限制每日使用一次"""

    __tablename__ = "guild_teleport_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    guild_id: Mapped[int] = mapped_column(Integer, index=True, comment="公会ID")
    teleport_date: Mapped[Date] = mapped_column(Date, index=True, default=date.today, server_default=func.current_date(), comment="传送日期")
    usage_count: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="当日使用次数")
