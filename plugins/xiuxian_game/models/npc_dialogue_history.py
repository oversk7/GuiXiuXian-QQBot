"""NPC对话历史数据模型"""
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import TYPE_CHECKING

from .db import Base

if TYPE_CHECKING:
    from .npc import NPC
    from .player import Player


class NPCDialogueHistory(Base):
    """记录玩家与NPC的对话历史"""
    __tablename__ = "npc_dialogue_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关键关联
    npc_id: Mapped[int] = mapped_column(Integer, ForeignKey("npc.id"), index=True, comment="NPC ID")
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")

    # 关联对象
    npc: Mapped["NPC"] = relationship("NPC", foreign_keys=[npc_id], back_populates="dialogue_histories")
    player: Mapped["Player"] = relationship("Player", foreign_keys=[player_id])

    # 对话内容
    dialogue_type: Mapped[str] = mapped_column(
        String(20),
        comment="对话类型: natural_dialogue | game_command"
    )
    player_input: Mapped[str] = mapped_column(Text, comment="玩家输入")
    npc_response: Mapped[str] = mapped_column(Text, comment="NPC回复")

    # 游戏命令相关（仅game_command类型使用）
    game_command: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="游戏指令内容（仅game_command类型）"
    )
    game_output: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="游戏指令执行结果"
    )
    game_command_status: Mapped[str] = mapped_column(
        String(20),
        default="success",
        comment="指令执行状态: success | failed | partial"
    )

    # 好感度变化
    favorability_change: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="本次对话导致的好感度变化"
    )
    favorability_after: Mapped[int] = mapped_column(
        Integer,
        default=50,
        comment="本次对话后的总好感度"
    )

    # 元数据
    dialogue_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="对话耗时(秒)"
    )
    ai_tokens_used: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI调用消耗的token数"
    )
    ai_cost: Mapped[float | None] = mapped_column(
        Integer,  # 使用Integer存储以分为单位的成本，避免浮点精度问题
        nullable=True,
        comment="AI调用成本(分，人民币)"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
        comment="对话时间"
    )

    # 复合索引：按NPC和玩家组合查询对话历史
    __table_args__ = (
        Index('idx_npc_player_created', 'npc_id', 'player_id', 'created_at'),
    )

    def __repr__(self):
        return f"<NPCDialogueHistory(id={self.id}, npc_id={self.npc_id}, player_id={self.player_id}, type={self.dialogue_type})>"
