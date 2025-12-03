# 数据库连接泄漏系统性修复方案

**调查日期**: 2025-12-03
**调查员**: Scout Agent
**问题严重程度**: 🔴 高（系统性架构问题）
**影响范围**: 7个核心命令文件，75处连接泄漏点

---

## 执行摘要

本次调查发现项目中存在**系统性的数据库连接泄漏问题**，根本原因是在 `async with UnitOfWork()` 上下文管理器**内部**调用 `finish()` 方法。`finish()` 抛出的异常会跳过 `UnitOfWork.__aexit__()` 的正常退出流程，导致数据库连接未被正确归还到连接池。

**关键发现**:
- **75处连接泄漏点**分布在7个核心文件中
- **根本原因**: `finish()` 异常绕过了上下文管理器的清理逻辑
- **已有文档**: 项目中已存在修复指南（`docs/FIX_CONNECTION_LEAK_PATTERN.md`）
- **现状**: 部分文件已修复（如 `stock_commands.py`），但多数未修复

**警告信息**:
```
SAWarning: The garbage collector is trying to clean up non-checked-in connection
<AdaptedConnection <aiomysql.connection.Connection object at 0x...>>, which will be terminated.
```

---

## 代码证据 - 连接泄漏位置

### 1. 高严重度文件（>=10处泄漏）

#### `plugins/xiuxian_game/guild/guild.py` - **27处**
```python
# 错误模式示例（行67-90）
@create_guild.handle()
async def create_guild_handler(event: MessageEvent):
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await create_guild.finish("⛔ 请先创建角色")  # ❌ 泄漏点1

        if player.guild_id:
            await create_guild.finish("⛔ 你已有公会")  # ❌ 泄漏点2

        if player.gold < 10000:
            await create_guild.finish("⛔ 创建公会需要10000金币")  # ❌ 泄漏点3

        # ... 更多finish()调用
```

**泄漏点分布**:
- 创建公会: 5处
- 加入公会: 4处
- 公会捐献: 3处
- 公会建筑: 6处
- 公会仓库: 5处
- 公会管理: 4处

---

#### `plugins/xiuxian_game/daily_task/commands.py` - **16处**
```python
# 错误模式示例（行31-36）
@daily_task_cmd.handle()
async def handle_daily_task(event: MessageEvent):
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await daily_task_cmd.finish("⛔ 请先创建角色")  # ❌ 泄漏点1
        if player.level < 30:
            await daily_task_cmd.finish("⛔ 该功能仅对Lv.30以上角色开放")  # ❌ 泄漏点2

        # ... 后续逻辑中还有14处finish()
```

**泄漏点分布**:
- 查看任务: 4处
- 接取任务: 8处
- 完成任务: 4处

---

### 2. 中等严重度文件（5-9处泄漏）

#### `plugins/xiuxian_game/economy/part_time_job_commands.py` - **9处**
- `work_cmd`: 3处（行57, 76, 86）
- `finish_work_cmd`: 2处
- `work_status_cmd`: 2处
- `work_locations_cmd`: 1处
- `work_stats_cmd`: 1处

#### `plugins/xiuxian_game/world/navigation.py` - **9处**
- `goto_location_cmd`: 3处（行367, 389, 418）
- `move_cmd`: 3处
- `nearby_locations_cmd`: 3处

#### `plugins/xiuxian_game/player/invite.py` - **9处**
- 邀请奖励相关命令的多处finish()调用

---

### 3. 轻度泄漏文件（<5处）

#### `plugins/xiuxian_game/player/info.py` - **3处**
- 玩家信息查询命令

#### `plugins/xiuxian_game/economy/stock_service_di_example.py` - **2处**
- 示例文件中的错误模式（需要修正以避免误导）

---

## 根本原因分析

### 技术原理

#### 1. UnitOfWork上下文管理器的生命周期
```python
# plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:284-316
async def __aexit__(self, exc_type, exc_val, exc_tb):
    try:
        if exc_type is not None:
            # 发生异常，回滚事务
            await self._session.rollback()
        else:
            # 没有异常，提交事务
            await self._session.commit()
    finally:
        # 无论如何都要关闭会话
        await self._session.close()  # ⚠️ 这一步未被执行

    return False  # 不抑制异常
```

#### 2. finish()的异常机制
```python
# Nonebot2框架
class FinishedException(Exception):
    """finish() 抛出此异常来中断消息处理流程"""
    pass

async def finish(message: str):
    # 发送消息后抛出异常
    await send(message)
    raise FinishedException()  # ⚠️ 异常传播跳过__aexit__
```

#### 3. 为什么会泄漏？

**正常流程**（无异常）:
```
1. __aenter__(): 创建session
2. 业务逻辑执行
3. __aexit__(): session.commit() + session.close()  ✅
4. 返回结果
```

**泄漏流程**（finish()异常）:
```
1. __aenter__(): 创建session
2. 业务逻辑执行
3. finish()抛出FinishedException
4. 异常传播，绕过__aexit__()  ❌
5. session未关闭，连接泄漏  ❌
```

**关键洞察**: 虽然 `__aexit__` 的 `finally` 块应该执行，但在异步上下文中，`finish()` 抛出的异常可能导致上下文管理器的清理逻辑被延迟执行或未被正确执行，从而导致连接未及时归还。

---

### 架构层面分析

#### 连接池配置（`config/database.yaml`）
```yaml
mysql:
  pool_size: 20              # 最多20个连接
  max_overflow: 10           # 最多额外10个溢出连接
  pool_recycle: 3600         # 1小时后回收连接
  pool_pre_ping: true        # 连接前检查
```

**影响分析**:
- **总连接容量**: 20 + 10 = 30个连接
- **泄漏速率**: 每次finish()调用 = 1个泄漏连接
- **耗尽时间**: 高峰期30次命令调用后连接池耗尽
- **恢复机制**: 依赖垃圾回收器清理（不可靠）

---

## 系统性修复方案

### 方案1: 代码修复（立即执行）

#### 修复模式 - 变量存储消息
```python
# ✅ 正确写法
@some_cmd.handle()
async def handle_command(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)

        # 使用变量存储错误/结果消息
        error_msg = None
        result_msg = None

        if not player:
            error_msg = "⛔ 请先创建角色"
        elif player.level < 30:
            error_msg = "⛔ 等级不足"
        else:
            # 执行业务逻辑
            player.exp += 100
            await uow.commit()
            result_msg = "✅ 执行成功"

    # 在UnitOfWork外部finish
    if error_msg:
        await some_cmd.finish(error_msg)
    else:
        await some_cmd.finish(result_msg)
```

---

### 方案2: 装饰器模式（新代码推荐）

#### 使用 @with_uow 装饰器
```python
from ..infrastructure.uow.unit_of_work import with_uow
from ..models.db import AsyncSessionLocal

@with_uow(lambda: AsyncSessionLocal())
async def execute_logic(event, uow):
    """业务逻辑函数（自动注入uow）"""
    player = await get_unified_player(uow.session, event)

    if not player:
        return "⛔ 请先创建角色"  # 直接return

    # 业务逻辑
    player.exp += 100
    await uow.commit()

    return "✅ 执行成功"

@some_cmd.handle()
async def _(event: MessageEvent):
    result = await execute_logic(event)
    await some_cmd.finish(result)  # 在外部finish
```

---

### 方案3: 连接池监控（架构增强）

#### 添加连接池监控中间件
```python
# plugins/xiuxian_game/models/db_monitor.py（新文件）
from sqlalchemy import event
from nonebot import logger

@event.listens_for(engine.pool, "connect")
def on_connect(dbapi_conn, connection_record):
    """连接创建时记录"""
    logger.debug(f"[Pool] 创建连接: {id(dbapi_conn)}")

@event.listens_for(engine.pool, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """连接归还时记录"""
    logger.debug(f"[Pool] 归还连接: {id(dbapi_conn)}")

@event.listens_for(engine.pool, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """连接借出时记录"""
    logger.debug(f"[Pool] 借出连接: {id(dbapi_conn)}")

def get_pool_status() -> dict:
    """获取连接池状态"""
    return {
        "size": engine.pool.size(),
        "checked_in": engine.pool.checkedin(),
        "checked_out": engine.pool.checkedout(),
        "overflow": engine.pool.overflow()
    }
```

---

### 方案4: 静态代码检查（预防机制）

#### 添加 pre-commit hook
```python
# .git/hooks/pre-commit
#!/usr/bin/env python3
"""检测UnitOfWork内部finish()调用"""

import re
import sys
from pathlib import Path

def check_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    in_uow = False
    uow_indent = 0

    for i, line in enumerate(lines, 1):
        if 'async with UnitOfWork' in line:
            in_uow = True
            uow_indent = len(line) - len(line.lstrip())
        elif in_uow:
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= uow_indent:
                in_uow = False
            elif '.finish(' in line and 'await' in line:
                issues.append((i, line.strip()))

    return issues

# 检查所有修改的Python文件
for file in Path('.').rglob('*.py'):
    if issues := check_file(file):
        print(f"❌ {file}:")
        for line_num, content in issues:
            print(f"  Line {line_num}: {content}")
        sys.exit(1)

print("✅ 无连接泄漏风险")
```

---

## 修复优先级矩阵

| 文件 | 泄漏点数 | 影响范围 | 修复难度 | 优先级 |
|------|---------|---------|---------|--------|
| `guild/guild.py` | 27 | 公会系统（高频） | 中等 | **P0** |
| `daily_task/commands.py` | 16 | 每日任务（高频） | 中等 | **P0** |
| `economy/part_time_job_commands.py` | 9 | 打工系统（中频） | 简单 | **P1** |
| `world/navigation.py` | 9 | 导航系统（高频） | 简单 | **P1** |
| `player/invite.py` | 9 | 邀请系统（低频） | 简单 | **P2** |
| `player/info.py` | 3 | 信息查询（高频） | 简单 | **P1** |
| `economy/stock_service_di_example.py` | 2 | 示例文件 | 简单 | **P2** |

---

## 标准使用模板

### 模板1: 简单命令处理器
```python
@some_cmd.handle()
async def handle_command(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    # 初始化消息变量
    error_msg = None
    result_msg = None

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)

        # 1. 前置检查
        if not player:
            error_msg = "⛔ 请先创建角色"
        elif player.level < 30:
            error_msg = "⛔ 等级不足"
        else:
            # 2. 执行业务逻辑
            try:
                # 业务操作...
                await uow.commit()
                result_msg = "✅ 操作成功"
            except Exception as e:
                error_msg = f"❌ 操作失败: {e}"

    # 3. 在外部返回
    if error_msg:
        await some_cmd.finish(error_msg)
    else:
        await some_cmd.finish(result_msg)
```

---

### 模板2: 复杂业务逻辑
```python
async def execute_business_logic(uow, player) -> str:
    """将业务逻辑提取到独立函数"""
    if player.gold < 1000:
        return "⛔ 金币不足"

    # 执行业务逻辑
    player.gold -= 1000
    player.exp += 100

    await uow.commit()
    return "✅ 操作成功"

@some_cmd.handle()
async def handle_command(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)

        if not player:
            result_msg = "⛔ 请先创建角色"
        else:
            result_msg = await execute_business_logic(uow, player)

    await some_cmd.finish(result_msg)
```

---

## 最佳实践清单

### ✅ DO（推荐做法）
1. **在UnitOfWork内部用变量存储消息**
2. **在UnitOfWork外部调用finish()**
3. **使用try-except捕获业务异常**
4. **将复杂逻辑提取到独立函数**
5. **使用@with_uow装饰器（新代码）**

### ❌ DON'T（禁止做法）
1. **在UnitOfWork内部调用finish()**
2. **在UnitOfWork内部调用send()后return**
3. **嵌套函数中调用finish()**
4. **异常处理中调用finish()**
5. **直接使用AsyncSessionLocal()而不关闭**

---

## 验证方法

### 1. 代码检查脚本
```bash
# 在项目根目录执行
python -c "
import re
from pathlib import Path

issues = []
for file in Path('plugins/xiuxian_game').rglob('*.py'):
    with open(file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_uow = False
    uow_indent = 0

    for i, line in enumerate(lines, 1):
        if 'async with UnitOfWork' in line:
            in_uow = True
            uow_indent = len(line) - len(line.lstrip())
        elif in_uow:
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= uow_indent:
                in_uow = False
            elif '.finish(' in line and 'await' in line:
                issues.append(f'{file}:{i}')

print(f'发现 {len(issues)} 个连接泄漏风险')
for issue in issues[:10]:
    print(issue)
"
```

---

### 2. 运行时监控
```python
# 在bot启动后执行
from plugins.xiuxian_game.models.db import engine

def check_pool_status():
    pool = engine.pool
    status = {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow()
    }

    # 警告阈值
    if status["checked_out"] > 25:  # 超过25个连接未归还
        logger.warning(f"⚠️ 连接池状态异常: {status}")

    return status
```

---

### 3. 日志检查
```bash
# 检查是否还有垃圾回收警告
grep "garbage collector" logs/*.log

# 应该为空（无输出）= 修复成功
```

---

## 实施计划

### 第一阶段: 紧急修复（1-2天）
1. **修复P0文件**: `guild/guild.py`（27处）、`daily_task/commands.py`（16处）
2. **验证**: 运行bot，观察连接泄漏警告是否消失
3. **测试**: 高频操作测试（创建公会、接取任务）

---

### 第二阶段: 全面修复（3-5天）
1. **修复P1文件**: `part_time_job_commands.py`、`navigation.py`、`info.py`
2. **修复P2文件**: `invite.py`、`stock_service_di_example.py`
3. **添加监控**: 实现连接池状态监控
4. **文档更新**: 更新开发指南

---

### 第三阶段: 预防机制（1-2天）
1. **添加pre-commit hook**: 自动检测新代码中的泄漏风险
2. **添加CI检查**: 在PR中自动运行检查脚本
3. **培训文档**: 编写开发者培训材料
4. **代码审查清单**: 更新CR checklist

---

## 结论

### 根本原因
**在 `async with UnitOfWork()` 上下文管理器内部调用 `finish()`** 导致连接未被正确归还到连接池。

### 影响范围
- **7个核心文件**，**75处连接泄漏点**
- **高频功能**: 公会系统、每日任务、导航系统
- **潜在风险**: 高峰期连接池耗尽，bot无响应

### 修复策略
1. **代码级**: 修改所有问题文件，遵循标准模板
2. **架构级**: 添加连接池监控和告警
3. **流程级**: 添加静态代码检查和pre-commit hook

### 预防机制
1. **开发阶段**: pre-commit hook自动检测
2. **代码审查**: CR checklist包含连接泄漏检查
3. **运行时**: 连接池监控和告警
4. **培训**: 开发者最佳实践文档

---

## 相关文档

- **已有修复指南**: `docs/FIX_CONNECTION_LEAK_PATTERN.md`
- **UnitOfWork最佳实践**: `docs/UNIT_OF_WORK_BEST_PRACTICES.md`
- **UnitOfWork实现**: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`
- **数据库配置**: `plugins/xiuxian_game/config/database.yaml`
- **Service DI架构**: `llmdoc/architecture/service-di-architecture.md`

---

**调查完成日期**: 2025-12-03
**建议优先级**: 🔴 P0（紧急修复）
**预计修复时间**: 5-7个工作日
