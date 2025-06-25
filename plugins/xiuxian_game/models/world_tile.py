from sqlalchemy import Integer, String, DateTime, func, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy.ext.mutable import MutableDict
from .db import Base

class WorldTile(Base):
    """区域内某坐标在某次刷新周期内对应的世界格信息"""
    __tablename__ = "world_tile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(32), index=True, comment="区域标识")
    x: Mapped[int] = mapped_column(Integer, comment="坐标X")
    y: Mapped[int] = mapped_column(Integer, comment="坐标Y")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), comment="当前格子最后一次生成/刷新时间")
    event_type: Mapped[str] = mapped_column(String(24), default="EMPTY", server_default="EMPTY", comment="事件类型")
    seed: Mapped[str] = mapped_column(String(64), comment="生成种子", nullable=True)
    state: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, server_default='{}', comment="事件状态JSON")

    # 添加唯一约束，确保同一区域同一坐标只能有一条记录
    __table_args__ = (
        UniqueConstraint('region', 'x', 'y', name='uq_region_coordinates'),
    )

    def __repr__(self) -> str:
        return f"<WorldTile {self.region} ({self.x},{self.y}) {self.event_type}>" 