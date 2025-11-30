# 架构总览

## 1. Identity

- **What it is**: 诡修仙项目的技术架构概览,总结当前架构特征和目标架构方向
- **Purpose**: 为LLM代理和开发者提供架构全景认知,快速定位模块和理解系统设计

## 2. 当前架构模式

### 架构风格: 单体插件式架构

诡修仙采用基于Nonebot2的**单体插件式架构**,所有功能封装在一个游戏插件中,按功能域划分为15+个子模块。

```
Nonebot2框架
    ↓
plugins/xiuxian_game (游戏插件)
    ├── 15个子系统模块
    ├── 49个数据模型
    └── 26个Service类
```

### 分层结构: 隐含三层架构

虽然代码中存在隐含的三层架构,但层次边界模糊:

**表现层 (Presentation)**:
- Nonebot2命令处理器 (`on_command`)
- 分散在各模块的 `*_commands.py` 和 `__init__.py`
- 直接调用Service或ORM操作

**业务层 (Business)**:
- 26个Service类 (静态方法模式)
- 核心逻辑文件 (`core.py`)
- 效果处理器 (`item_effects.py`, `battle_effects.py`)

**数据层 (Data)**:
- 49个SQLAlchemy模型 (`models/`)
- 数据库连接管理 (`db.py`)
- 无仓储抽象,直接使用ORM

**问题**: 表现层和业务层混合,数据访问逻辑散布在Service和Command Handler中。

## 3. 核心组件

### 数据库连接 (`models/db.py`)

三种会话管理器:
- `get_session()` - 基础会话,手动控制事务
- `safe_session()` - 主流使用,自动提交/回滚
- `retry_session()` - 带重试机制,处理锁定问题

双引擎支持:
- MySQL: 连接池20+10,pool_recycle=3600秒
- SQLite: WAL模式,用于测试和备份

### 配置管理 (`config.py`)

单例模式 + 缓存机制:
- `@property` + `@lru_cache` 实现懒加载
- 5个YAML配置文件: config.yaml, items.yaml, map.yaml, elixirs.yaml, database.yaml
- 全局访问: `from ..config import config`

**问题**: 单例模式导致全局状态,难以测试。

### 核心模型 (`models/`)

**Player模型** (`player.py`):
- 87个字段: 基础属性、战斗属性、双层坐标、公会关联、经济系统
- 15个方法: 包括5个异步方法(需要session参数)
- 关联: MonthlyCard(一对多), ItemInstance(外键), Guild(外键)

**ItemInstance模型** (`inventory.py`):
- 统一管理装备和消耗品
- 支持升阶(`upgrade_level`)、镶嵌(`gem_slots_data`)、耐久(`durability`)
- 静态方法: `add_item()`, `consume_item()`, `apply_attr_bonus()`

**Guild模型** (`guild.py`):
- 三表结构: Guild, GuildMember, GuildBuilding
- 使用 `cascade="all, delete-orphan"` 级联删除

### 效果系统

**物品效果** (`item/item_effects.py`):
- **模式**: 装饰器注册表
- **数量**: 45+种效果
- **触发**: 使用物品时
- **存储**: 永久属性直接修改Player字段,临时属性创建TemporaryBuff记录

**战斗效果** (`battle/battle_effects.py`):
- **模式**: 管理器模式 (`BattleEffectManager`)
- **数量**: 75+种效果, 12种触发类型
- **触发**: 攻击时、防御时、暴击时、回合开始等
- **存储**: 战斗期间存储在内存,战斗结束清除

**问题**: 两套效果系统设计不一致,难以统一扩展。

### 属性计算

**分散在5处**:
1. `Player.get_effective_attributes()` (主入口)
2. `Player.get_attribute_breakdown()` (详细分解)
3. `BattleAttributeCalculator.calculate_effective_attributes()` (同步版本,已弃用)
4. `BattleAttributeCalculator.calculate_effective_attributes_async()` (异步版本)
5. `recalc_equipment_attributes()` (装备重算)

**_persist_bonus机制** (优秀设计):
- 装备属性加成持久化存储在 `ItemInstance.extra_attrs["_persist_bonus"]`
- 避免每次战斗重新计算装备加成
- 卸下装备时准确回退属性

**问题**: 同步版本不包含临时buff,与异步版本逻辑不一致。

## 4. 数据流

### 命令处理流程

```
用户命令 (QQ消息)
    ↓
Nonebot2事件分发
    ↓
Command Handler (on_command装饰器)
    ↓
async with safe_session() (打开会话)
    ↓
get_player(session, event) (查询玩家)
    ↓
Service.method(session, ...) 或 直接ORM操作
    ↓
session自动commit() (safe_session退出时)
    ↓
返回消息给用户
```

### 属性计算流程

```
查询玩家属性
    ↓
Player.get_effective_attributes(session)
    ↓
基础属性 (player字段,包含装备和丹药的_persist_bonus)
    ↓
TemporaryBuff.get_total_attribute_bonuses(session, player_id)
    ↓
合并临时buff加成
    ↓
返回最终有效属性
```

### 装备穿戴流程

```
穿戴装备命令
    ↓
recalc_equipment_attributes(session, player)
    ↓
1. 卸下所有装备 (移除_persist_bonus)
2. 获取基础属性 (无装备状态)
3. 逐个装备计算加成
    ↓
ItemInstance.apply_attr_bonus(player, base_attrs, result_dict)
    ↓
4. 固定值加成 + 百分比加成 + 宝石加成
5. 保存_persist_bonus
6. 应用mp_from_hp特效
7. 修正HP/MP上限
    ↓
提交事务
```

## 5. 关键问题

### 架构层面

1. **缺少依赖注入**: 26个Service类硬编码依赖,全局导入config和safe_session
2. **无仓储抽象**: 直接使用SQLAlchemy ORM,查询逻辑散布在多处
3. **分层边界模糊**: Command Handler混合表现层和业务层逻辑
4. **循环依赖**: `item_effects.py:13` 导入 `equipment_commands.recalc_equipment_attributes`

### 数据访问层面

1. **多会话问题**: `player/info.py` 打开4个独立会话,破坏事务原子性
2. **N+1查询**: `bank.py` deposit_rank_cmd逐个查询Player对象
3. **缺少查询优化**: 附近玩家查询在Python中排序,未使用数据库索引
4. **配置不一致**: database.yaml(MySQL) vs alembic/env.py(SQLite)

### 业务逻辑层面

1. **属性计算分散**: 5处计算位置,同步版本不包含临时buff
2. **效果系统重复**: 装饰器注册 vs 管理器模式设计不一致
3. **缺少buff缓存**: 每次战斗都查询TemporaryBuff表

详细问题参见 `/reference/code-issues.md`

## 6. 目标架构方向

v4.0重构采用**设计模式驱动的松耦合架构**:

### 核心改进

1. **DI容器**: 依赖注入容器管理Service实例
2. **仓储+UoW**: Repository抽象数据访问,UnitOfWork统一事务边界
3. **统一属性计算**: 单一AttributeCalculator + IAttributeSource组合模式
4. **统一效果系统**: IEffect接口 + EffectRegistry策略模式
5. **性能优化**: 临时buff缓存、N+1查询优化、查询预加载

### 目标分层

```
Presentation (表现层)
    ↓ DTO Mappers
Application (应用层)
    ├── Use Cases
    ├── DI Container
    └── Unit of Work
    ↓
Domain (领域层)
    ├── Domain Models
    ├── Domain Services
    ├── AttributeCalculator
    └── EffectRegistry
    ↓
Infrastructure (基础设施层)
    ├── Repositories
    ├── MySQL/SQLite
    └── Local Cache
```

详细设计参见:
- `/architecture/target-architecture.md` - 目标架构设计
- `/guides/refactoring-roadmap.md` - 重构实施路线
- `/reference/design-patterns.md` - 设计模式参考

---

**相关文档**:
- 当前架构详情: `/architecture/current-architecture.md`
- 重构策略: `/overview/refactoring-strategy.md`
- 问题清单: `/reference/code-issues.md`
