# Logging Guidelines

> 使用 NoneBot logger 和标准 logging，按模块分级。

---

## Overview

- **NoneBot 模块**（插件入口、启动流程）：`from nonebot import logger`
- **业务模块**（service、repository）：`import logging` + `logger = logging.getLogger(__name__)`
- 日志主要用于启动诊断、迁移记录、异常追踪

---

## Log Levels

| Level | 用途 | 示例 |
|-------|------|------|
| `debug` | 开发调试信息 | 查询参数、计算中间值 |
| `info` | 正常业务流程 | 配置加载完成、玩家操作 |
| `success` | 启动/初始化成功（NoneBot 专有） | `logger.success("[模块] 启动完成")` |
| `warning` | 异常但可恢复 | 缓存未命中、配置回退到默认值 |
| `error` | 操作失败需关注 | 数据库查询失败、外部 API 超时 |

---

## Logger Setup

### NoneBot 入口模块

```python
from nonebot import logger

logger.success("[xiuxian] 效果系统已注册 42 个效果")
logger.info("[xiuxian] 数据库类型: MySQL")
```

### 业务模块

```python
import logging

logger = logging.getLogger(__name__)

logger.info("配置加载: %d 个物品", len(items))
logger.error("数据库查询失败: %s", str(e))
```

---

## What to Log

- **启动流程**：数据库类型、连接信息、配置加载数量、效果注册数量
- **自动迁移**：创建的表、添加的字段、修复的 ENUM（详细级别）
- **异常场景**：数据库错误、外部请求失败、配置缺失
- **管理员操作**：数据修改、抽奖、批量操作

---

## What NOT to Log

- 玩家密码、token、session key
- 正常的业务操作流水（每条命令不需要日志）
- 大量重复的轮询日志（避免日志刷屏）
- 数据库连接字符串中的密码部分

---

## Formatting

```python
# Good: 用 % 格式化（logging 标准）
logger.info("玩家 %s 升级到 %d 级", player.id, player.level)

# Good: 带模块标签
logger.info("[alchemy] 炼丹完成: %s", elixir_name)

# Bad: f-string（参数会在日志被过滤时仍然求值）
logger.debug(f"计算结果: {expensive_calc()}")
```
