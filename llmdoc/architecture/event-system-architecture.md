# 事件系统架构设计

## 架构概述

事件系统基于经典的**发布/订阅模式**（Pub/Sub），提供类型安全的异步事件通信机制。

```
┌─────────────┐         ┌─────────────┐         ┌──────────────────┐
│   Service   │  发布   │  EventBus   │  分发   │ EventHandler(s)  │
│  (发布者)   │────────>│  (事件总线) │────────>│   (订阅者)       │
└─────────────┘         └─────────────┘         └──────────────────┘
```

### 核心组件

1. **IEvent (事件接口)** - 所有领域事件的基类
2. **IEventHandler (处理器接口)** - 事件处理器的契约
3. **EventBus (事件总线)** - 发布/订阅的实现
4. **Game Events (领域事件)** - 具体的游戏事件定义

## 代码结构

```
plugins/xiuxian_game/domain/events/
├── __init__.py              # 模块入口，导出全局event_bus
├── interfaces.py            # IEvent、IEventHandler接口定义
├── event_bus.py             # EventBus实现
├── game_events.py           # 所有游戏事件定义
└── example_handlers.py      # 示例处理器
```

## 核心设计

### 1. IEvent - 事件基类

```python
@dataclass
class IEvent(ABC):
    """领域事件基类接口"""

    # 事件发生时间（自动生成）
    occurred_at: datetime = field(default_factory=datetime.now)

    @property
    @abstractmethod
    def event_name(self) -> str:
        """事件名称（用于日志和调试）"""
        pass
```

**设计要点：**
- 使用 `@dataclass` 简化事件数据定义
- `occurred_at` 自动记录事件发生时间
- `event_name` 用于日志输出和调试

### 2. EventBus - 事件总线

```python
class EventBus:
    """内存事件总线"""

    def __init__(self):
        # 存储订阅关系: {EventType: [handler1, handler2, ...]}
        self._subscribers: Dict[Type[IEvent], List[IEventHandler]] = defaultdict(list)
        self._function_subscribers: Dict[Type[IEvent], List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: Type[IEvent], handler: IEventHandler):
        """订阅事件（使用IEventHandler实例）"""

    def subscribe_func(self, event_type: Type[IEvent], handler_func: Callable):
        """订阅事件（使用异步函数）"""

    async def publish(self, event: IEvent):
        """发布事件"""
```

**设计要点：**
- 类型安全：使用 `Type[IEvent]` 确保类型正确
- 双重订阅：支持类处理器和函数处理器
- 异常隔离：处理器异常不影响其他处理器

### 3. 事件分发流程

```python
async def publish(self, event: IEvent) -> None:
    """发布事件"""
    event_type = type(event)

    # 获取所有订阅者
    handlers = self._subscribers.get(event_type, [])
    func_handlers = self._function_subscribers.get(event_type, [])

    # 依次执行（按注册顺序）
    for handler in handlers:
        try:
            await handler.handle(event)
        except Exception as e:
            logger.error(f"事件处理器异常: {e}", exc_info=True)
            # 继续执行其他处理器

    for func in func_handlers:
        try:
            await func(event)
        except Exception as e:
            logger.error(f"事件处理函数异常: {e}", exc_info=True)
```

**关键特性：**
1. **顺序执行**：处理器按注册顺序依次执行（非并发）
2. **异常隔离**：某个处理器失败不影响其他处理器
3. **日志记录**：所有异常都会被记录到日志

## 事件生命周期

```
1. Service执行业务逻辑
   ↓
2. 业务逻辑完成，创建事件对象
   ↓
3. 调用 event_bus.publish(event)
   ↓
4. EventBus查找该事件类型的所有订阅者
   ↓
5. 按注册顺序依次调用处理器
   ↓
6. 处理器执行完成（或失败但被捕获）
   ↓
7. 所有处理器执行完毕，publish返回
   ↓
8. Service继续执行（或返回）
```

## 事务与事件的关系

### 发布时机

事件应该在**业务逻辑完成后、事务提交前**发布：

```python
async def send_gift(self, sender_id: str, receiver_id: str, ...):
    # 1. 扣除发送者物品
    await self._item_repo.consume_item(...)

    # 2. 添加接收者物品
    await self._item_repo.add_item(...)

    # 3. 记录礼物
    await self._gift_record_repo.add(gift_record)

    # 4. 更新关系（如婚姻恩爱值）
    await self._marriage_service.update_gift_value(...)

    # ✅ 业务逻辑完成，发布事件
    await event_bus.publish(GiftGivenEvent(...))

    # 5. 返回成功消息
    return True, "送礼成功"

    # 注意：这里不commit，由调用方的safe_session自动commit
```

### 事务边界

```
┌─────────────────────────────────────────────┐
│  safe_session (Transaction Boundary)        │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Service.send_gift()                │   │
│  │    - 业务逻辑...                     │   │
│  │    - event_bus.publish(event) ✅     │   │
│  │    └─> Handler1.handle(event)       │   │
│  │        └─> safe_session (新事务)     │   │
│  │    └─> Handler2.handle(event)       │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  session.commit() ✅ (自动提交)             │
└─────────────────────────────────────────────┘
```

**重要原则：**
- Service发布事件时，**原事务尚未提交**
- 处理器如需数据库操作，应**自己创建新事务**
- 处理器失败**不会导致原事务回滚**

## 类型安全机制

### 1. 事件类型匹配

```python
# ✅ 类型安全：只能订阅IEvent的子类
event_bus.subscribe(GiftGivenEvent, handler)

# ❌ 类型错误：编译时会报错
event_bus.subscribe(str, handler)  # str不是IEvent子类
```

### 2. 处理器类型检查

```python
class MyHandler(IEventHandler):
    async def handle(self, event: IEvent) -> None:
        # 运行时类型检查
        if isinstance(event, GiftGivenEvent):
            # 这里event被窄化为GiftGivenEvent类型
            print(event.item_name)  # ✅ 可以访问特定字段
```

## 性能考虑

### 当前实现（内存事件总线）

**优点：**
- 简单高效，无外部依赖
- 延迟极低（微秒级）
- 易于调试和测试

**限制：**
- 单进程：不支持跨进程通信
- 无持久化：重启后订阅关系丢失
- 无重试：处理失败仅记录日志
- 同步执行：处理器按顺序执行（非并发）

### 性能优化建议

1. **轻量级处理器**
   ```python
   # ✅ 快速处理：仅记录日志
   async def log_event(event: GiftGivenEvent):
       logger.info(f"Gift: {event.item_name}")

   # ❌ 重量级处理：访问数据库
   async def heavy_handler(event: GiftGivenEvent):
       async with safe_session() as session:
           # 数据库操作会阻塞后续处理器...
   ```

2. **异步任务队列**（未来优化）
   ```python
   # 对于耗时操作，考虑使用Celery等任务队列
   async def handle(self, event: GiftGivenEvent):
       # 将耗时操作放入队列
       await task_queue.enqueue("update_statistics", event)
   ```

## 扩展性设计

### 未来可能的增强

1. **持久化事件总线**
   - 使用Redis/RabbitMQ代替内存
   - 支持跨进程/跨服务器通信
   - 事件持久化，支持重放

2. **事件优先级**
   ```python
   @dataclass
   class IEvent(ABC):
       priority: int = 0  # 优先级
   ```

3. **条件订阅**
   ```python
   event_bus.subscribe(
       GiftGivenEvent,
       handler,
       condition=lambda e: e.quantity > 100  # 仅处理大额送礼
   )
   ```

4. **并发处理**
   ```python
   # 并发执行处理器（需注意事务问题）
   await asyncio.gather(*[h.handle(event) for h in handlers])
   ```

## 测试策略

### 单元测试

```python
import pytest
from ..domain.events import EventBus, GiftGivenEvent

@pytest.mark.asyncio
async def test_event_publish():
    bus = EventBus()
    called = False

    async def handler(event: GiftGivenEvent):
        nonlocal called
        called = True

    bus.subscribe_func(GiftGivenEvent, handler)

    await bus.publish(GiftGivenEvent(
        sender_id="user1",
        receiver_id="user2",
        item_id="gift1",
        item_name="礼物",
        quantity=1,
        favorability_gained=10
    ))

    assert called
```

### 集成测试

```python
@pytest.mark.asyncio
async def test_gift_service_emits_event():
    # 准备
    event_received = None

    async def capture_event(event: GiftGivenEvent):
        nonlocal event_received
        event_received = event

    event_bus.subscribe_func(GiftGivenEvent, capture_event)

    # 执行
    async with safe_session() as session:
        gift_service = GiftService(...)
        await gift_service.send_gift(...)

    # 验证
    assert event_received is not None
    assert event_received.sender_id == "user1"
```

## 与其他架构的关系

```
┌─────────────────────────────────────────────────┐
│           Application Layer (Commands)          │
│                   ↓                             │
│  ┌──────────────────────────────────────────┐  │
│  │      Service Layer (Business Logic)      │  │
│  │          ↓                    ↓           │  │
│  │   Repository Layer    →  EventBus        │  │
│  │          ↓                    ↓           │  │
│  │   Database Layer        EventHandlers    │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  横切关注点: 成就、统计、通知等通过事件解耦      │
└─────────────────────────────────────────────────┘
```

- **Service层**：发布领域事件
- **Repository层**：仅负责数据访问，不涉及事件
- **EventHandler**：跨模块功能（成就、统计等）
- **DI容器**：管理Service和Handler的依赖注入

## 相关文档

- [事件系统使用指南](../guides/event-system-guide.md) - 如何使用
- [Service DI架构](./service-di-architecture.md) - Service层设计
- [重构计划](../overview/refactoring-plan-v4.md) - 事件系统的定位
