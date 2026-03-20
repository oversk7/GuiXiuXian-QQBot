# 新手任务链扩展设计：分章引导系统

## 1. 目标

将现有单任务链（10步）扩展为三章式引导系统，覆盖从入门到中期的核心玩法，降低新手流失率。

## 2. 现状

- 现有 `novice_basic_chain`（10步）覆盖：修炼、加点、突破、面板、观察、前往、攻击、使用物品、任务
- 未覆盖：签到、打工、装备穿戴、锻造、闭关、跑商、钓鱼、公会、切磋
- `DailyTask` 模型已有 `quest_chain_id` + `quest_step` 字段，天然支持多链

## 3. 设计

### 3.1 YAML 结构变更

将 `novice_quests.yaml` 从单链结构改为多链列表结构：

```yaml
chains:
  - chain_id: "novice_basic"
    name: "驭鬼者的第一步"
    chapter: 1
    unlock_after: null
    steps: [...现有10步不变...]
    completion_reward: {现有奖励不变}

  - chain_id: "novice_survival"
    name: "生存之道"
    chapter: 2
    unlock_after: "novice_basic"
    steps: [5步]
    completion_reward: {...}

  - chain_id: "novice_world"
    name: "行走江湖"
    chapter: 3
    unlock_after: "novice_survival"
    steps: [5步]
    completion_reward: {...}
```

### 3.2 第二章「生存之道」步骤

| 步骤 | 标题 | 触发指令 | completion_type | 奖励 |
|------|------|---------|----------------|------|
| 1 | 每日祭礼 | 签到 | command | exp:800, gold:2000 |
| 2 | 谋生之道 | 打工 | command | exp:500, gold:3000 |
| 3 | 武装自己 | 装备 | command | exp:500, gold:1000 |
| 4 | 铸器入门 | 锻造 | command | exp:1000, gold:2000 |
| 5 | 闭棺修行 | 闭关 | command | exp:800, gold:1500 |

第3步奖励发放材料 `spirit_bone×20 + bone_fragment×30 + grave_soil×15`（供第4步锻造白骨护甲使用）。
完成奖励：exp:5000, gold:15000, 称号「求生本能」

### 3.3 第三章「行走江湖」步骤

| 步骤 | 标题 | 触发指令 | completion_type | 奖励 |
|------|------|---------|----------------|------|
| 1 | 商道初探 | 市集 | command | exp:500, gold:2000 |
| 2 | 低买高卖 | 购买 | command | exp:800, gold:5000 |
| 3 | 愿者上钩 | 钓鱼 | command | exp:500, gold:1500, 鱼饵×10 |
| 4 | 同道中人 | 加入公会 | command | exp:1500, gold:3000, attr_points:15 |
| 5 | 以武会友 | 切磋 | command | exp:1000, gold:2000, attr_points:10 |

完成奖励：exp:8000, gold:20000, sweep_order×10, 称号「江湖新秀」

### 3.4 任务描述文本（跑商/挂牌详细引导）

跑商相关步骤使用详细的多行描述，确保新手能看懂操作流程：

- 商道初探："发送【市集】查看当地可买卖的货物和价格。不同地点的市集价格不同，低价买入、异地高价卖出就是跑商！\n💡 发送【市集列表】可查看所有市集位置"
- 低买高卖："在市集发送【购买 物品名 数量】买入货物，用【前往 其他城市】移动，再【出售 物品名 数量】卖出赚差价！\n💡 发送【跑商推荐】可查看当前最佳套利路线"

### 3.5 NoviceQuestService 改动

1. `_load_quest_config()` — 适配新 YAML 结构（chains 列表）
2. `init_novice_quests()` — 保持不变，只初始化第一章
3. `check_and_advance_quest()` — 当前链最后一步完成时，调用 `_init_next_chain()` 自动解锁下一章
4. 新增 `_init_next_chain(session, player, current_chain_id)` — 查找 `unlock_after == current_chain_id` 的链并初始化
5. 新增 `_get_chain_config(chain_id)` — 从 chains 列表中查找指定链配置

### 3.6 命令钩子接入

需要在以下命令处理器中添加 `check_and_advance_quest` 调用：

| 命令 | 文件 | completion_target |
|------|------|------------------|
| 签到 | entertainment/sign.py | "签到" |
| 打工 | economy/part_time_job_commands.py | "打工" |
| 装备/穿戴 | item/equipment_commands.py | "装备" |
| 锻造 | item/equipment_craft.py | "锻造" |
| 闭关 | cultivate/core.py | "闭关"（已有钩子，需确认） |
| 市集 | economy/merchants.py | "市集" |
| 购买 | economy/merchants.py | "购买" |
| 钓鱼 | fishing/commands.py | "钓鱼" |
| 加入公会 | guild/guild.py | "加入公会" |
| 切磋 | battle/pvp_commands.py | "切磋" |

### 3.7 向后兼容

- 现有第一章数据完全不变，已完成第一章的玩家不受影响
- 已完成第一章但未初始化第二章的老玩家：在任何新钩子命令触发时，检测是否需要补初始化
- `_check_completion` 方法逻辑不变，仅通过 chain_id 区分不同链

## 4. 不做的事

- 不改 DailyTask 模型（已有字段够用）
- 不改数据库迁移
- 不加等级门槛（各玩法本身无等级限制）
- 不改第一章任何内容
