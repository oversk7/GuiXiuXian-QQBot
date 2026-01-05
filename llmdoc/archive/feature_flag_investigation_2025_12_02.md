<!-- Feature Flag 深度调查报告 - Scout Agent Report -->

### Code Sections (The Evidence)

- `plugins/xiuxian_game/domain/effects/adapters/integration.py` (USE_NEW_EFFECT_SYSTEM): Feature Flag常量定义，从.env配置读取，控制新效果系统启用/禁用
- `plugins/xiuxian_game/__init__.py` (on_startup, USE_NEW_EFFECT_SYSTEM): 启动钩子中对Feature Flag的状态检查和日志输出
- `plugins/xiuxian_game/guild/guild.py` (USE_NEW_GUILD_SERVICE, USE_NEW_GUILD_APPLICATION_SERVICE, 等6个Guild相关Flag): Guild系统的6个Feature Flag定义和20+处使用位置
- `plugins/xiuxian_game/item/equipment_commands.py` (USE_NEW_EQUIPMENT_SERVICE): 装备系统Feature Flag定义(被4个文件重复定义)
- `plugins/xiuxian_game/economy/stock_commands.py` (USE_NEW_STOCK_SERVICE): 股票系统Flag定义和8处使用位置
- `plugins/xiuxian_game/entertainment/russian_roulette.py` (USE_NEW_RUSSIAN_ROULETTE_SERVICE): 俄罗斯轮盘赌系统Flag定义和42处使用位置(最密集)
- `plugins/xiuxian_game/economy/part_time_job_commands.py` (USE_NEW_PART_TIME_JOB_SERVICE): 打工系统Flag定义和9处使用位置
- `plugins/xiuxian_game/cultivate/core.py` (USE_NEW_MANSION_SERVICE): 阴宅系统Flag定义和3处使用位置
- `plugins/xiuxian_game/social/mentorship.py` (USE_NEW_MENTORSHIP_SERVICE): 师徒系统Flag被6个文件重复定义
- `plugins/xiuxian_game/item/item_effects.py` (USE_NEW_EQUIPMENT_SERVICE, USE_NEW_COMPLEX_EFFECT_SERVICES): 物品效果系统的两个Flag定义

### Report (The Answers)

#### result

**1. 所有USE_NEW_*模式的Feature Flag常量清单**

项目中共有**31个唯一Feature Flag**，但分散定义在45处位置：

**按定义位置分类**:
- `guild/guild.py`: 6个Flag (USE_NEW_GUILD_SERVICE, USE_NEW_GUILD_APPLICATION_SERVICE, USE_NEW_GUILD_BUILDING_SERVICE, USE_NEW_GUILD_ECONOMY_SERVICE, USE_NEW_GUILD_FACILITY_SERVICE, USE_NEW_GUILD_TASK_SERVICE)
- `item/equipment_commands.py`, `item/item_effects.py`, `item/equipment_upgrade_commands.py`, `item/sweep_dungeon_service.py`: 重复定义USE_NEW_EQUIPMENT_SERVICE (4处)
- `daily_task/commands.py`: 2个Flag (USE_NEW_DAILY_TASK_SERVICE, USE_NEW_GUILD_TASK_SERVICE)
- `economy/market.py`: USE_NEW_EQUIPMENT_TRADE_SERVICE
- `economy/stock_commands.py`, `economy/stock_service_di_example.py`: 重复定义USE_NEW_STOCK_SERVICE (2处)
- `economy/part_time_job_commands.py`: USE_NEW_PART_TIME_JOB_SERVICE
- 其他25个文件: 各定义1个flag
- `domain/effects/adapters/integration.py`: 唯一特殊的flag - USE_NEW_EFFECT_SYSTEM通过_get_feature_flag()从.env动态读取

**重复定义严重的Flag**: USE_NEW_GUILD_TASK_SERVICE (4处), USE_NEW_MENTORSHIP_SERVICE (6处), USE_NEW_EQUIPMENT_SERVICE (4处), USE_NEW_LOCATION_SERVICE (2处)

**2. 所有Feature Flag的使用位置**

**条件语句总数**: 157处 `if USE_NEW_*` 或 `elif USE_NEW_*` 语句

**使用密度最高的文件**:
- `entertainment/russian_roulette.py`: 42处条件语句(单个USE_NEW_RUSSIAN_ROULETTE_SERVICE)
- `economy/part_time_job_commands.py`: 9处条件语句
- `economy/stock_commands.py`: 8处条件语句
- `guild/guild.py`: 20+处条件语句(6个Flag混合)

**使用模式**:
- Pattern A: 模块顶部导入 - `if USE_NEW_*: from ...new import ... else: from ...old import ...`
- Pattern B: 函数内部分支 - `if USE_NEW_*: <new implementation> else: <old implementation>`
- Pattern C: 条件导入 - `if USE_NEW_*: use_new_service else: use_old_service`

**特殊情况**: USE_NEW_EFFECT_SYSTEM通过_get_feature_flag()从环境变量/NoneBot配置读取,而其他所有Flag都是硬编码为True

**3. 每个Flag控制的新旧代码分支范围**

**公会系统(6个Flag)**:
- USE_NEW_GUILD_SERVICE: 控制guild.py:72-120, 195-280, 478-570, 908-960间的新旧Service选择
- USE_NEW_GUILD_APPLICATION_SERVICE: 控制guild.py:434-475, 868-905, 933-1025间的新旧Service选择
- USE_NEW_GUILD_BUILDING_SERVICE: 控制guild.py:278-375, 339-370间的新旧Service选择
- USE_NEW_GUILD_ECONOMY_SERVICE: 控制guild.py:575-670, 669-750间的新旧Service选择
- USE_NEW_GUILD_FACILITY_SERVICE: 已定义但未使用(0处条件语句)
- USE_NEW_GUILD_TASK_SERVICE: 控制guild.py:691-740及其他4个文件中的任务相关逻辑

**装备系统(5个Flag)**:
- USE_NEW_EQUIPMENT_SERVICE: 4处定义,控制equipment_commands.py, item_effects.py, equipment_upgrade_commands.py, sweep_dungeon_service.py中的装备处理
- USE_NEW_EQUIPMENT_UPGRADE_SERVICE: 控制equipment_upgrade_commands.py中的升级逻辑
- USE_NEW_GEM_SOCKET_SERVICE: 控制gem_socket_commands.py中的镶嵌逻辑
- USE_NEW_GEM_UPGRADE_SERVICE: 控制gem_upgrade_commands.py中的宝石升级逻辑
- USE_NEW_EQUIPMENT_TRADE_SERVICE: 控制economy/market.py中的8处交易相关逻辑

**经济系统(4个Flag)**:
- USE_NEW_STOCK_SERVICE: 控制stock_commands.py:48, 178, 240, 284, 318, 407, 511处的股票操作
- USE_NEW_PART_TIME_JOB_SERVICE: 控制part_time_job_commands.py:46, 167, 203, 263, 334, 387, 439, 483处的打工操作
- USE_NEW_EQUIPMENT_TRADE_SERVICE: 控制market.py:361, 417, 557, 903, 950, 962处的装备交易
- USE_NEW_COMPLEX_EFFECT_SERVICES: 控制item_effects.py中复杂物品效果的新旧实现

**其他系统**: 类似模式,每个Flag都控制一个或多个命令处理器中的新旧Service选择

**4. 当前Flag值状态**

| 当前值 | Flag数量 | 备注 |
|--------|---------|------|
| True | 30个 | 所有Service DI Flag都启用 |
| _get_feature_flag() | 1个 | USE_NEW_EFFECT_SYSTEM (从.env读取) |
| 注释 | 1个 | USE_NEW_COMPLEX_EFFECT_SERVICES在item_effects_complex_legacy.py被注释掉 |

**关键发现**: 所有硬编码Flag都设置为True,表示新DI架构已完全启用,旧代码分支成为死代码

**5. Feature Flag统计数据**

- **唯一Flag数**: 31个
- **定义位置**: 45处(含重复)
- **使用条件语句**: 157处
- **涉及文件**: 38个
- **最重复的Flag**: USE_NEW_MENTORSHIP_SERVICE (6次) 和 USE_NEW_GUILD_TASK_SERVICE (4次)
- **条件最密集的文件**: russian_roulette.py (42处)
- **最长else分支**: guild.py中最长的else分支跨越~40行代码
- **旧Service类**: ~26个旧版Service类仍保留(对应新版Service)

#### conclusions

1. **Feature Flag已全部启用**: 所有USE_NEW_*常量都设置为True(除USE_NEW_EFFECT_SYSTEM从配置读取),表示项目已完全迁移到DI架构

2. **旧代码仍完整保留**: 所有157处条件分支中的else部分仍完整保留,成为死代码,可以安全删除

3. **Feature Flag定义分散**: 31个flag被分散定义在45处位置,存在4-6倍的重复定义,需要统一集中管理

4. **USE_NEW_EFFECT_SYSTEM特殊**: 是唯一从环境变量读取的flag,其他flag都是硬编码为True,表明效果系统的迁移独立于其他Service DI迁移

5. **旧Service类仍存在**: guild_service.py, equipment_service.py等~26个旧版Service类仍在代码库中,对应新版Service(guild_service_new.py等)

6. **条件分支设计一致**: 所有if/else分支都遵循统一模式:新版本使用DI架构(UnitOfWork+Repository+Service),旧版本使用静态Service方法

7. **可删除的代码范围明确**:
   - 157处else分支可全部删除(保留if部分)
   - ~26个旧Service文件可删除
   - 31个flag定义可统一集中后删除重复

8. **重构阶段指标**: Flag值全部为True表示新架构已稳定可用,可进入清理阶段

#### relations

- `domain/effects/adapters/integration.py::USE_NEW_EFFECT_SYSTEM` 从 `_get_feature_flag()` 函数读取.env配置
- `__init__.py::on_startup` 检查 `USE_NEW_EFFECT_SYSTEM` flag值并输出日志
- `guild/guild.py` 定义6个Guild系列Flag(USE_NEW_GUILD_SERVICE等),这些Flag在guild.py中被使用157次中的20+次
- `guild/guild.py` 调用对应的Service类: 如果Flag=True则使用GuildServiceNew,否则使用旧GuildService
- `item/equipment_commands.py` 定义USE_NEW_EQUIPMENT_SERVICE,同时也在4个其他文件中重复定义(item_effects.py, equipment_upgrade_commands.py, sweep_dungeon_service.py)
- `entertainment/russian_roulette.py` 中的42处条件语句都控制同一个USE_NEW_RUSSIAN_ROULETTE_SERVICE flag,分布在函数handle, play等中
- 所有新Service类(GuildServiceNew, EquipmentServiceNew等)都依赖 `infrastructure/uow/unit_of_work.py::UnitOfWork` 进行事务管理
- 所有旧Service类都采用静态方法模式,不使用UnitOfWork,无统一事务管理
- `domain/effects/adapters/integration.py::apply_effect_with_fallback` 根据USE_NEW_EFFECT_SYSTEM flag选择调用apply_effect_v2或旧的apply_effect

---

**报告类型**: Feature Flag完整清单与使用分析
**调查范围**: plugins/xiuxian_game所有Python文件
**发现总数**: 31个唯一flag + 157处使用 + 26个旧Service类
**建议**: 集中化flag定义 → 删除else分支 → 删除旧Service → 删除flag本身

