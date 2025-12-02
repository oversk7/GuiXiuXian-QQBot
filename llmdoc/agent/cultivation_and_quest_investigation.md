# 诡修仙修炼系统与新手任务系统调研报告

**调研日期**: 2025-12-02
**调研类型**: 代码实现调研
**调研目标**: 为优化修炼输出和实现新手任务链提供技术依据

---

## Code Sections (Evidence)

### 修炼系统核心代码

- `plugins/xiuxian_game/cultivate/core.py` (handle_cultivate): 修炼主逻辑，包含修炼经验计算、加成系统、冷却检查、闭关状态检查
- `plugins/xiuxian_game/cultivate/core.py:19-33` (CULTIVATE_FLAVOR_TEXTS): 修炼文案池，12条诡异氛围描述
- `plugins/xiuxian_game/cultivate/core.py:36-57` (SECLUSION_FLAVOR_TEXTS, OUT_SECLUSION_FLAVOR_TEXTS): 闭关和出关文案池
- `plugins/xiuxian_game/cultivate/core.py:80-234` (handle_cultivate): 修炼指令处理函数，包含完整的经验计算和输出构建
- `plugins/xiuxian_game/cultivate/core.py:112-191` (经验计算逻辑): 基础经验+月卡加成+转数加成+公会加成+阴宅加成的计算公式
- `plugins/xiuxian_game/cultivate/core.py:200-234` (修炼消息构建): 构建包含加成提示的修炼输出消息
- `plugins/xiuxian_game/cultivate/core.py:236-349` (handle_seclusion): 闭关逻辑，包含效率加成、棺材钉系统
- `plugins/xiuxian_game/cultivate/core.py:352-end` (handle_breakthrough): 突破逻辑，包含成功率计算、怨念消耗、棺材钉护航

### 修炼配置文件

- `plugins/xiuxian_game/data/config.yaml:38-62` (cultivate配置): 冷却时间300秒、基础经验50、突破成功率配置、属性基础增量
- `plugins/xiuxian_game/data/config.yaml:12-15` (reincarnation配置): 冥返机制的修炼和闭关效率加成配置（每转50%）

### 经验计算工具函数

- `plugins/xiuxian_game/utils.py:20-35` (calculate_level_up_exp): 升级所需经验计算，使用混合曲线（前期线性，后期指数）

### 消息格式化工具

- `plugins/xiuxian_game/utils.py:11-16` (message_add_head): 统一消息头函数，添加"『诡修仙』\n"前缀

### 新手任务系统代码

- `plugins/xiuxian_game/daily_task/commands.py` (handle_daily_task): 每日委托指令处理，查看任务列表
- `plugins/xiuxian_game/daily_task/commands.py:26-100` (daily_task_cmd): 任务列表查看命令，显示任务状态、奖励、进度
- `plugins/xiuxian_game/models/daily_task.py` (DailyTask): 每日任务数据模型，包含任务类型、目标坐标、敌人信息、奖励
- `plugins/xiuxian_game/models/daily_task.py:9-16` (TaskType): 任务类型枚举，6种任务类型（鬼怪消除、笔仙案件、伪仙邪教等）
- `plugins/xiuxian_game/models/daily_task.py:19-24` (TaskStatus): 任务状态枚举（可接取、已接取、已完成、已过期）
- `plugins/xiuxian_game/models/daily_task.py:118-136` (get_reward_summary): 奖励摘要方法，格式化任务奖励信息
- `plugins/xiuxian_game/daily_task/service.py:18-113` (DailyTaskService.generate_daily_task): 生成每日任务逻辑，包含随机坐标、敌人属性计算、奖励计算
- `plugins/xiuxian_game/daily_task/service.py:24-30` (GHOST_NAMES): 鬼怪真人名字池（50个）
- `plugins/xiuxian_game/daily_task/service.py:32-35` (CITY_NAMES): 城市名称池（16个古代城市名）

### 帮助系统和输出参考

- `plugins/xiuxian_game/player/help.py:23-47` (handle_help): 帮助系统主菜单，展示系统分类
- `plugins/xiuxian_game/player/help.py:342-363` (修炼系统帮助): 修炼系统的帮助文本，包含所有功能说明
- `plugins/xiuxian_game/player/help.py:687-715` (委托系统帮助): 委托系统的帮助文本，包含任务流程说明

### AI引导系统

- `plugins/xiuxian_game/ai_guide.py` (AI Guide): AI引导系统，包含完整的数据库Schema说明和指令说明
- `plugins/xiuxian_game/ai_guide.py:58-150` (DATABASE_SCHEMA): Player表的87个字段详细说明，包含基础信息、战斗属性、坐标系统等

### 配置和物品数据

- `plugins/xiuxian_game/data/items.yaml:3-17` (回春散、凝神草): 基础恢复药品，价格100金币，恢复40 HP/MP
- `plugins/xiuxian_game/data/items.yaml:86-91` (棺材钉): 修炼加成道具，闭关效率加成（最多100根，50%加成）

---

## Report (Answers)

### 1. 修炼系统调研

#### 1.1 修炼指令处理文件

**核心文件**: `plugins/xiuxian_game/cultivate/core.py`

**关键命令注册**:
- `cultivate = on_command("修炼", block=True, priority=5)` (Line 70)
- `seclusion = on_command("闭关", block=True, priority=5)` (Line 71)
- `out_seclusion = on_command("出关", block=True, priority=5)` (Line 72)
- `breakthrough = on_command("突破", block=True, priority=5)` (Line 73)

#### 1.2 修炼输出逻辑

**当前输出构建位置**: `core.py:200-234` (handle_cultivate函数内部)

**输出逻辑流程**:
1. **随机文案选择**: 从12条CULTIVATE_FLAVOR_TEXTS中随机选择一条诡异氛围描述 (Line 222)
2. **加成消息构建**: 根据实际加成值构建bonus_msg字符串 (Lines 200-219)
   - 月卡加成: `✧ 月卡加成 💳 +{card_bonus} 怨炁 (+{efficiency_percent:.0f}%)`
   - 转数加成: `✧ 转数加成 🌟 +{reincarnation_bonus} 怨炁 (+{reincarnation_percent:.0f}%)`
   - 公会加成: `✧ 公会加成 🏰 +{guild_bonus} 怨炁 (+{guild_percent:.1f}%)`
   - 阴宅加成: `✧ 阴宅加成 🏚️ +{mansion_bonus} 怨炁 (+{mansion_percent:.1f}%)`
   - 阴宅费用: `✧ 阴宅费用 💰 {payment_msg}`
3. **最终输出格式** (Lines 224-233):
```
{flavor_text}
━━━━━━━━━━━━━
✧ 汲取怨炁 + {exp_gain}↑
{bonus_msg}
✧ 修为残烛 {player.exp}↑/{exp_max} (可突破)
━━━━━━━━━━━━━
⬇️ 【[连续]突破】倾听骨骼断裂
⬇️ 【加点】缝合裂隙，塑形新肉
```

**输出特点**:
- 使用了大量诡异氛围的诗意文案
- 使用emoji增强视觉效果（✧、💳、🌟、🏰、🏚️、💰）
- 使用Unicode符号作为分隔线（━）
- 有条件显示加成信息（只有当加成>0时才显示）
- 包含下一步操作提示

#### 1.3 修炼经验计算和加成逻辑

**计算位置**: `core.py:112-191`

**基础经验计算** (Lines 112-115):
```python
k = 7 if player.level <= 10 else 6
base_gain = cfg["base_exp"] * (1 + player.level / k)
base_exp_gain = round(base_gain * random.uniform(0.8, 1.2))
```
- 基础经验 = 50（配置） * (1 + 等级/k) * [0.8-1.2随机]
- 10级以下k=7，10级以上k=6
- 添加了±20%的随机波动

**加成系统** (Lines 117-191):

1. **月卡加成** (Lines 117-119, 182):
   - 获取玩家月卡权益 `benefits = await get_player_card_benefits(...)`
   - 月卡加成 = 基础经验 * `benefits["cultivation_efficiency"]`
   - 基础月卡20%，高级月卡50%

2. **公会加成** (Lines 122-126, 186):
   - 从公会建筑获取加成 `guild_bonuses = await GuildBuildingService.get_guild_bonuses(...)`
   - 公会加成 = 基础经验 * `guild_cultivation_bonus`

3. **阴宅加成** (Lines 129-175, 188):
   - 检查当前坐标是否有阴宅
   - 验证使用权限（自己的阴宅或付费使用他人阴宅）
   - 支付阴宅使用费用（如果是他人阴宅）
   - 阴宅加成 = 基础经验 * `mansion_cultivation_bonus`
   - 等级效率公式: 每级+9%，最高30级（公式在mansion.py中）

4. **转数加成** (Lines 178-179, 184):
   - 冥返加成 = 基础经验 * `reincarnation_bonus_rate`
   - 加成率 = 0.5 * 转数（每转50%）

**总经验公式** (Line 191):
```python
exp_gain = base_exp_gain + card_bonus + reincarnation_bonus + guild_bonus + mansion_bonus
```

#### 1.4 修炼输出文字内容定义位置

**文案池位置**: `core.py:19-57`

**修炼文案池** (CULTIVATE_FLAVOR_TEXTS, 12条):
- "你在黑焰里看见自己的影子喘息。"
- "怨炁如潮水般涌入你的经脉，灼烧着每一寸血肉。"
- "虚无的低语在耳边回响，诉说着不可名状的真理。"
- 等等...（共12条诡异氛围描述）

**闭关文案池** (SECLUSION_FLAVOR_TEXTS, 8条):
- "{nickname} 躺入破棺，将最后一枚钉子钉入。"
- "{nickname} 缓缓合上棺盖，黑暗吞噬了最后一丝光明。"
- 等等...（共8条）

**出关文案池** (OUT_SECLUSION_FLAVOR_TEXTS, 8条):
- "你推开棺盖，阴灰散落。"
- "棺盖缓缓打开，你从死亡中苏醒。"
- 等等...（共8条）

**文案特点**:
- 高度诡异氛围
- 诗意化表达
- 采用第二人称/第三人称视角
- 强调黑暗、死亡、蜕变等主题

#### 1.5 修炼相关配置文件

**主配置文件**: `plugins/xiuxian_game/data/config.yaml:38-62`

```yaml
cultivate:
    cool_down: 300  # 冷却时间5分钟
    base_exp: 50   # 基础经验值
    breakthrough:
        change_level: 30  # 多高等级后可能失败
        fail_keep_ratio: 0.7  # 失败保留70%经验
        guardian_cost: 50  # 怨念护航消耗
        base_success_rate: 0.8  # 基础成功率80%
        decay_per_level: 0.005   # 每级衰减0.5%
        min_success_rate: 0.1    # 最低成功率10%
        fail_bonus_enabled: true  # 启用失败累加机制
        fail_bonus_rate: 0.01     # 每次失败+1%成功率
        fail_bonus_max_rate: 0.95 # 成功率上限95%
    attributes_base:
        max_hp: 3    # 体力基础增量
        max_mp: 1    # 智力基础增量
        attack: 1    # 攻击基础增量
        defense: 1   # 防御基础增量
        agility: 1   # 敏捷基础增量
        luck: 1      # 运气基础增量
```

**配置控制范围**:
- 冷却时间
- 基础经验值
- 突破成功率曲线
- 属性点增长基础值
- **但不控制输出文案**（文案硬编码在代码中）

---

### 2. 新手任务系统调研

#### 2.1 任务系统存在性

**结论**: **项目中已存在完整的每日任务系统**（Daily Task System），但并非专门的新手任务系统。

**系统名称**: "每日委托系统" / "大都会缉邪司委托"

**开放条件**: 30级以上玩家可用 (`commands.py:34`)

#### 2.2 任务系统数据模型

**核心模型**: `plugins/xiuxian_game/models/daily_task.py:27-137` (DailyTask类)

**数据库表结构** (daily_task表):

```python
class DailyTask(Base):
    __tablename__ = "daily_task"

    # 主键和关联
    id: int (主键)
    player_id: str (外键 -> player.id)

    # 任务基本信息
    task_type: TaskType (枚举: 6种任务类型)
    title: str (任务标题)
    description: str (任务描述)

    # 任务目标信息
    target_region: str (目标区域, 默认"大都会")
    target_x: int (目标坐标X)
    target_y: int (目标坐标Y)

    # 任务状态
    status: TaskStatus (枚举: 可接取/已接取/已完成/已过期)

    # 敌人信息（用于战斗）
    enemy_name: str (敌人名称)
    enemy_level: int (敌人等级)
    enemy_hp: int (敌人血量)
    enemy_attack: int (敌人攻击力)
    enemy_defense: int (敌人防御力)
    enemy_agility: int (敌人敏捷)

    # 奖励信息
    exp_reward: int (经验奖励)
    gold_reward: int (金币奖励)
    guild_points_reward: int (公会积分奖励)

    # 时间信息
    task_date: date (任务日期)
    accepted_at: datetime (接取时间)
    completed_at: datetime (完成时间)
    created_at: datetime (创建时间)
```

**任务类型枚举** (TaskType):
1. `GHOST_ELIMINATION` - 鬼怪入侵事件处理
2. `PEN_SPIRIT_CASE` - 笔仙案件调查
3. `FAKE_IMMORTAL_CULT` - 伪仙邪教事件
4. `SHAPE_SHIFTER_HUNT` - 变形鬼怪追捕
5. `STONE_CURSE_BREAK` - 石化诅咒破解
6. `TORTURE_CULT_RAID` - 酷刑邪教清剿

**任务状态枚举** (TaskStatus):
- `AVAILABLE` - 可接取
- `ACCEPTED` - 已接取
- `COMPLETED` - 已完成
- `EXPIRED` - 已过期

**实例方法**:
- `is_available()` / `is_accepted()` / `is_completed()` - 状态检查
- `accept_task()` - 接取任务
- `complete_task()` - 完成任务
- `expire_task()` - 任务过期
- `location_str` - 位置字符串属性 "大都会(x,y)"
- `enemy_stats` - 敌人属性字典
- `get_reward_summary(has_guild)` - 奖励摘要

#### 2.3 任务系统代码文件

**命令处理文件**: `plugins/xiuxian_game/daily_task/commands.py`

**业务逻辑文件**: `plugins/xiuxian_game/daily_task/service.py` (DailyTaskService类)

**数据模型文件**: `plugins/xiuxian_game/models/daily_task.py`

**关键功能**:
1. **查看委托** - `daily_task_cmd` (commands.py:26-100)
2. **接取委托** - `accept_task_cmd` (commands.py)
3. **完成委托** - `complete_task_cmd` (commands.py)
4. **刷新委托** - `refresh_task_cmd` (commands.py)
5. **委托统计** - `task_stats_cmd` (commands.py)

**任务生成逻辑**:
- `DailyTaskService.generate_daily_task()` - 生成随机任务
- 每日最多3个委托
- 随机生成目标坐标、敌人属性、奖励
- 使用真实中文名字作为鬼怪名（50个名字池）
- 使用古代城市名作为地点（16个城市池）

#### 2.4 类似成就/里程碑系统

**调研结果**: **项目中没有独立的成就系统**，但发现了以下相关内容:

1. **事件系统** (`domain/events/example_handlers.py`):
   - 包含成就系统的示例处理器
   - `AchievementHandler` 类展示了如何监听事件触发成就
   - 但这只是示例代码，未实际部署

2. **统计系统**:
   - Player表包含战斗统计字段 (total_battles, total_wins, total_damage_dealt)
   - DailyTaskService包含任务统计功能 (get_task_summary)
   - 但缺少综合性的成就追踪

3. **签到系统** (`entertainment/sign.py`):
   - 每日签到功能
   - 连续签到天数记录 (Player.sign_streak)
   - 但不是成就系统

**可复用的代码**:
- 事件系统的发布/订阅机制可用于成就触发
- DailyTask的状态追踪逻辑可借鉴
- Player表的统计字段可扩展

---

### 3. 输出格式调研

#### 3.1 游戏中其他指令的输出格式

**常见输出模式**:

1. **系统消息头** (utils.py:11-16):
   - 所有消息使用 `message_add_head()` 添加统一前缀
   - 前缀: `『诡修仙』\n`

2. **帮助系统格式** (help.py):
```
✨ 系统名称 ✨
简短说明
━━━━━━━━━━━━━
📋 功能分类：
【指令】 说明
【指令】 说明
━━━━━━━━━━━━━
💡 提示信息
```

3. **任务列表格式** (daily_task/commands.py:50-77):
```
🏛️ 大都会缉邪司 - 每日委托
━━━━━━━━━━━━━
📋 【委托1】标题
🔳 任务描述：...
📍 目标位置：...
👹 目标敌人：...
💰 任务奖励：...
📊 任务状态：...

━━━━━━━━━━━━━
📈 完成统计：...
💡 操作提示
```

4. **修炼输出格式** (cultivate/core.py:224-233):
```
诡异氛围文案
━━━━━━━━━━━━━
✧ 汲取怨炁 + 数值↑
✧ 加成项 emoji +数值 (+百分比%)
✧ 修为残烛 数值↑/最大值 (可突破)
━━━━━━━━━━━━━
⬇️ 【指令】说明
⬇️ 【指令】说明
```

**共同特征**:
- 大量使用emoji增强视觉效果
- Unicode分隔线（━）分隔内容区块
- ✧ 符号标记数据项
- 使用【】包裹指令名称
- 使用emoji前缀标记信息类型（📋任务、💰金币、📍位置等）

#### 3.2 统一消息模板系统

**当前状态**: **没有完整的模板系统**，但有统一的消息头函数

**消息头函数**: `plugins/xiuxian_game/utils.py:11-16`
```python
def message_add_head(content: str, event: Optional[MessageEvent] = None) -> Message:
    """后续可能添加统一的消息头"""
    head = "『诡修仙』\n"
    return Message(head + content)
```

**设计意图**:
- 预留了扩展空间（注释：后续可能添加...）
- 目前只添加固定前缀
- 可以根据event添加个性化消息头

**格式化工具**:
- `paginate_items()` - 背包物品分页格式化 (utils.py:70-106)
- `format_theme_banner()` - 主题横幅格式化 (utils.py:487-489)
- 没有通用的卡片/表格模板

#### 3.3 进度条、emoji等视觉元素使用情况

**Emoji使用**:

1. **系统标识emoji** (help.py):
   - 🧘 修炼系统
   - 🎭 玩家系统
   - 🎒 背包系统
   - 🛒 装备系统
   - ⚔️ 战斗系统
   - 🗺️ 探索系统
   - 🏰 公会系统
   - 💕 社交系统
   - 🔮 炼丹系统
   - ...等等（每个系统都有对应emoji）

2. **功能标识emoji** (修炼系统):
   - ⚰️ 闭关相关
   - 💳 月卡加成
   - 🌟 转数加成
   - 🏰 公会加成
   - 🏚️ 阴宅加成
   - 💰 金币/费用
   - ⬇️ 操作提示

3. **状态标识emoji** (任务系统):
   - 📋 可接取
   - ⚔️ 进行中
   - ✅ 已完成
   - ❌ 已过期

**Unicode符号**:
- ━ (分隔线)
- ✧ (数据项标记)
- ↑ (上升箭头)
- ✖️ (数量标记)

**进度条**:
- **没有发现ASCII进度条**的使用
- 使用 `数值↑/最大值` 的文本表示（如：1250↑/2000）
- 使用百分比表示进度（如：+20%）

**视觉增强技巧**:
- 使用emoji替代传统图标
- 使用Unicode符号美化输出
- 多层分隔线区分内容区块
- 使用缩进和空行提高可读性

---

### 4. 词汇风格调研

#### 4.1 游戏中"诡异氛围"的词汇

**修炼相关词汇** (core.py文案池):
- **力量相关**: 怨炁、黑焰、虚无、深渊、真伤、怨念
- **生理相关**: 经脉、血肉、骨骼、脊椎、灵魂、毛孔、血管
- **感知相关**: 低语、注视、呼吸、心跳、颤栗、灼烧
- **状态相关**: 喘息、痛苦、蜕变、游离、召唤、吞噬
- **意象相关**: 黑暗、光明、死亡、深渊、彼岸、阴灰、棺盖

**任务系统词汇** (daily_task):
- **机构**: 大都会缉邪司、缉邪司总部
- **事件**: 鬼怪入侵、笔仙案件、伪仙邪教、变形鬼怪、石化诅咒、酷刑邪教
- **职责**: 委托、退邪、讨伐、清剿、调查、追捕
- **身份**: 恶鬼身、菩萨事

**系统命名词汇**:
- **经验系统**: 怨炁（经验）、修为残烛（经验进度）、冥返（转生）
- **货币系统**: 金币、积分、怨念值、咒抗
- **属性系统**: 理智值（MP）、生命值（HP）、灵爆率（技能暴击）、咒抗（精神抗性）
- **地点系统**: 诡域（副本）、表世界（现实世界）、阴宅（建筑）
- **战斗系统**: 死斗、切磋、讨伐、处决

#### 4.2 当前修炼/突破功能使用的文案风格

**修炼文案风格特点**:
1. **诗意化表达**:
   - "你在黑焰里看见自己的影子喘息"
   - "意识在虚空中飘荡，你看见了死亡的另一面"

2. **感官刺激**:
   - 视觉: "黑焰"、"影子"、"黑暗"
   - 触觉: "灼烧"、"颤栗"、"刺骨"
   - 听觉: "低语"、"骨骼断裂的声音"

3. **氛围营造**:
   - 恐怖: "注视"、"诡异符文"、"深渊"
   - 蜕变: "重塑"、"塑形新肉"、"蜕变成别的存在"

4. **简洁精炼**:
   - 单句长度控制在30字以内
   - 避免冗长解释
   - 留白让玩家想象

**突破文案风格**:
- "倾听骨骼断裂" - 突破指令说明
- "缝合裂隙，塑形新肉" - 加点指令说明
- 使用诗意化的动作描述

**闭关文案风格**:
- 仪式感强烈: "躺入破棺"、"钉下最后一枚钉子"
- 死亡意象: "黑暗吞噬了最后一丝光明"
- 隔绝感: "与外界彻底隔绝"

#### 4.3 配置文件中的氛围描述文本

**调研结果**: **配置文件不包含氛围文案**

**配置文件内容类型** (data/config.yaml):
- 数值配置（冷却时间、基础经验、成功率等）
- 游戏机制参数
- 系统开关

**氛围文案的存储位置**:
- **硬编码在代码中**: 文案池直接定义在core.py中作为常量
- **物品描述在items.yaml**: 但风格相对简短，不是诗意化描述
  - 例如: "回春散" - "恢复少量生命值（+40HP）"
  - 例如: "棺材钉" - "锈迹斑斑的铁钉，由上世纪驭鬼者所制..."

**items.yaml中的诡异词汇**:
- "腐坏的内丹" - 散发着腐臭气息 🦠
- "鬼泪" - 厉鬼哭泣时凝结的冰晶，触之刺骨 ❄️
- "诅咒丝线" - 沾染怨念的红色丝线，隐约能听到哀嚎声 🧵
- "灵骨" - 蕴含微弱灵力的兽骨，可用于炼制法器 💀
- "墓土" - 来自古老墓地的黑色泥土 ⚫

---

## Conclusions (Key Takeaways)

### 修炼系统关键发现

1. **修炼输出采用硬编码文案池**，不在配置文件中，包含12条诡异氛围文案
2. **经验计算公式复杂**，包含5层加成：基础+月卡+转数+公会+阴宅，所有加成基于基础经验计算
3. **输出格式统一**，使用Unicode分隔线、emoji标识、✧符号标记数据项
4. **缺少进度条**，使用"数值↑/最大值"的文本表示代替
5. **文案风格诗意化**，单句精炼，强调感官刺激和蜕变意象

### 任务系统关键发现

1. **已存在完整的每日任务系统**，但非新手专用，30级以上开放
2. **数据模型完善**，包含任务类型、状态、目标、敌人、奖励等完整信息
3. **任务生成随机化**，使用真实中文名字池（50个）和古代城市名（16个）增强代入感
4. **缺少任务链机制**，当前只支持独立的每日任务，无连续剧情
5. **没有成就系统**，但有事件系统可复用，Player表有统计字段可扩展

### 输出格式关键发现

1. **emoji使用广泛**，每个系统都有标识emoji，每种数据都有对应emoji
2. **没有统一模板系统**，各命令独立构建输出，但风格相对一致
3. **消息头函数统一**，所有消息通过`message_add_head()`添加前缀
4. **视觉元素简约**，主要依赖emoji和Unicode符号，不使用ASCII艺术或进度条
5. **分层结构清晰**，使用分隔线、缩进、空行区分内容区块

### 词汇风格关键发现

1. **诡异氛围核心词**: 怨炁、黑焰、深渊、虚无、诅咒、蜕变、吞噬
2. **系统命名创新**: 怨炁（经验）、修为残烛（进度）、冥返（转生）、咒抗（精神抗性）
3. **文案风格诗意化**，避免直白说明，使用意象和动作描述
4. **配置文件无文案**，所有氛围文本硬编码或在items.yaml中简短描述
5. **推荐替换词库**: 正常→诡异、经验→怨炁、升级→突破、修炼→汲取怨炁、死亡→凋零/消散

---

## Relations (Code Relationships)

### 修炼系统代码关系

```
cultivate/core.py (命令处理)
    ↓ 调用
utils.py (calculate_level_up_exp) - 计算升级所需经验
    ↓ 调用
utils.py (message_add_head) - 添加消息头
    ↓ 调用
models/monthly_card.py (get_player_card_benefits) - 获取月卡权益
    ↓ 调用
guild/guild_building_service.py (get_guild_bonuses) - 获取公会加成
    ↓ 调用
cultivate/mansion_service_new.py (find_mansion_owner_at_location) - 查找阴宅
    ↓ 调用
cultivate/reincarnation.py (get_cultivation_efficiency_bonus) - 获取转数加成
    ↓ 读取
data/config.yaml (cultivate配置) - 冷却时间、基础经验、突破配置
```

### 任务系统代码关系

```
daily_task/commands.py (命令处理)
    ↓ 调用
daily_task/service.py (DailyTaskService) - 业务逻辑
    ↓ 调用
models/daily_task.py (DailyTask模型) - 数据模型
    ↓ 调用
world/npc_service.py (NPCService) - 创建任务NPC
    ↓ 调用
battle/integration_helper.py (BattleIntegrationHelper) - 战斗集成
```

### 输出格式代码关系

```
所有命令处理器
    ↓ 调用
utils.py (message_add_head) - 统一消息头
    ↓ 返回
nonebot.adapters.qq.Message - QQ消息对象
```

### 配置加载关系

```
config.py (Config单例)
    ↓ 加载
data/config.yaml - 游戏配置
data/items.yaml - 物品配置
data/map.yaml - 地图配置
    ↓ 缓存
lru_cache装饰器 - 单例缓存
```

---

## Technical Implementation Recommendations

### 1. 修炼输出优化建议

**优化方向**:
1. **增强文案池**: 扩展CULTIVATE_FLAVOR_TEXTS到30-50条，增加文案多样性
2. **分层文案**: 根据等级段（1-50、51-100、101-200、201-300）使用不同文案池
3. **加成可视化**: 使用emoji序列表示加成强度，如"🌟🌟🌟"表示高加成
4. **进度条添加**: 使用简单的ASCII进度条表示经验进度
   ```
   ✧ 修为残烛 [████████--] 80% (1600/2000)
   ```
5. **动态提示**: 根据当前状态给出下一步操作建议

**实现方案**:
```python
# 1. 扩展文案池（在core.py中）
CULTIVATE_FLAVOR_TEXTS_BY_LEVEL = {
    "novice": [  # 1-50级新手文案
        "初次接触怨炁，你感到一丝不适。",
        "黑暗的力量在你体内涌动，但还很微弱。",
        # ... 更多文案
    ],
    "advanced": [  # 51-100级进阶文案
        "怨炁如潮水般涌入你的经脉，灼烧着每一寸血肉。",
        # ... 现有的诡异文案
    ],
    "master": [  # 101-200级大师文案
        "你已能自如驾驭深渊之力，但代价是灵魂的扭曲。",
        # ... 更深邃的文案
    ],
    "legend": [  # 201-300级传说文案
        "你窥见了真理的一角，那是连诸神都不敢直视的存在。",
        # ... 最终阶段文案
    ]
}

# 2. 根据等级选择文案池
def get_cultivation_flavor_text(player_level: int) -> str:
    if player_level <= 50:
        return random.choice(CULTIVATE_FLAVOR_TEXTS_BY_LEVEL["novice"])
    elif player_level <= 100:
        return random.choice(CULTIVATE_FLAVOR_TEXTS_BY_LEVEL["advanced"])
    elif player_level <= 200:
        return random.choice(CULTIVATE_FLAVOR_TEXTS_BY_LEVEL["master"])
    else:
        return random.choice(CULTIVATE_FLAVOR_TEXTS_BY_LEVEL["legend"])

# 3. 进度条生成函数
def generate_progress_bar(current: int, maximum: int, length: int = 10) -> str:
    percentage = current / maximum
    filled = int(percentage * length)
    bar = "█" * filled + "-" * (length - filled)
    return f"[{bar}] {int(percentage * 100)}%"

# 4. 增强的修炼消息构建
flavor_text = get_cultivation_flavor_text(player.level)
progress_bar = generate_progress_bar(player.exp, exp_max)

msg = (
    f"{flavor_text}\n"
    "━━━━━━━━━━━━━\n"
    f"✧ 汲取怨炁 + {exp_gain}↑\n"
    f"{bonus_msg}\n"
    f"✧ 修为残烛 {progress_bar} {player.exp}/{exp_max}\n"
    "━━━━━━━━━━━━━\n"
    f"{'⬇️ 【突破】你已可以突破境界' if player.exp >= exp_max else '⬇️ 继续【修炼】积累怨炁'}\n"
    "⬇️ 【加点】分配属性点强化自身"
)
```

### 2. 新手任务链实现建议

**设计思路**: 基于现有DailyTask系统扩展，添加新手任务链机制

**数据库扩展** (新增字段):
```python
# 在DailyTask模型中添加
quest_chain_id: Optional[str]  # 任务链ID（如"novice_chain_1"）
quest_step: Optional[int]      # 任务链步骤（1、2、3...）
prerequisites: Optional[str]   # 前置任务ID（JSON格式）
is_tutorial: bool = False      # 是否为新手教程任务
auto_accept: bool = False      # 是否自动接取
```

**新手任务链设计**:
```yaml
# data/novice_quests.yaml (新文件)
novice_chains:
  - chain_id: "novice_basic"
    name: "新人驭鬼者的第一步"
    steps:
      - step: 1
        title: "初入大都会"
        description: "熟悉【帮助】系统，查看游戏玩法"
        target_type: "command"  # 完成条件：使用指令
        target_command: "帮助"
        rewards:
          exp: 50
          gold: 500
        auto_accept: true

      - step: 2
        title: "修炼入门"
        description: "尝试【修炼】，感受怨炁的力量"
        target_type: "command"
        target_command: "修炼"
        rewards:
          exp: 100
          gold: 1000
          items:
            - item_id: "heal_potion"
              quantity: 5

      - step: 3
        title: "初次突破"
        description: "积累经验后使用【突破】提升境界"
        target_type: "level"  # 完成条件：达到等级
        target_level: 2
        rewards:
          exp: 200
          gold: 2000
          items:
            - item_id: "spirit_herb"
              quantity: 5

      - step: 4
        title: "探索世界"
        description: "使用【上/下/左/右】移动到指定坐标(10,0)"
        target_type: "location"
        target_x: 10
        target_y: 0
        rewards:
          exp: 150
          gold: 1500

      - step: 5
        title: "首次战斗"
        description: "前往目标位置，【观察】并【攻击】目标鬼怪"
        target_type: "battle"
        target_x: 20
        target_y: 0
        spawn_enemy: true
        enemy_name: "怨灵·张伟"
        enemy_level: 3
        rewards:
          exp: 500
          gold: 3000
          items:
            - item_id: "rotten_core"
              quantity: 2
```

**实现代码**:
```python
# plugins/xiuxian_game/quest/novice_quest_service.py (新文件)
class NoviceQuestService:
    """新手任务链服务"""

    @staticmethod
    async def init_novice_quests(session: AsyncSession, player: Player):
        """为新玩家初始化新手任务链"""
        if player.level > 1:  # 只有1级新手触发
            return

        # 创建第一个任务
        chain_config = load_novice_chain_config("novice_basic")
        first_step = chain_config["steps"][0]

        task = DailyTask(
            player_id=player.id,
            task_type=TaskType.TUTORIAL,  # 新增类型
            title=first_step["title"],
            description=first_step["description"],
            quest_chain_id="novice_basic",
            quest_step=1,
            is_tutorial=True,
            auto_accept=first_step.get("auto_accept", False),
            # ... 其他字段
        )
        session.add(task)
        await session.commit()

    @staticmethod
    async def check_and_advance_quest(
        session: AsyncSession,
        player: Player,
        action_type: str,  # "command", "level", "location", "battle"
        action_data: dict
    ):
        """检查是否完成当前新手任务，自动推进到下一步"""
        # 1. 查找当前激活的新手任务
        current_task = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player.id,
                    DailyTask.is_tutorial == True,
                    DailyTask.status == TaskStatus.ACCEPTED
                )
            )
        ).scalar_one_or_none()

        if not current_task:
            return None

        # 2. 检查完成条件
        completed = False
        if action_type == "command" and action_data.get("command") == current_task.target_command:
            completed = True
        elif action_type == "level" and player.level >= current_task.target_level:
            completed = True
        # ... 其他条件检查

        if not completed:
            return None

        # 3. 完成当前任务
        current_task.complete_task()
        await give_quest_rewards(session, player, current_task)

        # 4. 生成下一步任务
        next_step = current_task.quest_step + 1
        chain_config = load_novice_chain_config(current_task.quest_chain_id)

        if next_step <= len(chain_config["steps"]):
            next_task = create_quest_from_config(
                player, chain_config, next_step
            )
            session.add(next_task)
            await session.commit()
            return next_task
        else:
            # 任务链完成
            return None

# 在各个命令处理器中集成检查
@cultivate.handle()
async def handle_cultivate(event: MessageEvent):
    # ... 原有逻辑

    # 新增：检查新手任务
    await NoviceQuestService.check_and_advance_quest(
        session, player, "command", {"command": "修炼"}
    )
```

**优势**:
1. 复用现有DailyTask系统，开发成本低
2. 任务配置化，易于扩展和调整
3. 自动推进机制，新手无需手动接取
4. 与现有战斗、移动系统无缝集成

**劣势**:
1. 需要修改多个命令处理器添加任务检查
2. 增加了代码耦合度

**替代方案**: 使用事件系统（EventBus）解耦
```python
# 在各命令处理器中发布事件
from ..domain.events.event_bus import EventBus
from ..domain.events.game_events import PlayerActionEvent

# 修炼命令完成后
await EventBus().publish(PlayerActionEvent(
    player_id=player.id,
    action_type="cultivate",
    details={"exp_gained": exp_gain}
))

# 在NoviceQuestService中订阅事件
class NoviceQuestHandler:
    async def handle_player_action(self, event: PlayerActionEvent):
        async with safe_session() as session:
            player = await session.get(Player, event.player_id)
            await NoviceQuestService.check_and_advance_quest(
                session, player, event.action_type, event.details
            )

# 注册处理器
EventBus().subscribe(PlayerActionEvent, NoviceQuestHandler().handle_player_action)
```

这种方案更解耦，但需要在所有命令中添加事件发布代码。

---

**报告完成日期**: 2025-12-02
**报告版本**: 1.0
**报告作者**: Scout Agent
