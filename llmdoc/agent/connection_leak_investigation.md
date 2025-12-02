# SQLAlchemy数据库连接泄漏调查报告

**调查日期**: 2025-12-02
**调查员**: scout agent
**问题类型**: 数据库连接资源泄漏

---

## 1. 问题描述

SQLAlchemy发出连接泄漏警告：

```
SAWarning: The garbage collector is trying to clean up non-checked-in connection
<AdaptedConnection <aiomysql.connection.Connection object at 0x7f4ef76b5f30>>,
which will be terminated. Please ensure that SQLAlchemy pooled connections are
returned to the pool explicitly, either by calling ``close()`` or by using
appropriate context managers to manage their lifecycle.
```

**影响范围**: `daily_task/commands.py` 刚完成重构，所有命令处理器均使用 `UnitOfWork` + `Matcher.finish()` 模式。

---

## 2. 调查结果总结

### 核心发现

**UnitOfWork 的 `__aexit__` 实现是正确的**，会正确关闭 session：
- ✅ 异常时调用 `rollback()`
- ✅ 正常时调用 `commit()`
- ✅ `finally` 块中调用 `close()`
- ✅ 返回 `False`（不抑制异常）

**Nonebot2 的 `FinishedException` 不会破坏 context manager 清理**：
- ✅ 标准 Python 异常，继承自 `NoneBotException`
- ✅ 异常传播时会触发 `__aexit__`
- ✅ 框架使用 `AsyncExitStack` 管理资源清理

**真正的问题根源**：UnitOfWork 在 `async with` 块**外部**调用 `.finish()`，导致 context manager **提前退出后才发送消息**。这本身不会泄漏连接，但可能存在其他隐患。

### 发现的异常情况

**guild.py 存在会话泄漏风险**（第174-198行）：
```python
async with UnitOfWork(session_factory) as uow:
    # ... 使用 uow.session ...
    session = uow.session  # ❌ 保存session引用

# ❌ 在 UnitOfWork 退出后继续使用 session！
building_service = GuildBuildingServiceNew(
    guild_repo=GuildRepository(session),  # session已关闭
    building_repo=GuildBuildingRepository(session),
    item_repo=None
)
bonuses = await building_service.get_guild_bonuses(guild_obj.id)
```

**这是真正的连接泄漏源头**：UnitOfWork 退出后 session 已关闭，但代码继续使用该 session 创建 Repository，可能导致隐式重新打开连接而未关闭。

---

## 3. Code Sections (证据清单)

### UnitOfWork 实现

- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:198-230` (`UnitOfWork.__aexit__`): 正确实现了异常处理和资源清理，异常时回滚，正常时提交，finally块中关闭session，返回False不抑制异常。

### daily_task/commands.py 所有 .finish() 调用

**❌ 错误模式（在 UnitOfWork 外部调用 .finish()）**:

- `daily_task/commands.py:115` (daily_task_cmd): 在 `async with UnitOfWork` 块内部调用 `.finish()`，这是正确的
- `daily_task/commands.py:198` (accept_task_cmd): 在 UnitOfWork 外部调用 `.finish()`，此时 session 已关闭
- `daily_task/commands.py:309` (complete_task_cmd): 在 UnitOfWork 外部调用 `.finish()`，此时 session 已关闭
- `daily_task/commands.py:359` (task_stats_cmd): 在 UnitOfWork 外部调用 `.finish()`，此时 session 已关闭
- `daily_task/commands.py:416` (refresh_task_cmd): 在 UnitOfWork 外部调用 `.finish()`，此时 session 已关闭

**所有提前退出的 .finish() 调用（在 async with 块内部）**:
- `daily_task/commands.py:34,36,133,135,145,147,175,212,233,244,323,373,375,395,400` - 这些调用都在 `async with UnitOfWork` 块内部，FinishedException 会正确触发 `__aexit__` 进行清理

### guild.py 使用模式对比

**✅ 正确模式（第67-125行，create_guild_cmd）**:
```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    if not player:
        await create_guild_cmd.finish("⛔ 请先创建角色")  # 内部调用，正确
    # ... 所有数据库操作 ...
    # UoW会在__aexit__中自动commit

# 返回成功消息
msg = "..."
await create_guild_cmd.finish(message_add_head(msg, event))  # 外部调用
```

**❌ 错误模式（第139-198行，guild_info_cmd）**:
```python
async with UnitOfWork(session_factory) as uow:
    # ... 使用 uow.session ...
    session = uow.session  # 保存引用

# ❌ 在 UnitOfWork 退出后使用 session
building_service = GuildBuildingServiceNew(
    guild_repo=GuildRepository(session),  # session已关闭
    ...
)
```

### 其他使用 AsyncSessionLocal() 的文件

- `economy/stock_commands.py:52-54` (`stock_list_cmd`): 正确使用 UnitOfWork 包装 AsyncSessionLocal
- `economy/part_time_job_commands.py`: 未检查，但需要审查
- `player/invite.py`: 未检查，但需要审查

---

## 4. Report (调查结论)

### result

**连接泄漏的真正原因**:

1. **UnitOfWork 自身实现无问题** - 所有资源清理逻辑正确
2. **Nonebot2 FinishedException 机制正常** - 不会破坏 context manager
3. **真正的问题在 guild.py:174-198** - 在 UnitOfWork 退出后继续使用已关闭的 session，可能导致隐式连接重新打开而未关闭
4. **daily_task/commands.py 存在反模式** - 虽然不会泄漏连接，但在 UnitOfWork 外部调用 `.finish()` 违反了最佳实践

### conclusions

**关键结论**:

1. **UnitOfWork 的 `__aexit__` 逻辑正确**
   - 异常处理：`if exc_type is not None: await self._session.rollback()`
   - 正常提交：`else: await self._session.commit()`
   - 资源清理：`finally: await self._session.close()`
   - 异常传播：`return False`（不抑制异常）

2. **FinishedException 不会阻止 context manager 清理**
   - FinishedException 是标准 Python 异常
   - 异常传播时会正确触发 `__aexit__`
   - Nonebot2 使用 AsyncExitStack 管理资源

3. **guild.py:174-198 是连接泄漏的真正源头**
   - 在 UnitOfWork 退出后保存并使用 session 引用
   - 已关闭的 session 被用于创建 Repository
   - Repository 查询可能隐式重新打开连接
   - 新打开的连接没有被 UnitOfWork 管理，导致泄漏

4. **daily_task/commands.py 的反模式**
   - 5处在 UnitOfWork 外部调用 `.finish()`
   - 虽然不会泄漏（session已正确关闭），但违反最佳实践
   - 应该在 `async with` 块内部调用所有 `.finish()`

5. **正确的使用模式（guild.py:67-125）**
   - 所有提前退出的 `.finish()` 在 UnitOfWork 内部调用
   - 最后的成功消息在外部调用，但不涉及数据库操作
   - 这种模式是安全的

### relations

**代码关系图**:

1. **UnitOfWork 生命周期**:
   - `UnitOfWork.__aenter__` → 创建 `AsyncSession` (line 199-202)
   - `UnitOfWork.__aexit__` → 提交/回滚 + 关闭 session (line 204-230)
   - `UnitOfWork.session` property → 返回内部 `_session` (line 192-196)

2. **daily_task/commands.py 调用链**:
   - `async with UnitOfWork(session_factory)` → 打开事务边界
   - `await task_service.xxx()` → 执行业务逻辑
   - `await uow.commit()` → 手动提交（可选）
   - `await xxx_cmd.finish()` → 发送消息 + 抛出 FinishedException
   - `UnitOfWork.__aexit__` → 自动清理资源

3. **guild.py:139-198 错误调用链**:
   - `async with UnitOfWork(session_factory) as uow` → 创建 UoW
   - `session = uow.session` → ❌ 保存 session 引用
   - `UnitOfWork.__aexit__` → session.close() 被调用
   - `GuildRepository(session)` → ❌ 使用已关闭的 session
   - `await building_service.get_guild_bonuses()` → ❌ 可能隐式重新打开连接
   - **连接未被管理，GC回收时触发警告**

4. **正确的 guild.py:67-125 调用链**:
   - `async with UnitOfWork(session_factory) as uow` → 创建 UoW
   - 所有提前退出都在 `async with` 内部调用 `.finish()`
   - FinishedException 抛出 → 触发 `__aexit__` → session 正确关闭
   - 最后的 `.finish()` 在外部调用，但此时不再使用 session
   - **没有连接泄漏**

---

## 5. 修复方案

### 方案A: 修复 guild.py 的 session 泄漏（P0紧急）

**问题位置**: `guild.py:139-198`

**修复方法**: 将 session 相关操作移回 UnitOfWork 内部

```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    # ... 其他查询 ...

    # ✅ 在 UnitOfWork 内部创建 Service
    building_service = GuildBuildingServiceNew(
        guild_repo=GuildRepository(uow.session),
        building_repo=GuildBuildingRepository(uow.session),
        item_repo=None
    )
    bonuses = await building_service.get_guild_bonuses(guild_obj.id)
    exp_multiplier = bonuses.get("exp_multiplier", 1.0)
    cultivation_bonus = bonuses.get("cultivation_bonus", 0.0)

    # 构建消息（不涉及数据库操作可在外部）
    base_info = "..."

# 发送消息
await guild_info_cmd.finish(message_add_head(msg, event))
```

### 方案B: 规范 daily_task/commands.py 的 .finish() 调用（P1重要）

**反模式**: 在 UnitOfWork 外部调用 `.finish()`
**正确模式**: 所有 `.finish()` 都在 `async with` 块内部调用

**需要修复的位置**:
- `accept_task_cmd.handle:198` - 移到 UnitOfWork 内部
- `complete_task_cmd.handle:309` - 移到 UnitOfWork 内部
- `task_stats_cmd.handle:359` - 移到 UnitOfWork 内部
- `refresh_task_cmd.handle:416` - 移到 UnitOfWork 内部

**修复示例**:

```python
# ❌ 错误（当前）
async with UnitOfWork(session_factory) as uow:
    # ... 业务逻辑 ...
    if success:
        await uow.commit()
        msg = "成功消息"
    else:
        msg = "失败消息"

await xxx_cmd.finish(message_add_head(msg, event))  # 外部调用

# ✅ 正确
async with UnitOfWork(session_factory) as uow:
    # ... 业务逻辑 ...
    if success:
        await uow.commit()
        await xxx_cmd.finish(message_add_head("成功消息", event))
    else:
        await xxx_cmd.finish(message_add_head("失败消息", event))
```

### 方案C: 全局审查其他文件（P2长期）

**需要审查的文件**（所有直接使用 `AsyncSessionLocal()` 的文件）:
- `economy/part_time_job_commands.py`
- `player/invite.py`
- `economy/stock_service_di_example.py`（示例文件，可能无需修复）
- `guild/guild_service_di_example.py`（示例文件，可能无需修复）

**审查重点**:
1. 是否在 UnitOfWork 退出后使用 session
2. 是否在 UnitOfWork 外部调用 `.finish()`
3. 是否有直接使用 `AsyncSessionLocal()` 而未包装在 UnitOfWork 中的代码

---

## 6. 验证步骤

**修复后验证**:

1. **运行项目，触发 daily_task 相关指令**
   - 每日委托、接取任务、完成任务、任务统计、刷新委托

2. **运行项目，触发 guild_info_cmd 指令**
   - 公会信息、公会加成

3. **监控日志，确认无 SAWarning**
   - 检查是否还有 "garbage collector is trying to clean up non-checked-in connection" 警告

4. **检查数据库连接池状态**
   - 确认连接数正常回收
   - 连接池不会持续增长

---

## 7. 相关文档

- `/llmdoc/architecture/service-di-architecture.md` - UnitOfWork 架构设计
- `/llmdoc/architecture/current-architecture.md` - 数据库会话管理
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` - UnitOfWork 实现

---

**调查结论**: 连接泄漏的根本原因是 `guild.py:139-198` 在 UnitOfWork 退出后继续使用已关闭的 session，导致隐式连接重新打开而未被管理。UnitOfWork 自身实现无误，Nonebot2 的 FinishedException 机制也不会破坏 context manager 清理。修复方案是将所有 session 相关操作移回 UnitOfWork 内部，并规范所有 `.finish()` 调用位置。
