"""
领域事件模块

提供事件系统的核心接口和基础设施：
- IEvent: 事件接口
- EventBus: 事件总线（发布/订阅）
- 各种领域事件定义
"""

from .interfaces import IEvent, IEventHandler
from .event_bus import EventBus

# 导出全局事件总线实例
event_bus = EventBus()

__all__ = [
    "IEvent",
    "IEventHandler",
    "EventBus",
    "event_bus",
]
