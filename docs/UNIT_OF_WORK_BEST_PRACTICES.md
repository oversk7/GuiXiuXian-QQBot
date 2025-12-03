# UnitOfWork 最佳实践指南

## 核心原则

**永远不要在 `async with UnitOfWork()` 内部调用 `finish()`**

## 为什么？

`finish()` 会抛出异常来终止消息处理。虽然 `UnitOfWork.__aexit__` 的 `finally` 块会执行并关闭会话，但在异步环境中，这种突然的异常中断可能导致连接状态不一致。

### 症状

```
SAWarning: The garbage collector is trying to clean up non-checked-in connection
```

## 解决方案

### 方案 1：手动模式（推荐用于现有代码修复）

在 UnitOfWork 内部准备数据，在外部调用 `finish()`：

```python
# ✅ 正确
@some_cmd.handle()
async def handle_command(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)

        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            # 执行业务逻辑...
            result_msg = "✅ 执行成功"

    # 在 UnitOfWork 外部 finish
    if error_msg:
        await some_cmd.finish(error_msg)
    else:
        await some_cmd.finish(result_msg)
```

### 方案 2：装饰器模式（推荐用于新代码）

使用 `@with_uow` 装饰器自动处理：

```python
from ..infrastructure.uow.unit_of_work import with_uow
from ..models.db import AsyncSessionLocal

@with_uow(lambda: AsyncSessionLocal())
async def execute_command_logic(event, uow):
    """业务逻辑函数

    Args:
        event: 消息事件
        uow: 自动注入的 UnitOfWork 实例

    Returns:
        str: 要发送给用户的消息
    """
    player = await get_unified_player(uow.session, event)

    if not player:
        return "⛔ 请先创建角色"  # 直接 return

    # 执行业务逻辑
    player.exp += 100
    await uow.commit()

    return "✅ 执行成功"


@some_cmd.handle()
async def _(event: MessageEvent):
    result = await execute_command_logic(event)
    await some_cmd.finish(result)  # 在外部 finish
```

### 方案 3：提取函数模式

将业务逻辑提取到独立函数：

```python
async def process_task(uow, player_id: str) -> str:
    """处理任务的业务逻辑

    Returns:
        str: 结果消息
    """
    player = await uow.players.get_by_id(player_id)

    if not player:
        return "⛔ 玩家不存在"

    # 业务逻辑...
    return "✅ 处理成功"


@some_cmd.handle()
async def handle_command(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        result = await process_task(uow, player_id)

    await some_cmd.finish(result)
```

## 常见错误示例

### ❌ 错误 1：直接在内部 finish

```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    if not player:
        await cmd.finish("⛔ 请先创建角色")  # ❌ 错误！
```

### ❌ 错误 2：嵌套调用中 finish

```python
async def check_permission(uow, player):
    if player.level < 30:
        await cmd.finish("⛔ 等级不足")  # ❌ 错误！

async with UnitOfWork(session_factory) as uow:
    await check_permission(uow, player)
```

### ❌ 错误 3：异常处理中 finish

```python
async with UnitOfWork(session_factory) as uow:
    try:
        # 业务逻辑...
    except SomeError:
        await cmd.finish("❌ 操作失败")  # ❌ 错误！
```

## 修复检查清单

修复现有代码时，检查以下内容：

- [ ] 找到所有 `async with UnitOfWork` 的使用
- [ ] 检查块内是否有 `await xxx.finish()` 调用
- [ ] 检查块内调用的函数是否包含 `finish()`
- [ ] 将所有 `finish()` 移到 UnitOfWork 外部
- [ ] 使用变量保存消息内容
- [ ] 测试验证无连接泄漏警告

## 自动检测脚本

使用以下脚本检查代码中的问题：

```python
#!/usr/bin/env python3
"""检测 UnitOfWork 内部的 finish() 调用"""

import re
from pathlib import Path

def check_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    issues = []
    in_uow_block = False
    uow_indent = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if 'async with UnitOfWork' in line:
            in_uow_block = True
            uow_indent = len(line) - len(line.lstrip())
            continue

        if in_uow_block:
            current_indent = len(line) - len(line.lstrip())

            # 退出 UnitOfWork 块
            if stripped and current_indent <= uow_indent:
                in_uow_block = False
                continue

            # 检查 finish 调用
            if '.finish(' in line and 'await' in line:
                issues.append((i, stripped))

    return issues

# 使用
for file in Path('plugins/xiuxian_game').rglob('*.py'):
    issues = check_file(file)
    if issues:
        print(f"\n{file}:")
        for line_num, content in issues:
            print(f"  Line {line_num}: {content}")
```

## 性能影响

### 方案对比

| 方案 | 代码简洁度 | 连接安全性 | 学习成本 | 推荐度 |
|------|----------|----------|---------|-------|
| 方案1：手动模式 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 方案2：装饰器 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 方案3：提取函数 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

### 推荐策略

- **修复现有代码**：使用方案1（手动模式）
- **编写新代码**：优先考虑方案2（装饰器）
- **复杂业务逻辑**：使用方案3（提取函数）

## 总结

记住这个简单的规则：

> **UnitOfWork 负责数据库操作，finish() 负责消息响应，不要混在一起！**

遵循这个原则，就能避免连接泄漏问题，写出更健壮的代码。
