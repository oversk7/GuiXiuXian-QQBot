# 诡修仙项目文档系统

**文档版本**: 2.2
**最后更新**: 2025-11-29
**文档受众**: LLM代理和项目开发者
**文档状态**: 已清理冗余单模块文档，保留核心架构和未完成模块调研

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
- `refactoring-strategy.md` - 重构策略概览

### `/architecture/` - 系统架构 (LLM检索地图)
回答"系统如何工作?":
- `current-architecture.md` - 当前架构详细分析
- `attribute-system.md` - 属性系统架构
- `battle-effect-bridge.md` - 战斗效果桥接器架构

### `/guides/` - 操作指南
回答"如何执行X任务?":
- `refactoring-roadmap.md` - 重构实施路线图
- `how-to-create-battle-effect-bridge.md` - 如何创建战斗效果桥接器
- `feature-flag-control.md` - Feature Flag控制指南
- `how-to-add-effect.md` - 如何添加新效果

### `/reference/` - 参考资料
回答"X的具体定义是什么?":
- `battle-effect-bridge-api.md` - BattleEffectBridge API参考
- `code-issues.md` - 代码问题清单
- `data-models.md` - 数据模型参考

### `/agent/` - 代理调研文档
LLM代理生成的调研和分析（仅保留未完成模块的调研）：
- `all_services_inventory.md` - 27个Service完整清单
- `ai_npc_system_investigation.md` - AI NPC系统架构设计（未来实现）
- `npc_service_di_and_ai_investigation.md` - NPCService DI重构与AI接口预留

---

## 3. 快速导航

### 了解项目
1. 先读 `/overview/project-overview.md` 了解项目定位
2. 再读 `/overview/architecture-summary.md` 了解技术架构
3. 最后读 `/architecture/current-architecture.md` 深入理解实现

### 重构开发
1. 阅读 `/overview/refactoring-strategy.md` 了解重构背景
2. 查看 `/guides/refactoring-roadmap.md` 获取实施步骤
3. 参考 `/architecture/target-architecture.md` 理解目标设计
4. 查阅 `/reference/design-patterns.md` 应用设计模式

### 功能开发
1. 查看 `/reference/data-models.md` 了解数据结构
2. 参考 `/guides/how-to-add-effect.md` 添加新效果
3. 使用 `/guides/how-to-optimize-query.md` 优化查询
4. 检查 `/reference/code-issues.md` 避免已知问题

---

## 4. 核心概念速查

| 概念 | 定义 | 参考文档 |
|------|------|----------|
| **属性计算** | 玩家最终属性=基础+装备+丹药+VIP+临时buff | `/architecture/attribute-system.md` |
| **效果系统** | IEffect统一接口、ItemEffectAdapter、BattleEffectBridge | `/architecture/battle-effect-bridge.md` |
| **桥接模式** | 包装TriggerConfig为IEffect接口，保留BattleEffectManager | `/architecture/battle-effect-bridge.md` |
| **会话管理** | safe_session(自动提交)、get_session(手动)、retry_session(重试) | `/architecture/data-access-layer.md` |
| **Service模式** | 26个静态方法Service类,外部注入session | `/architecture/current-architecture.md` |
| **N+1查询** | 循环中逐个查询关联对象的性能问题 | `/reference/code-issues.md` |
| **多会话问题** | 单命令打开多个独立会话破坏事务原子性 | `/reference/code-issues.md` |

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

---

## 6. 核心重构文档

**主规划文档**:
- `REFACTORING_PLAN_v4.md` - v4.0重构规划（五阶段路线图）
- `REFACTORING_PROGRESS.md` - 重构进度跟踪（63%完成）
- `ATTRIBUTE_CALCULATOR_REFACTORING.md` - 属性计算器重构总结

**代理调研文档** (`/agent/`):
- `all_services_inventory.md` - 27个Service完整清单（P0/P1/P2优先级）
- `ai_npc_system_investigation.md` - AI NPC系统架构设计（未来实现）
- `npc_service_di_and_ai_investigation.md` - NPCService DI重构与AI接口预留

**归档文档** (`/archive/`):
- 原始调研报告已整合到核心文档，移至archive目录
- 详见 `/archive/README.md`

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
4. 重构时参考 `/guides/refactoring-roadmap.md`

---

## 8. 文档维护

- **更新频率**: 重大代码变更后更新
- **维护者**: 使用recorder代理维护
- **版本控制**: 使用Git跟踪文档变更
- **质量要求**: 所有文档<150行,基于代码证据,包含文件路径引用

---

---

## 9. 最新更新 (2025-11-29)

### 文档系统清理完成 ✅

**删除冗余文档** (19个):

**llmdoc目录** (12个):
- ❌ `/overview/guild_di_refactoring.md` - 信息已整合到SERVICE_REFACTORING_PROGRESS.md
- ❌ `/architecture/guild_di_architecture.md` - 信息已整合到SERVICE_REFACTORING_PROGRESS.md
- ❌ `/reference/guild_services_api.md` - 信息已整合到SERVICE_REFACTORING_PROGRESS.md
- ❌ `/guides/guild_di_integration.md` - 信息已整合到SERVICE_REFACTORING_PROGRESS.md
- ❌ `/agent/stock_service_refactoring_analysis.md` - StockService已完成重构
- ❌ `/agent/equipment_service_refactoring_analysis.md` - EquipmentService已完成重构
- ❌ `/agent/equipment_upgrade_service_refactoring_analysis.md` - EquipmentUpgradeService已完成重构
- ❌ `/agent/item_effects_refactoring_analysis.md` - ItemEffects已完成重构
- ❌ `/agent/alchemy_service_refactoring_analysis.md` - AlchemyService已完成重构
- ❌ `/agent/item_module_services_investigation.md` - Item模块已完成重构
- ❌ `/agent/world_boss_module_services_investigation.md` - WorldBoss模块已完成重构
- ❌ `/agent/daily_task_and_ai_agent_npc_investigation.md` - 冗余，已被更详细的npc_service调研替代

**项目根目录** (7个):
- ❌ `monitor_refactoring.md` - 早期验证指南（Stock和PartTimeJob）
- ❌ `world_boss_chest_service_verification_report.md` - WorldBossChestService验证报告
- ❌ `world_boss_service_di_refactoring.md` - WorldBossService重构文档
- ❌ `world_boss_service_code_comparison.md` - 代码对比文档
- ❌ `world_boss_service_integration_guide.md` - 集成指南
- ❌ `WORLD_BOSS_REFACTORING_REPORT.md` - 重构完成报告
- ❌ `WORLD_BOSS_QUICK_REFERENCE.md` - 快速参考

**保留文档** (33个):
- llmdoc核心架构文档：13个（overview + architecture + guides + reference）
- llmdoc归档文档：11个（历史调研报告）
- llmdoc agent调研文档：3个（全局清单 + AI NPC设计 + NPC服务调研）
- llmdoc根目录规划文档：4个（index.md + REFACTORING_PLAN_v4.md + REFACTORING_PROGRESS.md + ATTRIBUTE_CALCULATOR_REFACTORING.md）
- 项目根目录：2个（SERVICE_REFACTORING_PROGRESS.md + DOC_CLEANUP_SUMMARY.md）

**清理原则**:
- ✅ 删除已完成模块的单模块重构文档（信息已整合到SERVICE_REFACTORING_PROGRESS.md）
- ✅ 删除已完成模块的agent调研报告（重构已完成，调研已过时）
- ✅ 保留未完成模块的agent调研报告（AI NPC系统设计）
- ✅ 保留全局性文档（all_services_inventory.md）
- ✅ 保留核心架构和操作指南文档

### NPCService DI重构完成 ✅

**重构完成度**: NPC模块100% (1/1 Service)
- ✅ NPCService (314→610行) - 含AI Agent接口预留
- ✅ NPCRepository (325行) - 含2个AI预留方法
- ✅ Feature Flag集成 (npc_interaction.py, 2个调用点)

**AI接口预留** (7个方法):
- Service层：is_ai_enabled(), get_ai_personality(), get_ai_model(), get_ai_forbidden_topics(), enable_ai_for_npc()
- Repository层：get_with_ai_config(), get_ai_enabled_by_location()

**未来AI扩展路径**:
- NPCCharacter模型 - NPC角色与性格设定
- AIDialogue模型 - AI NPC对话历史
- ConversationContext模型 - 对话上下文（1小时TTL）
- ReactiveDecisionEngine - 被动响应式AI决策引擎
- PlayerObserver - 玩家状态观察器

---

**下一步**: 阅读 `/overview/project-overview.md` 了解项目全貌
