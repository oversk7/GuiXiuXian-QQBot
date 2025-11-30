"""
事件系统接口定义
"""
from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class IEvent(ABC):
    """
    领域事件基类接口

    所有领域事件必须继承此类并实现必要的属性。
    使用dataclass简化事件数据的定义。
    """

    # 事件发生时间（自动生成，使用kw_only避免与子类必需参数冲突）
    occurred_at: datetime = field(default_factory=datetime.now, kw_only=True)

    # 事件名称（用于日志和调试）
    @property
    @abstractmethod
    def event_name(self) -> str:
        """事件名称"""
        pass


class IEventHandler(ABC):
    """
    事件处理器接口

    所有事件订阅者必须实现此接口。
    """

    @abstractmethod
    async def handle(self, event: IEvent) -> None:
        """
        处理事件

        Args:
            event: 领域事件对象

        Raises:
            可以抛出任何异常，EventBus会捕获并记录日志
        """
        pass
