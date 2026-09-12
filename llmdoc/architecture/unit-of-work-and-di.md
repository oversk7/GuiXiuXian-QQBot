# Unit of Work 与数据访问模式

## 1. Identity

- **What it is**: 工作单元（Unit of Work）模式管理多仓储事务边界；`safe_session()` 提供命令处理器的标准会话入口
- **Purpose**: 确保多个 Repository 操作共享同一数据库会话，提供自动事务提交/回滚机制，解决传统代码的多会话问题

## 2. Core Components

- `infrastructure/uow/unit_of_work.py` (`UnitOfWork`): 聚合全部仓储实例，事务生命周期统一委托 `safe_session(session_factory)`
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

## 6. 并发写入约定

- `infrastructure/locking.py` 的 `lock_row` / `lock_rows` 使用 `FOR UPDATE` 当前读并刷新 ORM 对象；多行按主键排序获取。必须在修改目标对象之前调用，重复刷新会丢弃本事务尚未写入的资产变更。身份查询留下的活跃时间与群信息会在锁后保留。
- 准备查询不要自动刷新尚未按顺序锁定的玩家对象。交易入口在改变资金、库存之前确定本次实际涉及的参与者集合；撤销与结算遵守同一业务内的锁顺序。
- 查询默认使用普通 MVCC 读取，修改时显式选择锁定查询。理财产品展示不锁基金统计，已有银行账户展示不锁余额；首次初始化仍要锁后复查。
- 装备选择旁路监听器先检查待选状态和回复格式，再用 `get_unified_player(..., read_only=True)` 识别角色。只读识别不更新活跃/群信息、不初始化区服绑定，也不回填身份缓存；无关消息不会触发 Player 版本更新。正式命令继续使用默认身份查询。
- 市场只锁按原成交优先级预计足够的候选前缀。若锁后数量减少且还有未选尾单，抛出 `StaleDataError` 整笔回滚，避免追加玩家锁打乱顺序。普通竞价只锁扣款、退款的玩家，一口价交割时才纳入卖家。
- 公会 Boss 普通攻击只在计算结束后锁攻击者，致命攻击才一次锁齐奖励接收者；锁定时用当前读核对攻击者版本，保留引擎产生的待写字段。计算阶段禁止自动刷新 Player，Guild/Boss 根锁仍保留。纯展示页面回滚结束会话，实际触发超时结算的页面提交后发送。
- 玩家、银行账户、库存、公会使用 `models/versioned.py` 的版本列，旧 ORM 快照写入会抛出 `StaleDataError`，整笔事务回滚。版本列通过 `auto_migrate.py` 的 `REQUIRED_FIELDS` 添加。
- Core / 原生 SQL 不自动执行 ORM 版本检查。直接更新上述表时，需要同步递增 `version_id`；基于旧值作决策的更新还必须带版本或余额、状态条件，并检查受影响行数。
- 下层仓储、物品发放和成就统计只能 `flush()`，不可提前提交业务事务。已被业务层捕获的失败若可能留下部分写入，应使用保存点回滚该操作。
- 成功消息及其他外部通知应在提交成功后发送，失败提示应先回滚释放锁。`finish()` 会先发送消息再抛出流程异常，在会话内调用时要特别注意事务结束顺序。
- `models/db.py:run_transaction` 仅用于可完整重放的数据库操作：冲突回滚后用新会话重跑，次数有界。回调内部不可提交、发送消息或产生其他外部副作用。
- MySQL 并发回归设置 `GUIX_MYSQL_TEST_URL` 后运行相关 `tests/test_*concurrency.py`。测试只连接本机，每个用例创建并清理独立数据库；SQLite 或 Mock 通过不能替代 MySQL 验证。

## 7. 历史说明：DI 容器已移除（2026-06-10）

`infrastructure/di/`（`DIContainer`、`setup_di_container` 等）已于 2026-06-10 删除：该容器自实现以来从未在启动流程中被初始化，业务代码零引用，属于未启用的预留设计。如未来确有需要，可从 git 历史（删除前最后提交）恢复。
