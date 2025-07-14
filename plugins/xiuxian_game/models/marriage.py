from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base


class Marriage(Base):
    """婚姻关系表"""
    __tablename__ = "marriage"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player1_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家1 ID")
    player2_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家2 ID")
    married_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="结婚时间")
    total_gift_value: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="双方互送礼物总价值")
    
    def get_spouse_id(self, player_id: str) -> str | None:
        """获取配偶ID"""
        if self.player1_id == player_id:
            return self.player2_id
        elif self.player2_id == player_id:
            return self.player1_id
        return None
    
    def involves_player(self, player_id: str) -> bool:
        """检查是否涉及指定玩家"""
        return self.player1_id == player_id or self.player2_id == player_id
