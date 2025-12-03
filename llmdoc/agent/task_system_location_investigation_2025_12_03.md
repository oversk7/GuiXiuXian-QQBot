# 任务系统位置字段功能调查报告

**调查日期**: 2025-12-03
**调查类型**: 任务系统位置字段集成调查
**调查目标**: 为任务系统添加位置字段并集成导航功能

---

## Code Sections (Evidence)

### DailyTask 数据模型

- `plugins/xiuxian_game/models/daily_task.py:28-144` (DailyTask): 每日任务数据模型，包含完整的字段定义
- `plugins/xiuxian_game/models/daily_task.py:44-46` (位置字段): 已存在 `target_region`, `target_x`, `target_y` 三个位置字段
- `plugins/xiuxian_game/models/daily_task.py:108-111` (location_str属性): 提供格式化位置字符串的属性方法
- `plugins/xiuxian_game/models/daily_task.py:64-68` (新手任务链字段): 包含 `quest_chain_id`, `quest_step`, `is_tutorial`, `auto_accept` 等扩展字段

### 任务Service层

- `plugins/xiuxian_game/daily_task/service_new.py:18-654` (DailyTaskService): 每日任务系统Service类（DI版本）
- `plugins/xiuxian_game/daily_task/service_new.py:35-54` (__init__): 构造函数，依赖注入4个Service（daily_task_repo, location_service, npc_service, guild_economy_service）
- `plugins/xiuxian_game/daily_task/service_new.py:59-131` (generate_daily_task): 生成每日任务逻辑，包含随机坐标生成（82-83行）
- `plugins/xiuxian_game/daily_task/service_new.py:289-345` (create_ghost_npc_for_task): 为任务创建鬼怪NPC，自动创建/查找目标地点
- `plugins/xiuxian_game/daily_task/service_new.py:216-264` (complete_task): 完成任务，包含位置检查（222-223行）

### 任务显示命令

- `plugins/xiuxian_game/daily_task/commands.py:24-121` (handle_daily_task): 【任务】命令处理器，显示任务列表
- `plugins/xiuxian_game/daily_task/commands.py:90-96` (任务信息显示): 显示任务标题、描述、位置、敌人、奖励、状态
- `plugins/xiuxian_game/daily_task/commands.py:92` (位置显示): 使用 `task.location_str` 显示位置信息
- `plugins/xiuxian_game/daily_task/commands.py:112-118` (操作提示): 根据任务状态给出不同的操作提示

### 导航系统

- `plugins/xiuxian_game/world/navigation.py:1-622` (导航系统): 完整的自动导航功能实现
- `plugins/xiuxian_game/world/navigation.py:37-41` (导航命令): 注册了 `导航`, `前往`, `查找`, `检查数据`, `中断导航` 5个命令
- `plugins/xiuxian_game/world/navigation.py:154-322` (handle_nav): 【导航】命令处理器，支持设置目标和查看进度
- `plugins/xiuxian_game/world/navigation.py:351-463` (handle_goto_location): 【前往】命令处理器，快速导航到地点
- `plugins/xiuxian_game/models/navigation_task.py:7-16` (NavigationTask): 导航任务数据模型，包含 `target_x`, `target_y`, `last_update`, `initial_distance` 字段

### 任务配置数据

- `plugins/xiuxian_game/daily_task/service_new.py:22-33` (常量定义): GHOST_NAMES（50个中文名）和 CITY_NAMES（16个古代城市名）
- `plugins/xiuxian_game/daily_task/service_new.py:406-466` (_get_task_descriptions_by_type): 根据任务类型生成任务描述文案
- `plugins/xiuxian_game/daily_task/service_new.py:469-485` (_generate_task_title_and_enemy): 根据任务类型生成任务标题和敌人名称
- `plugins/xiuxian_game/daily_task/service_new.py:617-653` (_calculate_rewards): 计算任务奖励（经验、金币、积分）

### Repository层

- `plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py`: DailyTaskRepository（从UnitOfWork推断）
- `plugins/xiuxian_game/infrastructure/repositories/location_repository.py`: LocationRepository（从LocationService推断）
- `plugins/xiuxian_game/infrastructure/repositories/npc_repository.py`: NPCRepository（从NPCService推断）

---

## Report (Answers)

### 1. DailyTask 数据模型字段分析

**核心发现**: DailyTask模型已经包含位置相关字段，无需添加新字段！

**已有字段列表** (44个字段):

| 字段名 | 类型 | 说明 |
|--------|------|------|
| **基础信息** |||
| `id` | int | 主键 |
| `player_id` | str | 玩家ID（外键） |
| **任务信息** |||
| `task_type` | str | 任务类型（7种枚举） |
| `title` | str | 任务标题 |
| `description` | str | 任务描述 |
| **位置字段（已存在）** |||
| `target_region` | str | 目标区域（默认"大都会"） |
| `target_x` | int | 目标坐标X（已实现） |
| `target_y` | int | 目标坐标Y（已实现） |
| **任务状态** |||
| `status` | str | 任务状态（available/accepted/completed/expired） |
| **敌人信息** |||
| `enemy_name` | str | 敌人名称 |
| `enemy_level` | int | 敌人等级 |
| `enemy_hp` | int | 敌人血量 |
| `enemy_attack` | int | 敌人攻击力 |
| `enemy_defense` | int | 敌人防御力 |
| `enemy_agility` | int | 敌人敏捷 |
| **奖励信息** |||
| `exp_reward` | int | 经验奖励 |
| `gold_reward` | int | 金币奖励 |
| `guild_points_reward` | int | 公会积分奖励 |
| **新手任务链字段** |||
| `quest_chain_id` | str | 任务链ID（可选） |
| `quest_step` | int | 任务链步骤（可选） |
| `is_tutorial` | bool | 是否为新手教程任务 |
| `auto_accept` | bool | 是否自动接取 |
| **时间信息** |||
| `task_date` | date | 任务日期 |
| `accepted_at` | datetime | 接取时间 |
| `completed_at` | datetime | 完成时间 |
| `created_at` | datetime | 创建时间 |

**关键属性方法**:
- `location_str` - 返回格式化位置字符串，如 "大都会(100,200)"
- `enemy_stats` - 返回敌人属性字典
- `get_reward_summary(has_guild)` - 返回奖励摘要字符串

### 2. 任务Service层架构分析

**设计模式**: Service DI架构（依赖注入）

**DailyTaskService依赖关系**:
```python
DailyTaskService(
    daily_task_repo: DailyTaskRepository,      # 任务数据仓储
    location_service: LocationService,         # 地点服务
    npc_service: NPCService,                   # NPC服务
    guild_economy_service: GuildEconomyService # 公会经济服务（可选）
)
```

**核心业务方法**:

1. **generate_daily_task(player)** - 生成每日任务
   - 随机生成坐标: `target_x = random.randint(-200, 200)`
   - 随机选择城市和鬼怪名称
   - 计算敌人属性和奖励
   - 使用Repository保存任务

2. **accept_task(task)** - 接取任务
   - 调用 `create_ghost_npc_for_task()` 在目标位置生成鬼怪NPC
   - 更新任务状态为 "accepted"

3. **complete_task(player, task)** - 完成任务
   - 检查玩家是否在任务目标位置: `player.x != task.target_x or player.y != task.target_y`
   - 检查鬼怪NPC是否已死亡
   - 发放奖励（经验、金币、积分、公会经验）

4. **create_ghost_npc_for_task(task)** - 为任务创建鬼怪NPC
   - 自动查找或创建目标地点Location
   - 在目标位置生成鬼怪NPC
   - 设置NPC的extra_data关联任务信息

**使用DI架构优势**:
- 清晰的依赖关系
- 易于单元测试
- 支持事务管理（UnitOfWork）
- 解耦数据访问和业务逻辑

### 3. 任务显示命令实现

**命令注册**:
```python
daily_task_cmd = on_command("每日委托", aliases={"任务", "每日任务"}, block=True, priority=5)
```

**当前显示格式** (commands.py:70-120):

```
🏛️ 大都会缉邪司 - 每日委托
━━━━━━━━━━━━━
📋 【委托1】缉邪司委托：长安城鬼怪张伟作祟事件
🔳 任务描述：近日长安城中异象频生，死者张伟化为厉鬼...
📍 目标位置：大都会(100,200)
👹 目标敌人：鬼怪·张伟 Lv.35
💰 任务奖励：经验+500 金币+2000 积分+200 公会经验+额外
📊 任务状态：可接取

━━━━━━━━━━━━━
📈 完成统计：
本周完成：3 次
总计完成：15 次

💡 使用【接取任务 <委托编号>】接取委托（如：接取任务 1）
```

**格式化要点**:
- 使用emoji标识不同信息类型（📋任务、📍位置、👹敌人、💰奖励、📊状态）
- 使用Unicode分隔线（━）分隔区块
- 位置显示使用 `task.location_str` 属性（格式：`大都会(100,200)`）
- 根据任务状态显示不同的emoji和文本（📋可接取、⚔️进行中、✅已完成、❌已过期）
- 动态生成操作提示（根据任务状态）

**位置显示代码**:
```python
lines.append(f"📍 目标位置：{task.location_str}")  # Line 92
```

### 4. 任务配置数据存储

**结论**: 任务配置硬编码在Service类中，无独立配置文件

**数据存储位置**:

1. **常量数据** (service_new.py:22-33):
   - `GHOST_NAMES`: 50个中文真人名字（张伟、王芳、李娜...）
   - `CITY_NAMES`: 16个古代城市名（长安、洛阳、金陵...）

2. **任务描述文案** (service_new.py:406-466):
   - `_get_task_descriptions_by_type(task_type, city_name, ghost_name)`
   - 根据6种任务类型返回对应的任务描述列表
   - 每种类型3-12条文案变种
   - 文案风格：诡异氛围、古风表达、详细叙事

3. **任务标题生成** (service_new.py:469-485):
   - `_generate_task_title_and_enemy(task_type, city_name, ghost_name)`
   - 根据任务类型生成标题和敌人名称
   - 示例：`"缉邪司委托：长安城鬼怪张伟作祟事件"`, `"鬼怪·张伟"`

4. **奖励计算公式** (service_new.py:617-653):
   - `_calculate_rewards(player_level, enemy_level, task_type)`
   - 基础奖励 + 任务类型倍率 + 等级差异调整
   - 返回: `{"exp": int, "gold": int, "guild_points": int}`

**创建新任务的流程**:
1. 调用 `DailyTaskService.generate_daily_task(player)`
2. Service内部随机选择城市、鬼怪名、任务类型
3. 生成随机坐标: `target_x = random.randint(-200, 200)`
4. 调用静态方法生成描述、标题、敌人名
5. 计算敌人属性和奖励
6. 创建DailyTask对象并保存到数据库

### 5. 导航系统集成点分析

**导航系统完整实现** (navigation.py):

**已有导航命令**:
1. `【导航 x y】` - 设置导航到指定坐标，查看导航进度
2. `【前往 地点名】` - 快速导航到指定地点
3. `【查找 NPC名称】` - 查询NPC位置
4. `【中断导航】` - 取消当前导航
5. `【检查数据】` - 检查Location和NPC数据状态

**导航核心机制**:
- 基于玩家敏捷值计算移动速度: `speed = agility / 2500` 格/秒
- 使用欧几里得距离计算路径: `distance = sqrt((x2-x1)^2 + (y2-y1)^2)`
- 持久化导航任务到数据库（NavigationTask表）
- 支持实时进度查看（进度条、剩余距离、预计时间）
- 支持诡域中设置现实世界导航

**与任务系统的集成点**:

1. **位置显示一致性**:
   - 任务系统: `大都会(100,200)` (task.location_str)
   - 导航系统: `(100,200)` 坐标格式

2. **快速导航入口**:
   - 当前任务命令显示目标位置，但没有快捷导航按钮
   - 玩家需要手动复制坐标使用【导航 x y】命令

3. **导航→任务的关联**:
   - 导航系统支持【前往 地点名】快速导航
   - 任务系统可显示【前往 任务位置】快捷按钮（需实现）

**集成建议**: 在任务显示中添加导航快捷方式

---

## Conclusions (Key Takeaways)

### 核心发现

1. **位置字段已完整实现**: DailyTask模型已包含 `target_region`, `target_x`, `target_y` 三个字段，无需添加新字段
2. **Service层采用DI架构**: 依赖注入模式，清晰的分层设计，易于扩展和测试
3. **任务配置硬编码**: 无独立配置文件，文案和规则直接编码在Service类的静态方法中
4. **导航系统已完善**: 完整的自动导航功能，支持坐标导航、地点导航、NPC查找
5. **集成点明确**: 任务系统与导航系统的集成点在于命令层的快捷方式添加

### 当前任务系统优势

1. **数据模型完善**: 包含任务类型、状态、位置、敌人、奖励等完整信息
2. **文案丰富**: 6种任务类型，每种类型3-12条文案变种，诡异氛围浓厚
3. **随机化设计**: 坐标、城市、鬼怪名、任务类型均随机生成，可玩性高
4. **自动化集成**: 接取任务自动创建鬼怪NPC和地点，完成任务自动检查位置和NPC状态
5. **奖励系统完善**: 支持经验、金币、积分、公会经验多种奖励

### 可改进点

1. **导航快捷方式缺失**: 任务显示时没有快捷导航按钮，需要玩家手动复制坐标
2. **任务链支持未完善**: 虽然模型包含任务链字段，但Service层未实现任务链逻辑
3. **配置灵活性低**: 任务文案和规则硬编码，修改需要改代码
4. **任务类型固定**: 仅支持7种任务类型，无法通过配置文件扩展

---

## Relations (Code Relationships)

### 数据流关系图

```
命令层 (commands.py)
    ↓ 调用
Service层 (service_new.py: DailyTaskService)
    ↓ 依赖注入
Repository层 (daily_task_repository.py)
    ↓ 操作
数据库 (daily_task表)

Service层 (DailyTaskService)
    ↓ 依赖
LocationService (location_service_new.py)
    ↓ 操作
Location表

Service层 (DailyTaskService)
    ↓ 依赖
NPCService (npc_service_new.py)
    ↓ 操作
NPC表
```

### 任务生成流程

```
1. 玩家触发【任务】命令
   ↓
2. handle_daily_task() [commands.py:27]
   ↓ 实例化
3. DailyTaskService(uow.daily_tasks, location_service, npc_service) [commands.py:48-54]
   ↓ 调用
4. task_service.generate_daily_task(player) [commands.py:62]
   ↓ 生成
5. DailyTask对象 (包含target_x, target_y, target_region) [service_new.py:110-128]
   ↓ 保存
6. daily_task_repo.add(task) [service_new.py:131]
   ↓
7. 返回任务对象并显示
```

### 任务接取流程

```
1. 玩家触发【接取任务 1】命令
   ↓
2. handle_accept_task() [commands.py:127]
   ↓ 调用
3. task_service.accept_task(task) [commands.py:190]
   ↓ 调用
4. create_ghost_npc_for_task(task) [service_new.py:207]
   ↓ 查找/创建
5. location_service.get_location_by_coordinates(task.target_x, task.target_y) [service_new.py:300-302]
   ↓ 创建
6. npc_service.create_ghost_npc(..., location_id, ...) [service_new.py:322-331]
   ↓ 更新
7. task.accept_task() [service_new.py:211]
   ↓
8. 返回接取成功消息（包含位置信息）
```

### 任务完成流程

```
1. 玩家击杀鬼怪后触发【完成任务】命令
   ↓
2. handle_complete_task() [commands.py:215]
   ↓ 检查
3. task_service.complete_task(player, task) [commands.py:270]
   ↓ 验证位置
4. player.x == task.target_x and player.y == task.target_y [service_new.py:222-223]
   ↓ 验证NPC
5. npc_service.get_npc_by_id(f"ghost_task_{task.id}") [service_new.py:226]
   ↓ 检查死亡
6. ghost_npc.is_dead() [service_new.py:230]
   ↓ 发放奖励
7. player.exp += task.exp_reward, player.gold += task.gold_reward [service_new.py:237-244]
   ↓ 完成任务
8. task.complete_task() [service_new.py:261]
   ↓
9. 返回完成消息和奖励信息
```

### 导航系统与任务系统的集成关系

```
任务系统 (commands.py)
    ↓ 显示
task.location_str → "大都会(100,200)"
    ↓ 玩家手动
【导航 100 200】命令
    ↓ 触发
导航系统 (navigation.py)
    ↓ 创建
NavigationTask(target_x=100, target_y=200)
    ↓ 持久化
navigation_task表

潜在集成点:
任务显示 → 添加【前往任务位置】按钮
    ↓ 自动调用
导航系统.goto_location_cmd
    ↓ 自动设置
NavigationTask(target_x=task.target_x, target_y=task.target_y)
```

---

## 实施步骤建议

### Phase 1: 基础集成（位置字段已存在）

**结论**: 无需添加字段，位置功能已完整实现

**验证清单**:
- ✅ DailyTask模型包含 `target_x`, `target_y`, `target_region` 字段
- ✅ 任务生成时自动设置随机坐标 (service_new.py:82-83)
- ✅ 任务显示时显示位置信息 (commands.py:92)
- ✅ 任务完成时检查位置匹配 (service_new.py:222-223)
- ✅ 位置相关的LocationService和NPCService已集成

### Phase 2: 导航快捷方式集成（推荐实施）

**目标**: 在任务显示中添加快捷导航按钮

**实施方案**:

1. **方案A: 纯文本提示（最简单）**
   - 修改文件: `plugins/xiuxian_game/daily_task/commands.py`
   - 修改位置: Line 96后添加导航提示
   ```python
   lines.append(f"📊 任务状态：{status_text}")
   lines.append(f"🧭 快捷导航：【导航 {task.target_x} {task.target_y}】")  # 新增
   lines.append("")
   ```
   - 优点: 实施简单，无需修改Service层
   - 缺点: 需要玩家手动复制坐标

2. **方案B: 集成【前往】命令（推荐）**
   - 修改文件: `plugins/xiuxian_game/daily_task/commands.py`
   - 修改位置: Line 203后添加导航建议
   ```python
   f"💡 请前往目标位置，使用【观察】查看鬼怪，击杀后使用【完成任务】\n"
   f"🧭 快捷导航：【导航 {task.target_x} {task.target_y}】"  # 新增
   ```
   - 优点: 与现有导航系统无缝集成
   - 缺点: 玩家需要记住导航命令格式

3. **方案C: 自动导航（最智能）**
   - 修改文件: `plugins/xiuxian_game/daily_task/commands.py`
   - 新增参数: `接取任务 <编号> --导航`
   - 实现逻辑:
   ```python
   if "--导航" in args_text or "导航" in args_text:
       # 自动创建NavigationTask
       from ..world.navigation import NavigationTask
       nav_task = NavigationTask(
           player_id=player.id,
           target_x=task.target_x,
           target_y=task.target_y,
           last_update=datetime.now(),
           initial_distance=_euclidean_distance(player.x, player.y, task.target_x, task.target_y)
       )
       await uow.session.merge(nav_task)
       msg += "\n🧭 已自动设置导航至任务位置"
   ```
   - 优点: 一键接取任务+自动导航，用户体验最佳
   - 缺点: 需要修改接取任务逻辑

**推荐实施**: 方案B + 方案C组合
- 方案B提供手动导航提示（所有任务）
- 方案C提供自动导航功能（可选参数）

### Phase 3: 任务列表优化（可选）

**目标**: 增强任务列表的可读性和可操作性

**优化点**:

1. **距离显示**: 在任务列表中显示玩家到任务位置的距离
   ```python
   from ..world.navigation import _euclidean_distance
   distance = _euclidean_distance(player.x, player.y, task.target_x, task.target_y)
   lines.append(f"📏 距离：{distance:.1f} 格")
   ```

2. **按距离排序**: 优先显示最近的任务
   ```python
   tasks_with_distance = [
       (task, _euclidean_distance(player.x, player.y, task.target_x, task.target_y))
       for task in tasks
   ]
   tasks_with_distance.sort(key=lambda x: x[1])
   tasks = [t[0] for t in tasks_with_distance]
   ```

3. **预计到达时间**: 显示导航到任务位置需要的时间
   ```python
   speed = _tiles_per_second(player.agility)
   eta_seconds = distance / speed if speed > 0 else 0
   lines.append(f"⏱️ 预计：{_format_eta(timedelta(seconds=int(eta_seconds)))}")
   ```

### Phase 4: 任务链支持（长期规划）

**目标**: 实现新手任务链功能（模型字段已存在）

**实施路径**: 参考 `llmdoc/agent/cultivation_and_quest_investigation.md` 中的新手任务链设计方案

---

## 需要修改的文件清单

### 立即可实施（Phase 2: 导航快捷方式）

**必需修改**:
1. `plugins/xiuxian_game/daily_task/commands.py`
   - Line 96后: 添加导航提示（方案B）
   - Line 203后: 添加快捷导航命令（方案B）
   - Line 190-207: 实现自动导航参数（方案C，可选）

**可选修改**:
2. `plugins/xiuxian_game/daily_task/service_new.py`
   - 无需修改（位置字段已完整）

3. `plugins/xiuxian_game/models/daily_task.py`
   - 无需修改（字段已完整）

4. `plugins/xiuxian_game/world/navigation.py`
   - 无需修改（功能已完整）

### 进阶优化（Phase 3: 任务列表优化）

**可选修改**:
1. `plugins/xiuxian_game/daily_task/commands.py`
   - Line 75-96: 添加距离显示、按距离排序、预计到达时间

2. `plugins/xiuxian_game/utils.py`
   - 添加 `calculate_distance()` 辅助函数（如果需要复用）

### 长期规划（Phase 4: 任务链支持）

**需要新增**:
1. `plugins/xiuxian_game/quest/novice_quest_service.py` - 新手任务链Service
2. `plugins/xiuxian_game/data/novice_quests.yaml` - 新手任务链配置

**需要修改**:
1. `plugins/xiuxian_game/daily_task/service_new.py` - 扩展任务链生成逻辑
2. `plugins/xiuxian_game/daily_task/commands.py` - 支持任务链显示

---

## 代码示例

### 示例1: 在任务显示中添加导航提示（方案B）

**文件**: `plugins/xiuxian_game/daily_task/commands.py`

**修改位置**: Line 90-96

```python
# 原代码
lines.append(f"{status_emoji} 【委托{i}】{task.title}")
lines.append(f"🔳 任务描述：{task.description}")
lines.append(f"📍 目标位置：{task.location_str}")
lines.append(f"👹 目标敌人：{task.enemy_name} Lv.{task.enemy_level}")
lines.append(f"💰 任务奖励：{task.get_reward_summary(bool(player.guild_id))}")
lines.append(f"📊 任务状态：{status_text}")
lines.append("")

# 修改后
lines.append(f"{status_emoji} 【委托{i}】{task.title}")
lines.append(f"🔳 任务描述：{task.description}")
lines.append(f"📍 目标位置：{task.location_str}")
lines.append(f"👹 目标敌人：{task.enemy_name} Lv.{task.enemy_level}")
lines.append(f"💰 任务奖励：{task.get_reward_summary(bool(player.guild_id))}")
lines.append(f"📊 任务状态：{status_text}")

# 新增：显示导航快捷方式
if task.is_available() or task.is_accepted():
    lines.append(f"🧭 快捷导航：【导航 {task.target_x} {task.target_y}】")

lines.append("")
```

### 示例2: 接取任务自动导航（方案C）

**文件**: `plugins/xiuxian_game/daily_task/commands.py`

**修改位置**: Line 190-208

```python
# 原代码
if success:
    await uow.commit()
    msg = (
        f"🏛️ 缉邪司委托接取成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"📋 委托{task_index}：{task.title}\n"
        f"🔳 任务描述：{task.description}\n"
        f"📍 目标：{task.location_str}\n"
        f"👹 敌人：{task.enemy_name} Lv.{task.enemy_level}\n"
        f"💰 奖励：{task.get_reward_summary(bool(player.guild_id))}\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 请前往目标位置，使用【观察】查看鬼怪，击杀后使用【完成任务】"
    )
else:
    msg = f"⛔ {message}"

# 修改后
if success:
    # 检查是否需要自动导航
    auto_nav = "--导航" in args_text or "导航" in args_text

    if auto_nav:
        # 导入依赖
        from ..world.navigation import NavigationTask, _euclidean_distance
        from datetime import datetime

        # 计算初始距离
        player_x = player.real_world_x or player.x or 0
        player_y = player.real_world_y or player.y or 0
        initial_distance = _euclidean_distance(
            player_x, player_y, task.target_x, task.target_y
        )

        # 创建或更新导航任务
        nav_task = await uow.session.get(NavigationTask, player.id)
        if nav_task:
            nav_task.target_x = task.target_x
            nav_task.target_y = task.target_y
            nav_task.last_update = datetime.now()
            nav_task.initial_distance = initial_distance
        else:
            nav_task = NavigationTask(
                player_id=player.id,
                target_x=task.target_x,
                target_y=task.target_y,
                last_update=datetime.now(),
                initial_distance=initial_distance
            )
            uow.session.add(nav_task)

    await uow.commit()

    msg = (
        f"🏛️ 缉邪司委托接取成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"📋 委托{task_index}：{task.title}\n"
        f"🔳 任务描述：{task.description}\n"
        f"📍 目标：{task.location_str}\n"
        f"👹 敌人：{task.enemy_name} Lv.{task.enemy_level}\n"
        f"💰 奖励：{task.get_reward_summary(bool(player.guild_id))}\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 请前往目标位置，使用【观察】查看鬼怪，击杀后使用【完成任务】\n"
    )

    if auto_nav:
        msg += f"🧭 已自动设置导航至任务位置\n"
        msg += f"💡 使用【导航】查看进度 | 【中断导航】停止前进"
    else:
        msg += f"🧭 快捷导航：【导航 {task.target_x} {task.target_y}】"
else:
    msg = f"⛔ {message}"
```

### 示例3: 任务列表显示距离和预计时间（Phase 3）

**文件**: `plugins/xiuxian_game/daily_task/commands.py`

**修改位置**: Line 75-96

```python
# 新增导入
from ..world.navigation import _euclidean_distance, _tiles_per_second, _format_eta
from datetime import timedelta

# 修改显示逻辑
for i, task in enumerate(tasks, 1):
    # 原有状态判断代码...

    lines.append(f"{status_emoji} 【委托{i}】{task.title}")
    lines.append(f"🔳 任务描述：{task.description}")
    lines.append(f"📍 目标位置：{task.location_str}")

    # 新增：计算距离和预计时间
    player_x = player.real_world_x or player.x or 0
    player_y = player.real_world_y or player.y or 0
    distance = _euclidean_distance(player_x, player_y, task.target_x, task.target_y)

    # 获取有效敏捷值
    effective_attrs = await player.get_effective_attributes(session)
    effective_agility = effective_attrs.get("agility", player.agility)
    speed = _tiles_per_second(effective_agility)
    eta_seconds = distance / speed if speed > 0 else 0
    eta = _format_eta(timedelta(seconds=int(eta_seconds)))

    lines.append(f"📏 距离：{distance:.1f} 格 | ⏱️ 预计：{eta}")

    lines.append(f"👹 目标敌人：{task.enemy_name} Lv.{task.enemy_level}")
    lines.append(f"💰 任务奖励：{task.get_reward_summary(bool(player.guild_id))}")
    lines.append(f"📊 任务状态：{status_text}")

    # 导航快捷方式
    if task.is_available() or task.is_accepted():
        lines.append(f"🧭 快捷导航：【导航 {task.target_x} {task.target_y}】")

    lines.append("")
```

---

**报告版本**: 1.0
**报告完成日期**: 2025-12-03
**调查人员**: Scout Agent
