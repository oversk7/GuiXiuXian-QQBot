"""
玩家食谱数据模型

记录玩家学会的食谱
"""
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class PlayerRecipe(Base):
    """玩家食谱模型

    记录玩家已学会的食谱
    """
    __tablename__ = "player_recipe"

    __table_args__ = (
        Index("ix_player_recipe_player_recipe", "player_id", "recipe_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id", ondelete="CASCADE"),
        index=True,
        comment="玩家ID"
    )
    recipe_id: Mapped[str] = mapped_column(String(32), comment="食谱ID(recipes.yaml)")
    learned_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="学会时间"
    )
