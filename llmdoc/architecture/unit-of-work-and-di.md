# Unit of Work 和依赖注入架构

## 1. Identity

- **What it is**: 工作单元（Unit of Work）模式管理事务边界，配合依赖注入容器（DI Container）实现服务生命周期管理
- **Purpose**: 确保多个 Repository 操作共享同一数据库会话，提供自动事务提交/回滚机制，解决传统代码的多会话问题

## 2. Core Components

- `infrastructure/uow/unit_of_work.py` (`UnitOfWork`): 工作单元实现，管理 42 个仓储实例和事务生命周期
- `infrastructure/di/container.py` (`DIContainer`, `ServiceLifetime`): 依赖注入容器，支持 Singleton/Scoped/Transient 三种生命周期
- `infrastructure/di/setup.py` (`setup_di_container`): DI 容器启动配置，注册所有服务和仓储
- `models/db.py` (`AsyncSessionLocal`): SQLAlchemy 会话工厂，创建异步数据库会话

## 3. Execution Flow (LLM Retrieval Map)

### Unit of Work 上下文管理流程
- **1. 创建会话**: `infrastructure/uow/unit_of_work.py:284-288` 的 `__aenter__` 方法调用 `session_factory()` 创建新的 `AsyncSession`
- **2. 延迟初始化仓储**: `infrastructure/uow/unit_of_work.py:94-131` 通过属性装饰器按需创建 Repository 实例，所有仓储共享同一个 `_session`
- **3. 业务操作**: Command Handler 通过 `uow.players.get_by_id()` 等方法执行数据操作
- **4. 自动提交/回滚**: `infrastructure/uow/unit_of_work.py:290-330` 的 `__aexit__` 方法根据异常类型自动调用 `commit()` 或 `rollback()`
- **5. 关闭会话**: `__aexit__` 的 `finally` 块确保会话总是被关闭，防止连接泄漏

### 异常处理与事务一致性
- **1. 流程控制异常**: `infrastructure/uow/unit_of_work.py:303-310` 检测 Nonebot2 的 `FinishedException` 等异常，执行提交而非回滚（因为这是正常流程控制）
- **2. 业务异常**: `infrastructure/uow/unit_of_work.py:311-314` 其他异常触发回滚，记录警告日志
- **3. 会话清理**: `infrastructure/uow/unit_of_work.py:323-326` 无论如何都关闭会话，记录调试日志

### 依赖注入生命周期管理
- **1. 注册服务**: `infrastructure/di/container.py:52-92` 提供 `register_singleton`, `register_scoped`, `register_transient` 方法
- **2. 解析服务**: `infrastructure/di/container.py:94-128` 的 `resolve()` 方法根据生命周期返回实例
- **3. 单例模式**: `infrastructure/di/container.py:114-118` 单例服务在 `_singletons` 字典中缓存，全局唯一
- **4. 作用域模式**: `infrastructure/di/container.py:120-124` 作用域服务在 `_scoped_instances` 字典中缓存，可通过 `create_scope()` 创建新作用域
- **5. 瞬时模式**: `infrastructure/di/container.py:126-128` 瞬时服务每次调用 `resolve()` 都创建新实例

## 4. Design Rationale

**为什么使用 Unit of Work**：
1. **事务原子性**：传统代码中 `player/info.py` 打开 4 个独立会话，破坏事务一致性；Unit of Work 确保所有操作在同一个事务中
2. **会话共享**：多个 Repository 协作时（如查询玩家及其公会），共享同一个 AsyncSession 避免 N+1 查询
3. **连接泄漏防护**：通过上下文管理器确保会话总是被关闭，即使发生异常
4. **清晰的事务边界**：`async with UnitOfWork()` 定义明确的 transaction scope，业务逻辑不直接调用 `commit()`

**为什么使用依赖注入**：
1. **解耦合**：Service 通过构造函数接收 Repository，而非直接创建依赖，便于替换实现
2. **可测试性**：单元测试时可通过 DI Container 注入 Mock Repository
3. **生命周期管理**：Singleton 服务（如配置）全局唯一，Scoped 服务（如 Unit of Work）每请求创建一次
4. **集中配置**：所有服务在 `setup_di_container()` 中注册，便于查看依赖关系

**当前实践建议**：
- **不完全依赖 DI 容器**：由于 Unit of Work 需要在 `async with` 上下文中使用，不适合自动注入
- **手动创建 Service**：在 Command Handler 中通过 `GuildService(player_repo=uow.players, guild_repo=uow.guilds)` 手动创建服务
- **混合模式**：接近 "Service Locator + UoW" 模式，而非纯 DI，更灵活且符合异步编程模型
