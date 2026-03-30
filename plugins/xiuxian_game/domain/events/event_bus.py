"""
事件总线实现

基于内存的异步事件总线，支持发布/订阅模式。
"""
from typing import Dict, List, Type, Callable, Awaitable
from collections import defaultdict
from nonebot import logger

from .interfaces import IEvent, IEventHandler


class EventBus:
    """
    内存事件总线

    特性：
    - 支持类型化订阅（按事件类型订阅）
    - 异步事件处理
    - 自动异常捕获和日志记录
    - 单例模式（全局共享）

    使用示例：
        # 订阅事件
        event_bus.subscribe(PlayerLevelUpEvent, achievement_handler)

        # 发布事件
        await event_bus.publish(PlayerLevelUpEvent(player_id="123", new_level=10))
    """

    def __init__(self):
        # 存储订阅关系: {EventType: [handler1, handler2, ...]}
        self._subscribers: Dict[Type[IEvent], List[IEventHandler]] = defaultdict(list)

        # 存储函数订阅者: {EventType: [func1, func2, ...]}
        self._function_subscribers: Dict[Type[IEvent], List[Callable[[IEvent], Awaitable[None]]]] = defaultdict(list)

    def subscribe(self, event_type: Type[IEvent], handler: IEventHandler) -> None:
        """
        订阅事件（使用IEventHandler实例）

        Args:
            event_type: 要订阅的事件类型
            handler: 事件处理器实例
        """
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.info(f"订阅事件: {event_type.__name__} -> {handler.__class__.__name__}")

    def subscribe_func(self, event_type: Type[IEvent], handler_func: Callable[[IEvent], Awaitable[None]]) -> None:
        """
        订阅事件（使用异步函数）

        Args:
            event_type: 要订阅的事件类型
            handler_func: 异步处理函数

        使用示例：
            async def on_level_up(event: PlayerLevelUpEvent):
                print(f"玩家 {event.player_id} 升到了 {event.new_level} 级")

            event_bus.subscribe_func(PlayerLevelUpEvent, on_level_up)
        """
        if handler_func not in self._function_subscribers[event_type]:
            self._function_subscribers[event_type].append(handler_func)
            logger.info(f"订阅事件: {event_type.__name__} -> {handler_func.__name__}")

    async def publish(self, event: IEvent) -> None:
        """
        发布事件

        事件会被分发给所有订阅了该事件类型的处理器。
        处理器按注册顺序依次执行。
        如果某个处理器抛出异常，会记录日志但不影响其他处理器。

        Args:
            event: 要发布的事件对象
        """
        event_type = type(event)
        event_name = event.event_name

        # 获取所有订阅者
        handlers = self._subscribers.get(event_type, [])
        func_handlers = self._function_subscribers.get(event_type, [])

        total_handlers = len(handlers) + len(func_handlers)

        if total_handlers == 0:
            logger.debug(f"事件 {event_name} 没有订阅者，跳过处理")
            return

        logger.info(f"发布事件: {event_name}，订阅者数量: {total_handlers}")

        # 处理IEventHandler订阅者
        for handler in handlers:
            try:
                await handler.handle(event)
            except Exception as e:
                logger.error(
                    f"事件处理器 {handler.__class__.__name__} "
                    f"处理事件 {event_name} 时发生错误: {e}",
                    exc_info=True
                )

        # 处理函数订阅者
        for func in func_handlers:
            try:
                await func(event)
            except Exception as e:
                logger.error(
                    f"事件处理函数 {func.__name__} "
                    f"处理事件 {event_name} 时发生错误: {e}",
                    exc_info=True
                )

