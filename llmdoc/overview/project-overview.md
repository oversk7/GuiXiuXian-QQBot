# 诡修仙项目概览

## 1. Identity

- **What it is**: 一个基于Nonebot2框架的多人在线QQ修仙游戏机器人,实现了完整的修仙世界观和复杂的游戏系统
- **Purpose**: 为QQ群用户提供修仙主题的文字RPG游戏体验,包含修炼、战斗、社交、经济等多维度玩法

## 2. High-Level Description

诡修仙是一个大型异步Python游戏项目,采用插件式架构构建在Nonebot2框架之上。项目包含165个Python源文件、49个SQLAlchemy数据模型,实现了15+个独立子系统,代码总量约3-4万行。

### 核心特性

**游戏系统**:
- 修炼系统 (突破、闭关、冥返)
- 战斗系统 (PVP、PVE、世界BOSS)
- 公会系统 (建筑、任务、经济)
- 经济系统 (市场、银行、股票、打工)
- 社交系统 (婚姻、师徒、礼物)
- 物品装备 (升阶、镶嵌、耐久、效果)
- 探索系统 (双层坐标、诡域、阴宅)

**技术架构**:
- **框架**: Nonebot2 (异步QQ机器人框架)
- **数据库**: SQLAlchemy 2.0 异步ORM + MySQL/SQLite双引擎
- **配置管理**: YAML配置文件 + 单例模式缓存
- **会话管理**: 三种会话管理器(safe_session主导)
- **效果系统**: 装饰器注册(物品效果) + 管理器模式(战斗效果)

### 项目规模

| 维度 | 数量 | 说明 |
|------|------|------|
| Python文件（核心） | ~142 | 删除旧Service后，分布在15+个子系统模块 |
| Python文件（总计） | ~274 | 含配置、测试和其他辅助文件 |
| 数据模型 | 49 | Player模型包含87个字段 |
| Service类 | 27 | 全部采用DI依赖注入模式 |
| Repository类 | 47 | 数据访问层统一实现 |
| 会话操作 | ~400 | 经过UnitOfWork统一管理 |
| 物品效果 | 45+ | 装饰器注册模式 |
| 战斗效果 | 75+ | 管理器模式 |
| 代码总量 | 2.5-3.5万行 | 清理后，不含配置和文档 |

### 关键文件位置

**入口和配置**:
- `bot.py` - Nonebot2主入口
- `plugins/xiuxian_game/__init__.py` - 游戏插件注册
- `plugins/xiuxian_game/config.py` - 配置管理器
- `plugins/xiuxian_game/models/db.py` - 数据库连接管理

**核心模型**:
- `plugins/xiuxian_game/models/player.py` - Player模型(87字段)
- `plugins/xiuxian_game/models/inventory.py` - ItemInstance模型
- `plugins/xiuxian_game/models/guild.py` - Guild/GuildMember/GuildBuilding

**核心系统**:
- `plugins/xiuxian_game/battle/enhanced_engine.py` - 战斗引擎
- `plugins/xiuxian_game/item/item_effects.py` - 物品效果系统
- `plugins/xiuxian_game/battle/battle_effects.py` - 战斗效果管理器

## 3. 系统特点

### 优秀设计

1. **_persist_bonus机制**: 装备属性加成持久化存储,避免每次战斗重新计算
2. **双引擎支持**: 代码层面支持MySQL和SQLite切换
3. **异步架构**: 全面采用async/await,性能优秀
4. **模块化设计**: 15个子系统按功能域清晰划分
5. **灵活的效果系统**: 支持45+物品效果和75+战斗效果

### 当前问题

基于四轮调研(architecture/attribute/effect/data_access),识别出以下核心问题:

1. **属性计算分散**: 5处计算位置,逻辑不一致
2. **循环依赖**: `item_effects.py` ↔ `equipment_commands.py`
3. **无依赖注入**: 26个Service类采用静态方法,硬编码依赖
4. **多会话问题**: 单命令打开4个独立会话,破坏事务原子性
5. **N+1查询**: 排行榜逐个查询Player对象
6. **效果系统重复**: 装饰器注册 vs 管理器模式设计不一致
7. **配置不一致**: database.yaml(MySQL) vs alembic/env.py(SQLite)

详细问题分析参见 `/reference/code-issues.md`

## 4. 重构状态

### 已完成阶段（v4.0重构）

项目已完成v4.0重构，采用设计模式驱动的松耦合架构：

**核心成果**:
- ✅ 引入DI容器和仓储模式，解耦模块依赖
- ✅ 统一属性计算入口（AttributeCalculator）
- ✅ 统一效果系统接口（IEffect抽象）
- ✅ 使用UoW模式统一事务管理
- ✅ N+1查询优化（Repository预加载）

### 代码清理阶段（2025-12-02）

**完成情况**:
- ✅ 删除31个Feature Flag定义
- ✅ 删除23个旧Service文件（5,681行）
- ✅ 修改56个命令处理器，移除条件分支
- ✅ 总删除代码7,690行，代码库减少8%

**相关文档**:
- Service DI架构: `/architecture/service-di-architecture.md`
- 属性系统: `/architecture/attribute-system.md`
- 效果桥接器: `/architecture/battle-effect-bridge.md`
- 清理详情: `/reference/code-cleanup-2025-12-02.md`

---

**相关文档**:
- 架构详情: `/architecture/current-architecture.md`
- 数据模型: `/reference/data-models.md`
- 设计模式: `/reference/design-patterns.md`
