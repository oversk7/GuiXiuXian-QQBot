# Directory Structure

> NoneBot2 修仙游戏 QQ 机器人的模块化目录组织。

---

## Overview

项目采用分层架构 + 领域模块化设计。核心代码在 `plugins/xiuxian_game/` 下，每个业务域独立目录，包含 handler 和 service。

---

## Directory Layout

```
plugins/xiuxian_game/
├── __init__.py              # 插件入口：注册、启动数据库、效果系统
├── config.py                # 游戏配置单例
├── utils.py                 # 通用工具（进度条、计算函数、消息格式）
├── utils_markdown.py        # Markdown 消息构建
├── platform_utils.py        # 跨平台工具（玩家获取、身份缓存）
│
├── models/                  # 数据层：ORM 模型 + 自动迁移
│   ├── db.py                # 会话管理（safe_session, retry_session）
│   ├── auto_migrate.py      # 自动迁移引擎（REQUIRED_FIELDS/INDEXES）
│   ├── player.py            # Player 模型
│   └── ...                  # 其他 ORM 模型
│
├── infrastructure/          # 基础设施层
│   ├── uow.py               # UnitOfWork 工作单元
│   ├── repositories/        # Repository 实现
│   └── cache/               # 缓存策略
│
├── domain/                  # 领域层（跨模块业务逻辑）
│   ├── attributes/          # 属性计算引擎
│   ├── effects/             # 物品/战斗效果系统
│   └── events/              # 事件处理
│
├── config/                  # 配置管理
├── data/                    # YAML 游戏数据文件
│   ├── config.yaml          # 核心配置（经验、属性）
│   ├── items.yaml           # 物品库
│   ├── map.yaml             # 地图 + 诡域
│   ├── elixirs.yaml         # 丹方
│   └── knowledge/           # AI 知识库 YAML（与 help.py 1:1 对应）
│
├── player/                  # 玩家系统（注册、信息、排行、月卡）
├── world/                   # 世界系统（地点、导航、NPC、诡域战斗）
├── cultivate/               # 修炼系统（经验、突破、修为）
├── economy/                 # 经济系统（市集、股票、银行、基金）
├── item/                    # 物品系统（背包、装备、锻造）
├── battle/                  # 战斗系统（PVP、天梯排行）
├── guild/                   # 公会系统（建筑、任务、活动）
├── alchemy/                 # 炼丹系统
├── cooking/                 # 烹饪 + 餐厅经营
├── social/                  # 社交系统（关系、邀请、黑名单）
├── spirit_field/            # 灵田种植（种植、偷菜、诡兽守田）
├── dialogue/                # NPC AI 对话（好感度、记忆、礼物）
├── daily_task/              # 日常任务（每日委托、任务链）
├── inner_realm/             # 诡域探索
├── fishing/                 # 钓鱼
├── pet/                     # 宠物伴侣
├── auction/                 # 拍卖行
├── stall/                   # 玩家摊位
├── achievement/             # 成就
├── event/                   # 活动（除夕、世界Boss）
├── admin/                   # 管理员功能
├── ai_guide/                # AI 引导
├── web/                     # Web 地图可视化
├── sponsor/                 # 赞助商店（诡烛氪金）
└── help.py (in player/)     # 帮助信息（命令注册必须同步更新）
```

---

## Module Organization

每个业务模块内部遵循以下结构：

```
plugins/xiuxian_game/{module}/
├── __init__.py              # 导入 handlers，使模块注册到 NoneBot
├── commands.py              # 命令定义（on_command + handler）
├── {module}_service.py      # 核心业务逻辑
└── ...                      # 其他特定功能文件
```

**分层职责**：
- **Handler**（commands.py）：命令解析、参数验证、权限检查、调用 service
- **Service**：核心业务逻辑、数据库操作
- **Domain**：跨模块逻辑（属性计算、效果引擎）
- **Repository**：数据访问抽象

---

## Naming Conventions

| 类型 | 规则 | 示例 |
|------|------|------|
| 目录名 | snake_case | `spirit_field/`, `daily_task/` |
| 模块文件 | snake_case | `stock_commands.py`, `player_service.py` |
| Handler 文件 | `*_commands.py` | `market_commands.py` |
| Service 文件 | `*_service.py` | `stock_service.py` |
| Model 文件 | 实体名 snake_case | `player.py`, `guild_member.py` |
| 工具文件 | `utils*.py` | `utils.py`, `utils_markdown.py` |

---

## Examples

参考 `economy/` 模块（包含股票、市集、银行等多子功能，按文件拆分清晰）和 `battle/ladder/`（竞技场排行，独立子目录）。
