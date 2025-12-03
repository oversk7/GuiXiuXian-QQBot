# 诡修仙项目文档系统

**文档版本**: 3.3
**最后更新**: 2025-12-03
**文档受众**: LLM代理和项目开发者
**文档状态**: 生产就绪，已清理临时bug修复文档

---

## 1. 项目概述

诡修仙是一个基于Nonebot2框架的QQ游戏机器人,采用异步SQLAlchemy ORM进行数据管理。项目包含约142个核心Python文件、49个数据模型,实现了修炼、战斗、公会、经济、社交等15+子系统。

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
- `service-di-architecture.md` - Service DI架构实现（Feature Flag移除前）
- `service-di-final-implementation.md` - Service DI最终实现（Feature Flag已全部移除）
- `attribute-system.md` - 属性系统架构
- `battle-effect-bridge.md` - 战斗效果桥接器架构
- `event-system-architecture.md` - 事件系统架构
- `dialogue-npc-system.md` - 对话NPC系统架构（自然对话+游戏指令+好感度）
- `account-switching-system.md` - 账号切换系统架构（多账号管理+转让+管理员临时切换）

### `/guides/` - 操作指南
回答"如何执行X任务?":
- `deploy-service-di.md` - 如何部署Service DI
- `how-to-create-battle-effect-bridge.md` - 如何创建战斗效果桥接器
- `how-to-add-effect.md` - 如何添加新效果
- `event-system-guide.md` - 事件系统使用指南
- `performance-optimization-summary.md` - 性能优化最佳实践
- `how-to-implement-dialogue-npc.md` - 如何实施对话NPC系统

**已归档** (Feature Flag已移除):
- `feature-flag-control.md` - 已过时（Feature Flag已全部删除，详见2025-12-02代码清理记录）

### `/reference/` - 参考资料
回答"X的具体定义是什么?":
- `service-api-reference.md` - 27个Service API清单
- `battle-effect-bridge-api.md` - BattleEffectBridge API参考
- `code-issues.md` - 代码问题清单
- `data-models.md` - 数据模型参考
- `dialogue-npc-api.md` - 对话NPC系统API参考
- `account-switching-api.md` - 账号切换系统API参考
- `code-cleanup-2025-12-02.md` - 代码清理记录（Feature Flag删除、旧Service移除）

### `/agent/` - 代理调研文档
LLM代理生成的调研和分析报告（仅保留系统分析和设计参考文档）:

**系统平衡与设计分析**:
- `game_balance_analysis_2025_12_01.md` - 游戏平衡分析与漏洞修复报告 (2025-12-01)
- `feature_flag_investigation_2025_12_02.md` - Feature Flag调查与架构决策记录
- `doc_cleanup_investigation.md` - 文档清理调研报告（元文档）

**投资系统调研**:
- `investment_system_investigation.md` - 投资系统初步调查报告（银行+股票）
- `stock_system_files_investigation.md` - 投资系统文件清单调查

**未来功能设计**:
- `ai_npc_implementation_investigation.md` - AI NPC系统架构设计
- `agent_npc_autonomous_behavior_investigation.md` - Agent NPC自主行为调查

**系统调研参考**:
- `player_panel_investigation_2025_12_01.md` - 玩家面板系统调查
- `cultivation_and_quest_investigation.md` - 修炼与任务系统调查
- `code_logic_comparison_investigation.md` - 代码逻辑对比分析

**清理说明**: 已删除11个临时性bug修复调查文档（装备bug、连接泄漏、ENUM修复等），这些问题均已解决且无长期参考价值。

### `/design/` - 系统设计方案
游戏设计和系统重构方案:
- `game_system_redesign_2025_12_02.md` - 新手体验破局完整方案 (2025-12-02)
- `EXECUTIVE_SUMMARY.md` - 执行摘要 (快速查阅版)

**投资系统反套利实施** (2025-12-02):
- `investment_anti_arbitrage_redesign.md` - 反套利设计方案（最终方案，191行）
- `investment_implementation_summary.md` - 实施总结（代码修改清单+部署指南，325行）
- `investment_system_redesign_2025_12_02.md` - 初版设计方案（已被反套利方案取代）

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

### 游戏平衡优化
1. 查看 `/agent/game_balance_analysis_2025_12_01.md` 了解已识别的平衡问题
2. 参考 `/design/investment_anti_arbitrage_redesign.md` 学习反套利机制设计
3. 阅读 `/design/investment_implementation_summary.md` 查看实施细节和部署步骤

---

## 4. 核心概念速查

| 概念 | 定义 | 参考文档 |
|------|------|----------|
| **属性计算** | 玩家最终属性=基础+装备+丹药+VIP+临时buff | `/architecture/attribute-system.md` |
| **效果系统** | IEffect统一接口、ItemEffectAdapter、BattleEffectBridge | `/architecture/battle-effect-bridge.md` |
| **事件系统** | EventBus、领域事件、发布/订阅模式 | `/architecture/event-system-architecture.md` |
| **会话管理** | safe_session(自动提交)、UnitOfWork(事务管理) | `/architecture/service-di-architecture.md` |
| **Service DI** | 依赖注入、Repository模式、UnitOfWork | `/architecture/service-di-architecture.md` |
| **账号切换** | 一个真实玩家拥有多个游戏账号，支持转让和管理员临时切换 | `/architecture/account-switching-system.md` |
| **N+1查询** | 循环中逐个查询关联对象的性能问题 | `/reference/code-issues.md` |
| **股票健康度** | 价格下跌损耗健康度，归零退市，防止套利 | `/design/investment_anti_arbitrage_redesign.md` |
| **持仓成本** | 每日0.1%管理费，防止无限持有 | `/design/investment_implementation_summary.md` |

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
- `plugins\xiuxian_game\models\account_ownership.py` - 账号所有权模型(多账号管理)

### 核心系统
- `plugins\xiuxian_game\battle\enhanced_engine.py` - 战斗引擎
- `plugins\xiuxian_game\item\item_effects.py` - 物品效果(45+种)
- `plugins\xiuxian_game\battle\battle_effects.py` - 战斗效果(75+种)
- `plugins\xiuxian_game\domain\events\event_bus.py` - 事件总线
- `plugins\xiuxian_game\infrastructure\di\container.py` - DI容器
- `plugins\xiuxian_game\social\account_switching_service.py` - 账号切换服务
- `plugins\xiuxian_game\platform_utils.py` - 统一玩家访问接口(支持账号切换)

### 经济系统（投资）
- `plugins\xiuxian_game\economy\stock_price_engine.py` - 股票价格引擎（反套利+健康度更新）
- `plugins\xiuxian_game\economy\stock_service_new.py` - 股票交易服务（0.5%手续费+退市+持仓成本）
- `plugins\xiuxian_game\economy\stock_scheduler.py` - 股票定时任务（每日管理费+黑天鹅事件）
- `plugins\xiuxian_game\models\stock.py` - Stock/StockHolding/StockEvent模型

---

## 6. 当前项目架构状态

### ✅ 已实现核心系统 (100%)

**Service DI 架构**:
- 27/27 Services已完成DI改造
- 47个Repository实现
- UnitOfWork事务管理
- Feature Flag已全部移除（新架构成为唯一实现）

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

## 7. 游戏平衡状态 (2025-12-01)

### ⚠️ 识别的平衡问题

**数据样本**: 1,736个玩家数据
**分析日期**: 2025-12-01
**详细报告**: `/agent/game_balance_analysis_2025_12_01.md`

#### 核心问题汇总

| 问题类型 | 严重程度 | 关键指标 | 影响范围 |
|---------|---------|---------|---------|
| 新手留存危机 | 🔴 高 | 77%玩家卡在0-10级 | 游戏成长曲线 |
| 经济通货膨胀 | 🔴 高 | 最高金币34.4亿 | 经济系统 |
| 装备属性膨胀 | 🔴 高 | 装备加成高达60% | 战斗平衡 |
| 扫荡令失衡 | 🟠 中 | 效率是正常修炼75-300倍 | 玩法多样性 |
| 药品刷经验漏洞 | 🔴 高 | 效率是正常修炼8.25倍 | 经验获取 |

#### 药品刷经验漏洞详情

**漏洞机制**:
- 回春散/凝神草仅售100金币 (`data/items.yaml:9,17`)
- 单次恢复40 HP/MP，无使用冷却和限制
- 副本每格仅消耗1 MP，玩家可无限续航
- 经验获取效率达到正常修炼的8.25倍

**涉及代码**:
- `plugins/xiuxian_game/item/item_effects.py` - 缺少冷却与限制
- `plugins/xiuxian_game/world/dungeon_battle.py` - MP消耗过低
- `plugins/xiuxian_game/data/items.yaml` - 药品价格过低

**修复优先级**:
- P0紧急修复：物品冷却10秒、药品价格提高5倍、每日使用上限50次
- P1重要修复：副本MP消耗提高至3-5、丹药每日上限、扫荡令递减收益
- P2长期优化：装备加成上限、首次探索奖励、重复格子递减

#### 已修复问题

**✅ 装备卸载属性清零Bug** (2025-12-01):
- **问题**: "一键卸下"后玩家属性清零
- **修复**: 添加`_persist_bonus`清理 + `recalc_equipment_attributes()`调用
- **位置**: `plugins/xiuxian_game/item/equipment_commands.py:669-692`
- **详情**: `/reference/code-issues.md#6-已修复问题`

**✅ 账号转让功能改进** (2025-12-01):
- **改进1 - 管理员权限增强**: 管理员可为任意账号生成转让密钥
  - **修复**: `AccountSwitchingService.generate_transfer_key()` 添加 `is_admin` 参数
  - **位置**: `plugins/xiuxian_game/social/account_switching_service.py:180-212`
- **改进2 - 新增管理员临时切换**: 管理员可临时切换到任意账号调试，不改变所有权
  - **核心逻辑**: 内存字典 `_admin_temp_switch` 存储临时切换状态
  - **优先级**: 临时切换 > 账号切换 > 默认账号
  - **位置**: `plugins/xiuxian_game/platform_utils.py:12-154` (核心逻辑)
  - **命令**: `plugins/xiuxian_game/social/account_switching.py:357-467` (3个新命令)
  - **详情**: `/architecture/account-switching-system.md`

**✅ 投资系统反套利机制实施** (2025-12-02):
- **问题**: 股票投资存在无风险套利漏洞（长期持有+正向趋势=稳赚不赔）
- **核心修复**:
  - **股票健康度系统**: 价格下跌损耗健康度（跌1%=-1点），归零退市
  - **持仓成本系统**: 每日0.1%管理费，防止无限持有
  - **无套利价格模型**: 移除正向趋势，期望收益=0
  - **黑天鹅事件框架**: 随机市场崩溃机制（框架就绪）
- **修改文件**: 8个核心文件（模型+引擎+Service+UI+调度器+Repository）
  - `plugins/xiuxian_game/models/stock.py` - 新增5个健康度字段+StockEvent模型
  - `plugins/xiuxian_game/economy/stock_price_engine.py` - 移除正向趋势+健康度更新
  - `plugins/xiuxian_game/economy/stock_service_new.py` - 手续费3%→0.5%+退市+持仓成本
  - `plugins/xiuxian_game/economy/stock_commands.py` - UI显示健康度emoji（🟢🟡🔴）
  - `plugins/xiuxian_game/economy/stock_scheduler.py` - 每日管理费+每周黑天鹅检查
  - `plugins/xiuxian_game/alembic/versions/add_stock_health_and_events.py` - 数据库迁移
- **设计文档**: `/design/investment_anti_arbitrage_redesign.md`
- **实施总结**: `/design/investment_implementation_summary.md`

---

## 8. 文档使用指南

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

## 9. 文档维护

- **更新频率**: 重大代码变更后更新
- **维护者**: 使用recorder代理维护
- **版本控制**: 使用Git跟踪文档变更
- **质量要求**: 所有文档<150行,基于代码证据,包含文件路径引用

---

## 10. 代码清理说明

### 文档清理 (2025-11-30)

**清理目标**: 删除重构过程文档，只保留当前项目架构

**已删除文档** (6个):
1. `SERVICE_REFACTORING_PROGRESS.md` - 重构进度跟踪
2. `/overview/refactoring-strategy.md` - 重构策略
3. `/overview/service-di-completion.md` - DI完成里程碑
4. `/guides/refactoring-roadmap.md` - 重构路线图
5. `/agent/refactoring_plan_v4_completion_investigation.md` - 完成度调研
6. `/agent/performance_bottleneck_investigation.md` - 性能瓶颈调研

### 代码清理 (2025-12-02)

**清理目标**: 删除Feature Flag定义、旧Service文件和相关条件分支

**详细说明**: `/llmdoc/reference/code-cleanup-2025-12-02.md`

**清理成果**:
- 删除23个旧Service文件（5,681行代码）
- 删除31个Feature Flag定义（100%清除）
- 修改56个命令处理文件（移除if/else分支）
- 总计删除7,690行代码
- Python文件从297减少到274（-8%）

### 文档清理 (2025-12-03)

**清理目标**: 删除临时性bug修复调查文档，精简`/agent/`目录

**清理成果**:
- 删除11个临时bug修复调查文档：
  - 装备相关bug (4个): equipment_unequip_attribute_bug, equipment_bonus_display_bug, equipment_durability_auto_unequip, sweep_token_equipment_bug
  - 连接泄漏调查 (3个): connection_leak_investigation, connection_leak_full_scan, connection_leak_updated_investigation
  - 其他已修复问题 (4个): npc_url_error, guild_approve_db_not_update, daily_task_di_migration, auto_migrate_enum_fix
- `/agent/`目录从21个文档精简到10个（-52%）
- 保留10个有长期参考价值的系统分析和设计文档

**保留文档**:
- 所有 `/architecture/` 架构文档 (8个)
- 所有 `/guides/` 操作指南 (6个)
- 所有 `/reference/` 参考资料 (6个)
- 所有 `/overview/` 项目概览 (2个)
- 所有 `/design/` 设计方案 (5个)
- `/agent/` 系统分析和设计参考 (10个)
- 所有 `/archive/` 历史归档 (11个)

**清理原则**:
- ✅ 保留描述当前架构如何工作的文档
- ✅ 保留系统分析、平衡性调研、未来设计等长期参考文档
- ✅ 保留操作指南和API参考
- ✅ 保留历史归档（追踪决策变化）
- ❌ 删除一次性bug修复调查（问题已解决，无复现风险）
- ❌ 删除重构过程、进度跟踪等临时性文档

---

**下一步**: 阅读 `/overview/project-overview.md` 了解项目全貌
