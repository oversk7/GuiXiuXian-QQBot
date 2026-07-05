"""
LLM 用量日志

记录每次 DeepSeek 调用的 token 消耗，按玩法归因，供管理员查看费用与后续限次。
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .db import Base


class LLMUsageLog(Base):
    """LLM 调用用量日志（仅 DeepSeek 计费调用）"""

    __tablename__ = "llm_usage_log"

    __table_args__ = (
        Index("ix_llm_usage_log_feature_time", "feature", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    feature: Mapped[str] = mapped_column(String(32), index=True, comment="玩法名，如：海龟汤/怪谈主线/NPC对话")
    model: Mapped[str] = mapped_column(String(64), default="", comment="模型名，如：deepseek-v4-pro")

    # 调用来源（部分后台调用无群/玩家上下文，允许为空）
    group_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="群 openid")
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="玩家平台ID")

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入 token 总数")
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输出 token 数（含思考）")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="总 token 数")
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入中缓存命中 token 数")
    cache_miss_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入中缓存未命中 token 数")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), index=True, comment="调用时间"
    )
