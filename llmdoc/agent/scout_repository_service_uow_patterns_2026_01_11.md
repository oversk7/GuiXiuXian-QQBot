# Repository、Service 和 Unit of Work 实现模式调查报告

**调查时间**: 2026-01-11
**调查目的**: 快速了解项目中 Repository、Service 和 Unit of Work 的实现模式
**调查范围**: infrastructure/repositories、*_service_new.py、infrastructure/uow

---

## Code Sections (证据)

### Repository 实现模式

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\domain\repositories\base.py` (IRepository[T])
  - 泛型抽象基类，定义标准 CRUD 方法
  - 必须实现的抽象方法: `get_by_id`, `add`, `update`, `delete`, `exists`, `count`
  - 使用 `Generic[T]` 和 `TypeVar` 支持强类型

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\player_repository.py` (PlayerRepository)
  - 继承 `IRepository[Player]`
  - 构造函数接收 `AsyncSession` (由 UnitOfWork 注入)
  - 标准方法示例: `get_by_id`, `add`, `update`, `delete`, `exists`, `count`
  - 领域查询方法示例: `get_by_uid`, `get_with_monthly_cards`, `get_nearby_players`, `get_active_by_platform_id`
  - 使用 SQLAlchemy 2.0 风格: `select()` + `execute()`
  - 使用 `joinedload()` 优化 N+1 查询

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\guild_repository.py` (GuildRepository)
  - 继承 `IRepository[Guild]`
  - 领域查询方法: `get_by_name`, `get_member`, `add_member`, `remove_member`, `get_member_count`

### Service 实现模式

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\guild\guild_service_new.py` (GuildService)
  - 构造函数依赖注入模式
  - 接收参数: `player_repo: PlayerRepository`, `guild_repo: GuildRepository`, `uow: Optional[UnitOfWork]`
  - 将仓储存储为私有字段: `self._player_repo`, `self._guild_repo`, `self._uow`
  - 所有业务方法改为实例方法 (非静态方法)
  - 可选地接收 `UnitOfWork` 用于需要直接访问 `session` 的复杂场景

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_new.py` (StockService)
  - 多依赖注入示例: 注入 5 个不同的 Repository
  - 接收参数: `player_repo`, `stock_repo`, `stock_holding_repo`, `stock_transaction_repo`, `bank_account_repo`
  - 所有仓储通过构造函数注入，无 session 参数

### Unit of Work 实现模式

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\uow\unit_of_work.py` (UnitOfWork)
  - 上下文管理器: `async with UnitOfWork(session_factory) as uow:`
  - 构造函数接收 `session_factory: Callable[[], AsyncSession]`
  - 延迟初始化仓储: 使用 `@property` 装饰器按需创建 Repository 实例
  - 所有 Repository 共享同一个 `_session`

**在 UnitOfWork 中注册新 Repository 的步骤**:
1. 在 `__init__` 中添加私有字段: `self._custom_repo = None`
2. 创建 `@property` 装饰器:
   ```python
   @property
   def custom_repo(self):
       """自定义仓储"""
       if self._custom_repo is None:
           from ..repositories.custom_repository import CustomRepository
           self._custom_repo = CustomRepository(self._session)
       return self._custom_repo
   ```

**使用示例**:
```python
async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id(player_id)
    guild = await uow.guilds.get_by_id(player.guild_id)
    # 自动提交或回滚
```

---

## Report (答案)

### result

#### 1. Repository 实现模式

**基类和必须实现的方法**:
- 基类: `IRepository[T]` (位于 `domain/repositories/base.py`)
- 必须实现的标准 CRUD 方法:
  - `async def get_by_id(self, id: Any) -> Optional[T]`
  - `async def add(self, entity: T) -> T`
  - `async def update(self, entity: T) -> T`
  - `async def delete(self, id: Any) -> bool`
  - `async def exists(self, id: Any) -> bool`
  - `async def count(self) -> int`

**Repository 类结构**:
```python
class PlayerRepository(IRepository[Player]):
    def __init__(self, session: AsyncSession):
        self._session = session

    # 实现 6 个标准方法...

    # 添加领域查询方法
    async def get_by_uid(self, uid: int) -> Optional[Player]:
        stmt = select(Player).where(Player.uid == uid)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

**关键设计要点**:
- 通过构造函数注入 `AsyncSession` (由 UnitOfWork 提供)
- 使用 SQLAlchemy 2.0 风格的 `select()` 语句
- 使用 `joinedload()` 预加载关联实体，避免 N+1 查询
- 领域查询方法根据业务需求添加 (如 `get_by_uid`, `get_nearby_players`)

#### 2. Service 实现模式

**构造函数依赖注入方式**:
```python
class GuildService:
    def __init__(
        self,
        player_repo: PlayerRepository,
        guild_repo: GuildRepository,
        uow: Optional[UnitOfWork] = None
    ):
        self._player_repo = player_repo
        self._guild_repo = guild_repo
        self._uow = uow
```

**使用示例** (在 Command Handler 中):
```python
async with UnitOfWork(AsyncSessionLocal) as uow:
    # 手动创建 Service 实例
    guild_service = GuildService(
        player_repo=uow.players,
        guild_repo=uow.guilds,
        uow=uow
    )

    # 调用业务方法
    success, message, guild = await guild_service.create_guild(player_id, guild_name)
```

**关键设计要点**:
- 所有业务方法改为实例方法 (从静态方法迁移)
- 通过构造函数注入 Repository 依赖，不接收 session 参数
- 可选地注入 `UnitOfWork` 用于需要直接访问 `session` 的复杂查询
- 仓储存储为私有字段 (命名约定: `self._xxx_repo`)

#### 3. Unit of Work 使用方式

**在 UnitOfWork 中注册新 Repository**:

**步骤 1**: 在 `UnitOfWork.__init__` 中添加私有字段
```python
def __init__(self, session_factory: Callable[[], AsyncSession]):
    # ... 现有仓储 ...
    self._custom_repo = None  # 新增
```

**步骤 2**: 创建属性装饰器
```python
@property
def custom_repo(self):
    """自定义仓储"""
    if self._custom_repo is None:
        from ..repositories.custom_repository import CustomRepository
        self._custom_repo = CustomRepository(self._session)
    return self._custom_repo
```

**使用新注册的 Repository**:
```python
async with UnitOfWork(AsyncSessionLocal) as uow:
    # 使用新注册的仓储
    result = await uow.custom_repo.some_method()
```

**关键设计要点**:
- 延迟初始化: Repository 在第一次访问时才创建
- 共享会话: 所有 Repository 使用同一个 `_session`
- 自动事务管理: `__aenter__` 创建会话，`__aexit__` 自动提交/回滚
- 异常处理:
  - Nonebot2 流程控制异常 (FinishedException 等): 提交事务
  - 其他异常: 回滚事务
  - 无论如何都关闭会话

---

## conclusions

1. **Repository 模式统一**: 所有 42 个 Repository 继承 `IRepository[T]` 泛型基类，实现 6 个标准 CRUD 方法，并添加领域特定查询方法

2. **Service 依赖注入**: Service 通过构造函数注入 Repository，使用私有字段存储依赖 (`self._xxx_repo`)，可选注入 UnitOfWork 用于复杂场景

3. **UnitOfWork 集中管理**: 管理所有 Repository 实例和事务边界，使用延迟初始化优化性能，确保会话共享和自动清理

4. **架构一致性**: 项目已完成 100% 架构统一，所有 Service 都遵循相同的依赖注入模式，无 legacy 静态方法服务残留

---

## relations

- Repository 基类定义 → `domain/repositories/base.py` (IRepository[T])
- Repository 实现示例 → `infrastructure/repositories/player_repository.py`, `infrastructure/repositories/guild_repository.py`
- Service 实现示例 → `guild/guild_service_new.py`, `economy/stock_service_new.py`
- Unit of Work 实现 → `infrastructure/uow/unit_of_work.py`
- 架构文档 → `llmdoc/architecture/repository-pattern-implementation.md`, `llmdoc/architecture/unit-of-work-and-di.md`
- 迁移指南 → `llmdoc/guides/data-access-migration-guide.md`
