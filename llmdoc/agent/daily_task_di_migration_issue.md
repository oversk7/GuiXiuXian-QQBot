# 每日任务系统DI架构迁移不完整问题调查报告

## 1. 错误概述

**错误信息**:
```
AttributeError: 'AsyncSession' object has no attribute '_daily_task_repo'
```

**错误位置**:
- `plugins/xiuxian_game/daily_task/commands.py:36` - 调用 `DailyTaskService.get_player_daily_tasks(session, player.id, today)`
- `plugins/xiuxian_game/daily_task/service_new.py:381` - 访问 `self._daily_task_repo.find_all_by_player_and_date(...)`

**根本原因**: 命令处理器仍然使用旧的静态方法调用模式，将 `session` 作为第一个参数传递给已经迁移到DI架构的实例方法。

---

## 2. Code Sections (The Evidence)

### 2.1 DailyTaskService的DI架构实现

**`plugins/xiuxian_game/daily_task/service_new.py`** (`DailyTaskService.__init__`): DI版本Service，构造函数依赖4个参数
- Line 18-56: 完整的DI架构实现
- Line 35-54: 构造函数签名，需要 `daily_task_repo`, `location_service`, `npc_service`, `guild_economy_service`
- Line 376-381: `get_player_daily_tasks` 实例方法，使用 `self._daily_task_repo`

### 2.2 错误的静态方法调用模式

**`plugins/xiuxian_game/daily_task/commands.py`** (所有DailyTaskService调用): 11处静态方法调用错误
- Line 36: `DailyTaskService.get_player_daily_tasks(session, player.id, today)` - 将session作为第一个参数
- Line 40: `DailyTaskService.generate_daily_task(session, player)`
- Line 45: `DailyTaskService.get_task_summary(session, player.id)`
- Line 130: `DailyTaskService.get_player_daily_tasks(session, player.id, today)`
- Line 134: `DailyTaskService.force_generate_new_task(session, player)`
- Line 146: `DailyTaskService.accept_task(session, task)`
- Line 179: `DailyTaskService.get_player_daily_tasks(session, player.id, today)`
- Line 205: `DailyTaskService.complete_task(session, player, task)`
- Line 274: `DailyTaskService.get_task_summary(session, player.id)`
- Line 312: `DailyTaskService.get_player_daily_tasks(session, player.id, today)`
- Line 318: `DailyTaskService.force_generate_new_task(session, player)`

### 2.3 正确的DI调用模式参考

**`plugins/xiuxian_game/guild/guild.py`** (`handle_create_guild`, `handle_quit_guild`等): 正确使用UnitOfWork + DI容器
- Line 61-67: 创建UnitOfWork，使用session_factory
- Line 96-99: 实例化Service，传入Repository
- Line 376-380: 创建Service实例，使用 `uow.players`, `uow.guilds`, `uow`

**`plugins/xiuxian_game/item/equipment_commands.py`** (Feature Flag已删除): 装备系统已完全迁移，无Feature Flag
- Line 1-26: Feature Flag已完全删除（注释仅保留标记位置）
- 使用旧的 `equipment_service.py` 中的函数（尚未完全迁移到DI）

### 2.4 UnitOfWork缺少daily_tasks仓储属性

**`plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`** (UnitOfWork类): 仅实现12个仓储属性，缺少daily_tasks
- Line 48-64: 初始化仓储为None（players, items, guilds, buffs, invite_rewards, stocks等12个）
- Line 66-160: 12个 `@property` 懒加载仓储（players, items, guilds, buffs, invite_rewards, stocks, stock_holdings, stock_transactions, bank_accounts, part_time_jobs, job_locations, player_job_stats）
- **缺失**: 无 `daily_tasks` 或 `daily_task_repo` 属性

### 2.5 DailyTaskRepository存在

**`plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py`**: Repository实现存在
- 文件存在，已实现DailyTaskRepository
- 但未在UnitOfWork中注册

### 2.6 相关依赖Service（已DI改造）

**`plugins/xiuxian_game/world/location_service_new.py`** (`LocationService`): 已完成DI改造
**`plugins/xiuxian_game/world/npc_service_new.py`** (`NPCService`): 已完成DI改造
**`plugins/xiuxian_game/guild/guild_economy_service_new.py`** (`GuildEconomyService`): 已完成DI改造

### 2.7 Feature Flag已全部移除

**`llmdoc/reference/code-cleanup-2025-12-02.md`**: Feature Flag清理记录
- Line 105-106: `USE_NEW_DAILY_TASK_SERVICE` 已被删除（31个Flag之一）
- Line 8: 清理完成度90%，主要目标已达成
- Line 119: 157处条件分支被修改

**`plugins/xiuxian_game/daily_task/commands.py`**: Feature Flag定义行已删除
- Line 18-21: 仅保留注释标记，Feature Flag定义已删除

---

## 3. Report (The Answers)

### 3.1 Result

#### 问题1: DailyTaskService是否已迁移到DI架构？

**是**。`DailyTaskService` 已完全迁移到DI架构（实例方法模式）：
- 构造函数需要4个依赖：`daily_task_repo`, `location_service`, `npc_service`, `guild_economy_service`
- 所有方法都是实例方法（除了 `@staticmethod` 的纯计算方法）
- 使用 `self._daily_task_repo` 访问仓储

#### 问题2: commands.py中所有静态方法调用位置

**11处错误调用**，全部在 `plugins/xiuxian_game/daily_task/commands.py`:
1. Line 36: `get_player_daily_tasks(session, ...)`
2. Line 40: `generate_daily_task(session, ...)`
3. Line 45: `get_task_summary(session, ...)`
4. Line 130: `get_player_daily_tasks(session, ...)`
5. Line 134: `force_generate_new_task(session, ...)`
6. Line 146: `accept_task(session, ...)`
7. Line 179: `get_player_daily_tasks(session, ...)`
8. Line 205: `complete_task(session, ...)`
9. Line 274: `get_task_summary(session, ...)`
10. Line 312: `get_player_daily_tasks(session, ...)`
11. Line 318: `force_generate_new_task(session, ...)`

**调用分布**:
- `get_player_daily_tasks`: 4次（Line 36, 130, 179, 312）
- `generate_daily_task`: 1次（Line 40）
- `get_task_summary`: 2次（Line 45, 274）
- `force_generate_new_task`: 2次（Line 134, 318）
- `accept_task`: 1次（Line 146）
- `complete_task`: 1次（Line 205）

#### 问题3: 其他文件是否错误调用DailyTaskService？

**否**。仅 `plugins/xiuxian_game/daily_task/commands.py` 一个文件存在错误调用。其他文件：
- `daily_task/__init__.py`: 仅导入，无调用
- `daily_task/service_new.py`: Service实现文件本身

#### 问题4: 正确的DI架构使用方式（参考guild.py, equipment_commands.py）

**UnitOfWork + DI容器模式**（guild.py标准实现）:
```python
# 1. 创建UnitOfWork
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal

def session_factory():
    return AsyncSessionLocal()

async with UnitOfWork(session_factory) as uow:
    # 2. 获取玩家（使用uow.session）
    player = await get_unified_player(uow.session, event)

    # 3. 实例化Service（传入Repository）
    service = GuildServiceNew(
        player_repo=uow.players,
        guild_repo=uow.guilds,
        uow=uow
    )

    # 4. 调用Service方法（实例方法）
    result = await service.create_guild(player.id, guild_name)

    # 5. 提交事务（可选，UoW退出时自动提交）
    await uow.commit()
```

**设备系统（equipment_commands.py）**:
- 仍使用 `safe_session()` 和旧的函数式调用
- 未完全迁移到DI架构（保留了旧的 `equipment_service.py`）

#### 问题5: DailyTaskService的依赖注入需求

**构造函数参数**（4个依赖）:
```python
def __init__(
    self,
    daily_task_repo: DailyTaskRepository,        # 必需
    location_service: LocationService,            # 必需（已DI）
    npc_service: NPCService,                      # 必需（已DI）
    guild_economy_service: GuildEconomyService    # 可选（已DI）
):
    self._daily_task_repo = daily_task_repo
    self._location_service = location_service
    self._npc_service = npc_service
    self._guild_economy_service = guild_economy_service
```

**依赖来源**:
- `daily_task_repo`: 需要从 `uow.daily_tasks` 获取（**UnitOfWork缺少此属性**）
- `location_service`: 需要实例化 `LocationServiceNew`（依赖 `uow.locations`, `uow.npcs`）
- `npc_service`: 需要实例化 `NPCServiceNew`（依赖 `uow.npcs`）
- `guild_economy_service`: 需要实例化 `GuildEconomyServiceNew`（依赖多个Guild仓储）

---

### 3.2 Conclusions

#### 核心发现

1. **DailyTaskService已完成DI改造**，所有方法都是实例方法
2. **commands.py未同步迁移**，仍使用旧的静态方法调用模式（11处错误）
3. **UnitOfWork缺少daily_tasks属性**，无法通过 `uow.daily_tasks` 访问Repository
4. **Feature Flag已全部删除**，无法通过Feature Flag回退到旧实现
5. **依赖链复杂**，DailyTaskService依赖4个组件，其中3个是已DI改造的Service

#### 架构不一致性

- **Guild系统**: 完全迁移到UnitOfWork模式（`guild.py` 所有命令处理器）
- **每日任务系统**: Service已DI改造，命令处理器未迁移（**部分迁移状态**）
- **装备系统**: 命令处理器使用 `safe_session()`，Service层仍保留旧的函数式实现

#### 修复复杂度

- **简单路径**: 修改commands.py的11处调用 + 在UnitOfWork添加daily_tasks属性（**2文件修改**）
- **复杂路径**: 处理DailyTaskService的3个Service依赖（LocationService, NPCService, GuildEconomyService），需要在命令处理器中实例化这些Service

---

### 3.3 Relations

#### 文件依赖关系

```
commands.py (命令处理器)
    ├─> DailyTaskService (实例方法，需DI)
    │   ├─> DailyTaskRepository (需uow.daily_tasks)
    │   ├─> LocationService (需实例化，依赖uow.locations, uow.npcs)
    │   ├─> NPCService (需实例化，依赖uow.npcs)
    │   └─> GuildEconomyService (可选，需实例化，依赖多个Guild仓储)
    │
    ├─> UnitOfWork (事务管理)
    │   ├─> 12个已注册Repository
    │   └─> ❌ 缺少 daily_tasks 属性
    │
    └─> safe_session() (旧模式，待替换)
```

#### 迁移状态对比

| 系统 | Service DI | Repository | UnitOfWork | 命令处理器 | 状态 |
|-----|-----------|-----------|-----------|-----------|------|
| Guild | ✅ | ✅ | ✅ | ✅ | 完全迁移 |
| DailyTask | ✅ | ✅ | ❌ 缺属性 | ❌ | 部分迁移 |
| Equipment | ⚠️ 函数式 | ✅ | N/A | ⚠️ safe_session | 未迁移 |

#### 错误传播路径

```
1. 命令处理器调用 DailyTaskService.get_player_daily_tasks(session, ...)
   ↓
2. Python将 session 作为 self 参数传递给实例方法
   ↓
3. 实例方法访问 self._daily_task_repo
   ↓
4. AsyncSession对象没有 _daily_task_repo 属性
   ↓
5. AttributeError: 'AsyncSession' object has no attribute '_daily_task_repo'
```

---

## 4. 修复方案

### 4.1 完整修复方案（推荐）

**步骤1: 在UnitOfWork添加daily_tasks属性**

修改 `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`:
```python
# 在 __init__ 中添加（Line 48-64 区域）
self._daily_tasks = None

# 添加属性方法（在 Line 160 之后）
@property
def daily_tasks(self):
    """每日任务仓储"""
    if self._daily_tasks is None:
        from ..repositories.daily_task_repository import DailyTaskRepository
        self._daily_tasks = DailyTaskRepository(self._session)
    return self._daily_tasks
```

**步骤2: 在UnitOfWork添加locations和npcs属性**（如果尚未添加）

检查UnitOfWork是否有 `locations` 和 `npcs` 属性，如果没有则添加。

**步骤3: 修改commands.py的所有命令处理器**

替换 `safe_session()` 为 `UnitOfWork`，实例化Service并传入Repository。

**示例修改**（Line 26-98，`handle_daily_task`）:
```python
@daily_task_cmd.handle()
async def handle_daily_task(event: MessageEvent):
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 1. 获取玩家
        player = await get_unified_player(uow.session, event)
        if not player:
            await daily_task_cmd.finish("⛔ 请先创建角色")
        if player.level < 30:
            await daily_task_cmd.finish("⛔ 该功能仅对Lv.30以上角色开放")

        # 2. 实例化依赖Service
        from ..world.location_service_new import LocationService
        from ..world.npc_service_new import NPCService
        from ..guild.guild_economy_service_new import GuildEconomyService

        location_service = LocationService(
            location_repo=uow.locations,
            npc_repo=uow.npcs
        )
        npc_service = NPCService(npc_repo=uow.npcs)
        guild_economy_service = GuildEconomyService(...) if player.guild_id else None

        # 3. 实例化DailyTaskService
        service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        # 4. 调用实例方法（移除第一个session参数）
        today = date.today()
        tasks = await service.get_player_daily_tasks(player.id, today)

        if not tasks:
            task = await service.generate_daily_task(player)
            tasks = [task] if task else []

        summary = await service.get_task_summary(player.id)

        # 5. 事务自动提交（UnitOfWork.__aexit__）
        # 构建消息并返回...
```

**需要修改的命令处理器**:
- `handle_daily_task` (Line 26-98)
- `handle_accept_task` (Line 104-164)
- `handle_complete_task` (Line 170-261)
- `handle_task_stats` (Line 267-295)
- `handle_refresh_task` (Line 301-336)

**总计**: 5个命令处理器，11处方法调用需要修改。

---

### 4.2 简化方案（依赖Service工厂）

**如果LocationService/NPCService/GuildEconomyService实例化过于复杂**，可以考虑：

**选项A**: 在DailyTaskService内部创建依赖Service
- 缺点：破坏DI原则，增加耦合

**选项B**: 创建ServiceFactory类统一管理Service实例化
- 优点：命令处理器代码简洁
- 缺点：增加间接层

**选项C**: 将LocationService/NPCService设为可选，内部按需创建
- 修改 `service_new.py` 构造函数，将依赖Service设为可选
- 在方法内部按需创建（如果未注入则从session创建）

---

### 4.3 临时修复方案（不推荐）

**回退到旧的静态方法模式**:
1. 在 `service_new.py` 中添加 `@staticmethod` 装饰器到所有方法
2. 将所有 `self._daily_task_repo` 改为参数传递
3. 保持commands.py不变

**缺点**:
- 违背DI架构设计原则
- 无法利用Repository模式的优势
- 与其他已迁移系统不一致

---

## 5. 推荐行动

### 优先级 P0（必须修复）

1. **修改UnitOfWork** - 添加 `daily_tasks`, `locations`, `npcs` 属性（3个属性）
2. **修改commands.py** - 将5个命令处理器迁移到UnitOfWork模式

### 优先级 P1（建议优化）

1. **统一LocationService/NPCService实例化** - 避免在每个命令处理器中重复创建
2. **检查GuildEconomyService依赖** - 确认可选依赖的正确处理逻辑

### 优先级 P2（长期改进）

1. **创建ServiceFactory** - 统一管理复杂Service的实例化
2. **完善UnitOfWork** - 添加所有缺失的Repository属性
3. **迁移Equipment系统** - 统一所有系统到DI架构

---

## 6. 参考资源

### 文档

- `/llmdoc/architecture/service-di-final-implementation.md` - DI架构最终实现状态
- `/llmdoc/architecture/service-di-architecture.md` - DI架构核心组件
- `/llmdoc/guides/deploy-service-di.md` - 如何部署Service DI
- `/llmdoc/reference/code-cleanup-2025-12-02.md` - Feature Flag清理记录

### 代码参考

- `plugins/xiuxian_game/guild/guild.py` - 标准DI调用模式（Line 61-100）
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` - UnitOfWork实现
- `plugins/xiuxian_game/daily_task/service_new.py` - DI版本Service实现

---

**调查日期**: 2025-12-02
**调查状态**: 完成（根本原因已定位，修复方案已提供）
**维护者**: scout代理
**版本**: v1.0
