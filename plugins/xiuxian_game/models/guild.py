from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Guild(Base):
    __tablename__ = "guild"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, comment="公会名称")
    president_id: Mapped[str] = mapped_column(String(32), comment="会长的玩家平台ID")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间") 