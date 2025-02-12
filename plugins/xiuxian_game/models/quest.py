from enum import Enum
from sqlalchemy import JSON
from .db import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from sqlalchemy import ForeignKey

class QuestType(str, Enum):
    MAIN_STORY = "主线"    # 推进剧情的主线任务
    DAILY = "日常"        # 每日刷新
    ACHIEVEMENT = "成就"  # 一次性永久成就
    RANDOM = "奇遇"       # 随机触发任务

class Quest(Base):
    __tablename__ = "quests"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    quest_type: Mapped[QuestType]
    title: Mapped[str]
    description: Mapped[str]
    condition_type: Mapped[str]  # 条件类型：SIGN_IN, KILL_MONSTER, etc
    condition_params: Mapped[dict] = mapped_column(JSON)  # 条件参数
    rewards: Mapped[dict] = mapped_column(JSON)  # 奖励配置
    repeatable: Mapped[bool] = mapped_column(default=False)
    min_level: Mapped[int] = mapped_column(default=1)
    
    player_quests: Mapped[list["PlayerQuest"]] = relationship(back_populates="quest")

class PlayerQuest(Base):
    __tablename__ = "player_quests"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("player.id"))
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id"))
    progress: Mapped[int] = mapped_column(default=0)
    is_completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime] = mapped_column(nullable=True) 

    quest: Mapped["Quest"] = relationship(back_populates="player_quests")