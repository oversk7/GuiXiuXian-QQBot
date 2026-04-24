# 诡修仙2 (GuiXiuXian2) 技术文档索引

> **面向LLM的检索地图** - 本索引为AI Agent和其他LLM提供快速、精确的文档检索路径

---

## 快速导航

- **[项目概览](#项目概览)** - 了解这是什么项目
- **[核心系统](#核心系统)** - 理解主要功能模块
- **[架构设计](#架构设计)** - 系统如何构建
- **[使用指南](#使用指南)** - 操作指南和最佳实践
- **[参考手册](#参考手册)** - API规范和配置
- **[设计文档](#设计文档)** - 功能设计规格
- **[调查报告](#调查报告)** - 仍有参考价值的系统分析

---

## 项目概览

### 入门文档
- **[项目概述](/llmdoc/overview/project-overview.md)** - 项目定位、核心玩法循环、技术架构全景图
  - 游戏特色: 修仙+暗黑题材RPG,35个境界体系,冥返转生系统
  - 技术栈: NoneBot2 + SQLAlchemy 2.0 + Repository模式 + Unit of Work
  - 核心系统: 战斗、经济、公会、NPC对话、故事引擎

### 系统概览
- **[玩家与属性系统](/llmdoc/overview/player-attributes-overview.md)** - 玩家数据管理、属性计算框架、境界转生机制
- **[战斗系统](/llmdoc/overview/combat-system-overview.md)** - 回合制战斗引擎、装备驱动效果、PvP/PvE机制
- **[经济系统](/llmdoc/overview/economy-system-overview.md)** - 双轨货币、交易市场、跑商、气运投资
- **[数据访问层](/llmdoc/overview/data-access-overview.md)** - Repository模式、Unit of Work、依赖注入、自动迁移

---

## 核心系统

### 玩家与成长
- **[玩家系统架构](/llmdoc/architecture/player-system-architecture.md)** - 数据模型、Repository实现、生命周期管理
- **[属性计算架构](/llmdoc/architecture/attribute-calculation-architecture.md)** - 组合模式+策略模式,多来源属性计算
- **[境界突破指南](/llmdoc/guides/realm-breakthrough-guide.md)** - 突破成功率、冥返转生、经验曲线

### 战斗系统
- **[战斗引擎架构](/llmdoc/architecture/battle-engine-architecture.md)** - 回合执行流程、伤害计算、胜负判定
- **[效果系统架构](/llmdoc/architecture/effect-system-architecture.md)** - 统一效果管理,触发机制,效果叠加
- **[战斗系统指南](/llmdoc/guides/battle-system-guide.md)** - 发起PvP/PvE战斗、查询战斗属性
- **[添加战斗效果指南](/llmdoc/guides/how-to-add-battle-effect.md)** - 通过YAML配置添加新效果

### 经济系统
- **[经济系统架构](/llmdoc/architecture/economy-system-architecture.md)** - 货币管理、价格计算、交易撮合、税收控制
- **[市场交易架构](/llmdoc/architecture/market-trading-architecture.md)** - 跑商系统、动态定价、供需因子
- **[市场交易指南](/llmdoc/guides/market-trading-guide.md)** - 挂牌买卖、撤牌、查牌、税率
- **[经济平衡指南](/llmdoc/guides/economy-balance-guide.md)** - 通胀控制、财富分配、价格调控

### 烹饪与餐厅经营
- **[烹饪与餐厅经营系统设计](/llmdoc/architecture/cooking-restaurant-system-design.md)** - 烹饪、餐厅经营、厨师雇佣、食谱配方

---

## 架构设计

### 数据访问层
- **[Repository模式实现](/llmdoc/architecture/repository-pattern-implementation.md)** - 42个Repository,泛型接口,领域查询
- **[Unit of Work和DI](/llmdoc/architecture/unit-of-work-and-di.md)** - 事务边界管理、依赖注入容器、生命周期

### 设计模式
- **Repository模式** - 数据访问抽象,可测试性,查询集中化
- **Unit of Work模式** - 事务原子性,会话共享,连接泄漏防护
- **依赖注入(DI)** - 解耦合,可测试性,生命周期管理
- **策略模式** - 属性来源系统(IAttributeSource)
- **桥接模式** - 战斗效果桥接(BattleEffectBridge)

---

## 使用指南

- **[玩家属性指南](/llmdoc/guides/player-attribute-guide.md)** - 获取有效属性、添加属性来源、修改玩家属性
- **[VIP装备设计模板](/llmdoc/guides/vip-equipment-design-templates.md)** - VIP定制装备设计方案集，带专属主动技能
- **[攻略合集](/llmdoc/guides/攻略合集.md)** - 跑商、战斗、经济等玩家攻略(面向玩家)

---

## 参考手册

- **[经济系统参考](/llmdoc/reference/economy-system-reference.md)** - 配置参数、计算公式、常量定义
- **[编码规范](/llmdoc/reference/coding-conventions.md)** - Python代码风格、命名约定
- **[Git规范](/llmdoc/reference/git-conventions.md)** - Git提交规范
- **[QQ Bot Markdown模板](/llmdoc/reference/markdown-templates.md)** - QQ Bot模板ID和模板语法参考

---

## 设计文档

功能设计规格，由 brainstorming 会话产出。

### 设计规格 (specs)
- **[战斗UI Markdown设计](/llmdoc/design/specs/2026-03-13-battle-ui-markdown-design.md)** (2026-03-13)
- **[龙斩鞋设计](/llmdoc/design/specs/2026-03-13-dragon-blade-shoes-design.md)** (2026-03-13)
- **[奋进系统设计](/llmdoc/design/specs/2026-03-15-fenjin-design.md)** (2026-03-15)
- **[装备词缀铭文设计](/llmdoc/design/specs/2026-03-18-equipment-affix-inscription-design.md)** (2026-03-18)
- **[铭文掉落Phase3设计](/llmdoc/design/specs/2026-03-19-inscription-drop-phase3-design.md)** (2026-03-19)
- **[新手任务扩展设计](/llmdoc/design/specs/2026-03-20-novice-quest-expansion-design.md)** (2026-03-20)
- **[导航随机事件设计](/llmdoc/design/specs/2026-03-20-navigation-random-events-design.md)** (2026-03-20)
- **[荔湾鬼城内界设计](/llmdoc/design/specs/2026-03-24-liwan-ghost-town-inner-realm-design.md)** (2026-03-24)
- **[餐厅经济平衡重设计](/llmdoc/design/specs/2026-03-27-restaurant-economy-balance-design.md)** (2026-03-27)

### 进行中的实现计划 (plans)
- **[个人摊位系统](/llmdoc/design/plans/2026-04-08-personal-stall-system.md)** (2026-04-08)
- **[斗法天梯系统](/llmdoc/design/plans/2026-04-10-dharma-ladder-impl.md)** (2026-04-10)
- **[世界地图扩展](/llmdoc/design/plans/2026-04-04-world-map-expansion-impl.md)** (2026-04-04)

---

## 调查报告

仍有参考价值的系统分析报告。

- **[技术架构调查](/llmdoc/agent/tech_architecture_investigation_2026_02_18.md)** (2026-02-18)
- **[阴宅公会仓库调查](/llmdoc/agent/scout_mansion_guild_warehouse_investigation_2026_02_22.md)** (2026-02-22)
- **[NPC对话与物品管理](/llmdoc/agent/scout_npc_ai_dialogue_and_item_management_2026_03_04.md)** (2026-03-04)
- **[下界系统](/llmdoc/agent/scout_lower_world_system_2026_03_15.md)** (2026-03-15)

---

## 快速开始

### 新手入门路径

#### 1. 了解项目 (必读)
1. 阅读 [项目概述](/llmdoc/overview/project-overview.md) - 了解项目定位和核心玩法
2. 阅读 [数据访问层概览](/llmdoc/overview/data-access-overview.md) - 理解Repository+UnitOfWork+DI架构
3. 阅读 [编码规范](/llmdoc/reference/coding-conventions.md) - 遵循项目代码风格

#### 2. 理解核心系统 (按需)
- **玩家系统**: [玩家系统架构](/llmdoc/architecture/player-system-architecture.md)
- **属性系统**: [属性计算架构](/llmdoc/architecture/attribute-calculation-architecture.md)
- **战斗系统**: [战斗系统指南](/llmdoc/guides/battle-system-guide.md)
- **经济系统**: [经济系统架构](/llmdoc/architecture/economy-system-architecture.md)

#### 3. 开始开发
- **添加战斗效果**: 参考 [如何添加战斗效果](/llmdoc/guides/how-to-add-battle-effect.md)
- **修改玩家属性**: 参考 [玩家属性指南](/llmdoc/guides/player-attribute-guide.md)
- **数据库迁移**: 在 `auto_migrate.py` 的 `REQUIRED_FIELDS` 添加字段 → 重启Bot

### 常见任务速查

| 任务 | 步骤 |
|------|------|
| 添加新功能 | 创建Model → Repository → 添加到UoW → 创建Service → 更新help.py |
| 数据库迁移 | 在auto_migrate.py的REQUIRED_FIELDS添加字段 → 重启Bot |
| 添加战斗效果 | 参考 [how-to-add-battle-effect](/llmdoc/guides/how-to-add-battle-effect.md) |

---

**版本**: 5.0
**最后更新**: 2026-04-24
**最近更新**: 清理已完成的实现计划(10)和过时调查报告(9)，移除死链
