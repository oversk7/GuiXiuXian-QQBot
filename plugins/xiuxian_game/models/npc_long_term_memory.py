"""
NPC长期记忆模型

存储NPC与玩家的长期记忆，包括对话总结和关键事件
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship

from .db import Base


class NPCLongTermMemory(Base):
    """NPC长期记忆表

    存储NPC与玩家的对话总结和关键事件，用于构建长期记忆上下文
    """

    __tablename__ = "npc_long_term_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, ForeignKey("npc.id", ondelete="CASCADE"), nullable=False, comment="NPC ID")
    player_id = Column(String(50), nullable=False, comment="玩家user_id")

    # 记忆类型
    memory_type = Column(String(20), nullable=False, comment="记忆类型：summary（对话总结）/ event（关键事件）")

    # 记忆内容
    content = Column(Text, nullable=False, comment="记忆内容（对话总结或事件描述）")

    # 关键事件相关字段
    event_type = Column(String(20), nullable=True, comment="事件类型：gift/quest/promise/conflict/emotion/other")
    importance_score = Column(Integer, default=5, comment="重要性评分（1-10）")
    emotion_change = Column(Integer, default=0, comment="情感变化值（好感度变化）")

    # 时间和权重
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    weight = Column(Float, default=1.0, comment="记忆权重（随时间衰减）")
    last_accessed_at = Column(DateTime, default=datetime.now, comment="最后访问时间")

    # 关联的对话范围
    from_dialogue_id = Column(Integer, nullable=True, comment="关联的起始对话ID")
    to_dialogue_id = Column(Integer, nullable=True, comment="关联的结束对话ID")

    # 元数据（改名为extra_metadata避免与SQLAlchemy保留属性冲突）
    extra_metadata = Column(JSON, nullable=True, comment="额外元数据")

    # 定义索引
    __table_args__ = (
        Index("idx_npc_player_time", "npc_id", "player_id", "created_at"),
        Index("idx_memory_type", "memory_type"),
        Index("idx_importance", "importance_score"),
        Index("idx_weight", "weight"),
    )

    def __repr__(self):
        return f"<NPCLongTermMemory(id={self.id}, npc_id={self.npc_id}, player_id={self.player_id}, type={self.memory_type})>"

    def decay_weight(self, days_passed: int, decay_rate: float = 0.95):
        """
        根据时间衰减记忆权重

        Args:
            days_passed: 经过的天数
            decay_rate: 衰减率（0-1），默认0.95（每天衰减5%）
        """
        self.weight *= (decay_rate ** days_passed)
        self.weight = max(0.1, self.weight)  # 最低权重0.1

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "event_type": self.event_type,
            "importance_score": self.importance_score,
            "emotion_change": self.emotion_change,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "weight": self.weight,
            "extra_metadata": self.extra_metadata
        }


class NPCDialogueSummaryCheckpoint(Base):
    """NPC对话总结检查点表

    记录每个NPC-玩家对的对话总结触发点，避免重复总结
    """

    __tablename__ = "npc_dialogue_summary_checkpoint"

    id = Column(Integer, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, ForeignKey("npc.id", ondelete="CASCADE"), nullable=False, comment="NPC ID")
    player_id = Column(String(50), nullable=False, comment="玩家user_id")

    # 总结状态
    last_summarized_dialogue_id = Column(Integer, nullable=False, comment="最后总结的对话ID")
    total_dialogues_summarized = Column(Integer, default=0, comment="已总结的对话总数")
    last_summary_time = Column(DateTime, default=datetime.now, comment="最后总结时间")

    # 下次总结阈值
    next_summary_threshold = Column(Integer, default=20, comment="下次总结的对话数阈值")

    # 定义索引
    __table_args__ = (
        Index("idx_npc_player_checkpoint", "npc_id", "player_id", unique=True),
    )

    def __repr__(self):
        return f"<NPCDialogueSummaryCheckpoint(npc_id={self.npc_id}, player_id={self.player_id}, last_id={self.last_summarized_dialogue_id})>"

    def should_trigger_summary(self, current_dialogue_count: int) -> bool:
        """
        判断是否应该触发总结

        Args:
            current_dialogue_count: 当前对话总数

        Returns:
            是否应该触发
        """
        unsummarized_count = current_dialogue_count - self.total_dialogues_summarized
        return unsummarized_count >= self.next_summary_threshold

    def update_after_summary(self, latest_dialogue_id: int, summarized_count: int):
        """
        更新总结后的状态

        Args:
            latest_dialogue_id: 最新总结的对话ID
            summarized_count: 本次总结的对话数量
        """
        self.last_summarized_dialogue_id = latest_dialogue_id
        self.total_dialogues_summarized += summarized_count
        self.last_summary_time = datetime.now()
