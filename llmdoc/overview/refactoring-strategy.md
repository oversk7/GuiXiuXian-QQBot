# 重构策略概览

## 1. Identity

- **What it is**: 诡修仙项目v4.0重构策略的执行摘要
- **Purpose**: 快速了解重构背景、目标、策略和预期收益

## 2. 重构背景

### 调研依据

基于四轮scout代理调研,量化分析当前代码库:
- `architecture_investigation.md` - 165个Python文件,49个数据模型
- `attribute_system_investigation.md` - 5处属性计算位置
- `effect_system_investigation.md` - 45+物品效果,75+战斗效果
- `data_access_investigation.md` - 542处会话操作,26个Service类

### 核心问题量化

| 问题 | 当前状态 | 严重程度 |
|------|---------|---------|
| 属性计算分散 | 5处位置,逻辑不一致 | 🔴 高 |
| 循环依赖 | item_effects.py:13 ↔ equipment_commands.py:96 | 🔴 高 |
| 无依赖注入 | 26个Service类静态方法,硬编码依赖 | 🔴 高 |
| 多会话问题 | player/info.py打开4个独立会话 | 🔴 高 |
| N+1查询 | bank.py逐个查询Player对象 | 🟠 中 |
| 效果系统重复 | 装饰器注册 vs 管理器模式 | 🟡 低 |
| 配置不一致 | database.yaml vs alembic/env.py | 🟠 中 |

详细问题分析参见 `/reference/code-issues.md`

## 3. 重构目标

### 四大核心目标

**松耦合**:
- 通过依赖注入和仓储模式解耦模块
- 消除循环依赖和硬编码依赖
- Service类从静态方法改为实例方法

**易扩展**:
- 使用策略/工厂/责任链模式支持功能扩展
- 统一效果系统接口(IEffect)
- 属性来源组合模式(IAttributeSource)

**可测试**:
- 分离核心逻辑与框架依赖
- Service依赖注入支持Mock
- 单一职责原则提升单元测试覆盖率

**可维护**:
- 清晰的分层架构(表现/应用/领域/基础设施)
- 统一的数据访问层(Repository + UoW)
- 单一属性计算入口

## 4. 核心设计模式

### 依赖注入容器 (DI Container)

**解决问题**: 26个Service类硬编码依赖

**关键代码位置**: `infrastructure/di/container.py` (待创建)

**设计要点**:
- 支持singleton/scoped/transient三种生命周期
- Service类从静态方法改为实例方法
- 通过容器解析依赖注入

### 仓储+工作单元 (Repository + UoW)

**解决问题**: 多会话破坏事务原子性,无数据访问抽象

**关键代码位置**:
- `domain/repositories/base.py` - IRepository接口 (待创建)
- `infrastructure/uow/unit_of_work.py` - UnitOfWork实现 (待创建)

**设计要点**:
- Repository管理查询,支持预加载优化
- UoW管理事务边界,统一会话
- 单个Use Case使用单个UoW

### 策略模式统一效果 (Strategy Pattern)

**解决问题**: 装备效果和战斗效果设计不一致

**关键代码位置**:
- `domain/effects/effect_interface.py` - IEffect接口 (待创建)
- `domain/effects/effect_registry.py` - EffectRegistry注册表 (待创建)
- `domain/effects/adapters/` - 适配器层 (待创建)

**设计要点**:
- 统一IEffect接口(can_trigger, execute)
- EffectRegistry管理所有效果
- 适配器模式迁移现有效果

### 属性计算器统一 (Composite Pattern)

**解决问题**: 属性计算分散在5处,逻辑不一致

**关键代码位置**:
- `domain/attributes/attribute_calculator.py` - AttributeCalculator (待创建)
- `domain/attributes/attribute_sources/` - IAttributeSource实现 (待创建)

**设计要点**:
- 单一AttributeCalculator入口
- IAttributeSource组合模式(装备、buff、丹药、VIP)
- 保留_persist_bonus机制(优秀设计)
- 增加临时buff缓存(60秒TTL)

## 5. 实施策略

### 五阶段渐进式重构

**阶段0: 合规修正+配置修复 (P0, 5天)**
- block=True修正
- 异常类型指定
- UID展示替换
- 修复Alembic配置不一致
- 删除db_new.py重复文件

**阶段1: 基础框架 (5周)**
- DI容器实现
- 仓储+UoW模式
- 属性计算器重构
- 效果系统统一
- 临时buff缓存优化

**阶段2: 解耦重构 (4周)**
- 循环依赖解除
- Service静态方法改造
- 命令模式引入
- 事件系统实现

**阶段3: 性能优化 (3周)**
- N+1查询优化
- 多会话问题修复
- 本地缓存集成
- 查询预加载优化

**阶段4: 测试与文档 (1周)**
- 单元测试编写
- 文档完善

详细路线图参见 `/guides/refactoring-roadmap.md`

### 优先级矩阵

| 任务 | 价值 | 难度 | 优先级 |
|-----|------|------|--------|
| 修复配置不一致 | 🔴 | 🟢 | P0 |
| 修复多会话问题 | 🔴 | 🟠 | P0 |
| 属性计算器 | 🔴 | 🟠 | P0 |
| 效果系统统一 | 🔴 | 🔴 | P0 |
| DI容器 | 🟠 | 🟡 | P1 |
| 仓储+UoW | 🟠 | 🟠 | P1 |
| N+1查询优化 | 🟡 | 🟢 | P1 |
| 临时buff缓存 | 🟡 | 🟢 | P1 |

## 6. 保留优秀设计

### 不改动的部分

| 现有设计 | 评估 | 处理方式 |
|---------|------|---------|
| _persist_bonus机制 | ✅ 优秀 | 保留,EquipmentAttributeSource直接读取 |
| Player.get_effective_attributes | ✅ 良好 | 保留,作为主入口 |
| safe_session自动提交 | ✅ 实用 | 保留,但优先使用UoW |
| 装备效果装饰器注册 | ✅ 简洁 | 保留,增加适配器层 |
| 战斗效果管理器 | ✅ 灵活 | 保留,统一到IEffect接口 |

### 废弃的部分

- ❌ `BattleAttributeCalculator.calculate_effective_attributes` (同步版本不含buff)
- ❌ `db_new.py` (完全重复的代码)
- ❌ Service静态方法模式 → 改为实例方法+依赖注入

## 7. 预期收益

### 量化指标

| 指标 | 当前 | 目标 | 提升 |
|-----|------|------|------|
| 循环依赖数 | 1 | 0 | -100% |
| 属性计算入口 | 5 | 1 | -80% |
| 效果系统数量 | 2 | 1 | -50% |
| Service可测试性 | 0% | 100% | +100% |
| 多会话问题 | 存在 | 消除 | +100% |
| N+1查询优化 | 存在 | 消除 | +100% |
| 临时buff查询 | 每次 | 缓存60秒 | -90% |

### 质量提升

**可维护性**:
- 清晰的分层架构
- 单一职责原则
- 统一的数据访问层

**可扩展性**:
- 新增效果仅需实现IEffect接口
- 新增属性来源实现IAttributeSource
- DI容器支持替换实现

**可测试性**:
- Service依赖注入支持Mock
- 核心逻辑与框架解耦
- 单元测试覆盖率>80%

## 8. 风险控制

### 风险缓解措施

| 风险 | 缓解措施 |
|-----|---------|
| 破坏现有功能 | 并行开发新旧代码,Feature Flag控制切换 |
| 性能回归 | 性能基准测试,灰度发布,监控关键指标 |
| 测试覆盖不足 | 核心逻辑测试优先,TDD测试先行 |
| 多会话修复不完整 | 全局搜索safe_session,逐个审查 |

### 回滚策略

- 立即回滚Feature Flag
- 降级到旧实现
- 保留safe_session作为fallback
- 延长测试周期

---

**详细文档**:
- 完整重构规划: `/llmdoc/REFACTORING_PLAN_v4.md`
- 实施路线图: `/guides/refactoring-roadmap.md`
- 目标架构: `/architecture/target-architecture.md`
- 设计模式: `/reference/design-patterns.md`
