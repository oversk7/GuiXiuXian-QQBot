# Error Handling

> NoneBot2 流程控制异常是核心约束，所有 handler 的异常处理必须围绕它设计。

---

## Overview

NoneBot2 的 `finish()`, `send()`, `reject()` 通过**抛异常**实现流程控制。`except Exception:` 会拦截这些异常，导致 handler 无法正常终止。这是本项目最重要的错误处理规则。

---

## Error Types

### NoneBot2 流程控制异常（必须放行）

| 异常 | 触发方式 | 含义 |
|------|----------|------|
| `FinishedException` | `await matcher.finish()` | 终止当前 handler |
| `PausedException` | `await matcher.pause()` | 暂停，等待下一条消息 |
| `RejectedException` | `await matcher.reject()` | 拒绝当前事件 |

### 业务异常（需要捕获）

| 异常 | 场景 |
|------|------|
| `ValueError` | 参数转换失败 |
| `SQLAlchemyError` | 数据库操作失败 |
| `requests.RequestException` | 外部 HTTP 请求失败 |
| `json.JSONDecodeError` | JSON 解析失败 |
| `KeyError` / `IndexError` | 配置或数据结构访问失败 |

---

## Error Handling Patterns

### 标准 Handler 模式

```python
@matcher.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # 1. 参数验证（在 try 之外）
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await matcher.finish("usage hint")

    try:
        target_uid = int(arg_text)
    except ValueError:
        await matcher.finish("UID must be a number")

    # 2. 业务逻辑（用 safe_session）
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await matcher.finish("need registration")

        # 3. 具体异常捕获
        try:
            result = await some_external_call()
        except requests.RequestException:
            await matcher.finish("network error")

        await matcher.finish("success")
```

### safe_session 的异常处理

`safe_session()` 已内置 NoneBot 异常安全逻辑：

```python
async with safe_session() as session:
    # FinishedException/PausedException/RejectedException:
    #   → 先 commit 事务，再重新抛出
    # 其他异常:
    #   → rollback 事务，再重新抛出
    pass
```

### 权限检查链

```python
async with safe_session() as session:
    player = await get_unified_player(session, event)

    if not player:
        await matcher.finish("need registration")

    if player.is_in_dungeon():
        await matcher.finish("cannot do this in dungeon")

    if not player.guild_id:
        await matcher.finish("need guild")

    # 通过所有检查，执行操作
```

---

## Forbidden Patterns

```python
# FATAL: 捕获所有异常 — 会吞掉 NoneBot 流程控制
try:
    await matcher.finish("message")
except Exception:  # FinishedException 被吞掉！
    await matcher.finish("unknown error")  # 无法执行

# FATAL: BaseException 同理
try:
    ...
except BaseException:
    ...

# BAD: 宽泛的异常捕获
try:
    player.level += 1
    session.add(player)
except Exception as e:
    logger.error(e)  # 吞掉了 FinishedException
```

**规则**：只捕获你知道会发生的具体异常类型。

---

## Response Format

错误消息统一格式（QQ 消息）：

```
前缀标记 + 具体说明
```

- `"need registration"` — 需要创建角色
- `"insufficient gold"` — 金币不足
- `"cooldown N seconds"` — 冷却时间

---

## Common Mistakes

| 错误 | 后果 | 修复 |
|------|------|------|
| `except Exception:` 在 handler 中 | finish/send 静默失效 | 改为具体异常类型 |
| 验证逻辑放在 try 内 | 验证异常被错误类型捕获 | 验证逻辑放 try 之外 |
| 忘记用 `safe_session()` | 数据库事务未正确提交/回滚 | 统一使用 safe_session |
| 直接 `session.commit()` 不处理 NoneBot 异常 | commit 后 FinishedException 导致重复 commit | 用 safe_session 代替 |
