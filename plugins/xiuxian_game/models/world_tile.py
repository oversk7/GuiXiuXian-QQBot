from sqlalchemy import Integer, String, DateTime, func, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy.ext.mutable import MutableDict
from .db import Base

class WorldTile(Base):
    """区域内某坐标在某次刷新周期内对应的世界格信息

    支持双层坐标系统：
    - 现实世界：region="大都会"，x/y为大坐标
    - 诡域：region="N层诡域"，x/y为小坐标(-5到5)
    """
    __tablename__ = "world_tile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, default=1, server_default="1", index=True, comment="所属区服ID")
    region: Mapped[str] = mapped_column(String(32), index=True, comment="区域标识(大都会/N层诡域)")
    x: Mapped[int] = mapped_column(Integer, comment="坐标X(现实世界大坐标或诡域小坐标)")
    y: Mapped[int] = mapped_column(Integer, comment="坐标Y(现实世界大坐标或诡域小坐标)")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), comment="当前格子最后一次生成/刷新时间")
    event_type: Mapped[str] = mapped_column(String(24), default="EMPTY", server_default="EMPTY", comment="事件类型")
    seed: Mapped[str] = mapped_column(String(64), comment="生成种子", nullable=True)
    state: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, comment="事件状态JSON")

    __table_args__ = (
        UniqueConstraint('server_id', 'region', 'x', 'y', name='uq_server_region_coordinates'),
    )

    def __repr__(self) -> str:
        return f"<WorldTile {self.region} ({self.x},{self.y}) {self.event_type}>"

    def is_dungeon_tile(self) -> bool:
        """判断是否为诡域格子"""
        return self.region != "大都会" and "层诡域" in self.region

    def get_dungeon_level(self) -> int:
        """获取诡域层级，如果不是诡域则返回0"""
        if not self.is_dungeon_tile():
            return 0
        try:
            return int(self.region.replace("层诡域", ""))
        except ValueError:
            return 0
