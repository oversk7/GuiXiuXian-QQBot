# 重构实施路线图

## How to Execute Refactoring (v4.0)

本文档提供诡修仙项目v4.0重构的详细实施步骤,采用五阶段渐进式重构策略,确保在不破坏现有功能的前提下逐步优化架构。

---

## 阶段0: 合规修正+配置修复 (P0, 5天)

### 目标
修复影响部署和迁移的P0问题,为后续重构打好基础。

### 任务清单

**1. 修复Alembic配置不一致** (1天)
   - 修改 `plugins/xiuxian_game/alembic/env.py`
   - 从 `database.yaml` 读取配置,动态构建URL
   - 测试迁移命令 `alembic upgrade head`

**2. 删除db_new.py重复文件** (0.5天)
   - 确认 `models/db.py` 和 `models/db_new.py` 内容相同
   - 全局搜索 `db_new` 引用,替换为 `db`
   - 删除 `models/db_new.py`

**3. block=True修正** (1天)
   - 搜索所有 `on_command` 装饰器
   - 确保所有命令处理器设置 `block=True`

**4. 异常类型指定** (1天)
   - 搜索所有 `except Exception` 和裸 `except`
   - 指定具体的异常类型(如 `SQLAlchemyError`, `ValueError`)

**5. UID展示替换** (1.5天)
   - 搜索所有直接展示 `player.id` 的位置
   - 替换为 `player.uid` 或其他用户友好标识

**验证标准**:
- `alembic upgrade head` 成功执行
- 无 `db_new` 引用
- 所有命令设置 `block=True`
- 无裸except语句

---

## 阶段1: 基础框架 (5周)

### 目标
建立松耦合架构的基础设施:DI容器、仓储模式、统一属性计算、统一效果系统。

### 1. DI容器实现 (3天)

**任务**:
1. 创建 `infrastructure/di/container.py`
2. 实现 `DIContainer` 类,支持singleton/scoped/transient
3. 注册核心服务(Session, Repository, Service)
4. 在启动钩子中初始化容器

**代码参考**: `/llmdoc/REFACTORING_PLAN_v4.md:86-148`

**验证**:
```python
container = DIContainer()
player_repo = container.resolve(IPlayerRepository)
assert player_repo is not None
```

---

### 2. 仓储+UoW模式 (5天)

**任务**:
1. 创建 `domain/repositories/base.py` (IRepository接口)
2. 创建 `infrastructure/repositories/player_repository.py`
3. 创建 `infrastructure/uow/unit_of_work.py` (UnitOfWork类)
4. 重构 `player/info.py` 使用UoW(消除4个独立会话)

**代码参考**: `/llmdoc/REFACTORING_PLAN_v4.md:189-318`

**验证**:
```python
async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id("test")
    player.gold += 100
    await uow.commit()
```

---

### 3. 属性计算器重构 (4天)

**任务**:
1. 创建 `domain/attributes/attribute_calculator.py`
2. 创建 `domain/attributes/attribute_sources/` 目录
3. 实现 `IAttributeSource` 接口
4. 实现 `EquipmentAttributeSource` (读取_persist_bonus)
5. 实现 `BuffAttributeSource` (增加60秒缓存)
6. 废弃 `BattleAttributeCalculator.calculate_effective_attributes` (同步版本)
7. 重构异步版本调用 `AttributeCalculator`

**代码参考**: `/llmdoc/REFACTORING_PLAN_v4.md:477-617`

**验证**:
- 废弃同步版本后,所有战斗测试通过
- 属性计算结果与旧版本一致
- buff缓存命中率>80%

---

### 4. 效果系统统一 (6天)

**任务**:
1. 创建 `domain/effects/effect_interface.py` (IEffect, EffectContext, EffectResult)
2. 创建 `domain/effects/effect_registry.py` (EffectRegistry)
3. 创建 `domain/effects/adapters/item_effect_adapter.py`
4. 保留现有 `_REGISTRY` 和装饰器
5. 为每个旧效果创建适配器
6. 增加Feature Flag控制新旧逻辑切换
7. 灰度验证一致性

**代码参考**: `/llmdoc/REFACTORING_PLAN_v4.md:320-462`

**验证**:
- Feature Flag=old时,所有效果测试通过
- Feature Flag=new时,适配器效果结果一致

---

### 5. 临时buff缓存优化 (2天)

**任务**:
1. 在 `BuffAttributeSource` 中增加缓存机制
2. 实现60秒TTL缓存
3. 使用临时buff物品时调用 `invalidate_cache(player_id)`

**代码参考**: `/llmdoc/REFACTORING_PLAN_v4.md:583-616`

**验证**:
- 缓存命中率>80%
- 使用buff物品后缓存正确失效

---

## 阶段2: 解耦重构 (4周)

### 目标
解除循环依赖,Service改造,引入命令模式和事件系统。

### 1. 循环依赖解除 (4天)

**任务**:
1. 将 `recalc_equipment_attributes` 从 `equipment_commands.py` 移到 `domain/services/`
2. 使用事件系统替代直接调用
3. 定义 `AttributeRecalculationNeededEvent`
4. `item_effects` 发布事件,不直接调用

**验证**:
- `item_effects.py` 不再导入 `equipment_commands`
- 循环依赖检测工具通过

---

### 2. Service静态方法改造 (5天)

**任务**:
1. 选择3个代表性Service(GuildService, BankService, PlayerService)
2. 改为实例方法,注入Repository依赖
3. 在DI容器中注册
4. 重构对应的Command Handler使用DI容器

**示例**:
```python
# 旧代码
class GuildService:
    @staticmethod
    async def create_guild(session, player_id, name):
        pass

# 新代码
class GuildService:
    def __init__(self, guild_repo, player_repo):
        self._guild_repo = guild_repo
        self._player_repo = player_repo

    async def create_guild(self, player_id, name):
        pass
```

**验证**:
- 3个Service改造完成
- 单元测试覆盖率>60%

---

### 3. 命令模式引入 (3天)

**任务**:
1. 创建 `application/commands/` 目录
2. 定义 `ICommand` 接口
3. 实现3个代表性命令(CreateGuildCommand, DepositCommand, WearEquipmentCommand)

**验证**:
- 命令可以单独测试
- 命令可以撤销(undo)

---

### 4. 事件系统实现 (4天)

**任务**:
1. 创建 `domain/events/event_bus.py`
2. 定义领域事件(PlayerLevelUpEvent, EquipmentChangedEvent等)
3. 实现事件发布和订阅机制
4. 重构属性重算使用事件系统

**验证**:
- 事件发布后,订阅者收到通知
- 属性重算通过事件触发

---

## 阶段3: 性能优化 (3周)

### 目标
优化N+1查询,修复多会话问题,集成本地缓存。

### 1. N+1查询优化 (5天)

**任务**:
1. 全局搜索 `session.get` 在循环中的使用
2. 重构 `bank.py` deposit_rank_cmd使用joinedload
3. 在Repository中添加预加载方法

**示例**:
```python
class BankRepository:
    async def get_top_accounts_with_players(self, limit=30):
        stmt = (
            select(BankAccount)
            .options(joinedload(BankAccount.player))
            .order_by(BankAccount.balance.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.unique().scalars().all()
```

**验证**:
- 数据库查询次数从31次减少到1次
- 排行榜响应时间<100ms

---

### 2. 多会话问题修复 (4天)

**任务**:
1. 全局搜索多个 `async with safe_session`
2. 重构为单个UoW
3. 审查所有Command Handler的会话使用

**验证**:
- `player/info.py` 只打开1个会话
- 所有Use Case使用单个UoW

---

### 3. 本地缓存集成 (3天)

**任务**:
1. 集成cachetools或diskcache
2. 缓存玩家基础信息(TTL 300秒)
3. 缓存临时buff(TTL 60秒)
4. 缓存物品配置(永久缓存)

**验证**:
- 缓存命中率>70%
- 响应时间减少30%

---

### 4. 查询预加载优化 (3天)

**任务**:
1. 审查所有Repository查询方法
2. 添加专用的预加载方法
3. 使用selectinload/joinedload优化

**验证**:
- 无N+1查询告警
- 数据库查询次数减少50%

---

## 阶段4: 测试与文档 (1周)

### 1. 单元测试编写 (3天)

**任务**:
1. 核心逻辑单元测试覆盖率>80%
2. AttributeCalculator测试
3. EffectRegistry测试
4. UnitOfWork事务测试

**验证**:
- pytest覆盖率报告>80%
- 所有测试通过

---

### 2. 文档完善 (2天)

**任务**:
1. 更新 `/llmdoc/architecture/target-architecture.md`
2. 添加迁移指南
3. 更新API文档

**验证**:
- 文档与代码一致
- 新人可以根据文档上手

---

## 关键成功因素

1. ✅ **合规优先**: 先完成P0合规修正和配置修复
2. ✅ **保留优秀设计**: _persist_bonus、Player.get_effective_attributes
3. ✅ **小步迭代**: 每次重构一个模块,验证后再继续
4. ✅ **测试保障**: 核心逻辑测试覆盖>80%
5. ✅ **并行开发**: 新旧代码并行,Feature Flag控制
6. ✅ **持续监控**: 关键指标实时监控
7. ✅ **基于证据**: 所有决策基于真实代码调研

---

## 风险控制

| 风险 | 缓解措施 | 应急预案 |
|-----|---------|---------|
| 破坏现有功能 | 并行开发,Feature Flag,回归测试 | 立即回滚Feature Flag |
| 性能回归 | 性能基准测试,灰度发布,监控 | 降级到旧实现 |
| 测试覆盖不足 | TDD,核心逻辑优先,Mock框架 | 延长测试周期 |
| 多会话修复不完整 | 全局搜索,逐个审查,事务测试 | 保留safe_session作为fallback |

---

**相关文档**:
- 完整重构规划: `/llmdoc/REFACTORING_PLAN_v4.md`
- 重构策略: `/overview/refactoring-strategy.md`
- 目标架构: `/architecture/target-architecture.md`
- 问题清单: `/reference/code-issues.md`
