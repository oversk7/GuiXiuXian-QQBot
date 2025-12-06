"""NPC好感度数据模型"""
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime
from typing import TYPE_CHECKING

from .db import Base

if TYPE_CHECKING:
    from .npc import NPC
    from .player import Player


class NPCFavorability(Base):
    """记录玩家与NPC的好感度关系"""
    __tablename__ = "npc_favorability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关键关联（复合唯一索引）
    npc_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("npc.id"),
        index=True,
        comment="NPC ID"
    )
    player_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id"),
        index=True,
        comment="玩家ID"
    )

    # 关联对象
    npc: Mapped["NPC"] = relationship("NPC", foreign_keys=[npc_id], back_populates="favorability_records")
    player: Mapped["Player"] = relationship("Player", foreign_keys=[player_id])

    # 好感度数据
    current_favorability: Mapped[int] = mapped_column(
        Integer,
        default=50,
        comment="当前好感度(0-100)"
    )
    total_interactions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="累计互动次数"
    )
    total_favorability_gained: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="累计好感度获得（可为负）"
    )

    # 关系等级
    relationship_level: Mapped[str] = mapped_column(
        String(20),
        default="陌生人",
        comment="关系等级: 陌生人|熟识|友好|亲密|知心"
    )

    # 特殊关系
    is_follower: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="是否跟随关系"
    )
    is_partner: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="是否伴侣关系"
    )

    # 关键事件记录（JSON存储）
    milestone_events: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment='关键事件记录，如{"first_100_favorability": "2025-12-06 12:00:00"}'
    )

    # 时间戳
    first_interaction_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="首次互动时间"
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后互动时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="记录更新时间"
    )

    def __repr__(self):
        return f"<NPCFavorability(npc_id={self.npc_id}, player_id={self.player_id}, favorability={self.current_favorability}, level={self.relationship_level})>"

    def get_relationship_level(self) -> str:
        """根据好感度返回关系等级"""
        if self.current_favorability <= 20:
            return "陌生人"
        elif self.current_favorability <= 40:
            return "熟识"
        elif self.current_favorability <= 60:
            return "友好"
        elif self.current_favorability <= 80:
            return "亲密"
        else:
            return "知心"

    def get_favorability_attitude(self) -> str:
        """根据好感度返回对应的态度描述"""
        if self.current_favorability <= 20:
            return "冷漠、敷衍"
        elif self.current_favorability <= 40:
            return "友好、配合"
        elif self.current_favorability <= 60:
            return "热情、主动"
        elif self.current_favorability <= 80:
            return "亲切、信任"
        else:
            return "忠诚、无条件"
