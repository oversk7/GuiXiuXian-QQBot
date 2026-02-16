# PROJECT KNOWLEDGE BASE - 诡修仙2 (GuiXiuXian2)

**Generated:** 2026-02-16
**Stack:** NoneBot2 + SQLAlchemy 2.0 + Python 3.9+

## OVERVIEW

QQ bot文字修仙RPG游戏。暗黑题材，35个境界体系，冥返转生系统。DD架构(Repository + UoW + DI)。

## STRUCTURE

```
GuiXiuXian2/
├── bot.py                    # 入口 (16行)
├── plugins/xiuxian_game/     # 主代码 (非src/)
│   ├── __init__.py           # 插件入口，注册20个子模块
│   ├── models/               # 50个SQLAlchemy模型 → 见 ./plugins/xiuxian_game/models/AGENTS.md
│   ├── domain/               # DDD领域层 → 见 ./plugins/xiuxian_game/domain/AGENTS.md
│   ├── infrastructure/       # 基础设施层
│   │   ├── repositories/     # 35个Repository → 见 ./plugins/xiuxian_game/infrastructure/repositories/AGENTS.md
│   │   ├── di/               # DI容器
│   │   └── uow/              # UnitOfWork
│   ├── player/               # 玩家系统 (帮助、注册)
│   ├── cultivate/            # 修炼、突破
│   ├── battle/               # PVP/PVE战斗
│   ├── economy/              # 经济、市场、交易
│   ├── guild/                # 宗门系统
│   ├── item/                 # 物品、装备
│   ├── world/                # 世界地图、探索
│   ├── cooking/              # 烹饪、餐厅经营
│   ├── fishing/              # 钓鱼系统
│   ├── story/                # 故事引擎
│   ├── dialogue/             # NPC AI对话
│   ├── admin/                # 管理员功能
│   └── [其他12个模块]
├── llmdoc/                   # LLM文档索引 (37个md)
├── tests/                    # 单元测试
├── scripts/                  # 独立脚本
└── data/                     # YAML配置、存档
```

## WHERE TO LOOK

| 任务 | 位置 | 备注 |
|------|------|------|
| 玩家数据 | `models/player.py` | Player模型70+字段 |
| 数据访问 | `infrastructure/repositories/` | IRepository[T]泛型 |
| 属性计算 | `domain/attributes/` | IAttributeSource接口 |
| 战斗效果 | `domain/effects/` | IEffect + 适配器 |
| 领域事件 | `domain/events/` | EventBus发布订阅 |
| 配置文件 | `data/*.yaml` | items.yaml, config.yaml |
| 帮助信息 | `player/help.py` | 必须同步更新 |
| 详细文档 | `llmdoc/index.md` | 37个架构/指南文档 |

## CONVENTIONS

**命名:**
- 类: PascalCase (`PlayerRepository`)
- 函数/变量: snake_case (`get_by_uid`)
- 模型字段: snake_case (`spirit_stones`)

**导入顺序:** std → third → local

**类型注解:** 强制使用
```python
# ORM字段
spirit_stones: Mapped[int] = mapped_column(default=0)
# 函数
async def get_by_uid(self, uid: str) -> Player | None:
```

**异常处理 (NoneBot2):**
```python
# ✅ 正确: 只捕获特定异常
try:
    response = requests.get(url)
except requests.RequestException:
    await handler.finish("网络错误")

# ❌ 错误: 捕获所有会拦截NoneBot2控制流
try:
    await handler.finish("...")  # FinishedException被吞掉!
except Exception:
    pass
```

## ANTI-PATTERNS (严禁)

1. **Alembic禁用** - 使用 `models/auto_migrate.py`
   ```python
   # 在REQUIRED_FIELDS字典添加字段定义
   REQUIRED_FIELDS = {"player": {"new_field": ("VARCHAR(100)", None)}}
   ```

2. **UoW内禁止finish()** - 导致连接泄漏
   ```python
   # ❌ 错误
   async with UnitOfWork() as uow:
       await handler.finish("done")  # 连接不会释放!

   # ✅ 正确
   async with UnitOfWork() as uow:
       await uow.player_repo.save(player)
   await handler.finish("done")  # 在UoW外部
   ```

3. **Service禁止commit()** - 由UoW管理事务
   ```python
   # ❌ 错误
   class PlayerService:
       async def update(self):
           await self.session.commit()  # 越权!

   # ✅ 正确
   async with UnitOfWork() as uow:
       await uow.player_service.update()
       # 自动commit
   ```

## UNIQUE STYLES

**DDD分层架构:**
- `domain/`: 纯领域逻辑，无基础设施依赖
- `infrastructure/`: 数据访问、DI、UoW
- `models/`: SQLAlchemy ORM模型

**双轨Service命名:**
- `*_service.py`: 旧legacy服务
- `*_service_new.py`: 新DI服务
- 正在逐步迁移到 `_new.py`

**Feature Flags:**
```bash
# .env
USE_NEW_EFFECT_SYSTEM=true
```

## COMMANDS

```bash
# 开发
nb run                      # 启动bot
python bot.py               # 直接运行

# 数据库迁移
python -m plugins.xiuxian_game.models.auto_migrate

# 脚本
python scripts/migrate_sqlite_to_mysql.py
python scripts/check_fonts.py
```

## NOTES

- 中文注释/文档字符串
- 帮助系统必须同步更新 (`player/help.py`)
- 修改命令时更新 `llmdoc/` 文档
- 测试使用自定义 `pytest_raises()`，非标准pytest
- 25+文件超过500行，主要热点: `inner_realm/service.py`(2573行), `guild/guild.py`(1650行)
