# 每日委托系统NPC匹配问题调查报告

**调查日期**: 2025-12-10
**问题类型**: 每日委托系统重名NPC无法区分
**严重程度**: 中等（影响玩家完成任务）

---

## 问题描述

每日委托系统会在地图随机位置生成鬼怪NPC，玩家通过名字攻击NPC，但当同一位置出现多个重名NPC时，无法区分和指定攻击目标。

---

## Code Sections (The Evidence)

### 每日委托系统实现

- `plugins/xiuxian_game/models/daily_task.py` (DailyTask模型): 每日任务数据模型，包含任务信息、目标坐标、敌人属性等字段
- `plugins/xiuxian_game/daily_task/service_new.py:59-131` (DailyTaskService.generate_daily_task): 生成每日委托任务，包括随机坐标、鬼怪名称、敌人属性计算
- `plugins/xiuxian_game/daily_task/service_new.py:198-214` (DailyTaskService.accept_task): 接取任务时在目标位置创建鬼怪NPC
- `plugins/xiuxian_game/daily_task/service_new.py:292-348` (DailyTaskService.create_ghost_npc_for_task): 为委托任务创建鬼怪NPC的核心方法

### NPC生成与命名

- `plugins/xiuxian_game/daily_task/service_new.py:22-28` (GHOST_NAMES常量): 包含50个真实中文名字作为鬼怪名字池
- `plugins/xiuxian_game/daily_task/service_new.py:472-488` (_generate_task_title_and_enemy): 根据任务类型生成敌人名称，格式为"类型前缀·真实名字"（如"邪教徒·乔强"）
- `plugins/xiuxian_game/daily_task/service_new.py:295-297` (npc_id生成): 使用`f"ghost_task_{task.id}"`作为NPC唯一标识

### NPC攻击系统

- `plugins/xiuxian_game/world/attack_command.py:164-257` (handle_attack): 攻击命令的主处理函数，支持按名称或UID攻击
- `plugins/xiuxian_game/world/attack_command.py:259-339` (parse_attack_target): 解析攻击目标，先尝试UID，再尝试名称精确匹配
- `plugins/xiuxian_game/world/attack_command.py:342-394` (find_npc_by_smart_match): 智能NPC名称匹配，支持部分匹配和带点号的名字

### NPC名称匹配逻辑

- `plugins/xiuxian_game/world/attack_command.py:326-332` (精确匹配): 使用`NPCService.get_npc_by_name()`进行精确名称匹配
- `plugins/xiuxian_game/world/attack_command.py:329-337` (智能匹配): 当精确匹配失败时，调用`find_npc_by_smart_match()`进行模糊匹配
- `plugins/xiuxian_game/world/attack_command.py:361-368` (匹配策略): 支持三种匹配模式：包含目标名称、点号后部分匹配、点号前部分匹配
- `plugins/xiuxian_game/world/attack_command.py:236-254` (多匹配提示): 当找到多个匹配结果时，显示前5个NPC并提示使用更具体的名称

### NPC数据查询

- `plugins/xiuxian_game/infrastructure/repositories/npc_repository.py:52-69` (get_by_name): 按名称精确查询NPC，仅返回单个结果
- `plugins/xiuxian_game/infrastructure/repositories/npc_repository.py:71-98` (get_by_location): 按地点查询所有NPC，可按类型过滤
- `plugins/xiuxian_game/infrastructure/repositories/npc_repository.py:127-153` (find_by_partial_name): 模糊查询NPC名称，返回匹配列表

### NPC模型

- `plugins/xiuxian_game/models/npc.py:34-100` (NPC模型): NPC数据模型，包含id、npc_id、name、npc_type、location_id等字段
- `plugins/xiuxian_game/models/npc.py:38-39` (唯一标识): `npc_id`为字符串类型的唯一标识符（如"ghost_task_123"），`id`为数据库自增主键

---

## Report (The Answers)

### result

**问题根源分析**：

1. **重名NPC生成**: 每日委托系统从固定的50个真实名字池中随机选择，多个任务可能生成相同名字的鬼怪（如"邪教徒·乔强"）

2. **名字匹配机制**:
   - 精确匹配（`get_by_name`）：仅返回第一个匹配的NPC，无法处理重名
   - 智能匹配（`find_npc_by_smart_match`）：支持模糊匹配和部分匹配，但当匹配到多个NPC时，只显示前5个并提示使用更具体名称

3. **无法区分原因**:
   - NPC按名称匹配时使用`name`字段（如"邪教徒·乔强"）
   - 当同一地点有多个同名NPC时，精确匹配只能返回第一个
   - 智能匹配虽能找到所有同名NPC，但没有提供进一步区分的方式
   - 玩家无法通过名称区分两个"邪教徒·乔强"

4. **NPC唯一标识**:
   - 每个NPC都有唯一的`npc_id`（如"ghost_task_123"）和自增`id`
   - 攻击命令支持按UID攻击玩家，但不支持按npc_id攻击NPC

### conclusions

1. **名字池过小导致高重名率**: 50个名字 × 6种任务类型 = 300种组合，在高频委托场景下容易重名

2. **攻击系统设计缺陷**: 攻击命令仅支持按`name`匹配NPC，没有按`npc_id`或位置编号的机制

3. **智能匹配的局限性**: 虽然实现了模糊匹配和多结果提示，但无法解决重名NPC的区分问题

4. **缺少唯一标识符的用户接口**: NPC的`npc_id`和`id`字段可以唯一标识，但没有暴露给玩家使用

5. **观察命令未显示NPC唯一标识**: `plugins/xiuxian_game/world/real_world_explore.py`中的观察命令仅显示NPC名称，不显示编号或ID

### relations

**数据流关系**：

```
每日委托系统流程:
1. DailyTaskService.generate_daily_task()
   → 随机选择鬼怪名字（从GHOST_NAMES池）
   → 生成任务标题和敌人名称（"类型·名字"）
   → 创建DailyTask记录

2. DailyTaskService.accept_task()
   → DailyTaskService.create_ghost_npc_for_task()
   → NPCService.create_ghost_npc()
   → 在目标位置创建NPC（npc_id="ghost_task_{task.id}"）

攻击NPC流程:
3. attack_command.handle_attack()
   → parse_attack_target()
   → 先尝试UID匹配（仅玩家）
   → 再尝试名称精确匹配（NPCService.get_npc_by_name）
   → 失败时尝试智能匹配（find_npc_by_smart_match）
   → 多个匹配结果时显示前5个

4. NPCRepository.get_by_name()
   → 使用`NPC.name == name`精确匹配
   → 仅返回第一个结果（scalar_one_or_none）
   → 无法处理重名情况

5. find_npc_by_smart_match()
   → 使用LIKE模糊匹配和点号分隔符匹配
   → 返回所有匹配的NPC列表
   → 按匹配优先级排序
```

**问题触发链路**：

```
触发条件:
- 玩家在同一位置接取多个每日委托
- 或者附近2格内有其他玩家的委托NPC
- 随机生成的NPC名字相同（如都是"乔强"）

导致结果:
→ 两个"邪教徒·乔强"出现在附近
→ 玩家使用【攻击 邪教徒·乔强】
→ parse_attack_target()调用get_by_name()
→ 只返回第一个匹配的NPC
→ 玩家可能攻击了错误的NPC（不是自己任务的目标）
→ 完成任务时检查npc_id，发现不是任务目标NPC
→ 任务无法完成
```

**核心矛盾**：
- **唯一性保证层面**: NPC在数据库层面有唯一的`npc_id`（ghost_task_123）和`id`（数据库主键）
- **用户交互层面**: 玩家只能通过`name`字段攻击，该字段不保证唯一性
- **设计脱节**: 系统有唯一标识符但未暴露给用户使用

---

## 解决方案建议

### 方案1：扩大名字池（最简单）
- 将GHOST_NAMES从50个扩大到200+个
- 或者在名字后添加随机编号（如"乔强#1"、"乔强#2"）
- **优点**: 改动最小，只需修改名字生成逻辑
- **缺点**: 治标不治本，无法彻底解决重名问题

### 方案2：观察命令显示NPC编号（推荐）
- 在【观察】命令中为NPC分配临时编号（1、2、3...）
- 攻击命令支持【攻击 #1】或【攻击 编号1】
- LocationService维护当前地点的NPC编号映射
- **优点**: 用户友好，不改变NPC命名规则
- **缺点**: 需要维护临时编号映射关系

### 方案3：支持npc_id攻击（最彻底）
- 攻击命令支持【攻击 ghost_task_123】
- 观察命令显示NPC的npc_id
- **优点**: 使用系统已有的唯一标识符，最准确
- **缺点**: npc_id对用户不友好（如"ghost_task_123"）

### 方案4：任务关联优先匹配（业务优化）
- 完成任务时优先匹配玩家自己任务的NPC
- 在parse_attack_target中增加任务关联检查
- 如果玩家有已接取的任务，优先返回任务关联的NPC
- **优点**: 符合业务逻辑，玩家更可能攻击自己任务的NPC
- **缺点**: 无法解决一个玩家接取多个重名任务的情况

---

## 相关文件清单

**核心文件**（需要修改）:
- `plugins/xiuxian_game/daily_task/service_new.py` - 每日任务服务（名字生成）
- `plugins/xiuxian_game/world/attack_command.py` - 攻击命令（NPC匹配）
- `plugins/xiuxian_game/world/real_world_explore.py` - 观察命令（NPC显示）
- `plugins/xiuxian_game/infrastructure/repositories/npc_repository.py` - NPC仓储（查询方法）

**相关文件**（可能需要参考）:
- `plugins/xiuxian_game/models/npc.py` - NPC数据模型
- `plugins/xiuxian_game/models/daily_task.py` - 每日任务数据模型
- `plugins/xiuxian_game/world/npc_service_new.py` - NPC服务类
- `plugins/xiuxian_game/world/location_service.py` - 地点服务类
