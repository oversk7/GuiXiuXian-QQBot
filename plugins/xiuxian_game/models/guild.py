from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Guild(Base):
    __tablename__ = "guild"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, comment="公会名称")
    president_id: Mapped[str] = mapped_column(String(32), comment="会长的玩家平台ID")
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="公会等级")
    exp: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="公会经验/活跃度")
    notice: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="公会公告")
    base_x: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地X坐标")
    base_y: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地Y坐标")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")