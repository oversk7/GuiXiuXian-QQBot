# 代码问题清单

## 1. Core Summary

本文档汇总诡修仙项目当前存在的架构和代码问题,基于四轮scout代理调研的真实代码证据,为重构工作提供量化依据。

## 2. Source of Truth

**调研报告来源**:
- `llmdoc/agent/architecture_investigation.md` - 架构和依赖关系调研
- `llmdoc/agent/attribute_system_investigation.md` - 属性计算系统调研
- `llmdoc/agent/effect_system_investigation.md` - 效果系统调研
- `llmdoc/agent/data_access_investigation.md` - 数据访问和会话管理调研

**重构规划**:
- `llmdoc/REFACTORING_PLAN_v4.md` - 完整重构规划(基于调研证据)

---

## 3. 核心问题汇总表

| 问题类别 | 具体表现 | 代码证据 | 影响范围 | 严重程度 |
|---------|---------|---------|---------|---------|
| **属性计算分散** | 5处属性计算逻辑,逻辑不一致 | `player.py:218`, `battle_attributes.py:39/88`, `equipment_commands.py:96`, `inventory.py:162` | 战斗/装备/buff系统 | 🔴 高 |
| **循环依赖** | item_effects ↔ equipment_commands | `item_effects.py:13` 导入 `recalc_equipment_attributes` | 物品/装备模块 | 🔴 高 |
| **无依赖注入** | 26个Service类静态方法,硬编码依赖 | 全项目 `from ..models.db import safe_session` | 全项目 | 🔴 高 |
| **多会话破坏事务** | 单命令打开4个独立会话 | `player/info.py` 打开4个safe_session | 数据一致性 | 🔴 高 |
| **N+1查询问题** | 逐个查询Player对象 | `bank.py` deposit_rank_cmd逐个`session.get(Player, id)` | 查询性能 | 🟠 中 |
| **效果系统重复** | 装饰器注册 vs 管理器模式 | `item_effects.py` 45+效果, `battle_effects.py` 75+效果 | 物品/战斗系统 | 🟡 低 |
| **配置不一致** | 数据库配置与迁移脱节 | `database.yaml`(MySQL) vs `alembic/env.py`(SQLite) | 迁移系统 | 🟠 中 |
| **代码重复** | 完全相同的文件 | `models/db.py` ≈ `models/db_new.py` | 维护成本 | 🟡 低 |

---

## 4. 详细问题分析

### P0问题(必须修复)

#### 1. 属性计算分散(5处位置)

**代码位置**:
1. `plugins/xiuxian_game/models/player.py:218-256` - get_effective_attributes (主入口)
2. `plugins/xiuxian_game/models/player.py:287-415` - get_attribute_breakdown (详细分解)
3. `plugins/xiuxian_game/battle/battle_attributes.py:39-85` - calculate_effective_attributes (同步,已弃用)
4. `plugins/xiuxian_game/battle/battle_attributes.py:88-152` - calculate_effective_attributes_async (异步版本)
5. `plugins/xiuxian_game/item/equipment_commands.py:96-175` - recalc_equipment_attributes (装备重算)

**问题**:
- 同步版本(battle_attributes.py:39)不包含临时buff,与异步版本逻辑不一致
- 每处计算逻辑略有差异,维护时容易遗漏
- 缺少单一真相来源(Single Source of Truth)

**影响**: 战斗系统、装备系统、buff系统属性计算结果可能不一致

**修复方案**: 参见 `/architecture/target-architecture.md` 的AttributeCalculator设计

---

#### 2. 循环依赖

**代码位置**:
```python
# item_effects.py:13
from .equipment_commands import recalc_equipment_attributes

# equipment_commands.py:96
def recalc_equipment_attributes(session, player):
    # 可能调用item_effects中的效果处理
```

**问题**:
- item_effects模块依赖equipment_commands
- 违反分层原则,物品效果应该是更高层抽象
- 无法独立测试和部署模块

**影响**: 模块耦合,难以重构和测试

**修复方案**: 使用事件系统或依赖注入解耦

---

#### 3. 多会话破坏事务原子性

**代码位置**: `plugins/xiuxian_game/player/info.py`

**问题**:
```python
# 打开第1个会话 - 查询玩家基础信息
async with safe_session() as session1:
    player = await get_player(session1, event)

# 打开第2个会话 - 更新导航
async with safe_session() as session2:
    # 更新操作

# 打开第3个会话 - 查询属性
async with safe_session() as session3:
    # 属性查询

# 打开第4个会话 - 查询公会
async with safe_session() as session4:
    # 公会查询
```

**问题**:
- 每个会话独立提交,无法保证整体业务逻辑的原子性
- 可能出现部分操作成功、部分失败的不一致状态
- 会话2提交后失败,会话1的修改已经持久化

**影响**: 数据一致性风险,用户可能看到中间状态

**修复方案**: 使用UnitOfWork模式,单个业务流程使用单个会话

---

#### 4. 无依赖注入(26个Service类)

**代码位置**: 全项目26个Service类

**问题**:
```python
# guild_service.py
class GuildService:
    @staticmethod
    async def create_guild(session: AsyncSession, player_id: str, name: str):
        # 硬编码依赖: 直接导入config
        from ..config import config
        # 无法进行单元测试: 无法mock session
```

**问题**:
- 静态方法无法进行依赖注入
- 全局导入config和safe_session,硬编码依赖
- 无法mock依赖进行单元测试
- 难以替换实现(如切换数据库、缓存策略)

**影响**: 可测试性差,扩展性差

**修复方案**: Service改为实例方法,通过DI容器注入依赖

---

### P1问题(应该修复)

#### 5. N+1查询问题

**代码位置**: `plugins/xiuxian_game/economy/bank.py` deposit_rank_cmd

**问题**:
```python
# 查询前30个账户
stmt = select(BankAccount).order_by(BankAccount.balance.desc()).limit(30)
accounts = (await session.execute(stmt)).scalars().all()

# N+1查询: 逐个查询Player
for acc in accounts:
    player = await session.get(Player, acc.player_id)  # 额外的30次查询
```

**问题**:
- 1次查询BankAccount + 30次查询Player = 31次数据库往返
- 应该使用joinedload预加载Player信息,减少到1次查询

**影响**: 排行榜查询性能差

**修复方案**:
```python
stmt = (
    select(BankAccount)
    .options(joinedload(BankAccount.player))
    .order_by(BankAccount.balance.desc())
    .limit(30)
)
```

---

#### 6. 临时buff每次查询数据库

**代码位置**: `plugins/xiuxian_game/models/temporary_buff.py:151-164`

**问题**:
```python
# 每次查询属性都要查询临时buff表
async def get_total_attribute_bonuses(session, player_id):
    stmt = select(TemporaryBuff).where(...)
    buffs = (await session.execute(stmt)).scalars().all()
```

**问题**:
- 高频战斗场景下,每次攻击都查询一次buff表
- 临时buff变化频率低,但查询频率高
- 缺少缓存机制

**影响**: 战斗性能瓶颈

**修复方案**: 增加60秒TTL本地缓存,使用buff物品时主动失效

---

#### 7. 配置不一致

**代码位置**:
- `plugins/xiuxian_game/data/database.yaml` - 配置MySQL
- `plugins/xiuxian_game/alembic/env.py` - 硬编码SQLite路径

**问题**:
```yaml
# database.yaml
type: mysql
host: localhost
database: guixiuxian_db
```

```python
# alembic/env.py
sqlalchemy.url = sqlite:///data/game.db  # 硬编码
```

**问题**:
- 迁移系统与实际数据库配置脱节
- 运行alembic命令会操作错误的数据库
- 部署时容易出错

**影响**: 数据库迁移失败,部署风险

**修复方案**: 从database.yaml读取配置,动态构建URL

---

### P2问题(可以推迟)

#### 8. 效果系统设计不一致

**代码位置**:
- `plugins/xiuxian_game/item/item_effects.py` - 装饰器注册表,45+效果
- `plugins/xiuxian_game/battle/battle_effects.py` - 管理器模式,75+效果

**问题**:
- 两套效果系统使用不同的设计模式
- 无法统一扩展和管理
- 添加新效果时需要理解两套系统

**影响**: 维护复杂度,新人学习曲线

**修复方案**: 统一IEffect接口,适配器模式迁移现有效果

---

#### 9. 代码重复

**代码位置**:
- `plugins/xiuxian_game/models/db.py`
- `plugins/xiuxian_game/models/db_new.py` (内容完全相同)

**问题**: 维护成本,可能导致修改不同步

**影响**: 代码质量

**修复方案**: 删除db_new.py

---

## 5. 问题优先级矩阵

| 任务 | 价值 | 难度 | 代码证据 | 优先级 |
|-----|------|------|---------|--------|
| 修复多会话问题 | 🔴 | 🟠 | player/info.py打开4个会话 | P0 |
| 属性计算器统一 | 🔴 | 🟠 | 5处分散计算 | P0 |
| 效果系统统一 | 🔴 | 🔴 | 45+装备效果, 75+战斗效果 | P0 |
| 修复配置不一致 | 🔴 | 🟢 | database.yaml vs alembic/env.py | P0 |
| 解除循环依赖 | 🟠 | 🟡 | item_effects.py:13 | P1 |
| N+1查询优化 | 🟡 | 🟢 | bank.py逐个查询Player | P1 |
| 临时buff缓存 | 🟡 | 🟢 | 每次战斗查询buff表 | P1 |
| DI容器引入 | 🟠 | 🟡 | 26个Service静态方法 | P1 |
| 删除重复代码 | 🟡 | 🟢 | db.py ≈ db_new.py | P2 |

---

## 6. 已修复问题

### ✅ 装备卸载属性清零Bug (2025-12-01)

**问题描述**: 使用"一键卸下"命令后，玩家的攻击、敏捷、理智等属性被清零，而不是恢复到基础值（无装备状态）。

**根本原因**:
1. 卸载装备时仅减去了装备的属性加成
2. 未清理 `_persist_bonus` 持久化加成记录
3. 未调用 `recalc_equipment_attributes()` 重新计算剩余装备的属性

**代码位置**: `plugins/xiuxian_game/item/equipment_commands.py:669-692`

**修复内容**:
```python
# 1. 清除装备的持久化加成记录
if "_persist_bonus" in (equip.extra_attrs or {}):
    extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
    equip.extra_attrs = extra_new

# 2. 重新计算剩余装备的属性加成
if USE_NEW_EQUIPMENT_SERVICE:
    equipment_service = EquipmentService(...)
    await equipment_service.recalc_equipment_attributes(player)
else:
    await recalc_equipment_attributes(session, player)
```

**修复日期**: 2025-12-01

**影响范围**: 所有使用"一键卸下"功能的玩家

**验证方法**:
1. 装备多件装备后记录攻击力
2. 使用"一键卸下"命令
3. 验证攻击力恢复到基础值（非零）

### ✅ 扫荡令卸下装备属性减少Bug (2025-12-02)

**问题描述**: 使用扫荡令后自动卸下耐久度为0的装备，重新穿戴时属性减少。

**根本原因**:
1. 自动卸下装备时手动回退了属性加成
2. 未清理 `_persist_bonus` 持久化加成记录
3. 导致重新穿戴时基于错误的基础值计算

**代码位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:496-509`

**修复内容**:
```python
# 清除_persist_bonus持久化记录
if "_persist_bonus" in (eq.extra_attrs or {}):
    extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
    eq.extra_attrs = extra_new
```

**修复日期**: 2025-12-02

**影响范围**: 所有使用扫荡令导致装备耐久度降至0的玩家

**验证方法**:
1. 穿戴多件装备，记录攻击力A
2. 使用扫荡令，直到某件装备耐久度降至0被自动卸下
3. 查看攻击力B，应该等于 A - 该装备的加成
4. 修理该装备并重新穿戴
5. 查看攻击力C，应该等于A（而非小于A）

**详细调查**: `/llmdoc/agent/sweep_token_equipment_bug_investigation.md`

---

**相关文档**:
- 游戏平衡分析: `/llmdoc/agent/game_balance_analysis_2025_12_01.md`
- 重构规划: `/llmdoc/REFACTORING_PLAN_v4.md` (已归档)
- 重构路线: `/guides/refactoring-roadmap.md` (已归档)
- 目标架构: `/architecture/target-architecture.md` (已归档)
- 设计模式: `/reference/design-patterns.md` (已归档)
