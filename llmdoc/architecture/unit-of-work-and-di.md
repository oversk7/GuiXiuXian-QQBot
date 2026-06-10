# Unit of Work 与数据访问模式

## 1. Identity

- **What it is**: 工作单元（Unit of Work）模式管理多仓储事务边界；`safe_session()` 提供命令处理器的标准会话入口
- **Purpose**: 确保多个 Repository 操作共享同一数据库会话，提供自动事务提交/回滚机制，解决传统代码的多会话问题

## 2. Core Components

- `infrastructure/uow/unit_of_work.py` (`UnitOfWork`): 工作单元实现，聚合全部仓储实例并管理事务生命周期
- `models/db.py` (`safe_session`): 异步上下文管理器，命令处理器的标准会话入口（自动提交/回滚/关闭）
- `models/db.py` (`AsyncSessionLocal`): SQLAlchemy 会话工厂，创建异步数据库会话

## 3. 数据访问的两档标准模式（项目约定）

| 场景 | 使用 | 形式 |
|------|------|------|
| 命令处理器中的常规读写 | `safe_session()` | `async with safe_session() as session:` 配合 Repository 或直接查询 |
| 跨多个 Repository 的多表事务 | `UnitOfWork` | `async with UnitOfWork(AsyncSessionLocal) as uow:` 通过 `uow.players` 等属性访问仓储 |

服务的依赖通过**构造函数手动传入** Repository（例如 `GuildService(player_repo=uow.players, guild_repo=uow.guilds)`），不使用容器解析。

## 4. Execution Flow (LLM Retrieval Map)

### Unit of Work 上下文管理流程
- **1. 创建会话**: `infrastructure/uow/unit_of_work.py` 的 `__aenter__` 方法调用 `session_factory()` 创建新的 `AsyncSession`
- **2. 延迟初始化仓储**: 通过属性装饰器按需创建 Repository 实例，所有仓储共享同一个 `_session`
- **3. 业务操作**: Command Handler 通过 `uow.players.get_by_id()` 等方法执行数据操作
- **4. 自动提交/回滚**: `__aexit__` 方法根据异常类型自动调用 `commit()` 或 `rollback()`
- **5. 关闭会话**: `__aexit__` 的 `finally` 块确保会话总是被关闭，防止连接泄漏

### 异常处理与事务一致性
- **1. 流程控制异常**: 检测 Nonebot2 的 `FinishedException` 等异常，执行提交而非回滚（因为这是正常流程控制）
- **2. 业务异常**: 其他异常触发回滚，记录警告日志
- **3. 会话清理**: 无论如何都关闭会话，记录调试日志

## 5. Design Rationale

**为什么使用 Unit of Work**：
1. **事务原子性**：传统代码中打开多个独立会话，破坏事务一致性；Unit of Work 确保所有操作在同一个事务中
2. **会话共享**：多个 Repository 协作时（如查询玩家及其公会），共享同一个 AsyncSession 避免 N+1 查询
3. **连接泄漏防护**：通过上下文管理器确保会话总是被关闭，即使发生异常
4. **清晰的事务边界**：`async with UnitOfWork()` 定义明确的 transaction scope

**为什么不用 DI 容器**：
- Unit of Work 需要在 `async with` 上下文中使用，不适合容器自动注入
- 服务在 Command Handler 中手动创建、显式传入仓储，依赖关系一目了然，且天然支持单测注入 Mock
- 实际模式接近 "手动构造注入 + UoW"，比纯 DI 更符合异步编程模型

## 6. 历史说明：DI 容器已移除（2026-06-10）

`infrastructure/di/`（`DIContainer`、`setup_di_container` 等）已于 2026-06-10 删除：该容器自实现以来从未在启动流程中被初始化，业务代码零引用，属于未启用的预留设计。如未来确有需要，可从 git 历史（删除前最后提交）恢复。
