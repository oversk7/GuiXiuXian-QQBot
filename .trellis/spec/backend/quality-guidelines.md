# Quality Guidelines

> 代码风格、禁止模式、必须模式。

---

## Overview

Python 3.10+ 异步项目，SQLAlchemy 2.0 ORM，NoneBot2 框架。核心约束：NoneBot 流程控制异常安全、异步优先、分层架构。

---

## Forbidden Patterns

### 1. 宽泛异常捕获（致命）

```python
# NEVER: 会吞掉 NoneBot 的 FinishedException
except Exception:
    ...

except BaseException:
    ...
```

### 2. 同步阻塞调用

```python
# NEVER: 阻塞事件循环
import requests
resp = requests.get(url)

# ALWAYS: 用异步
import aiohttp
async with aiohttp.ClientSession() as s:
    resp = await s.get(url)
```

### 3. Session 并发

```python
# NEVER: 共享 session 并发操作
await asyncio.gather(fn1(session), fn2(session))
```

### 4. 手动 Alembic

```python
# NEVER: 手动迁移命令
alembic upgrade head  # 禁止
```

### 5. 硬编码 SQL

```python
# NEVER
session.execute(text("SELECT * FROM player WHERE id = " + user_id))

# ALWAYS: 用 ORM
stmt = select(Player).where(Player.id == user_id)
```

---

## Required Patterns

### 1. 玩家数据获取

```python
# ALWAYS: 通过 get_unified_player 获取玩家（支持账号切换）
player = await get_unified_player(session, event)
```

### 2. 事务管理

```python
# ALWAYS: 用 safe_session 管理事务
async with safe_session() as session:
    ...
```

### 3. 命令注册同步

添加/修改命令时，必须同步更新：
1. `plugins/xiuxian_game/player/help.py` — 命令语法、描述、示例
2. `plugins/xiuxian_game/data/knowledge/*.yaml` — AI 知识库

### 4. Import 顺序

```python
from __future__ import annotations  # 如使用 3.10+ 语法

# 标准库
import logging
from datetime import datetime
from typing import Optional

# 第三方
from nonebot import on_command
from sqlalchemy import select

# 项目内部（相对导入）
from ..models.db import safe_session
from ..utils import message_add_head
```

### 5. 类型提示

```python
# 函数签名必须有类型提示
async def get_player_by_uid(session: AsyncSession, uid: int) -> Optional[Player]:
    ...

# 可选类型用 union 语法
guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

---

## Code Style

| 规则 | 标准 |
|------|------|
| 命名 | snake_case（函数、变量、模块）、PascalCase（类） |
| 私有函数 | `_` 前缀：`async def _format_location()` |
| 异步 | Handler 和 Service 层全部 async |
| 字符串 | f-string 用于消息构建，`%` 用于 logging |
| 枚举 | 继承 `str, Enum`，值用中文：`MALE = "男"` |

---

## Architecture Rules

| 层 | 职责 | 禁止 |
|----|------|------|
| Handler | 命令解析、参数验证、权限检查 | 不包含业务逻辑 |
| Service | 核心业务逻辑 | 不直接操作 `matcher` |
| Repository | 数据库查询封装 | 不包含业务判断 |
| Domain | 跨模块逻辑（属性计算、效果引擎） | 不依赖框架 |

---

## Circular Import Prevention

```python
# 跨模块依赖用惰性导入
async def some_function():
    from ..other_module.service import OtherService
    await OtherService.do_something()
```

---

## Message Formatting

```python
from ..utils_markdown import cmd, build_markdown
from ..utils import message_add_head

# Markdown 格式
content = "# Title\n***\nBody text\n"
msg = build_markdown(content)
await matcher.finish(message_add_head(msg, event))

# 可点击命令蓝字
cmd_text = cmd("查看面板", "角色")  # 显示"查看面板"，点击执行"角色"
```

---

## Code Review Checklist

- [ ] 没有 `except Exception:` 或 `except BaseException:`
- [ ] 数据库操作用 `safe_session()` 包裹
- [ ] 玩家获取用 `get_unified_player()`
- [ ] 新命令已同步更新 `help.py` 和 `knowledge/*.yaml`
- [ ] 新字段通过 `auto_migrate.py` 的 `REQUIRED_FIELDS` 添加
- [ ] 无同步阻塞调用
- [ ] 类型提示完整
- [ ] Import 使用相对路径，无循环导入
