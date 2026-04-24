# Database Guidelines

> SQLAlchemy 2.0 异步 ORM + 自动迁移，支持 SQLite（开发）和 MySQL（生产）。

---

## Overview

- **ORM**：SQLAlchemy 2.0（`Mapped` + `mapped_column` 语法）
- **异步**：`AsyncSession` + 异步引擎
- **迁移**：`auto_migrate.py` 自动执行，**禁止手动 Alembic**
- **双引擎**：开发用 SQLite，生产用 MySQL

---

## Query Patterns

### 会话管理

使用 `safe_session()` 管理事务，**自动处理 NoneBot2 流程控制异常**：

```python
from ..models.db import safe_session

async with safe_session() as session:
    player = await get_unified_player(session, event)
    if not player:
        await matcher.finish("need registration")

    player.level += 1
    session.add(player)
    # safe_session 自动 commit
```

三种会话管理器：
- `safe_session()`：默认选择，自动 commit + NoneBot 异常安全
- `get_session()`：手动 commit/rollback 场景
- `retry_session(max_retries=3)`：处理 SQLite 并发锁定

### UnitOfWork 模式

跨 repository 的复杂操作用 UnitOfWork：

```python
from ..infrastructure.uow import UnitOfWork

async with UnitOfWork(AsyncSessionLocal) as uow:
    player = await uow.player_repo.get_by_id(player_id)
    items = await uow.item_repo.get_by_player(player_id)
    player.gold += 1000
    await uow.commit()
```

### 禁止模式

```python
# NEVER: 共享 session 的并发操作
await asyncio.gather(
    source1.calculate(session),  # session 不是线程安全的
    source2.calculate(session),
)

# ALWAYS: 顺序执行
for source in sources:
    bonus = await source.calculate(session)
```

---

## Migrations

**唯一方式**：修改 `plugins/xiuxian_game/models/auto_migrate.py`，重启机器人。

### 添加新字段

在 `REQUIRED_FIELDS` 字典中添加条目：

```python
REQUIRED_FIELDS = {
    "player": {
        "new_field": "INTEGER DEFAULT 0",
    },
}
```

### 添加新索引

在 `REQUIRED_INDEXES` 中添加：

```python
REQUIRED_INDEXES = {
    "ix_player_guild_id": ("player", ["guild_id"]),
}
```

### 四步自动迁移流程

启动时自动执行：
1. 创建缺失的表
2. 添加缺失的字段（或修改字段类型）
3. 创建缺失的索引
4. 修复 ENUM 列（通过临时列中转）

---

## Naming Conventions

| 类型 | 规则 | 示例 |
|------|------|------|
| 表名 | snake_case 全小写 | `player`, `guild_member`, `inventory` |
| 字段名 | snake_case 全小写 | `guild_id`, `last_active_at` |
| 主键 | 业务主键优先 | `player.id`（平台ID）, `guild.id`（自增） |
| 时间戳 | `*_at` 后缀 | `created_at`, `last_cultivation` |
| 布尔值 | `is_*` 前缀 | `is_active`, `is_bound` |
| 索引名 | `ix_{table}_{column}` | `ix_player_guild_id` |

### 字段定义标准

```python
class Player(Base):
    __tablename__ = "player"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True, comment="平台ID")
    uid: Mapped[int] = mapped_column(Integer, unique=True, comment="自增UID")
    nickname: Mapped[str] = mapped_column(String(24))
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="等级")
    guild_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    extra_attrs: Mapped[dict] = mapped_column(JSON, default={}, server_default='{}')
```

**必须**：
- 所有重要字段添加 `comment=` 中文说明
- 数值字段同时设 `default=` 和 `server_default=`
- 可选字段显式标注 `nullable=True` 和 `Mapped[X | None]`
- 枚举字段用 `String(N)` 存储字符串值，不用 MySQL ENUM

---

## Common Mistakes

| 错误 | 正确做法 |
|------|----------|
| 手动运行 Alembic | 只用 `auto_migrate.py` 的 `REQUIRED_FIELDS` |
| `except Exception:` 包裹数据库操作 | 用 `safe_session()` 自动处理 |
| `asyncio.gather` 共享 session | 顺序执行 session 操作 |
| 忘记 `server_default` | 始终同时设置 `default` 和 `server_default` |
| 直接写 raw SQL | 用 SQLAlchemy ORM 或 Repository |
