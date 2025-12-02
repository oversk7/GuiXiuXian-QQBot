# Service DI最终实现状态

## 1. Identity

- **What it is**: 诡修仙项目Service层依赖注入（DI）架构的最终实现文档，描述Feature Flag移除后的生产级实现
- **Purpose**: 为LLM代理和开发者提供DI架构的完整理解，包括架构设计、集成模式和最佳实践

## 2. 最终架构概览

### 分层架构设计

```
┌──────────────────────────────────────────────────────┐
│         Presentation Layer (命令处理层)               │
│  46个命令处理器 (guild.py, equipment_commands.py等)  │
├──────────────────────────────────────────────────────┤
│         Application Layer (Service层)                │
│  27个Service类 - DI实例化 - UnitOfWork管理          │
│  GuildServiceNew, EquipmentServiceNew, ...           │
├──────────────────────────────────────────────────────┤
│         Domain Layer (领域层)                        │
│  47个Repository接口 + UnitOfWork上下文管理           │
│  IRepository[T], GuildRepository, PlayerRepository   │
├──────────────────────────────────────────────────────┤
│         Infrastructure Layer (基础设施层)             │
│  DI容器, UnitOfWork, 47个Repository实现              │
│  Container, Unit of Work, Repository实现             │
├──────────────────────────────────────────────────────┤
│         Persistence Layer (持久化层)                 │
│  SQLAlchemy异步ORM - 49个数据模型                   │
│  Player, Guild, ItemInstance, ...                    │
└──────────────────────────────────────────────────────┘
```

### 关键特性

| 特性 | 描述 | 文件位置 |
|-----|------|--------|
| **DI容器** | 管理Service生命周期 | `infrastructure/di/container.py` |
| **UnitOfWork** | 事务管理 + 懒加载Repository | `infrastructure/uow/unit_of_work.py` |
| **Repository模式** | 数据访问抽象（47个） | `infrastructure/repositories/` |
| **Service实例** | 业务逻辑编排（27个）| `*/service_new.py` |
| **异步支持** | async/await全覆盖 | 所有层 |

---

## 3. 核心组件详解

### 3.1 DI容器 (Container)

`plugins/xiuxian_game/infrastructure/di/container.py`

**职责**:
- 注册Service和Repository
- 管理生命周期（singleton/scoped/transient）
- 自动解析依赖链

**使用示例**:
```python
# 注册（应用启动）
container.register(
    GuildService,          # 接口
    GuildServiceNew,       # 实现
    lifetime='scoped'      # 生命周期
)

# 解析（命令处理）
scope = container.create_scope()
service = scope.resolve(GuildService)
scope.dispose()
```

### 3.2 UnitOfWork (事务管理)

`plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`

**职责**:
- 统一事务边界
- 懒加载47个Repository
- 自动提交/回滚

**工作流程**:
```python
async with UnitOfWork() as uow:
    # 懒加载Repository - 首次访问时创建
    guild = await uow.guilds.get_by_id(guild_id)

    # 同一session操作
    member = await uow.guild_members.add(new_member)

    # 自动提交（成功）或回滚（异常）
    await uow.commit()
```

### 3.3 Repository模式（数据访问）

`plugins/xiuxian_game/infrastructure/repositories/`

**47个Repository实现**:
- GuildRepository - 公会查询
- PlayerRepository - 玩家查询
- InventoryRepository - 物品库存
- ...等共47个

**核心方法**:
```python
class GuildRepository(BaseRepository[Guild]):
    async def get_by_id(self, guild_id: int) -> Guild | None
    async def get_with_members(self, guild_id: int) -> Guild | None
    async def add(self, guild: Guild) -> Guild
    async def delete(self, guild_id: int) -> bool
    async def get_all_by_owner(self, owner_id: int) -> list[Guild]
```

### 3.4 Service层（业务逻辑）

`plugins/xiuxian_game/*/service_new.py`

**27个Service类**:
- 依赖Repository进行数据访问
- 编排复杂业务逻辑
- 使用UnitOfWork管理事务

**标准Service结构**:
```python
class GuildServiceNew:
    def __init__(
        self,
        guild_repo: GuildRepository,
        player_repo: PlayerRepository,
        member_repo: GuildMemberRepository
    ):
        self.guild_repo = guild_repo
        self.player_repo = player_repo
        self.member_repo = member_repo

    async def create_guild(self, player_id: int, name: str) -> Guild:
        player = await self.player_repo.get_by_id(player_id)
        if not player:
            raise ValueError("玩家不存在")

        guild = Guild(owner_id=player_id, name=name)
        return await self.guild_repo.add(guild)
```

---

## 4. 集成模式

### 模式1: 简单命令处理（单Repository）

**场景**: 只需访问一个数据表

**实现**:
```python
@matcher.handle()
async def handle_fishing(user_id: str):
    async with UnitOfWork() as uow:
        service = FishingServiceNew(uow.fishing)
        result = await service.cast_rod(player_id=user_id)
        await uow.commit()

    await matcher.send(f"钓鱼结果: {result}")
```

### 模式2: 复杂命令处理（多Repository）

**场景**: 涉及多个数据表的协作

**实现**:
```python
@matcher.handle()
async def handle_create_guild(user_id: str, guild_name: str):
    async with UnitOfWork() as uow:
        service = GuildServiceNew(
            uow.guilds,
            uow.players,
            uow.guild_members,
            uow.guild_buildings
        )
        guild = await service.create_guild(user_id, guild_name)
        await uow.commit()

    await matcher.send(f"公会{guild.name}创建成功")
```

### 模式3: Service间协作

**场景**: Service A 需要调用 Service B

**实现** (避免循环依赖):
```python
async def can_use_teleport(self, guild_id: int) -> bool:
    # 不在构造函数注入其他Service
    # 而是在方法内按需创建
    building_service = GuildBuildingServiceNew(
        self.building_repo,
        self.guild_repo
    )
    config = await building_service.get_building_config(
        guild_id, "传送阵"
    )
    return config is not None
```

### 模式4: N+1查询优化

**场景**: 查询关联对象

**Repository实现预加载**:
```python
class PlayerRepository(BaseRepository[Player]):
    async def get_with_equipment(
        self,
        player_id: int
    ) -> Player | None:
        # 使用joinedload预加载关联
        result = await self.session.execute(
            select(Player)
            .options(joinedload(Player.inventories))
            .where(Player.id == player_id)
        )
        return result.unique().scalar_one_or_none()
```

**Service调用**:
```python
# 直接访问关联对象，不触发额外查询
player = await self.player_repo.get_with_equipment(player_id)
for inventory in player.inventories:
    # 处理物品
    pass
```

---

## 5. 生命周期管理

### Scoped生命周期（推荐用于Service）

**特点**:
- 每个请求/命令创建一个实例
- 同一作用域内复用实例
- 适合无状态Service

**使用**:
```python
# 创建作用域
scope = container.create_scope()

# 解析Service实例（同作用域复用）
service1 = scope.resolve(GuildService)
service2 = scope.resolve(GuildService)
assert service1 is service2  # True

# 清理
scope.dispose()
```

### Singleton生命周期（用于配置和常量）

**特点**:
- 整个应用生命周期仅一个实例
- 适合配置、常量、缓存

**使用**:
```python
container.register(
    ConfigManager,
    ConfigManagerImpl,
    lifetime='singleton'
)
```

### Transient生命周期（避免使用）

**特点**:
- 每次解析都创建新实例
- 不适合Service（会导致多个UnitOfWork）

---

## 6. 事务管理最佳实践

### 原则1: 一个命令一个UnitOfWork

```python
# ✅ 正确
@matcher.handle()
async def handle_create_guild(user_id: str, guild_name: str):
    async with UnitOfWork() as uow:  # 单一UnitOfWork
        service = GuildServiceNew(...)
        guild = await service.create_guild(user_id, guild_name)
        await uow.commit()
    # UnitOfWork自动清理

# ❌ 错误 - 多个UnitOfWork导致事务隔离问题
@matcher.handle()
async def handle_bad(user_id: str):
    async with UnitOfWork() as uow1:
        guild = await uow1.guilds.get_by_id(1)

    async with UnitOfWork() as uow2:
        player = await uow2.players.get_by_id(user_id)
```

### 原则2: Service内部不创建UnitOfWork

```python
# ✅ 正确 - Service通过构造函数接收Repository
class GuildServiceNew:
    def __init__(self, guild_repo: GuildRepository):
        self.guild_repo = guild_repo

# ❌ 错误 - Service内部创建UnitOfWork（破坏事务原子性）
class GuildService:
    async def create_guild(self, name: str):
        async with UnitOfWork() as uow:  # 不应该在这里
            guild = Guild(name=name)
            await uow.guilds.add(guild)
```

### 原则3: 异常处理和回滚

```python
async with UnitOfWork() as uow:
    try:
        service = GuildServiceNew(uow.guilds, uow.players)
        guild = await service.create_guild(player_id, name)
        await uow.commit()
    except ValueError as e:
        # UnitOfWork自动回滚（__aexit__）
        await matcher.send(f"创建失败: {e}")
```

---

## 7. 与其他系统的集成

### 属性计算系统

**现状**: 5处属性计算，待统一

**建议路径**:
```python
# Service中使用AttributeCalculator
class EquipmentServiceNew:
    async def equip_item(self, player_id: int, item_id: int):
        player = await self.player_repo.get_by_id(player_id)
        equipment = await self.item_repo.get_by_id(item_id)

        # 使用统一的AttributeCalculator
        from ..attribute_system import AttributeCalculator
        attrs = AttributeCalculator.calculate(player, equipment)

        return attrs
```

### 事件系统

**集成方式**:
```python
from ..domain.events.event_bus import EventBus

class GuildServiceNew:
    async def create_guild(self, player_id: int, name: str):
        guild = Guild(owner_id=player_id, name=name)
        guild = await self.guild_repo.add(guild)

        # 发布事件
        await EventBus.publish(
            "guild.created",
            guild_id=guild.id,
            owner_id=player_id
        )
        return guild
```

### 效果系统

**物品效果** (已集成):
```python
from ..domain.effects.adapters import apply_effect_with_fallback

class InventoryServiceNew:
    async def use_item(self, player_id: int, item_id: int):
        result = await apply_effect_with_fallback(
            session=self.session,
            player=player,
            item_config=item_config,
            quantity=1
        )
        return result
```

**战斗效果** (集成中):
- 当前仅注册到效果系统
- 完整集成需在 `enhanced_engine.py` 中完成
- 参考: `/architecture/battle-effect-bridge.md`

---

## 8. 性能特性

### 懒加载Repository优化

**效果**:
```python
async with UnitOfWork() as uow:
    # 首次访问uow.guilds时创建GuildRepository
    guild = await uow.guilds.get_by_id(1)      # 创建 GuildRepository

    # 再次访问uow.players时创建PlayerRepository
    player = await uow.players.get_by_id(1)    # 创建 PlayerRepository

    # 只会创建实际使用的Repository，避免初始化全部47个
```

### 连接复用

**特点**:
```python
# UnitOfWork保持单一SQLAlchemy会话
async with UnitOfWork() as uow:
    guild = await uow.guilds.get_by_id(1)      # 使用同一session
    member = await uow.guild_members.add(m)    # 使用同一session
    player = await uow.players.get_by_id(1)    # 使用同一session
    # 所有操作共享一个数据库连接
```

---

## 9. 监控和调试

### 启用调试日志

```python
# 在 .env 中设置
LOG_LEVEL=DEBUG

# 期望输出
[DEBUG] UnitOfWork: Creating session
[DEBUG] Repository: Executing query SELECT * FROM guilds
[DEBUG] UnitOfWork: Committing transaction
[DEBUG] UnitOfWork: Session closed
```

### 常见问题排查

| 问题 | 原因 | 解决 |
|-----|------|------|
| 事务冲突 | 多个UnitOfWork | 确保一个命令一个UoW |
| 延迟加载异常 | 关闭UoW后访问关联 | Repository中预加载关联对象 |
| 内存泄漏 | UnitOfWork未释放 | 确保使用async with |
| 重复查询 | N+1问题 | Repository中使用joinedload |

---

## 10. 对比：Feature Flag移除前后

### 代码复杂度

**移除前**:
```python
USE_NEW_GUILD_SERVICE = True

if USE_NEW_GUILD_SERVICE:
    service = GuildServiceNew(uow.guilds, uow.players)
    guild = await service.create_guild(player_id, name)
else:
    guild = await GuildService.create_guild(player_id, name)
```

**移除后**（清晰线性）:
```python
service = GuildServiceNew(uow.guilds, uow.players)
guild = await service.create_guild(player_id, name)
```

### 代码库规模

| 指标 | 移除前 | 移除后 |
|-----|------|------|
| Service类 | 52个（26新+26旧）| 27个 |
| Feature Flag | 31个 | 0个 |
| 条件分支 | 157处 | 0处 |
| 代码行数 | ~3.5-4万 | ~2.5-3.5万 |
| 死代码比例 | ~23% | 0% |

---

## 11. 总结

### 架构优势

✅ **清晰的分层** - Presentation → Service → Repository → Database
✅ **单一职责** - 每层职责明确
✅ **易于测试** - Repository可Mock，Service可独立测试
✅ **易于扩展** - 新Service只需遵循标准模式
✅ **事务安全** - UnitOfWork统一管理事务
✅ **性能优化** - 懒加载Repository，连接复用

### 适用范围

- ✅ 所有新Service实现
- ✅ 所有命令处理器
- ✅ 复杂的业务逻辑编排
- ✅ 跨多个数据表的操作

### 注意事项

- ⚠️ Service内不创建UnitOfWork
- ⚠️ 避免Service间直接依赖（使用方法内创建）
- ⚠️ 属性计算仍未统一（5处位置）
- ⚠️ 战斗效果桥接器集成未完成

---

**文档版本**: 1.0
**更新日期**: 2025-12-02
**架构稳定性**: ✅ 生产级别
**维护者**: 通过recorder代理更新
