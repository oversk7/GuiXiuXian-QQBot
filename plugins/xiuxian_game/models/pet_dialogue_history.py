"""宠物对话历史模型"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class PetDialogueHistory(Base):
    """宠物对话历史记录"""
    __tablename__ = "pet_dialogue_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pet_id: Mapped[int] = mapped_column(Integer, index=True, comment="宠物实例ID")
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    player_input: Mapped[str] = mapped_column(Text, comment="玩家输入")
    pet_response: Mapped[str] = mapped_column(Text, comment="宠物回复")
    affection_change: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="好感度变化")
    mood_change: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="心情变化")
    ai_tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="AI消耗token数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="对话时间")
