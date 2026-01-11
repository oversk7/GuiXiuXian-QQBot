"""
玩家间关系数据模型

记录玩家之间的好感度和关系状态(师徒/结拜/结婚)
"""
from sqlalchemy import String, Integer, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum as PyEnum
from .db import Base


class RelationshipType(str, PyEnum):
    """关系类型枚举"""
    NONE = "none"           # 陌生人
    MENTORSHIP = "mentorship"  # 师徒
    SWORN = "sworn"         # 结拜
    MARRIAGE = "marriage"   # 结婚


class PlayerRelationship(Base):
    """
    玩家间关系表

    设计要点:
    - 双向关系: player_id和target_id通过排序确保唯一性
    - 好感度: 0-10000,通过送礼等行为增加
    - 每日上限: 防止刷好感度,每天对同一人最多获得500好感度
    - 关系类型: 达到好感度阈值后可通过NPC建立正式关系(结婚/结义需要5000好感度)
    """
    __tablename__ = "player_relationship"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 双向关系(使用较小的ID作为player_id,确保唯一性)
    player_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
        comment="玩家A的ID"
    )
    target_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
        comment="玩家B的ID"
    )

    # 好感度数据 (0-10000)
    favorability: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="好感度(0-10000)"
    )

    # 今日送礼统计 (每日上限500)
    today_favorability_gain: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="今日已获得好感度"
    )
    last_gift_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=None,
        nullable=True,
        comment="最后送礼日期"
    )

    # 互动统计
    total_gifts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="双方送礼总次数"
    )
    last_interaction_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=None,
        nullable=True,
        comment="最后互动日期"
    )

    # 关系状态
    relationship_type: Mapped[str] = mapped_column(
        String(20),
        default=RelationshipType.NONE.value,
        comment="关系类型: none/mentorship/sworn/marriage"
    )

    # 索引和约束
    __table_args__ = (
        UniqueConstraint(
            'player_id', 'target_id',
            name='uk_player_relationship'
        ),
        Index('idx_favorability', 'favorability'),
        Index('idx_relationship_type', 'relationship_type'),
    )
