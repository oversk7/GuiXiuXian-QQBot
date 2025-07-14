from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class Mentorship(Base):
    """师徒关系表"""
    __tablename__ = "mentorship"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[str] = mapped_column(String(32), index=True, comment="师父 ID")
    disciple_id: Mapped[str] = mapped_column(String(32), index=True, comment="徒弟 ID")
    established_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="建立师徒关系时间")
    mentor_points: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="恩师点数（由徒弟等级增长获得）")
    disciple_start_level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="徒弟拜师时的等级")
    
    def is_master(self, player_id: str) -> bool:
        """检查是否为师父"""
        return self.master_id == player_id
    
    def is_disciple(self, player_id: str) -> bool:
        """检查是否为徒弟"""
        return self.disciple_id == player_id
    
    def involves_player(self, player_id: str) -> bool:
        """检查是否涉及指定玩家"""
        return self.master_id == player_id or self.disciple_id == player_id
