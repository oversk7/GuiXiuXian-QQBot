# 修复连接泄漏的通用模式

## 问题描述

当在 `async with UnitOfWork()` 上下文管理器**内部**调用 `finish()` 时，会导致数据库连接泄漏。

### 错误示例

```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    if not player:
        await cmd.finish("⛔ 请先创建角色")  # ❌ 错误！

    # 其他逻辑...
```

### 为什么会泄漏？

1. `finish()` 方法会抛出一个特殊异常来终止消息处理
2. 这个异常会**跳过** `async with` 的正常退出流程（`__aexit__`）
3. `UnitOfWork.__aexit__()` 没有被调用
4. 数据库连接没有被关闭和归还到连接池
5. SQLAlchemy 的垃圾回收器检测到未归还的连接，发出警告

## 正确的修复模式

### 模式 1：提前检查，外部 finish

**适用场景**：在 UnitOfWork 开始时就能确定是否需要终止

```python
# ✅ 正确
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    if not player:
        error_msg = "⛔ 请先创建角色"
    else:
        error_msg = None
        # 正常的业务逻辑...
        result_msg = "执行成功"

# 在 UnitOfWork 外部 finish
if error_msg:
    await cmd.finish(error_msg)
else:
    await cmd.finish(result_msg)
```

### 模式 2：多个错误条件处理

**适用场景**：有多个可能的错误检查点

```python
# ✅ 正确
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)

    # 使用变量记录错误
    error_msg = None
    result_msg = None

    if not player:
        error_msg = "⛔ 请先创建角色"
    elif player.level < 30:
        error_msg = "⛔ 该功能仅对Lv.30以上角色开放"
    else:
        # 执行业务逻辑
        result_msg = "✅ 执行成功"

# 在外部处理返回
if error_msg:
    await cmd.finish(error_msg)
else:
    await cmd.finish(result_msg)
```

### 模式 3：复杂业务逻辑

**适用场景**：需要在 UnitOfWork 内执行多步操作

```python
# ✅ 正确
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)

    error_msg = None
    success_msg = None

    if not player:
        error_msg = "⛔ 请先创建角色"
    else:
        # 执行业务逻辑
        try:
            # 步骤1
            task = await uow.daily_tasks.get_by_id(task_id)

            if not task:
                error_msg = "❌ 任务不存在"
            elif task.status != TaskStatus.ACCEPTED:
                error_msg = "❌ 任务未接取"
            else:
                # 步骤2：完成任务
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()

                # 步骤3：发放奖励
                player.exp += task.exp_reward
                player.gold += task.gold_reward

                await uow.commit()
                success_msg = f"✅ 任务完成！获得经验 {task.exp_reward}"

        except Exception as e:
            error_msg = f"❌ 操作失败: {e}"

# 外部处理返回
if error_msg:
    await cmd.finish(error_msg)
else:
    await cmd.finish(success_msg)
```

### 模式 4：使用 return 提前退出

**适用场景**：代码结构允许使用 return

```python
async def handle_command(event):
    # ✅ 正确
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)

        if not player:
            return "⛔ 请先创建角色"  # 使用 return 而非 finish

        if player.level < 30:
            return "⛔ 等级不足"

        # 业务逻辑...
        return "✅ 执行成功"

    # 注意：这个 return 永远不会被执行，但语法需要
    # 因为 UnitOfWork 退出后函数应该结束

# 或者更清晰的写法：
async def handle_command(event):
    result_msg = await _execute_logic(event)
    await cmd.finish(result_msg)

async def _execute_logic(event):
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            return "⛔ 请先创建角色"
        # 业务逻辑...
        return "✅ 成功"
```

## 批量修复步骤

### 1. 识别问题代码

搜索所有在 UnitOfWork 内部调用 finish() 的地方：

```bash
# 在 Git Bash 或 Linux 终端
grep -rn "async with UnitOfWork" plugins/xiuxian_game/ | \
while read line; do
    file=$(echo "$line" | cut -d: -f1)
    grep -A20 "async with UnitOfWork" "$file" | grep "\.finish("
done
```

### 2. 修复文件

对于每个发现的文件，应用上述修复模式。

### 3. 验证修复

修复后运行 bot，观察是否还有连接泄漏警告：

```
SAWarning: The garbage collector is trying to clean up non-checked-in connection
```

如果没有这个警告，说明修复成功。

## 需要修复的文件列表

根据代码检查，以下文件需要修复：

### 高优先级（已发现泄漏）

1. **plugins/xiuxian_game/economy/part_time_job_commands.py**
   - `work_cmd` (line ~57)
   - `finish_work_cmd` (line ~177)
   - `work_status_cmd` (line ~229)
   - `work_locations_cmd` (line ~286)
   - `work_history_cmd` (line ~330)
   - `work_stats_cmd` (line ~373)

2. **plugins/xiuxian_game/daily_task/commands.py**
   - `daily_task_cmd` (line ~34, ~36)
   - `accept_task_cmd` (line ~137)
   - `complete_task_cmd` (line ~222)
   - `task_stats_cmd` (line ~338)
   - `refresh_task_cmd` (line ~393, ~395)

3. **plugins/xiuxian_game/guild/guild.py**
   - 需要检查所有 UnitOfWork 使用

### 已修复

- ✅ `plugins/xiuxian_game/economy/stock_commands.py`
  - `stock_list_cmd` (已修复)
  - `stock_events_cmd` (已修复)

## 测试方法

### 1. 本地测试

修复后，在测试环境运行 bot：

```bash
# 启动 bot
python bot.py

# 触发相关命令
# 观察日志中是否有 SAWarning
```

### 2. 代码审查

使用以下脚本检查是否还有未修复的地方：

```python
import re
from pathlib import Path

def check_uow_finish(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_uow_block = False
    uow_indent = 0
    issues = []

    for i, line in enumerate(lines, 1):
        if 'async with UnitOfWork' in line:
            in_uow_block = True
            uow_indent = len(line) - len(line.lstrip())
            continue

        if in_uow_block:
            current_indent = len(line) - len(line.lstrip())

            # 退出 UnitOfWork 块
            if line.strip() and current_indent <= uow_indent:
                in_uow_block = False
                continue

            # 检查是否调用 finish
            if '.finish(' in line and 'await' in line:
                issues.append((i, line.strip()))

    return issues

# 检查所有 Python 文件
for py_file in Path('plugins/xiuxian_game').rglob('*.py'):
    issues = check_uow_finish(py_file)
    if issues:
        print(f"\n{py_file}:")
        for line_num, content in issues:
            print(f"  Line {line_num}: {content}")
```

## 性能影响

### 修复前
- 每次在 UnitOfWork 内调用 finish() = 1个泄漏的连接
- 连接池耗尽后，新请求会被阻塞
- 最终可能导致 "Too many connections" 错误

### 修复后
- 所有连接正确归还到连接池
- 连接池可以高效复用
- 避免连接耗尽问题

## 参考资料

- [SQLAlchemy Session 生命周期](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [UnitOfWork 模式设计](../plugins/xiuxian_game/infrastructure/uow/unit_of_work.py)
- [之前的修复提交](https://github.com/your-repo/commit/206a6e8)

## 总结

**核心原则**：
> 永远不要在 `async with UnitOfWork()` 内部调用 `finish()`

**修复方法**：
1. 在 UnitOfWork 内部用变量保存错误/结果消息
2. 在 UnitOfWork 外部调用 finish()

**检查清单**：
- [ ] 识别所有 UnitOfWork 使用
- [ ] 检查是否有内部 finish() 调用
- [ ] 应用修复模式
- [ ] 测试验证无连接泄漏警告
- [ ] 提交代码

遵循这个模式，就能彻底解决连接泄漏问题！
