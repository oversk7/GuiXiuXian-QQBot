# 诡修仙项目文档系统

**文档版本**: 3.0
**最后更新**: 2025-11-30
**文档受众**: LLM代理和项目开发者
**文档状态**: 生产就绪，仅保留当前架构文档

---

## 1. 项目概述

诡修仙是一个基于Nonebot2框架的QQ游戏机器人,采用异步SQLAlchemy ORM进行数据管理。项目包含165个Python文件、49个数据模型,实现了修炼、战斗、公会、经济、社交等15+子系统。

**核心技术栈**:
- Nonebot2 (QQ机器人框架)
- SQLAlchemy 2.0+ (异步ORM)
- MySQL/SQLite (双引擎支持)
- Python 3.9+ (异步编程)

---

## 2. 文档结构

本文档系统采用**4层扁平分类**,面向LLM检索优化:

### `/overview/` - 项目概览
回答"这是什么项目?":
- `project-overview.md` - 项目整体介绍
- `architecture-summary.md` - 架构总览

### `/architecture/` - 系统架构 (LLM检索地图)
回答"系统如何工作?":
- `current-architecture.md` - 当前架构详细分析
- `service-di-architecture.md` - Service DI架构实现
- `attribute-system.md` - 属性系统架构
- `battle-effect-bridge.md` - 战斗效果桥接器架构
- `event-system-architecture.md` - 事件系统架构

### `/guides/` - 操作指南
回答"如何执行X任务?":
- `deploy-service-di.md` - 如何部署Service DI
- `how-to-create-battle-effect-bridge.md` - 如何创建战斗效果桥接器
- `feature-flag-control.md` - Feature Flag控制指南
- `how-to-add-effect.md` - 如何添加新效果
- `event-system-guide.md` - 事件系统使用指南
- `performance-optimization-summary.md` - 性能优化最佳实践

### `/reference/` - 参考资料
回答"X的具体定义是什么?":
- `service-api-reference.md` - 27个Service API清单
- `battle-effect-bridge-api.md` - BattleEffectBridge API参考
- `code-issues.md` - 代码问题清单
- `data-models.md` - 数据模型参考

### `/agent/` - 代理调研文档
LLM代理生成的调研和分析:
- `all_services_inventory.md` - 27个Service完整清单
- `ai_npc_system_investigation.md` - AI NPC系统架构设计（未来实现）
- `npc_service_di_and_ai_investigation.md` - NPCService DI重构与AI接口预留
- `doc_cleanup_investigation.md` - 文档清理调研报告

### `/archive/` - 历史文档归档
已归档的历史调研报告和重构文档:
- 详见 `/archive/README.md`

---

## 3. 快速导航

### 了解项目
1. 先读 `/overview/project-overview.md` 了解项目定位
2. 再读 `/overview/architecture-summary.md` 了解技术架构
3. 最后读 `/architecture/current-architecture.md` 深入理解实现

### 功能开发
1. 查看 `/reference/data-models.md` 了解数据结构
2. 参考 `/guides/how-to-add-effect.md` 添加新效果
3. 使用 `/guides/performance-optimization-summary.md` 优化查询
4. 检查 `/reference/code-issues.md` 避免已知问题

### 系统扩展
1. 阅读 `/architecture/service-di-architecture.md` 了解Service DI模式
2. 查看 `/architecture/event-system-architecture.md` 使用事件系统
3. 参考 `/guides/event-system-guide.md` 发布和订阅事件

---

## 4. 核心概念速查

| 概念 | 定义 | 参考文档 |
|------|------|----------|
| **属性计算** | 玩家最终属性=基础+装备+丹药+VIP+临时buff | `/architecture/attribute-system.md` |
| **效果系统** | IEffect统一接口、ItemEffectAdapter、BattleEffectBridge | `/architecture/battle-effect-bridge.md` |
| **事件系统** | EventBus、领域事件、发布/订阅模式 | `/architecture/event-system-architecture.md` |
| **会话管理** | safe_session(自动提交)、UnitOfWork(事务管理) | `/architecture/service-di-architecture.md` |
| **Service DI** | 依赖注入、Repository模式、UnitOfWork | `/architecture/service-di-architecture.md` |
| **N+1查询** | 循环中逐个查询关联对象的性能问题 | `/reference/code-issues.md` |

---

## 5. 关键文件索引

### 核心入口
- `D:\QQbot\GuiXiuXian2\bot.py` - Nonebot2主程序入口
- `plugins\xiuxian_game\__init__.py` - 游戏插件注册
- `plugins\xiuxian_game\models\db.py` - 数据库连接管理

### 核心模型
- `plugins\xiuxian_game\models\player.py` - Player模型(87字段)
- `plugins\xiuxian_game\models\inventory.py` - 物品系统
- `plugins\xiuxian_game\models\guild.py` - 公会系统

### 核心系统
- `plugins\xiuxian_game\battle\enhanced_engine.py` - 战斗引擎
- `plugins\xiuxian_game\item\item_effects.py` - 物品效果(45+种)
- `plugins\xiuxian_game\battle\battle_effects.py` - 战斗效果(75+种)
- `plugins\xiuxian_game\domain\events\event_bus.py` - 事件总线
- `plugins\xiuxian_game\infrastructure\di\container.py` - DI容器

---

## 6. 当前项目架构状态

### ✅ 已实现核心系统 (100%)

**Service DI 架构**:
- 27/27 Services已完成DI改造
- 47个Repository实现
- UnitOfWork事务管理
- Feature Flag全部启用

**属性计算系统**:
- AttributeCalculator统一入口
- BuffAttributeSource (60秒TTL缓存)
- EquipmentAttributeSource
- 已替代5处散落的属性计算

**效果系统**:
- IEffect统一接口
- EffectRegistry注册表
- ItemEffectAdapter适配器
- BattleEffectBridge桥接器

**事件系统**:
- EventBus事件总线
- 领域事件定义
- 发布/订阅机制
- Service层集成

---

## 7. 文档使用指南

### 面向LLM代理
1. **优先读取 `/llmdoc/index.md`** (本文档) 建立全局认知
2. **根据任务类型选择对应分类**:
   - 理解项目 → `/overview/`
   - 了解实现 → `/architecture/`
   - 执行任务 → `/guides/`
   - 查阅细节 → `/reference/`
3. **使用文件路径引用代码**: 格式 `path/to/file.ext:line-range`
4. **避免复制大段代码**: 优先引用文件位置

### 面向人类开发者
1. 从 `/overview/project-overview.md` 开始了解项目
2. 根据开发任务查阅对应的指南文档
3. 遇到问题时查看 `/reference/code-issues.md`
4. 添加新功能时参考 `/guides/` 下的how-to文档

---

## 8. 文档维护

- **更新频率**: 重大代码变更后更新
- **维护者**: 使用recorder代理维护
- **版本控制**: 使用Git跟踪文档变更
- **质量要求**: 所有文档<150行,基于代码证据,包含文件路径引用

---

## 9. 文档清理说明 (2025-11-30)

**清理目标**: 删除重构过程文档，只保留当前项目架构

**已删除文档** (6个):
1. `SERVICE_REFACTORING_PROGRESS.md` - 重构进度跟踪
2. `/overview/refactoring-strategy.md` - 重构策略
3. `/overview/service-di-completion.md` - DI完成里程碑
4. `/guides/refactoring-roadmap.md` - 重构路线图
5. `/agent/refactoring_plan_v4_completion_investigation.md` - 完成度调研
6. `/agent/performance_bottleneck_investigation.md` - 性能瓶颈调研

**保留文档**:
- 所有 `/architecture/` 架构文档 (5个)
- 所有 `/guides/` 操作指南 (6个)
- 所有 `/reference/` 参考资料 (4个)
- 所有 `/overview/` 项目概览 (2个)
- 所有 `/agent/` 未来设计调研 (3个)
- 所有 `/archive/` 历史归档 (11个)

**清理原则**:
- ✅ 保留描述当前架构如何工作的文档
- ✅ 保留操作指南和API参考
- ✅ 保留历史归档（追踪决策变化）
- ❌ 删除重构过程、进度跟踪等临时性文档

---

**下一步**: 阅读 `/overview/project-overview.md` 了解项目全貌
