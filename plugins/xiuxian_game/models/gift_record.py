from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum as PyEnum
from .db import Base


class GiftType(str, PyEnum):
    """礼物类型"""
    MARRIAGE = "marriage"  # 夫妻间送礼
    MENTORSHIP = "mentorship"  # 师徒间送礼


class GiftRecord(Base):
    """礼物记录表"""
    __tablename__ = "gift_record"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(String(32), index=True, comment="送礼人 ID")
    receiver_id: Mapped[str] = mapped_column(String(32), index=True, comment="收礼人 ID")
    item_id: Mapped[str] = mapped_column(String(32), comment="物品 ID")
    item_name: Mapped[str] = mapped_column(String(64), comment="物品名称")
    quantity: Mapped[int] = mapped_column(Integer, comment="数量")
    total_value: Mapped[int] = mapped_column(Integer, comment="总价值")
    gift_type: Mapped[GiftType] = mapped_column(String(16), index=True, comment="礼物类型")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="送礼时间")
    
    def involves_players(self, player1_id: str, player2_id: str) -> bool:
        """检查是否涉及指定的两个玩家"""
        return (self.sender_id == player1_id and self.receiver_id == player2_id) or \
               (self.sender_id == player2_id and self.receiver_id == player1_id)
