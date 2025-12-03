# 成就系统数据库连接泄漏调查报告

**调查日期**: 2025-12-03
**调查员**: Scout Agent
**问题严重程度**: 🟡 中等（潜在的泄漏风险点）
**影响范围**: 成就系统命令处理（`achievement/commands.py`）

---

## 执行摘要

成就系统的命令处理代码存在**潜在的数据库连接泄漏风险**，根本原因是：

1. **在safe_session()上下文内部调用finish()**：命令处理器在`async with safe_session()`内部多处直接调用`.finish()`
2. **嵌套函数的finish()调用**：`show_achievement_detail()`函数被传入session后，在其内部调用`.finish()`
3. **异常处理的时序问题**：虽然`safe_session()`已实现`FinishedException`处理，但在异步上下文中的执行顺序可能导致连接未被及时正确关闭

**警告信息匹配**:
```
The garbage collector is trying to clean up non-checked-in connection
<AdaptedConnection <aiomysql.connection.Connection object at 0x...>>
```

---

## 代码证据 - 连接泄漏位置

### 1. 命令处理器中的直接finish()调用

**文件**: `plugins/xiuxian_game/achievement/commands.py`

#### 泄漏点1: handle_achievement函数
```python
@achievement_cmd.handle()
async def handle_achievement(event: MessageEvent, args: Message = CommandArg()):
    """显示玩家成就列表或成就详情"""
    async with safe_session() as session:  # ← 上下文开始
        player = await get_unified_player(session, event)
        if not player:
            await achievement_cmd.finish("⛔ 请先创建角色")  # ❌ 泄漏点1（行23）
```

**问题**:
- 在`safe_session()`上下文**内部**直接调用`.finish()`
- `.finish()`会抛出`FinishedException`异常
- 虽然`safe_session()`已在异常处理中捕获此异常（db.py:209-212），但异步上下文的清理时序仍有风险

#### 泄漏点2: show_achievement_detail函数内部多处finish()
```python
async def show_achievement_detail(session, player, achievement_name: str, event: MessageEvent):
    """显示成就详情"""
    config = AchievementService._load_achievement_config()
    if not config:
        await achievement_cmd.finish("⛔ 成就配置加载失败")  # ❌ 泄漏点2（行114）

    # ...查找成就逻辑...

    if not achievement_data:
        await achievement_cmd.finish(f"❌ 未找到成就: {achievement_name}")  # ❌ 泄漏点3（行126）

    # ...构建详情信息...

    await achievement_cmd.finish(message_add_head("\n".join(lines), event))  # ❌ 泄漏点4（行199）
```

**问题**:
- `show_achievement_detail()`被从`handle_achievement()`内部调用，传入了一个仍在`safe_session()`上下文中的session
- 该函数内部有3处`.finish()`调用
- 这些`.finish()`调用虽然发生在`safe_session()`上下文内部，但在嵌套的函数调用中

#### 泄漏点3: 控制流路径
```python
async def handle_achievement(...):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await achievement_cmd.finish("...")  # ❌ 直接在上下文内finish

        # ...参数解析...

        if arg_text:
            if arg_text.isdigit():
                page = int(arg_text)
            else:
                # 这个调用会导致：
                await show_achievement_detail(session, player, arg_text, event)  # ← 行36
                # show_achievement_detail内部会调用finish()，跳过后续代码
                return
```

**问题分析**:
1. 主函数在`safe_session()`内部调用`show_achievement_detail(session, ...)`
2. `show_achievement_detail()`函数内部调用`.finish()`时，此时仍在主函数的`safe_session()`上下文中
3. 虽然`.finish()`会被`safe_session()`的异常处理捕获，但异步上下文的清理顺序可能不确定

---

## 根本原因分析

### 1. safe_session()的FinishedException处理

**代码位置**: `plugins/xiuxian_game/models/db.py:195-221`

```python
@asynccontextmanager
async def safe_session():
    """安全会话管理器（自动回滚+资源清理）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # 正常流程
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        except Exception as e:
            # ← 这里捕获了FinishedException
            try:
                from nonebot.exception import FinishedException, PausedException, RejectedException
                if isinstance(e, (FinishedException, PausedException, RejectedException)):
                    # 提交事务后重新抛出
                    await session.commit()
                    raise e
            except ImportError:
                pass

            # 其他异常：回滚事务
            await session.rollback()
            raise e
        finally:
            await session.close()  # ← 应该被执行
```

**现状**:
- ✅ `safe_session()`已实现了对`FinishedException`的处理
- ✅ 在`finally`块中明确调用了`await session.close()`
- ⚠️ 但异步上下文的异常处理和资源清理顺序可能存在竞态条件

### 2. 与系统性泄漏问题的区别

**系统性问题** (已在`connection_leak_systematic_fix_2025_12_03.md`中记录):
- 发生在使用`UnitOfWork()`的文件中（guild.py、daily_task/commands.py等）
- 原因：`UnitOfWork()`内部调用`finish()`，导致`__aexit__`清理逻辑被跳过
- 影响：75个泄漏点

**成就系统的问题**:
- 使用的是`safe_session()`而非`UnitOfWork()`
- `safe_session()`已实现了`FinishedException`处理和`finally`清理
- 风险：异步上下文中的时序问题和边界情况

---

## 技术深度分析

### 为什么safe_session()可能仍然存在泄漏风险？

#### 1. Nonebot2异常处理的特殊性

```python
# Nonebot2框架中的finish()实现
class FinishedException(Exception):
    """finish() 抛出此异常来中断消息处理流程"""
    pass

async def finish(message: str):
    await send(message)
    raise FinishedException()  # 立即抛出异常
```

**问题**: `.finish()`抛出的异常会立即中断当前执行，导致：
- 上下文管理器的`__aenter__`返回的对象可能未被正确清理
- 异步事件循环的处理可能不完整

#### 2. 异步上下文管理器的资源清理

在异步上下文中，当异常被抛出时：
```
正常流程:
1. __aenter__() 执行
2. yield session
3. 业务逻辑执行
4. __aexit__() 执行（try-except-finally）
5. 连接归还到连接池

异常流程(finish()):
1. __aenter__() 执行
2. yield session
3. 业务逻辑执行
4. .finish()抛出FinishedException
5. __aexit__()执行异常处理路径
6. finally块执行session.close()
7. 异常重新抛出

问题: 第6步和第7步的时序可能不确定
```

#### 3. 嵌套函数中的finish()风险

```python
# handle_achievement函数内部
async with safe_session() as session:  # ← Context 1
    await show_achievement_detail(session, ...)  # ← 调用嵌套函数

# show_achievement_detail函数内部
async def show_achievement_detail(session, ...):
    # session 仍然属于父函数的 Context 1
    await achievement_cmd.finish(...)  # ← 在 Context 1 内部抛出异常
```

**关键问题**:
- 嵌套函数接收到的`session`对象属于外部上下文
- 嵌套函数中的`finish()`会导致外部上下文的`__aexit__`处理异常
- 如果异步事件循环的处理不完整，连接可能未被正确归还

---

## 修复方案

### 方案1: 改进命令处理器的控制流（推荐）

**目标**: 避免在`safe_session()`上下文内部直接调用`.finish()`

**修复模式**:

```python
@achievement_cmd.handle()
async def handle_achievement(event: MessageEvent, args: Message = CommandArg()):
    """显示玩家成就列表或成就详情"""

    # 初始化结果消息变量
    result_message = None

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            result_message = "⛔ 请先创建角色"
        else:
            # 解析参数
            arg_text = args.extract_plain_text().strip()

            if arg_text:
                if arg_text.isdigit():
                    # 显示成就列表（指定页码）
                    page = int(arg_text)
                    result_message = await build_achievement_list_message(
                        session, player, page, event
                    )
                else:
                    # 显示成就详情
                    result_message = await build_achievement_detail_message(
                        session, player, arg_text, event
                    )
            else:
                # 显示成就列表（第1页）
                result_message = await build_achievement_list_message(
                    session, player, 1, event
                )

    # 在safe_session()外部调用finish()
    if result_message:
        await achievement_cmd.finish(result_message)
    else:
        await achievement_cmd.finish("❌ 获取成就信息失败")


async def build_achievement_list_message(session, player, page: int, event) -> str:
    """构建成就列表消息（返回字符串而非finish）"""
    data = await AchievementService.get_player_achievements(session, player.id)

    all_achievements = []
    for ach in data["unlocked"]:
        ach_copy = ach.copy()
        ach_copy["is_unlocked"] = True
        all_achievements.append(ach_copy)

    for ach in data["locked"]:
        ach_copy = ach.copy()
        ach_copy["is_unlocked"] = False
        ach_copy["progress"] = data.get("progress", {}).get(ach["id"], 0)
        all_achievements.append(ach_copy)

    # ... 分页逻辑和消息构建 ...

    return message_add_head("\n".join(lines), event)


async def build_achievement_detail_message(session, player, achievement_name: str, event) -> str:
    """构建成就详情消息（返回字符串而非finish）"""
    config = AchievementService._load_achievement_config()
    if not config:
        return "⛔ 成就配置加载失败"

    # ... 查找成就逻辑 ...

    if not achievement_data:
        return f"❌ 未找到成就: {achievement_name}"

    # ... 构建详情消息 ...

    return message_add_head("\n".join(lines), event)
```

**优点**:
1. 所有`.finish()`调用都在`safe_session()`外部
2. 清晰的控制流，易于维护
3. 避免异步上下文清理的潜在问题
4. 符合UnitOfWork修复的最佳实践

### 方案2: 使用try-except在finish()前确保session关闭

**风险**: 不推荐，因为仍然存在时序问题

```python
async with safe_session() as session:
    try:
        player = await get_unified_player(session, event)
        if not player:
            await session.close()  # 显式关闭
            await achievement_cmd.finish("⛔ 请先创建角色")
    finally:
        pass  # safe_session的finally会处理
```

**问题**: 不彻底，可能导致session被关闭两次

### 方案3: 使用safe_session()提供的上下文完整性保证

**现状**: `safe_session()`已经实现了完整的异常处理

**建议**: 如果确实无法避免在上下文内部`.finish()`，应确保：
1. 在`safe_session()`实现中添加详细的日志
2. 监控连接池状态
3. 添加单元测试验证连接归还

---

## 修复优先级

| 位置 | 泄漏点数 | 严重程度 | 修复难度 | 优先级 |
|------|---------|---------|---------|--------|
| `handle_achievement()` | 1 | 🟡 中等 | 简单 | **P1** |
| `show_achievement_detail()` | 3 | 🟡 中等 | 简单 | **P1** |
| **总计** | **4** | 🟡 中等 | **简单** | **P1** |

---

## 验证方法

### 1. 运行时日志检查

```bash
# 检查是否出现垃圾回收警告
grep "garbage collector" logs/*.log

# 监控连接池状态
# 在bot启动后频繁执行成就命令，观察连接数变化
```

### 2. 代码检查脚本

```python
import re
from pathlib import Path

# 检测在safe_session()内部的finish()调用
file_path = Path("plugins/xiuxian_game/achievement/commands.py")
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_safe_session = False
safe_session_indent = 0

for i, line in enumerate(lines, 1):
    if 'async with safe_session()' in line:
        in_safe_session = True
        safe_session_indent = len(line) - len(line.lstrip())
    elif in_safe_session:
        current_indent = len(line) - len(line.lstrip())
        if line.strip() and current_indent <= safe_session_indent:
            in_safe_session = False
        elif '.finish(' in line and 'await' in line:
            print(f"⚠️ Line {i}: finish() 在 safe_session() 内部")
            print(f"   {line.strip()}")
```

### 3. 性能基准测试

```python
# 执行1000次成就查询，检查连接泄漏
async def test_achievement_command_leaks():
    initial_checkedout = engine.pool.checkedout()

    for i in range(1000):
        # 模拟玩家查询成就命令
        await simulate_achievement_query(player_id)

    final_checkedout = engine.pool.checkedout()

    if final_checkedout > initial_checkedout:
        print(f"❌ 连接泄漏: {final_checkedout - initial_checkedout} 个未归还连接")
    else:
        print(f"✅ 无连接泄漏")
```

---

## 相关代码位置

### 核心文件
- `plugins/xiuxian_game/achievement/commands.py:17-200` - 命令处理器（泄漏点）
- `plugins/xiuxian_game/achievement/achievement_service.py:200-250` - 服务层
- `plugins/xiuxian_game/models/db.py:195-221` - safe_session实现

### 相关文档
- `/llmdoc/agent/connection_leak_systematic_fix_2025_12_03.md` - 系统性泄漏修复
- `/llmdoc/architecture/service-di-architecture.md#会话管理` - 会话管理最佳实践
- `/llmdoc/guides/achievement-system-guide.md` - 成就系统使用指南

### 数据库配置
- `plugins/xiuxian_game/config/database.yaml:mysql.pool_size` - 连接池大小（20）

---

## 最佳实践清单

### ✅ DO（推荐做法）
1. **在safe_session()或UnitOfWork外部调用finish()**
2. **使用变量存储消息，在上下文外返回**
3. **异常处理使用try-except而不依赖finish()**
4. **提取消息构建逻辑到独立函数**

### ❌ DON'T（禁止做法）
1. **在async with safe_session()内部调用finish()**
2. **在async with UnitOfWork()内部调用finish()**
3. **嵌套函数中调用finish()，同时父函数在上下文内**
4. **异常路径中调用finish()而不先关闭session**

---

## 结论

### 问题概述
成就系统的命令处理器在`safe_session()`上下文**内部**调用`.finish()`方法，存在**潜在的连接泄漏风险**。虽然`safe_session()`已实现了`FinishedException`处理和`finally`清理，但异步上下文中的清理时序仍可能导致连接未被及时正确归还。

### 影响范围
- **4个泄漏风险点**: `handle_achievement()`1处，`show_achievement_detail()`3处
- **严重程度**: 🟡 中等（与系统性的UnitOfWork泄漏相比风险较低）
- **用户影响**: 高频成就查询命令可能导致连接池逐渐耗尽

### 修复建议
**优先级**: P1（应该尽快修复）

**推荐方案**:
1. 提取消息构建逻辑到返回字符串的独立函数
2. 在`safe_session()`外部调用`.finish()`
3. 遵循已在其他系统性泄漏修复中验证的标准模板

### 预计修复时间
- **代码修改**: 30分钟
- **单元测试**: 30分钟
- **集成测试和验证**: 1小时
- **总计**: 2小时

---

**调查完成日期**: 2025-12-03
**建议优先级**: 🟡 P1（应该修复但不紧急）
**预计修复时间**: 2-3小时
