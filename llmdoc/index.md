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
- **[数据访问层](/llmdoc/overview/data-access-overview.md)** - Repository模式、Unit of Work、自动迁移

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

- **[NoneBot 指令分发优化](/llmdoc/architecture/command-dispatch-optimization.md)** - 指令提前筛选、Map 候选索引、性能证据、兼容边界及面试说明

### 数据访问层
- **[Repository模式实现](/llmdoc/architecture/repository-pattern-implementation.md)** - 63个Repository,泛型接口,领域查询
- **[Unit of Work与数据访问模式](/llmdoc/architecture/unit-of-work-and-di.md)** - 事务边界管理、safe_session与UoW的使用约定

### 设计模式
- **Repository模式** - 数据访问抽象,可测试性,查询集中化
- **Unit of Work模式** - 事务原子性,会话共享,连接泄漏防护
- **策略模式** - 属性来源系统(IAttributeSource)

---

## 使用指南

- **[自动化测试与 MySQL、Redis 回归](/llmdoc/guides/testing-guide.md)** - Docker 测试环境、服务隔离、必跑模式与 CI 报告
- **[Redis 地图缓存与共享限流](/llmdoc/guides/redis-guide.md)** - 配置、快照过期、Lua 滑动窗口与故障回退
- **[全游戏百科维护指南](/llmdoc/guides/codex-guide.md)** - 统一图鉴、资料提供器、来源用途与数据准确性约定
- **[玩家属性指南](/llmdoc/guides/player-attribute-guide.md)** - 获取有效属性、添加属性来源、修改玩家属性
- **[装备等级与品质配置](/llmdoc/guides/equipment-quality-stage-guide.md)** - 同阶段品质梯度、独立掉落池与存量装备保护
- **[VIP装备设计模板](/llmdoc/guides/vip-equipment-design-templates.md)** - VIP定制装备设计方案集，带专属主动技能
- **[攻略合集](/llmdoc/guides/攻略合集.md)** - 跑商、战斗、经济等玩家攻略(面向玩家)

---

## 参考手册

- **[经济系统参考](/llmdoc/reference/economy-system-reference.md)** - 配置参数、计算公式、常量定义
- **[编码规范](/llmdoc/reference/coding-conventions.md)** - Python代码风格、命名约定
- **[Git规范](/llmdoc/reference/git-conventions.md)** - Git提交规范
- **[QQ原生Markdown](/llmdoc/reference/native-markdown.md)** - 原生Markdown语法、utils_markdown用法与排版惯例
- **[QQ单聊主动私信](/llmdoc/reference/qq-proactive-dm.md)** - 平台近期开放的主动消息能力：规则、频控、adapter-qq调用方式(2026-07-24调研)

---

## 设计文档

功能设计规格，由 brainstorming 会话产出。

### 设计规格 (specs)
- **[焕活方案·天灾远征与诡契体系](/llmdoc/design/specs/2026-07-19-expedition-contract-revitalization-design.md)** (2026-07-19) - 数值宪法、任务引擎、下界副本群、诡契系统、香火经济；含待拍板项清单
- **[装备档位重构设计](/llmdoc/design/specs/2026-07-14-equipment-tier-rework-design.md)** (2026-07-14)
- **[血祭开坛设计](/llmdoc/design/specs/2026-07-13-blood-altar-design.md)** (2026-07-13)
- **[公会镇诡Boss设计](/llmdoc/design/specs/2026-07-08-guild-boss-design.md)** (2026-07-08)
- **[网页引流小游戏设计](/llmdoc/design/specs/2026-04-17-web-demo-funnel-game-design.md)** (2026-04-17)
- ~~[网页版P0账号绑定设计](/llmdoc/design/specs/2026-04-17-web-p0-account-binding-design.md)~~ (2026-04-17，已废弃：产品方向改为独立引流小游戏)
- **[斗法天梯PvP设计](/llmdoc/design/specs/2026-04-10-dharma-ladder-pvp-design.md)** (2026-04-10，已上线)
- **[世界地图扩展设计](/llmdoc/design/specs/2026-04-04-world-map-expansion-design.md)** (2026-04-04，已上线)
- **[餐厅经济平衡重设计](/llmdoc/design/specs/2026-03-27-restaurant-economy-balance-design.md)** (2026-03-27)
- ~~[荔湾鬼城内界设计](/llmdoc/design/specs/2026-03-24-liwan-ghost-town-inner-realm-design.md)~~ (2026-03-24，已废弃：里界系统 2026-07-02 整体删除)
- **[导航随机事件设计](/llmdoc/design/specs/2026-03-20-navigation-random-events-design.md)** (2026-03-20)
- **[新手任务扩展设计](/llmdoc/design/specs/2026-03-20-novice-quest-expansion-design.md)** (2026-03-20)
- **[铭文掉落Phase3设计](/llmdoc/design/specs/2026-03-19-inscription-drop-phase3-design.md)** (2026-03-19)
- **[装备词缀铭文设计](/llmdoc/design/specs/2026-03-18-equipment-affix-inscription-design.md)** (2026-03-18)
- **[奋进系统设计](/llmdoc/design/specs/2026-03-15-fenjin-design.md)** (2026-03-15)
- **[龙斩鞋设计](/llmdoc/design/specs/2026-03-13-dragon-blade-shoes-design.md)** (2026-03-13)
- **[战斗UI Markdown设计](/llmdoc/design/specs/2026-03-13-battle-ui-markdown-design.md)** (2026-03-13)

---

## 调查报告

仍有参考价值的系统分析报告。

- **[玩家等级分布审计](/llmdoc/agent/player_level_distribution_audit_2026_07_21.md)** (2026-07-21) - 生产库全量 3,939 个角色的等级与转生分布；标出前 40 级漏斗及后续活跃分层口径
- **[玩家实力组成审计](/llmdoc/agent/power_composition_audit_2026_07_03.md)** (2026-07-03) - 五条生效通道全景、现症数值bug清单、重复实现清单、优化方向

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
| 添加新功能 | 创建Model → Repository → 添加到UoW → 创建Service → 更新 data/knowledge/*.yaml 帮助 |
| 数据库迁移 | 在auto_migrate.py的REQUIRED_FIELDS添加字段 → 重启Bot |
| 添加战斗效果 | 参考 [how-to-add-battle-effect](/llmdoc/guides/how-to-add-battle-effect.md) |

---

**版本**: 5.4
**最后更新**: 2026-07-24
**最近更新**: 新增《QQ单聊主动私信》参考——平台近期开放单聊主动消息，记录频控规则与 adapter-qq 调用方式；上一版：新增生产库玩家等级分布审计（3,939 个角色）；清理过时文档——删除 4 份失效侦查报告（技术架构 02-18 描述的 DI/Alembic 已移除、阴宅 02-22、NPC 03-04 行号失效、下界 03-15 数据过时）与 3 份已完结实现计划（天梯/世界地图已上线、摆摊已下线），plans 目录清空；里界/网页P0 两份规格标记废弃；specs 列表补齐缺失条目并改为倒序
