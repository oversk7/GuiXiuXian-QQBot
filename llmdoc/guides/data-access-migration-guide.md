# 如何从 Legacy 架构迁移到新数据访问层

迁移传统代码（静态方法 + 直接 Session 操作）到新架构（Repository + Unit of Work + Service）需要遵循以下步骤：

1. **步骤 1: 创建 Repository 实现** (如果不存在)
   - 在 `infrastructure/repositories/` 目录创建 `xxx_repository.py`
   - 定义 Repository 类，继承 `IRepository[EntityType]`
   - 实现标准 CRUD 方法（`get_by_id`, `add`, `update`, `delete`, `exists`, `count`）
   - 添加领域查询方法（如 `get_by_uid`, `get_with_monthly_cards`）
   - 通过构造函数注入 `AsyncSession`
   - 参考 `infrastructure/repositories/player_repository.py:11-50`

2. **步骤 2: 将 Repository 添加到 Unit of Work**
   - 在 `infrastructure/uow/unit_of_work.py` 的 `__init__` 方法中添加私有属性（如 `self._players = None`）
   - 创建 `@property` 装饰器方法（如 `def players(self)`），延迟初始化 Repository
   - 在属性方法中导入并实例化 Repository（如 `PlayerRepository(self._session)`）
   - 确保所有 Repository 共享同一个 `_session`
   - 参考 `infrastructure/uow/unit_of_work.py:94-99`

3. **步骤 3: 创建新 Service 类**
   - 在对应目录创建 `xxx_service_new.py`（保留旧文件作为后备）
   - 定义 Service 类，通过构造函数注入所需 Repository（如 `def __init__(self, player_repo, guild_repo)`）
   - 将静态方法转换为实例方法（移除 `@staticmethod`，添加 `self` 参数）
   - 移除所有 `session.commit()` 调用（由外层 Unit of Work 控制）
   - 移除 `session` 参数，改用通过 Repository 访问数据
   - 参考 `guild/guild_service_new.py:851-914`

4. **步骤 4: 更新 Command Handler**
   - 替换旧的直接 Session 操作为 Unit of Work 上下文
   - 使用 `async with UnitOfWork(session_factory) as uow:` 创建事务边界
   - 手动创建 Service 实例（如 `guild_service = GuildService(player_repo=uow.players, guild_repo=uow.guilds)`）
   - 在 Unit of Work 外部调用 `finish()`（避免连接泄漏）
   - 将返回值存储在变量中，在 UoW 外部发送消息
   - 参考 `infrastructure/uow/unit_of_work.py:353-391` 的 `@with_uow` 装饰器模式

5. **步骤 5: 测试和验证**
   - 运行相关功能的单元测试，确保业务逻辑正确
   - 检查日志中的 `[UnitOfWork]` 调试信息，确认会话创建和关闭
   - 验证事务回滚是否正常工作（通过手动触发异常）
   - 确认没有连接泄漏（监控数据库连接数）
   - 保留旧代码作为后备（如 `try-except` 回退到 `LegacyService.some_method`）

6. **步骤 6: 清理旧代码** (可选，在完全验证后)
   - 删除或重命名旧的 `*_legacy.py` 文件
   - 将 `xxx_service_new.py` 重命名为 `xxx_service.py`
   - 更新所有引用旧 Service 的代码

**迁移检查清单**：
- [ ] Repository 实现 `IRepository[T]` 接口
- [ ] Repository 通过构造函数接收 `AsyncSession`
- [ ] Service 通过构造函数接收 Repository
- [ ] Service 移除所有内部 `session.commit()`
- [ ] Command Handler 使用 `async with UnitOfWork()`
- [ ] 确保在 UoW 外部调用 `finish()`
- [ ] 编写单元测试 Mock Repository
- [ ] 验证事务回滚正常工作
