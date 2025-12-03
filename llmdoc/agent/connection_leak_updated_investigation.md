# SQLAlchemy连接泄漏问题更新调查报告

**调查日期**: 2025-12-03
**调查范围**: 基于前期两份调查报告的补充验证
**警告信息**: `SAWarning: The garbage collector is trying to clean up non-checked-in connection`

---

## 概览

项目在前两次调查（2025-12-02）中已识别出**5个确认的连接泄漏源头**（2个P0+3个P1）。本报告对这些问题进行补充验证，并基于最新代码现状进行评估。

---

## 代码证据 (The Evidence)

### P0级 - 已确认的严重泄漏

#### 1. player/invite.py:253-296 - 在UoW外使用session

- `plugins/xiuxian_game/player/invite.py:239-321` (`handle_invite_status`): 在UnitOfWork内部获取invite_status，但消息构建逻辑**全部在UoW内部完成**（L254-320行）
  - **当前状态**: ✅ 已修复 - 所有数据库操作都在`async with UnitOfWork`块内进行
  - **修复方式**: 将两个`uow.session.execute()`调用（L264、L296）保持在UoW内部
  - **风险**: 无 - session生命周期完整

#### 2. economy/stock_commands.py:76 - 保存session引用

- `plugins/xiuxian_game/economy/stock_commands.py:50-99` (`handle_stock_list`): 在UnitOfWork内部获取stocks
  - **当前状态**: ✅ 已修复 - 没有找到`session = uow.session`的赋值语句（L76已删除）
  - **验证**: L75行读取`stocks = (await uow.session.execute(stmt)).scalars().all()`后，直接在UoW外使用stocks（已加载到内存，无需session）
  - **风险**: 无 - stocks对象已离线化到内存

### P1级 - 潜在泄漏源头

#### 3. daily_task/commands.py:284-287 - Repository手动创建

- `plugins/xiuxian_game/daily_task/commands.py:274-289` (`handle_complete_task`): 在UoW内部创建4个Repository并传递给Service
  - **问题代码位置**:
    ```
    L284: PlayerTaskStatsRepository(uow.session)
    L285: GuildTaskRecordRepository(uow.session)
    L286: PlayerDonationLogRepository(uow.session)
    L287: GuildBuildingRepository(uow.session)
    ```
  - **当前状态**: ❌ 未修复 - 仍在使用`Repository(uow.session)`模式而非UoW的懒加载属性
  - **风险**: 中等 - 如果GuildTaskServiceNew保存了这些Repository引用，可能在UoW退出后持有session
  - **修复缺陷**: UnitOfWork未提供这4个Repository的懒加载属性，无法直接用`uow.player_task_stats`替代

#### 4. guild/guild.py:186 - 在UoW内创建Repository

- `plugins/xiuxian_game/guild/guild.py:139-220` (`handle_guild_info`): 在UoW内部创建GuildBuildingRepository
  - **问题代码位置**:
    ```
    L186: building_repo=GuildBuildingRepository(uow.session)
    ```
  - **当前状态**: ❌ 未修复 - 仍在手动创建Repository而非使用UoW属性
  - **风险**: 中等 - GuildBuildingServiceNew可能保存Repository引用
  - **说明**: UoW已有`guild_buildings`懒加载属性（L213-218），应该能替代

#### 5. guild/guild.py:761 - 在UoW内创建Repository

- `plugins/xiuxian_game/guild/guild.py:700-800` (范围，需确认)
  - **风险**: 中等 - SocialApplicationRepository手动创建
  - **修复缺陷**: UnitOfWork未提供此Repository的懒加载属性

### 相关设计文档

- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:1-86` (懒加载属性定义): 当前UoW提供23个属性，**缺少以下4个**:
  - `player_task_stats` ❌ 未定义
  - `guild_task_records` ❌ 未定义
  - `player_donation_logs` ❌ 已定义（L221-226）✅
  - `guild_buildings` ✅ 已定义（L213-218）
  - `social_applications` ❌ 未定义

- `plugins/xiuxian_game/models/db.py:225-258` (`retry_session`): 异步函数，项目中**未被使用**
  - **风险**: 低 - 但存在潜在泄漏（循环内创建session，仅在finally关闭）

---

## 调查结果 (The Report)

### result

#### 当前泄漏情况总结

**✅ 已修复 (2个P0)**:
1. `player/invite.py` - 所有操作已在UoW内部完成，消息构建逻辑不再需要session
2. `economy/stock_commands.py` - stocks数据已加载到内存，UoW外部使用无需session

**❌ 仍需修复 (3个P1)**:
1. `daily_task/commands.py:284-287` - 4个Repository未使用UoW属性（其中2个缺失属性定义）
2. `guild/guild.py:186` - 可以用`uow.guild_buildings`替代，但代码未更新
3. `guild/guild.py:761` - SocialApplicationRepository缺失UoW属性定义

#### 连接泄漏仍然出现的原因

尽管P0级泄漏已修复，P1级泄漏仍在运行：

1. **high-frequency命令**: 如果`完成任务`被频繁调用，P1泄漏会快速累积
2. **Repository引用**:
   - GuildTaskServiceNew可能在Service内部保存Repository引用
   - 当Service被重用或缓存时，旧session引用仍存活
   - UoW退出后，这些引用可能导致连接无法正确释放
3. **缺失的UoW属性**: P1级泄漏无法直接修复，因为UoW缺少必要的懒加载属性

#### 修复优先级

| 泄漏位置 | 严重程度 | 使用频率 | 修复难度 | 预期时间 |
|---------|---------|---------|---------|---------|
| daily_task L284-287 | P1 | 高(完成任务) | 中(需扩展UoW) | 15min |
| guild L186 | P1 | 中(查看公会) | 低(直接替换) | 5min |
| guild L761 | P1 | 低 | 中(需定义属性) | 10min |

### conclusions

#### 关键发现

1. **UnitOfWork设计问题**:
   - 当前定义23个Repository懒加载属性
   - 缺少至少3个属性定义（player_task_stats、guild_task_records、social_applications）
   - 设计缺陷导致某些代码无法遵循UoW模式

2. **编码模式问题**:
   - P1泄漏的根本原因：手动创建Repository而非使用UoW属性
   - 无法追踪是否已完全遵循UoW模式
   - 需要统一编码规范

3. **警告仍然出现的可能原因**:
   - P1级泄漏累积效应（高频操作）
   - GuildTaskServiceNew等Service可能缓存Repository引用
   - 需要验证Service实现是否保存了Repository

4. **后续验证需要**:
   - 检查GuildTaskServiceNew、GuildBuildingServiceNew等Service实现
   - 确认这些Service是否在构造函数或方法内保存Repository引用
   - 运行压力测试（连续10+次操作）观察警告变化

#### 修复后预期

完全修复所有P1泄漏后：
- 连接泄漏警告应该**完全消失**
- 如果仍有警告，则需要调查Service层的Repository缓存问题
- 建议添加日志监控Repository生命周期

### relations

#### 代码关系图

```
UnitOfWork架构问题:
├─ 定义了23个懒加载属性 ✅
├─ 缺少player_task_stats ❌
├─ 缺少guild_task_records ❌
├─ 缺少social_applications ❌
└─ guild_buildings已定义但guild.py:186未使用 ⚠️

daily_task/commands.py泄漏链:
├─ L219: async with UnitOfWork() as uow ✅
├─ L284-287: 创建4个Repository(uow.session) ❌
├─ L281: GuildTaskServiceNew(repos...) - 保存Repository引用?
└─ L289: 退出UoW - Repository可能持有session ⚠️

guild/guild.py泄漏链:
├─ L139-191: async with UnitOfWork() as uow ✅
├─ L186: GuildBuildingRepository(uow.session) - 可用uow.guild_buildings替代 ⚠️
├─ L189: await building_service.get_guild_bonuses() - Repository引用泄漏?
└─ L220: 退出UoW - 数据已加载,无需session ✅
```

#### Service与Repository生命周期

```
当前模式（有泄漏风险）:
async with UnitOfWork() as uow:
    repo = Repository(uow.session)  # ❌ 直接创建
    service = Service(repo)         # Repository被Service保存
    result = await service.method() # Service持有repo
# UoW退出，session关闭，但service.repo仍持有关闭的session引用

推荐模式（安全）:
async with UnitOfWork() as uow:
    service = Service(uow.repo)    # ✅ 使用UoW属性（短生命周期）
    result = await service.method() # Service仅持有repo引用（在UoW内销毁）
# UoW退出时统一管理所有Repository的生命周期
```

---

## 修复方案

### 方案优先级排列

#### Phase 1: 扩展UnitOfWork（今天）

**文件**: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`

**添加缺失的3个属性**:

```python
# 在UnitOfWork.__init__中添加初始化（L82-83后）
self._player_task_stats = None        # 新增
self._guild_task_records = None       # 新增
self._social_applications = None      # 新增

# 添加3个懒加载属性（在player_donation_logs后）
@property
def player_task_stats(self):
    if self._player_task_stats is None:
        from ..repositories.player_task_stats_repository import PlayerTaskStatsRepository
        self._player_task_stats = PlayerTaskStatsRepository(self._session)
    return self._player_task_stats

@property
def guild_task_records(self):
    if self._guild_task_records is None:
        from ..repositories.guild_task_record_repository import GuildTaskRecordRepository
        self._guild_task_records = GuildTaskRecordRepository(self._session)
    return self._guild_task_records

@property
def social_applications(self):
    if self._social_applications is None:
        from ..repositories.social_application_repository import SocialApplicationRepository
        self._social_applications = SocialApplicationRepository(self._session)
    return self._social_applications
```

#### Phase 2: 修复daily_task/commands.py（10分钟）

**文件**: `plugins/xiuxian_game/daily_task/commands.py:274-289`

**替换代码**:

```python
# ❌ 当前（L274-289）
if player.guild_id:
    from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew
    from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
    from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
    from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
    from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

    guild_task_service = GuildTaskServiceNew(
        player_repo=uow.players,
        guild_repo=uow.guilds,
        player_task_stats_repo=PlayerTaskStatsRepository(uow.session),
        guild_task_record_repo=GuildTaskRecordRepository(uow.session),
        player_donation_log_repo=PlayerDonationLogRepository(uow.session),
        guild_building_repo=GuildBuildingRepository(uow.session),
    )

# ✅ 修复后（使用UoW属性）
if player.guild_id:
    from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew

    guild_task_service = GuildTaskServiceNew(
        player_repo=uow.players,
        guild_repo=uow.guilds,
        player_task_stats_repo=uow.player_task_stats,
        guild_task_record_repo=uow.guild_task_records,
        player_donation_log_repo=uow.player_donation_logs,
        guild_building_repo=uow.guild_buildings,
    )
```

#### Phase 3: 修复guild/guild.py（10分钟）

**文件**: `plugins/xiuxian_game/guild/guild.py:181-188`

**替换代码**:

```python
# ❌ 当前（L181-188）
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

building_service = GuildBuildingServiceNew(
    guild_repo=uow.guilds,
    building_repo=GuildBuildingRepository(uow.session),
    item_repo=None
)

# ✅ 修复后（使用UoW属性）
building_service = GuildBuildingServiceNew(
    guild_repo=uow.guilds,
    building_repo=uow.guild_buildings,  # 使用UoW属性
    item_repo=None
)
```

#### Phase 4: 查找guild.py:761的社交应用泄漏

需要搜索代码库定位确切位置和修复方式。

---

## 验证步骤

### 修复后验证清单

1. **代码审查**:
   - [ ] UnitOfWork添加了3个新属性
   - [ ] daily_task/commands.py使用了UoW属性
   - [ ] guild/guild.py:186已更新
   - [ ] Grep确认没有`Repository(uow.session)`的使用

2. **运行测试**:
   - [ ] 重启机器人
   - [ ] 连续执行10次`完成任务`
   - [ ] 连续执行10次`公会信息`
   - [ ] 监控日志，无SAWarning出现

3. **日志监控**:
   ```bash
   # 查看数据库连接日志
   grep "UnitOfWork" bot.log
   # 查看警告
   grep "garbage collector" bot.log
   ```

4. **连接池状态** (可选):
   ```python
   from plugins.xiuxian_game.models.db import engine
   print(f"活跃连接: {engine.pool.size()}")
   ```

---

## 相关文档

- `/llmdoc/agent/connection_leak_investigation.md` - 第一次调查（guild.py泄漏识别）
- `/llmdoc/agent/connection_leak_full_scan.md` - 第二次调查（全面扫描）
- `/llmdoc/architecture/service-di-architecture.md` - UnitOfWork设计文档
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` - UnitOfWork实现

---

## 补充说明

### 为什么P0级泄漏已解决但警告仍然出现？

1. **P1级泄漏仍在运行** - daily_task频繁调用，累积效应
2. **异步特性** - SQLAlchemy可能延迟检测泄漏
3. **连接池阈值** - 只在连接数达到某个阈值时才警告

### 为什么要统一用UoW属性而不是直接创建Repository？

**原因**:
- UoW确保所有Repository共享同一session
- 事务边界清晰（UoW退出时自动commit/rollback）
- 生命周期管理统一（所有Repository在UoW退出时同时销毁）
- 便于测试（可Mock整个UoW）

**对比**:
```python
# ❌ 容易泄漏 - Repository生命周期独立
repo = Repository(session)
# session关闭后repo可能仍持有引用

# ✅ 安全 - Repository生命周期由UoW管理
repo = uow.repo
# UoW退出时统一销毁所有Repository
```

---

**调查结论**: P0级泄漏已修复，P1级泄漏需要通过扩展UoW并更新3处调用代码来彻底解决。预计30分钟内可完全修复。
