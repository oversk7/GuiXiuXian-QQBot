# 诡修仙2 (GuiXiuXian2) 技术文档索引

> **面向LLM的检索地图** - 本索引为AI Agent和其他LLM提供快速、精确的文档检索路径

---

## 快速导航

- **[项目概览](#项目概览)** - 了解这是什么项目
- **[核心系统](#核心系统)** - 理解主要功能模块
- **[架构设计](#架构设计)** - 系统如何构建
- **[使用指南](#使用指南)** - 操作指南和最佳实践
- **[参考手册](#参考手册)** - API规范和配置
- **[设计文档](#设计文档)** - 功能设计规格和实现计划
- **[调查报告](#调查报告)** - Agent调查报告
- **[快速开始](#快速开始)** - 新手入门路径

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
  - Player模型30+字段(属性、坐标、社交关系)
  - PlayerRepository领域查询(get_by_uid, get_nearby_players)
  - UnitOfWork事务边界管理

- **[属性计算架构](/llmdoc/architecture/attribute-calculation-architecture.md)** - 组合模式+策略模式,多来源属性计算
  - AttributeCalculator v2管理多个属性来源
  - 60秒TTL缓存优化90%临时buff查询
  - 区分持久化(装备/丹药)与动态计算(buff)

- **[境界突破指南](/llmdoc/guides/realm-breakthrough-guide.md)** - 突破成功率、冥返转生、经验曲线
  - 30级前100%成功,30级后递减(最低10%)
  - 冥返等级要求(300/500/1000/1500/2000级)
  - 转数加成(属性点、修炼效率)

### 战斗系统
- **[战斗引擎架构](/llmdoc/architecture/battle-engine-architecture.md)** - 回合执行流程、伤害计算、胜负判定
  - EnhancedBattleEngine控制战斗初始化和回合循环
  - BattleAttributeCalculator计算战斗属性(暴击、连击、闪避等)
  - 支持随机种子实现可重现战斗

- **[效果系统架构](/llmdoc/architecture/effect-system-architecture.md)** - 统一效果管理,触发机制,效果叠加
  - 20+种效果类型,10+种触发类型
  - 桥接模式集成IEffect接口
  - 装备效果解锁(普通装备+2阶解锁,VIP装备0阶全解锁)

- **[战斗系统指南](/llmdoc/guides/battle-system-guide.md)** - 发起PvP/PvE战斗、查询战斗属性、理解伤害计算
  - 防御减伤公式: max(1, damage - min(defense, damage*defense/(defense+100)))

- **[添加战斗效果指南](/llmdoc/guides/how-to-add-battle-effect.md)** - 通过YAML配置添加新效果,无需修改代码

### 经济系统
- **[经济系统架构](/llmdoc/architecture/economy-system-architecture.md)** - 货币管理、价格计算、交易撮合、税收控制
  - MarketOrder订单簿模式,自动撮合
  - 阶梯税收(0-20%),直接销毁回收货币
  - 财富指数联动(1.0-3.0倍)响应全服财富水平

- **[市场交易架构](/llmdoc/architecture/market-trading-architecture.md)** - 跑商系统、动态定价、供需因子

- **[市场交易指南](/llmdoc/guides/market-trading-guide.md)** - 挂牌买卖、撤牌、查牌、税率

- **[经济平衡指南](/llmdoc/guides/economy-balance-guide.md)** - 通胀控制、财富分配、价格调控

### 烹饪与餐厅经营
- **[烹饪与餐厅经营系统设计](/llmdoc/architecture/cooking-restaurant-system-design.md)** - 烹饪系统、餐厅经营、厨师雇佣、食谱配方
  - 联动钓鱼系统: 鱼类食材 → 烹饪 → 菜肴 → 餐厅售卖/食用
  - **实现状态**: ✅ 已完成(2026-02-08)

---

## 架构设计

### 数据访问层
- **[Repository模式实现](/llmdoc/architecture/repository-pattern-implementation.md)** - 42个Repository,泛型接口,领域查询
- **[Unit of Work和DI](/llmdoc/architecture/unit-of-work-and-di.md)** - 事务边界管理、依赖注入容器、生命周期
- **[数据访问迁移指南](/llmdoc/guides/data-access-migration-guide.md)** - 从Legacy架构迁移到新架构(✅ 已全部完成)

### 设计模式
- **Repository模式** - 数据访问抽象,可测试性,查询集中化
- **Unit of Work模式** - 事务原子性,会话共享,连接泄漏防护
- **依赖注入(DI)** - 解耦合,可测试性,生命周期管理
- **策略模式** - 属性来源系统(IAttributeSource)
- **桥接模式** - 战斗效果桥接(BattleEffectBridge)

### 架构特点
- **自动数据库迁移** - 启动时自动检测并升级数据库结构,零停机部署
- **缓存优化** - 60秒TTL缓存减少90%临时buff查询
- **属性持久化** - 装备加成预计算并持久化到player表
- **架构迁移完成** - 26/26服务全部迁移到DI架构(2026-01-10)

---

## 使用指南

### 属性系统
- **[玩家属性指南](/llmdoc/guides/player-attribute-guide.md)** - 获取有效属性、添加属性来源、修改玩家属性

### 数据库操作
- **[自动迁移系统](/llmdoc/overview/project-overview.md#64-自动数据库迁移-auto-migrate)** - 添加新字段、添加ENUM值

### 开发规范
- **[编码规范](/llmdoc/reference/coding-conventions.md)** - Python代码风格、命名约定、文件组织、设计模式

### 装备设计
- **[VIP装备设计模板](/llmdoc/guides/vip-equipment-design-templates.md)** - VIP定制装备设计方案集，带专属主动技能

### 玩家攻略
- **[攻略合集](/llmdoc/guides/攻略合集.md)** - 跑商、战斗、经济等玩家攻略(面向玩家)

---

## 参考手册

- **[经济系统参考](/llmdoc/reference/economy-system-reference.md)** - 配置参数、计算公式、常量定义
- **[编码规范](/llmdoc/reference/coding-conventions.md)** - Python代码风格、命名约定
- **[Git规范](/llmdoc/reference/git-conventions.md)** - Git提交规范
- **[QQ Bot Markdown模板](/llmdoc/reference/markdown-templates.md)** - QQ Bot模板ID和模板语法参考

### 配置文件
- **NoneBot配置** (`.env`) - ENVIRONMENT, LOG_LEVEL, COMMAND_START, SUPERUSERS
- **游戏配置** (`data/config.yaml`) - 修炼、突破、掉落率、经济倍率
- **数据库配置** (`config/database.yaml`) - SQLite/MySQL连接配置
- **物品配置** (`data/items.yaml`) - 物品主配置,装备特殊效果

### 月卡配置
| 功能 | 基础月卡 | 高级月卡 |
|------|---------|---------|
| 修炼效率 | +20% | +50% |
| 闭关时长 | 9小时 | 12小时 |
| 闭关效率 | +20% | +50% |
| 背包格子 | +5 | +20 |
| 突破保护 | 75% | 80% |
| 自动采集 | 无 | 有 |

---

## 设计文档

功能设计规格和实现计划,由 brainstorming 会话产出。

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

### 实现计划 (plans)
- **[奋进系统实现](/llmdoc/design/plans/2026-03-15-fenjin-impl.md)** (2026-03-15)
- **[装备词缀Phase1](/llmdoc/design/plans/2026-03-18-equipment-affix-phase1-impl.md)** (2026-03-18)
- **[装备词缀Phase2](/llmdoc/design/plans/2026-03-18-equipment-affix-phase2-impl.md)** (2026-03-18)
- **[铭文掉落Phase3](/llmdoc/design/plans/2026-03-19-inscription-drop-phase3-impl.md)** (2026-03-19)
- **[宠物伴侣系统](/llmdoc/design/plans/2026-03-20-pet-companion-system.md)** (2026-03-20)
- **[宠物进化系统](/llmdoc/design/plans/2026-03-21-pet-evolution-system.md)** (2026-03-21)
- **[宠物自定义性格](/llmdoc/design/plans/2026-03-22-pet-custom-personality.md)** (2026-03-22)
- **[荔湾鬼城实现](/llmdoc/design/plans/2026-03-24-liwan-ghost-town-impl.md)** (2026-03-24)
- **[原生Markdown帮助经济](/llmdoc/design/plans/2026-03-26-native-markdown-help-economy.md)** (2026-03-26)
- **[餐厅经济平衡](/llmdoc/design/plans/2026-03-27-restaurant-economy-balance.md)** (2026-03-27)

---

## 调查报告

Agent调查报告,记录系统分析和设计决策。

- **[Repository/Service/UoW模式](/llmdoc/agent/scout_repository_service_uow_patterns_2026_01_11.md)** (2026-01-11)
- **[周主题调查](/llmdoc/agent/scout_weekly_theme_investigation_2026_01_11.md)** (2026-01-11)
- **[修炼系统调查](/llmdoc/agent/scout_cultivation_system_investigation_2025_01_23.md)** (2025-01-23)
- **[经济社交菜单结构](/llmdoc/agent/economy_social_systems_menu_structure_2026_01_23.md)** (2026-01-23)
- **[战斗装备背包UI](/llmdoc/agent/scout_battle_equipment_inventory_ui_2026_01_23.md)** (2026-01-23)
- **[帮助系统调查](/llmdoc/agent/help_system_investigation_2026_01_31.md)** (2026-01-31)
- **[内界设计](/llmdoc/agent/inner_realms_design_2026_02_07.md)** (2026-02-07)
- **[世界Boss调查](/llmdoc/agent/scout_world_boss_system_investigation_2026_02_11.md)** (2026-02-11)
- **[技术架构调查](/llmdoc/agent/tech_architecture_investigation_2026_02_18.md)** (2026-02-18)
- **[阴宅公会仓库调查](/llmdoc/agent/scout_mansion_guild_warehouse_investigation_2026_02_22.md)** (2026-02-22)
- **[战斗日志调查](/llmdoc/agent/battle_log_scout.md)**
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
- **添加新功能**: 参考 [数据访问迁移指南](/llmdoc/guides/data-access-migration-guide.md)
- **添加战斗效果**: 参考 [如何添加战斗效果](/llmdoc/guides/how-to-add-battle-effect.md)
- **修改玩家属性**: 参考 [玩家属性指南](/llmdoc/guides/player-attribute-guide.md)
- **数据库迁移**: 参考 [自动迁移系统](/llmdoc/overview/project-overview.md#64-自动数据库迁移-auto-migrate)

### 常见任务速查

| 任务 | 步骤 |
|------|------|
| 添加新功能 | 创建Model → Repository → 添加到UoW → 创建Service → 更新help.py |
| 数据库迁移 | 在auto_migrate.py的REQUIRED_FIELDS添加字段 → 重启Bot |
| 添加战斗效果 | 参考 [how-to-add-battle-effect](/llmdoc/guides/how-to-add-battle-effect.md) |

---

## 文档分类说明

| 目录 | 用途 | 回答的问题 |
|------|------|-----------|
| `/llmdoc/overview/` | 高层次项目上下文、系统概览 | "这是什么?" |
| `/llmdoc/architecture/` | 核心组件、执行流程、设计原理 | "如何构建?" |
| `/llmdoc/guides/` | 步骤化操作指南、最佳实践 | "如何操作?" |
| `/llmdoc/reference/` | API规范、配置参数、模板 | "具体细节?" |
| `/llmdoc/design/` | 功能设计规格和实现计划 | "为什么这样设计?" |
| `/llmdoc/agent/` | Agent调查报告和分析 | "调查了什么?" |

---

**版本**: 4.0
**最后更新**: 2026-04-01
**最近更新**: 整合docs/到llmdoc/,新增design/分类,修复死链,清理过时内容
