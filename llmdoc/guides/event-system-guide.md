# 事件系统使用指南

## 概述

事件系统是一个基于发布/订阅模式的异步事件总线，用于解耦跨模块功能。

**核心价值：**
- 解耦业务逻辑：核心Service无需依赖成就、统计等辅助系统
- 提高可维护性：新功能可通过订阅事件实现，无需修改现有代码
- 统一事件流：所有领域事件集中管理，便于追踪和调试

**适用场景：**
- 成就系统：监听玩家行为，自动触发成就
- 统计系统：收集游戏数据，生成排行榜
- 通知系统：在特定事件发生时发送通知
- 日志系统：记录关键游戏事件

## 快速开始

### 1. 发布事件

在Service中发布事件非常简单：

```python
from ..domain.events import event_bus, GiftGivenEvent

class GiftService:
    async def send_gift(self, sender_id: str, receiver_id: str, ...):
        # ... 业务逻辑 ...

        # 发布事件
        await event_bus.publish(GiftGivenEvent(
            sender_id=sender_id,
            receiver_id=receiver_id,
            item_id=item_config.item_id,
            item_name=item_name,
            quantity=quantity,
            favorability_gained=love_value
        ))
```

### 2. 订阅事件（类处理器）

创建一个实现 `IEventHandler` 接口的类：

```python
from ..domain.events import IEvent, IEventHandler, GiftGivenEvent
from nonebot import logger

class GiftStatisticsHandler(IEventHandler):
    """送礼统计处理器"""

    async def handle(self, event: IEvent) -> None:
        if not isinstance(event, GiftGivenEvent):
            return

        # 处理逻辑
        logger.info(f"玩家 {event.sender_id} 送出礼物")
        # 更新统计数据...
```

### 3. 订阅事件（函数式）

对于简单的逻辑，可以使用函数式处理器：

```python
async def log_gift(event: GiftGivenEvent) -> None:
    """记录送礼日志"""
    logger.info(f"{event.sender_id} → {event.receiver_id}: {event.item_name}")
```

### 4. 注册订阅

在应用启动时注册订阅关系：

```python
from ..domain.events import event_bus, GiftGivenEvent

# 类处理器
event_bus.subscribe(GiftGivenEvent, GiftStatisticsHandler())

# 函数处理器
event_bus.subscribe_func(GiftGivenEvent, log_gift)
```

## 可用事件列表

### 玩家事件
- `PlayerLevelUpEvent` - 玩家升级
- `PlayerBreakthroughEvent` - 玩家突破境界
- `PlayerAttributeChangeEvent` - 玩家属性变化
- `PlayerDeathEvent` - 玩家死亡

### 战斗事件
- `MonsterKilledEvent` - 击杀怪物
- `PvPBattleEvent` - PvP战斗
- `WorldBossDamageEvent` - 世界BOSS伤害

### 经济事件
- `ItemTradedEvent` - 物品交易
- `GoldChangeEvent` - 金币变化

### 社交事件
- `GuildDonationEvent` - 公会捐献
- `MarriageCreatedEvent` - 结婚
- `MentorshipEstablishedEvent` - 师徒关系建立
- `GiftGivenEvent` - 送礼

### 物品事件
- `ItemCraftedEvent` - 物品制作
- `EquipmentEnhancedEvent` - 装备强化

### 世界事件
- `DungeonEnteredEvent` - 进入诡域
- `DungeonCompletedEvent` - 完成诡域
- `ResourceNodeGatheredEvent` - 资源采集

## 进阶用法

### 处理多种事件

一个处理器可以处理多种事件类型：

```python
class AchievementHandler(IEventHandler):
    async def handle(self, event: IEvent) -> None:
        if isinstance(event, GiftGivenEvent):
            await self._check_gift_achievements(event)
        elif isinstance(event, WorldBossDamageEvent):
            await self._check_boss_achievements(event)
        elif isinstance(event, PlayerLevelUpEvent):
            await self._check_level_achievements(event)
```

### 访问数据库

事件处理器可以访问数据库（注意事务管理）：

```python
class StatisticsHandler(IEventHandler):
    def __init__(self, stats_repo: StatisticsRepository):
        self._stats_repo = stats_repo

    async def handle(self, event: IEvent) -> None:
        if isinstance(event, GiftGivenEvent):
            # 注意：这里需要自己管理事务
            from ..models.db import safe_session

            async with safe_session() as session:
                stats_repo = StatisticsRepository(session)
                await stats_repo.increment_gift_count(event.sender_id)
```

### 异常处理

EventBus会自动捕获处理器抛出的异常，不会影响其他处理器：

```python
async def risky_handler(event: GiftGivenEvent) -> None:
    # 即使这里抛出异常，其他处理器仍会正常执行
    if event.quantity > 1000:
        raise ValueError("数量过大")
```

## 注意事项

### 1. 事务边界

- **发布事件的时机**：应该在业务逻辑完成后、事务提交前发布
- **事件处理器的事务**：处理器如需访问数据库，应自己管理事务
- **失败处理**：事件处理器的异常不会导致原事务回滚

### 2. 性能考虑

- **同步执行**：事件处理器按注册顺序依次执行（非并发）
- **阻塞影响**：耗时的处理器会阻塞后续处理器
- **建议**：对于耗时操作，考虑使用异步任务队列

### 3. 内存事件总线的限制

- **无持久化**：重启后订阅关系会丢失
- **无重试机制**：处理失败仅记录日志
- **单进程**：不支持跨进程通信

## 最佳实践

### 1. 事件命名

事件类名应清晰描述发生了什么：
- ✅ `PlayerLevelUpEvent` - 玩家升级了
- ❌ `PlayerEvent` - 太宽泛

### 2. 事件数据

包含足够的信息，让处理器无需额外查询：
```python
@dataclass
class MonsterKilledEvent(IEvent):
    player_id: str
    monster_id: str
    monster_name: str  # ✅ 包含名称，避免额外查询
    monster_level: int
    exp_gained: int    # ✅ 包含经验值
```

### 3. 处理器职责单一

每个处理器应专注于一个功能：
```python
# ✅ 职责单一
class GiftStatisticsHandler(IEventHandler):
    """仅负责统计"""

# ✅ 职责单一
class GiftAchievementHandler(IEventHandler):
    """仅负责成就"""

# ❌ 职责混乱
class GiftEverythingHandler(IEventHandler):
    """统计、成就、通知、日志...全都做"""
```

### 4. 避免循环依赖

不要在事件处理器中发布会导致循环的事件：
```python
# ❌ 可能导致死循环
class BadHandler(IEventHandler):
    async def handle(self, event: GiftGivenEvent) -> None:
        # 处理送礼事件时又发布送礼事件！
        await event_bus.publish(GiftGivenEvent(...))
```

## 示例：实现成就系统

完整示例：如何使用事件系统实现成就检查

```python
from ..domain.events import (
    event_bus, IEventHandler, IEvent,
    GiftGivenEvent, WorldBossDamageEvent
)

class AchievementService:
    """成就服务"""

    async def check_and_unlock(self, player_id: str, achievement_id: str):
        """检查并解锁成就"""
        # 检查条件...
        # 解锁成就...
        pass

class AchievementEventHandler(IEventHandler):
    """成就事件处理器"""

    def __init__(self, achievement_service: AchievementService):
        self._service = achievement_service

    async def handle(self, event: IEvent) -> None:
        if isinstance(event, GiftGivenEvent):
            # 检查送礼相关成就
            if event.quantity >= 100:
                await self._service.check_and_unlock(
                    event.sender_id, "achievement_generous"
                )

        elif isinstance(event, WorldBossDamageEvent):
            # 检查BOSS伤害成就
            if event.damage >= 1_000_000:
                await self._service.check_and_unlock(
                    event.player_id, "achievement_damage_king"
                )

# 注册
achievement_handler = AchievementEventHandler(achievement_service)
event_bus.subscribe(GiftGivenEvent, achievement_handler)
event_bus.subscribe(WorldBossDamageEvent, achievement_handler)
```

## 相关文档

- [事件系统架构设计](../architecture/event-system-architecture.md) - 技术实现细节
- [Service DI架构](../architecture/service-di-architecture.md) - Service层设计
- [重构计划](../overview/refactoring-plan-v4.md) - 事件系统在重构中的位置
