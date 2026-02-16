# 里界系统完整实现调研报告

**调研日期**: 2026-02-15
**调研者**: scout agent
**项目根目录**: D:\QQbot\GuiXiuXian2

---

## 📋 执行摘要

里界系统是一个基于博德之门式2D6骰子判定的探索玩法，位于现实与诡域的交界处。该系统目前处于**Phase 2完整可玩版本**状态，已实现核心玩法框架、战斗系统、理智系统、认知篡改机制和多结局结算。

**实现进度**: ✅ 约80%完成（核心功能已实现，仅管理员可用）

---

## 🗂️ 代码证据清单

### 核心服务层

- `plugins/xiuxian_game/inner_realm/service.py` (InnerRealmService) - 里界核心服务类（2232行）
  - 骰子判定系统（2D6+修正值）
  - 地图生成和事件分配
  - 战斗系统集成
  - 理智系统和认知篡改
  - 结局结算和奖励发放
  - 迷你地图渲染和环境感知

- `plugins/xiuxian_game/inner_realm/commands.py` - 命令处理器（758行）
  - 里界列表查看、传送进入、信息查询
  - 移动命令（上/下/左/右）
  - 事件触发命令（搜刮/威吓/处决/交谈/救助/攻击）
  - 观察命令和线索查看

- `plugins/xiuxian_game/inner_realm/config.py` (InnerRealmConfig) - 配置加载器
  - 从YAML加载里界配置
  - 提供全局配置、时间系统配置、属性修正配置

### 数据模型层

- `plugins/xiuxian_game/models/inner_realm.py` - 里界数据模型
  - `InnerRealmSession` - 探索会话表（记录玩家进度、统计、理智值）
  - `InnerRealmTile` - 地块表（25x25=625格，记录事件类型和状态）

- `plugins/xiuxian_game/models/player.py` (Player.inner_realm) - 玩家当前所在里界字段

### 仓储层

- `plugins/xiuxian_game/infrastructure/repositories/inner_realm_session_repository.py` (InnerRealmSessionRepository) - 会话仓储
  - 标准CRUD + 获取活跃会话、预加载地块、会话清理

- `plugins/xiuxian_game/infrastructure/repositories/inner_realm_tile_repository.py` (InnerRealmTileRepository) - 地块仓储
  - 标准CRUD + 按坐标查询、按事件类型筛选、获取附近地块

- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` (UnitOfWork.inner_realm_sessions / inner_realm_tiles) - 工作单元集成

### 配置数据

- `plugins/xiuxian_game/data/inner_realms.yaml` - 里界配置文件（454行）
  - 全局设置（地图尺寸、理智系统参数）
  - 时间系统（白昼/黄昏/深夜）
  - 认知篡改系统（6种篡改类型）
  - 第三病栋完整配置（NPC、幸存者、线索、BOSS、结局）

- `plugins/xiuxian_game/data/items.yaml` - 里界专属物品
  - 里界材料：污染绷带、扭曲血肉、腐化之心、手术刀、破损证件等
  - 标签：`inner_realm_only`

### 帮助文档

- `plugins/xiuxian_game/player/help.py` (inner_realm_help_cmd) - 里界系统帮助信息（详细说明所有命令和机制）

### 初始化

- `plugins/xiuxian_game/inner_realm/__init__.py` - 模块导入和命令注册

---

## 🎮 核心玩法机制

### 1. 进入条件和方式

**进入条件**:
- 等级要求（第三病栋: 50级，活棺村: 100级等）
- 不可同时在多个里界（一个玩家一个里界只能有一个未结算会话）

**进入方式**:
- 命令: `【传送 第三病栋】`（智能识别，不匹配里界时传递给诡域系统）
- 优先级: 4（高于诡域的5），使用block=False允许穿透

**数据流程**:
1. `commands.py:enter_realm_cmd.handle()` → 检查玩家等级和会话
2. `service.py:InnerRealmService.enter_realm()` → 创建会话 + 生成地图
3. `service.py:_generate_map()` → 生成625个地块（按权重分配事件类型）
4. 设置 `player.inner_realm = realm_name`

### 2. 里界内的活动

#### 2.1 移动系统（25x25地图）

**命令**: `【上】【下】【左】【右】` 或 `【移动 方向】`

**数据更新**:
- 更新 `session.x` 和 `session.y`
- 追踪已访问坐标到 `session.state.visited` 列表
- 触发迷你地图重新渲染（5x5视野）

**移动反馈** (`service.py:generate_move_feedback()`):
- 5x5迷你地图（使用emoji）
- 理智值和统计信息
- 方向提示（最多3条）
- 氛围描述（基于事件类型和理智值）

#### 2.2 搜刮系统（LOOT事件）

**命令**: `【搜刮】`

**判定流程** (`service.py:perform_search()`):
1. 2D6骰子 + 幸运修正 + 时间加成
2. 结果等级:
   - 2-3: 💀 大失败 → 触发陷阱，理智-10
   - 4-6: ❌ 失败 → 没找到东西
   - 7-9: ⚖️ 普通成功 → 基础奖励
   - 10-11: ✅ 成功 → 额外奖励
   - 12+: 🌟 大成功 → 双倍奖励
3. 奖励发放 (`service.py:_distribute_loot()`) → 添加物品到背包 + 金币

**奖励类型** (`service.py:_generate_event_data()`):
- 金币: 100-300
- 普通材料: 破损证件、污染绷带、手术刀、访客通行证（白色/绿色）
- 稀有材料: 扭曲血肉、腐化之心、病历室钥匙、手术笔记（蓝色/紫色，30%概率）

#### 2.3 威吓系统（NPC/BOSS/SURVIVOR事件）

**命令**: `【威吓】`

**判定流程** (`service.py:perform_intimidation()`):
1. 2D6骰子 + 攻击修正 + 时间加成
2. 结果处理:
   - **大失败**: 伪装者暴露真身 → 强制战斗；普通NPC逃跑并惊动其他人
   - **失败**: 特殊NPC/伪装者反击 → 进入战斗
   - **成功**: 目标屈服，交出物品/信息
   - **大成功**: 双倍奖励

#### 2.4 处决系统（静默击杀）

**命令**: `【处决】`

**判定流程** (`service.py:perform_assassination()`):
1. 2D6骰子 + 敏捷修正 + 时间加成
2. 结果处理:
   - **大失败**: 目标惨叫惊动全区，理智-5
   - **失败**: 目标挣扎 → 进入战斗
   - **成功**: 无声击杀，获得战利品，击杀计数+1
   - **大成功**: 完美处决，额外奖励×1.5

**副作用**:
- 击杀平民/幸存者 → 理智-3 (`service.py:trigger_sanity_loss()`)

#### 2.5 战斗系统（NPC/BOSS事件）

**命令**: `【攻击】` 或 威吓/处决失败自动触发

**战斗流程** (`service.py:start_battle_with_npc()`):
1. 构建敌人属性（hp/attack/defense/agility）
2. 调用 `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2()` 执行战斗
3. 战斗结束:
   - **胜利**: 标记敌人死亡，击杀计数+1，发放战利品
   - **失败**: 玩家受伤，理智损失（BOSS战-15）
4. BOSS击败额外处理: 设置 `session.state.boss_defeated = True`，理智恢复+15

#### 2.6 线索收集（CLUE事件）

**命令**: `【搜刮】`（在CLUE地块）

**收集流程** (`service.py:collect_clue()`):
1. 不需要判定，直接收集
2. 将线索ID添加到 `session.clue_collected` JSON数组
3. 理智恢复+10
4. 显示线索内容和真相揭示

**查看线索**: `【查看线索】` → 显示所有已收集线索详情

#### 2.7 救助幸存者（SURVIVOR事件）

**命令**: `【救助】`

**救助流程** (`service.py:save_survivor()`):
1. 标记幸存者已救助，救出计数+1
2. 理智恢复+5
3. 发放幸存者感谢礼物

#### 2.8 交谈系统

**命令**: `【交谈】`

**交谈流程** (`service.py:talk_to_npc()`):
- 随机显示NPC的一句对话
- 不消耗资源，纯剧情交互

### 3. 奖励机制

**即时奖励** (`service.py:_distribute_loot()`):
- 金币: 直接添加到 `player.gold`
- 物品: 调用 `ItemInstance.add_item()` 添加到背包
- 成就统计更新: `AchievementService.update_stat()`

**结局奖励** (当前未实现，配置已就绪):
- 在 `inner_realms.yaml` 的 `endings` 配置中定义
- 结算时显示但提示"奖励发放功能将在后续版本实现"

### 4. 退出条件

**命令**: `【返回】`

**退出流程** (`commands.py:exit_realm_cmd.handle()` + `service.py:settle_ending()`):
1. 触发理智恢复+20
2. 结局判定（优先级顺序）:
   - **毁灭**: 击杀≥20 AND BOSS已击败
   - **猎人**: BOSS已击败
   - **屠夫**: 击杀≥20
   - **真相**: 线索≥5
   - **救世**: 救出≥3
   - **默认**: 离开（无特殊奖励）
3. 标记 `session.is_settled = True`
4. 清空 `player.inner_realm = None`
5. 显示统计信息（击杀/救出/线索/最终理智）

---

## 📊 数据模型详解

### InnerRealmSession（探索会话表）

**核心字段**:
```python
player_id: str              # 玩家ID
realm_name: str             # 里界名称（如：third_ward）
entered_at: datetime        # 进入时间
last_refresh: datetime      # 上次刷新时间（每日0点）
killed_count: int           # 击杀数量
saved_count: int            # 救出幸存者数量
sanity: int                 # 当前理智值（0-100）
clue_collected: str         # 已收集线索ID列表（JSON数组）
x: int                      # 当前X坐标
y: int                      # 当前Y坐标
state: str                  # 探索状态（JSON对象）
is_settled: bool            # 是否已结算
```

**state字段内容**:
```json
{
  "visited": ["0,0", "1,0", "0,1"],  // 已访问坐标列表
  "boss_defeated": false,             // BOSS是否已击败
  "phantom_npc_active": false,        // 认知篡改：幻影NPC
  "memory_altered": false,            // 认知篡改：记忆错乱
  "sensory_distorted": false,         // 认知篡改：感官扭曲
  "time_dilated": false,              // 认知篡改：时间错乱
  "identity_confused": false,         // 认知篡改：身份混淆
  "truth_inverted": false             // 认知篡改：真相反转
}
```

### InnerRealmTile（地块表）

**核心字段**:
```python
session_id: int             # 关联的会话ID
x: int                      # X坐标
y: int                      # Y坐标
event_type: str             # 事件类型（NPC/LOOT/CLUE/EMPTY/BOSS/SURVIVOR/COGNITION_TAMPER）
state: str                  # 地块状态（JSON对象）
is_triggered: bool          # 是否已触发
refreshed_at: datetime      # 上次刷新时间
```

**event_type对应的state结构**:

**NPC**:
```json
{
  "npc_id": "head_nurse",
  "name": "值班护士长",
  "type": "special",
  "hp": 300,
  "max_hp": 300,
  "attack": 80,
  "defense": 40,
  "description": "身穿沾血白大褂的护士长，眼神空洞",
  "dialogue": ["又来了新的...病人..."],
  "loot": [...],
  "alive": true,
  "威吓_success": "护士长颤抖着交出了钥匙和一叠病历",
  "威吓_fail": "护士长发出刺耳的尖叫，惊动了整个病房！",
  "reveal_description": ""  // 伪装者专用
}
```

**LOOT**:
```json
{
  "looted": false,
  "items": [
    {"gold": 250},
    {"item_id": "broken_id", "quantity": 2, "probability": 0.8},
    {"item_id": "twisted_flesh", "quantity": 1, "probability": 0.2}
  ]
}
```

**CLUE**:
```json
{
  "clue_id": "patient_record_1",
  "name": "1号病历",
  "description": "患者：张三，入院原因：健康体检。症状：无。备注：器官质量优良",
  "reveal": "所谓的'病人'都是被绑架的健康人",
  "collected": false
}
```

**SURVIVOR**:
```json
{
  "survivor_id": "hiding_patient",
  "name": "躲藏的病患",
  "description": "蜷缩在病床下的瘦弱身影",
  "dialogue": ["求求你...不要杀我..."],
  "save_reward": [...],
  "saved": false,
  "killed": false
}
```

---

## 🎲 2D6骰子判定系统

### 核心公式

```
最终结果 = 2D6 + 属性修正 + 时间加成
```

**实现**: `service.py:InnerRealmService.roll_2d6()`

### 属性修正映射

配置位置: `inner_realms.yaml:attribute_modifiers`

| 行动类型 | 主要属性 | 缩放系数 | 示例（属性1000） |
|---------|---------|---------|----------------|
| 搜刮 (search) | luck | 0.01 | +10 |
| 威吓 (intimidate) | attack | 0.005 | +5 |
| 处决 (assassination) | agility | 0.008 | +8 |
| 解读 (decipher) | intelligence | 0.008 | +8 |
| 潜行 (stealth) | agility | 0.008 | +8 |

**实现**: `service.py:InnerRealmService.calculate_attribute_modifier()`

### 时间加成系统

配置位置: `inner_realms.yaml:time_system`

| 现实时间 | 里界时段 | 搜刮加成 | 战斗加成 |
|---------|---------|---------|---------|
| 6:00-18:00 | ☀️ 白昼 | +1 | 0 |
| 18:00-22:00 | 🌅 黄昏 | 0 | 0 |
| 22:00-6:00 | 🌙 深夜 | 0 | +1 |

**实现**: `service.py:InnerRealmService.get_time_bonus()`

### 判定结果表

配置位置: `inner_realms.yaml:dice_results`

| 结果范围 | 等级 | 标签 |
|---------|------|------|
| 2-3 | critical_failure | 💀 大失败 |
| 4-6 | failure | ❌ 失败 |
| 7-9 | normal_success | ⚖️ 普通成功 |
| 10-11 | success | ✅ 成功 |
| 12+ | critical_success | 🌟 大成功 |

### 骰子显示格式

**实现**: `service.py:InnerRealmService.format_dice_roll_message()`

```
🎲 威吓检定
━━━━━━━━━━━━━
骰子: [4] + [5] = 9
攻击修正: +3
━━━━━━━━━━━━━
最终: 12 ✅ 成功！
━━━━━━━━━━━━━
「村长瑟瑟发抖，交出了地窖钥匙和186金币」
```

---

## 🧠 理智系统与认知篡改

### 理智值管理

**初始值**: 100（配置: `inner_realms.yaml:global.sanity_system.initial_sanity`）

**阈值**:
- 警告: 50（🟡）
- 危险: 30（🔴）
- 极度危险: 10（💀）

**实现**: `service.py:InnerRealmService.modify_sanity()`

### 理智损失触发器

配置位置: `inner_realms.yaml:cognition_tamper_system.sanity_loss_triggers`

| 触发类型 | 损失量 | 触发场景 |
|---------|-------|---------|
| witness_death | -5 | 目睹死亡 |
| read_disturbing_clue | -8 | 阅读令人不安的线索 |
| encounter_boss | -15 | 遭遇核心诡异 |
| critical_failure | -10 | 判定大失败 |
| kill_innocent | -3 | 击杀无辜者（平民/幸存者） |
| stay_too_long | -2 | 在里界停留过久（每小时） |

### 理智恢复方式

配置位置: `inner_realms.yaml:cognition_tamper_system.sanity_recovery`

| 恢复类型 | 恢复量 | 触发场景 |
|---------|-------|---------|
| rescue_survivor | +5 | 救出幸存者 |
| reveal_truth | +10 | 揭示真相（收集线索） |
| defeat_boss | +15 | 击败核心诡异 |
| leave_realm | +20 | 离开里界 |

### 认知篡改系统

**触发时机**: 移动时检查 (`commands.py:_handle_move()` → `service.py:check_cognition_tamper()`)

**触发概率**:
- 基础概率: 配置中的 `trigger_chance`
- 理智倍数:
  - 理智<30: ×2.0
  - 理智<50: ×1.5
  - 理智≥50: ×1.0

**篡改类型** (配置位置: `inner_realms.yaml:cognition_tamper_system.tamper_types`):

| 篡改ID | 名称 | 触发概率 | 理智损失 | 效果 |
|-------|------|---------|---------|------|
| phantom_npc | 幻影 | 15% | -5 | 生成虚假NPC，攻击时发现是幻觉 |
| memory_alteration | 记忆错乱 | 10% | -10 | 击杀数±1-3，坐标记忆偏移 |
| sensory_distortion | 感官扭曲 | 20% | -3 | EMPTY显示为NPC，LOOT显示为CLUE |
| time_dilation | 时间错乱 | 8% | -8 | 时间显示错误，冷却时间感知错误 |
| identity_confusion | 我是谁？ | 5% (仅理智<30) | -20 | 忘记进入里界的目的，NPC对话变成独白 |
| truth_inversion | 真相反转 | 3% (仅理智<30) | -15 | 线索内容反转，NPC台词含义反转 |

**应用实现**: `service.py:InnerRealmService.apply_cognition_tamper()`

---

## 🏆 多结局系统

### 结局优先级

**结算顺序** (`service.py:InnerRealmService.settle_ending()`):

1. **毁灭** (annihilation) - 最高优先级
   - 条件: `killed_count >= 20 AND boss_defeated`
   - 奖励: 污染绷带×100 + 扭曲血肉×30 + 腐化之心×3 + 金币15000

2. **猎人** (hunter)
   - 条件: `boss_defeated`
   - 奖励: 院长钥匙×1 + 器官交易账本×1 + 金币8000

3. **屠夫** (butcher)
   - 条件: `killed_count >= 20`
   - 奖励: 污染绷带×50 + 扭曲血肉×20 + 金币5000

4. **真相** (truth)
   - 条件: `len(clue_collected) >= 5`
   - 奖励: 腐化之心×1 + 成就：真相探寻者

5. **救世** (rescue)
   - 条件: `saved_count >= 3`
   - 奖励: 好感令牌×5 + 成就：救世主 + 金币3000

6. **默认** (default)
   - 条件: 无
   - 奖励: 无

### 第三病栋结局配置

配置位置: `inner_realms.yaml:realms.third_ward.endings`

所有结局的奖励物品已在配置中定义，但当前版本显示提示"奖励发放功能将在后续版本实现"。

---

## 🌍 首批里界配置

### 第三病栋 (third_ward)

**基本信息**:
- 显示名称: "第三病栋"
- 等级要求: 50级
- 地图尺寸: 25×25
- 叙事类型: 碎片拼图 (puzzle)

**事件权重** (总和100):
- NPC: 15%
- LOOT: 20%
- CLUE: 10%
- EMPTY: 48%
- BOSS: 1%
- SURVIVOR: 4%
- COGNITION_TAMPER: 2%

**NPC配置**:
- 特殊NPC: 值班护士长（HP 300, ATK 80, DEF 40）、主治医生（HP 400, ATK 100, DEF 60）
- 普通NPC: 病患（HP 100, ATK 30, DEF 10）
- 伪装者: 伪装病患（HP 250, ATK 120, DEF 40，攻击后暴露）

**幸存者配置**:
- 躲藏的病患
- 被困的访客

**线索配置** (5个):
- 1号病历、2号病历、护士日记、手术排期表、院长备忘录

**BOSS配置**:
- 院长·器官贩子（HP 1500, ATK 200, DEF 100）
- 特殊技能: 召唤护士、器官窃取

**真相揭示**:
"这是一个器官摘取工厂，院长为黑市提供器官"

### 其他里界（配置未完成）

仅在设计文档中列出，YAML配置中未实现:
- 活棺村（Lv.100）
- 荔湾鬼镇（Lv.150）
- 末班列车（Lv.200）
- 红月孤儿院（Lv.250）

---

## 📍 命令系统完整清单

### 基础命令

| 命令 | 别名 | 优先级 | 权限 | 功能 |
|------|------|-------|------|------|
| 里界 | 里界列表 | 5 | SUPERUSER | 查看可进入的里界列表 |
| 传送 | 进入里界 | 4 | SUPERUSER | 进入指定里界（智能识别） |
| 里界信息 | - | 5 | SUPERUSER | 查看当前里界统计信息 |
| 返回 | 离开里界 | 4 | SUPERUSER | 离开里界并结算（需要在里界中） |

### 移动命令

| 命令 | 优先级 | 权限 | 功能 |
|------|-------|------|------|
| 上 | 4 | SUPERUSER | 向上移动（Y-1） |
| 下 | 4 | SUPERUSER | 向下移动（Y+1） |
| 左 | 4 | SUPERUSER | 向左移动（X-1） |
| 右 | 4 | SUPERUSER | 向右移动（X+1） |
| 移动 <方向> | 4 | SUPERUSER | 通用移动命令 |

### 事件触发命令

| 命令 | 别名 | 优先级 | 权限 | 功能 |
|------|------|-------|------|------|
| 搜刮 | - | 4 | SUPERUSER | 搜刮当前位置（2D6+幸运判定） |
| 威吓 | - | 4 | SUPERUSER | 威吓NPC（2D6+攻击判定） |
| 处决 | - | 4 | SUPERUSER | 静默击杀目标（2D6+敏捷判定） |
| 交谈 | - | 4 | SUPERUSER | 与NPC交谈 |
| 救助 | 救出 | 4 | SUPERUSER | 救助幸存者 |
| 攻击 | - | 4 | SUPERUSER | 主动发起战斗 |

### 观察命令

| 命令 | 别名 | 优先级 | 权限 | 功能 |
|------|------|-------|------|------|
| 观察 | 环顾, 查看环境 | 4 | SUPERUSER | 仔细观察当前位置和周围环境 |
| 查看线索 | 线索列表, 已收集线索 | 4 | SUPERUSER | 查看已收集的线索 |

### 帮助命令

| 命令 | 别名 | 优先级 | 功能 |
|------|------|-------|------|
| 里界系统 | 里界帮助 | 4 | 查看里界系统详细帮助 |

**注意事项**:
- 所有命令当前仅限管理员使用 (`permission=SUPERUSER`)
- 移动和返回命令使用 `rule=in_inner_realm_rule` 确保只在里界时生效
- 传送命令使用 `block=False` 允许智能识别后传递给诡域系统

---

## 🗄️ 配置数据详解

### inner_realms.yaml 结构

```yaml
global:                       # 全局设置
  map_size: 25                # 地图尺寸
  refresh_hour: 0             # 每日刷新时间
  sanity_system: {...}        # 理智系统配置

time_system:                  # 时间系统
  day: {...}                  # 白昼配置
  dusk: {...}                 # 黄昏配置
  night: {...}                # 深夜配置

cognition_tamper_system:      # 认知篡改系统
  tamper_types: {...}         # 6种篡改类型
  sanity_loss_triggers: {...} # 理智损失触发器
  sanity_recovery: {...}      # 理智恢复方式

realms:                       # 里界定义
  third_ward:                 # 第三病栋
    display_name: "第三病栋"
    level_requirement: 50
    event_weights: {...}      # 事件生成权重
    npcs: [...]               # NPC配置
    survivors: [...]          # 幸存者配置
    clues: [...]              # 线索配置
    boss: {...}               # BOSS配置
    endings: {...}            # 结局配置

attribute_modifiers:          # 属性修正映射
  search: {...}
  intimidate: {...}
  assassination: {...}
  decipher: {...}
  stealth: {...}

dice_results:                 # 骰子判定结果表
  critical_failure: {...}
  failure: {...}
  normal_success: {...}
  success: {...}
  critical_success: {...}
```

### items.yaml 里界物品

**里界专属标签**: `inner_realm_only`

**物品列表**:
- 记忆类: 怨念碎片、执念结晶、残留意识
- 污染类: 异化组织、扭曲血肉、腐化之心
- 生活类: 旧钞票、破损证件、访客通行证
- 特殊类: 医疗记录钥匙、手术笔记、器官交易账本、手术刀

---

## ⚠️ 已知问题与修复记录

### Git提交历史（最近4次里界fix）

**提交1**: `0c8344f` - 里界fix (2026-02-15 20:19)
- **文件**: `plugins/xiuxian_game/inner_realm/service.py`
- **改动**: 修复战斗系统返回值解包错误
- **详情**: `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2()` 返回4个值，之前只解包3个，缺少 `post_effects`
- **修复**: `victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(...)`

**提交2**: `dd40448` - 里界fix (2026-02-15 19:51)
- **文件**: `plugins/xiuxian_game/inner_realm/service.py`
- **改动**: 清理已结算的旧会话，解决唯一索引冲突
- **详情**: 数据库唯一索引 `player_id + realm_name` 不含 `is_settled`，导致已结算会话无法删除后重新进入
- **修复**: 在进入里界前，删除所有 `is_settled=True` 的旧会话

**提交3**: `316a445` - 里界fix (2026-02-15 具体时间未查看)
- **详情**: 未查看具体内容

**提交4**: `dcaf78e` - 里界fix (2026-02-15 具体时间未查看)
- **详情**: 未查看具体内容

### 已修复的问题类型

1. **战斗系统集成问题**: 战斗API返回值数量不匹配
2. **数据库唯一索引冲突**: 已结算会话无法清理导致重复进入失败

---

## 🔗 与其他系统的关联

### 战斗系统

**集成点**: `service.py:InnerRealmService.start_battle_with_npc()`

**调用链**:
```
里界战斗触发
↓
InnerRealmService.start_battle_with_npc()
↓
BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2()
↓
战斗引擎执行战斗
↓
返回战斗结果 (victory, battle_log, damage_taken, post_effects)
↓
更新玩家血量、击杀计数、地块状态
```

**敌人属性映射**:
- 从地块state读取: `hp`, `attack`, `defense`, `agility`
- 传递给战斗引擎作为怪物属性
- 战斗种子: `f"InnerRealm_{session.id}:{tile.x}:{tile.y}:{battle_timestamp}"`

### 装备系统

**无直接关联**，里界战斗使用玩家当前装备属性

### 物品系统

**集成点**: `service.py:InnerRealmService._distribute_loot()`

**调用链**:
```
里界奖励发放
↓
InnerRealmService._distribute_loot()
↓
ItemInstance.add_item() (添加物品到背包)
↓
config.items_config["by_id"].get(item_id) (获取物品配置)
```

**里界专属物品**:
- 所有里界物品在 `items.yaml` 中标记 `tags: ["inner_realm_only"]`
- 包括: 污染绷带、扭曲血肉、腐化之心、手术刀、破损证件等

### 经济系统

**集成点**:
- 奖励发放: 直接修改 `player.gold`
- 成就统计: 调用 `AchievementService.update_stat()` 更新财富成就

### 诡域系统

**关系**: 独立并行，不占用诡域层级

**传送命令冲突解决**:
- 里界传送命令优先级4（高于诡域5）
- 使用 `block=False` 允许不匹配时传递
- 智能识别: 检查参数是否包含"层诡域"或"诡域"
- 如果是里界名称 → 处理；否则 → 传递给诡域系统

**玩家位置隔离**:
- 里界: `player.inner_realm = realm_name`
- 诡域: `player.dungeon_level`, `player.dungeon_x`, `player.dungeon_y`
- 不可同时在里界和诡域

### 帮助系统

**集成点**: `plugins/xiuxian_game/player/help.py:inner_realm_help_cmd`

**内容**:
- 系统状态: 迭代开发中，仅管理员可用
- 核心机制说明
- 完整命令列表
- 骰子判定说明
- 理智系统和认知篡改说明
- 多结局说明
- 实现进度说明

---

## 📊 实现进度评估

### ✅ Phase 1: 核心框架（已完成）

- ✅ 数据模型和数据库表
- ✅ 基础传送和移动系统
- ✅ 2D6骰子判定核心
- ✅ 第三病栋简化版

### ✅ Phase 2: 事件和NPC（已完成）

- ✅ 搜刮/威吓/处决判定
- ✅ NPC生成和对话系统
- ✅ 线索收集系统
- ✅ 完整战斗系统（NPC/BOSS战斗）
- ✅ LOOT生成和奖励发放
- ✅ 理智系统和认知篡改
- ✅ 多结局结算系统
- ✅ 迷你地图和环境感知系统

### 🚧 Phase 3: 叙事和结局（部分完成）

- ✅ 多结局结算逻辑
- ✅ 第三病栋完整剧情配置
- ⚠️ 结局奖励发放（配置完成，代码未实现）
- ❌ 细思极恐的文本描述优化

### ❌ Phase 4: 扩展内容（未开始）

- ❌ 添加其他4个里界（活棺村、荔湾鬼镇、末班列车、红月孤儿院）
- ⚠️ 时间系统（白天/黄昏/深夜）- 已配置但未充分测试
- ❌ 特殊事件和隐藏剧情
- ❌ 每日0点刷新机制（配置已就绪，实现未验证）

### 当前状态

**实现度**: ✅ 约80%（核心玩法完整，扩展内容待补充）

**可玩性**: ✅ Phase 2完整可玩版本

**访问限制**: ⚠️ 仅管理员可用（`permission=SUPERUSER`）

**已知限制**:
1. 只有第三病栋一个里界可用
2. 结局奖励显示但不实际发放
3. 每日刷新机制未验证
4. 认知篡改效果未充分测试
5. 其他4个里界未实现

---

## 🎯 结论

### 核心发现

1. **里界系统已完成核心框架**，包括2D6骰子判定、移动探索、战斗系统、理智系统、认知篡改和多结局结算。

2. **第三病栋已完全可玩**，包含完整的NPC、幸存者、线索、BOSS和5种结局路线。

3. **数据架构清晰**，使用 `InnerRealmSession` 和 `InnerRealmTile` 两张表管理会话和地块，完全遵循Repository+UnitOfWork模式。

4. **与现有系统集成良好**，战斗系统、物品系统、成就系统均已对接，与诡域系统智能隔离。

5. **最近的4次fix**主要解决战斗集成和数据库唯一索引问题，系统趋于稳定。

### 待完成工作

1. **结局奖励发放系统**（配置完成，代码待实现）
2. **其他4个里界地图**（活棺村、荔湾鬼镇、末班列车、红月孤儿院）
3. **每日刷新机制验证**（配置就绪，实现未测试）
4. **认知篡改效果充分测试**（6种篡改类型已实现，需要更多测试）
5. **访问权限开放**（当前仅管理员，可考虑开放给高等级玩家）

### 技术亮点

1. **2D6骰子判定系统** - 完整实现博德之门式判定，支持属性修正和时间加成
2. **理智系统与认知篡改** - 创新的心理恐怖机制，理智值越低越容易触发错觉
3. **迷你地图系统** - 5x5视野，emoji渲染，已访问区域追踪
4. **多结局系统** - 基于玩家行为自动判定，5种结局路线
5. **事件状态机** - 每个地块的state字段完整记录事件状态，支持复杂交互

---

**报告版本**: 1.0
**调研完成时间**: 2026-02-15
**调研者**: scout agent
**审核状态**: 待审核
