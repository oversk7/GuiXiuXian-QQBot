from sqlalchemy import String, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .db import Base
from datetime import datetime
import json
from typing import Dict, Any, Optional


class StorySession(Base):
    """剧情会话模型 - 存储玩家的剧情进度和状态"""
    __tablename__ = "story_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家平台ID")
    story_id: Mapped[str] = mapped_column(String(64), comment="剧情ID")
    current_node: Mapped[str] = mapped_column(String(64), comment="当前节点ID")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='True', comment="是否激活")
    story_data: Mapped[str] = mapped_column(Text, nullable=True, comment="剧情数据JSON")
    variables: Mapped[str] = mapped_column(Text, nullable=True, comment="剧情变量JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def get_story_data(self) -> Dict[str, Any]:
        """获取剧情数据"""
        if self.story_data:
            return json.loads(self.story_data)
        return {}

    def set_story_data(self, data: Dict[str, Any]):
        """设置剧情数据"""
        self.story_data = json.dumps(data, ensure_ascii=False)

    def get_variables(self) -> Dict[str, Any]:
        """获取剧情变量"""
        if self.variables:
            return json.loads(self.variables)
        return {}

    def set_variables(self, variables: Dict[str, Any]):
        """设置剧情变量"""
        self.variables = json.dumps(variables, ensure_ascii=False)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取单个剧情变量"""
        variables = self.get_variables()
        return variables.get(key, default)

    def set_variable(self, key: str, value: Any):
        """设置单个剧情变量"""
        variables = self.get_variables()
        variables[key] = value
        self.set_variables(variables)

    @classmethod
    async def get_active_session(cls, session, player_id: str) -> Optional['StorySession']:
        """获取玩家的活跃剧情会话"""
        from sqlalchemy import select
        result = await session.execute(
            select(cls).where(
                cls.player_id == player_id,
                cls.is_active == True
            ).order_by(cls.updated_at.desc())
        )
        return result.scalars().first()

    @classmethod
    async def create_session(cls, session, player_id: str, story_id: str, start_node: str = "start") -> 'StorySession':
        """创建新的剧情会话"""
        # 先结束之前的活跃会话
        from sqlalchemy import update
        await session.execute(
            update(cls).where(
                cls.player_id == player_id,
                cls.is_active == True
            ).values(is_active=False)
        )
        
        # 创建新会话
        story_session = cls(
            player_id=player_id,
            story_id=story_id,
            current_node=start_node,
            is_active=True
        )
        session.add(story_session)
        await session.flush()  # 获取ID
        return story_session
