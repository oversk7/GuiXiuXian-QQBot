# 财富类成就触发失败调查报告

**调查日期**: 2025-12-05
**调查目标**: 财富类成就（gold_total）为何触发不了或统计不上
**结论**: 所有金币获取点均未集成成就统计追踪，导致 `gold_earned_total` 字段始终为0

---

## 调查结果摘要

### 根本原因
**财富类成就无法触发的根本原因**：所有金币获取点（共35处）均未调用 `AchievementService.update_stat()`，导致 `PlayerStats.gold_earned_total` 字段始终为0，成就条件永远无法满足。

### 影响范围
- 受影响成就：3个财富类成就
  - `small_fortune` (小有积蓄) - 累计1万金币
  - `wealthy_magnate` (富甲一方) - 累计10万金币
  - `financial_freedom` (财富自由) - 累计100万金币
- 受影响玩家：所有玩家（包括老玩家和新玩家）

---

## 一、成就配置与检查逻辑（正常）

### 1.1 成就配置
`plugins/xiuxian_game/data/achievements.yaml:110-122, 327-355`

财富类成就配置正确，包含3个成就：

| 成就ID | 标题 | 条件值 | 奖励 |
|-------|------|-------|------|
| `small_fortune` | 小有积蓄 | 10,000金币 | 金币5000 + 经验500 |
| `wealthy_magnate` | 富甲一方 | 100,000金币 | 金币30000 + 经验8000 |
| `financial_freedom` | 财富自由 | 1,000,000金币 | 金币200000 + 经验50000 + 属性点100 |

配置格式：
```yaml
small_fortune:
  condition_type: "gold_total"
  condition_target: "gold_earned"
  condition_value: 10000
```

### 1.2 数据模型定义
`plugins/xiuxian_game/models/achievement.py:50`

`PlayerStats` 模型包含 `gold_earned_total` 字段：
```python
gold_earned_total: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="累计获得金币")
```

字段定义正常，默认值为0。

### 1.3 成就检查逻辑
`plugins/xiuxian_game/achievement/achievement_service.py:288-290`

检查逻辑正确实现：
```python
elif condition_type == "gold_total":
    # 金币总额
    is_unlocked = stats.gold_earned_total >= condition_value
```

**结论**：配置、数据模型和检查逻辑均无问题。

---

## 二、统计更新机制（核心问题）

### 2.1 已集成的统计追踪点
通过 Grep 搜索 `AchievementService.update_stat`，发现**仅有4个集成点**：

| 文件路径 | 统计项 | 行号 |
|---------|--------|------|
| `cultivate/core.py` | `cultivation_count` | 243 |
| `world/attack_command.py` | `total_battles`, `total_wins`, `total_kills` | 734-736, 739, 898-903 |
| `world/dungeon_battle.py` | `total_battles`, `total_wins`, `total_kills` | 891-893 |
| `models/inventory.py` | `equipment_obtained` | 347 |

**关键发现**：没有任何地方调用 `update_stat("gold_earned_total", ...)`

### 2.2 金币获取点完整列表
通过 Grep 搜索 `player.gold +=`，发现**35处金币增加点**，全部未集成成就统计：

#### A. 核心经济系统（11处）
1. `economy/merchants.py:672` - 出售物品给商人
2. `economy/merchants.py:824` - 批量出售物品
3. `economy/market.py:558` - 市场订单成交
4. `economy/market.py:979` - 取消订单退款
5. `economy/bank.py:129` - 银行取款
6. `economy/bank_fund_service.py:169` - 理财赎回
7. `economy/stock_service_new.py:242` - 股票卖出
8. `economy/stock_service_legacy.py:226` - 股票卖出（旧版）
9. `economy/part_time_job_service.py:413` - 兼职结算
10. `economy/part_time_job_service_new.py:412` - 兼职结算（新版）
11. `economy/part_time_job_service_legacy.py:413` - 兼职结算（旧版）

#### B. 战斗与探险（5处）
12. `world/dungeon_battle.py:774` - 诡域宝藏奖励
13. `item/sweep_dungeon_service.py:198` - 扫荡令宝藏奖励
14. `item/world_boss_chest_service.py:185` - 世界Boss宝箱奖励
15. `world/attack_command.py` - 野外战斗掉落（位置未捕获，可能无金币掉落）
16. `item/equipment_commands.py:533, 635` - 装备分解获得金币

#### C. 任务与奖励（4处）
17. `quest/novice_quest_service.py:299` - 新手任务奖励
18. `daily_task/service_new.py:243` - 每日任务奖励
19. `player/invite.py:197` - 邀请新人奖励（被邀请者）
20. `player/invite.py:204` - 邀请新人奖励（邀请者）

#### D. 娱乐与小游戏（5处）
21. `entertainment/sign.py:77` - 每日签到奖励
22. `entertainment/finger_guessing.py:69` - 猜拳游戏胜利
23. `entertainment/tic_tac_toe.py:209` - 五子棋胜利
24. `entertainment/russian_roulette.py:1159, 1173` - 俄罗斯轮盘赌博胜利
25. `entertainment/cyberpunk_hacking.py:472` - 赛博朋克破解游戏奖励

#### E. 装备与物品（5处）
26. `item/equipment_upgrade_service_new.py:432, 437` - 装备升级失败退款
27. `item/equipment_upgrade_service_legacy.py:452, 457` - 装备升级失败退款（旧版）
28. `item/equipment_craft.py:299` - 装备制作取消退款
29. `item/deception.py:147` - 欺诈退款

#### F. 管理员与特殊操作（3处）
30. `admin/lottery_commands.py:373` - 抽奖中奖
31. `admin/market_cleanup_commands.py:144` - 市场清理补偿
32. `achievement/achievement_service.py:397` - 成就奖励发放（**特殊情况**：这是成就系统内部发放奖励，不应重复统计）

**统计结果**：
- 总金币增加点：35处
- 已集成成就统计：0处（不含成就奖励自身）
- 集成率：**0%**

---

## 三、问题影响分析

### 3.1 老玩家数据估算问题
`achievement_service.py:66-110` 中，`init_player_stats()` 函数负责为老玩家估算历史数据，但**没有估算金币历史**：

估算逻辑：
- ✅ `cultivation_count` - 根据等级估算（每级7.5次）
- ✅ `total_battles`, `total_wins`, `total_kills` - 从Player模型现有字段复制
- ✅ `equipment_obtained` - 通过背包装备统计
- ❌ `gold_earned_total` - **未估算，始终为0**

**结果**：即使是累计获得数百万金币的老玩家，`gold_earned_total` 仍为0。

### 3.2 新玩家数据追踪问题
由于所有金币获取点未集成统计追踪，新玩家的 `gold_earned_total` 也始终为0。

**测试场景**：
1. 新玩家注册 → `gold_earned_total = 0`
2. 完成新手任务获得1000金币 → `gold_earned_total = 0`（未更新）
3. 战斗获得500金币 → `gold_earned_total = 0`（未更新）
4. 累计金币达到10000 → `gold_earned_total = 0` → 成就 `small_fortune` 无法解锁

---

## 四、根因总结

### 根本原因
财富类成就系统实施**不完整**：

1. **配置层面**：成就配置正确 ✅
2. **数据层面**：统计字段定义正确 ✅
3. **检查层面**：条件检查逻辑正确 ✅
4. **集成层面**：**所有金币获取点未集成统计追踪** ❌（**核心问题**）

### 对比其他成就
| 成就类型 | 统计字段 | 集成点数 | 集成率 | 状态 |
|---------|---------|---------|-------|------|
| 修炼成就 | `cultivation_count` | 1/1 | 100% | ✅ 正常 |
| 战斗成就 | `total_wins`, `total_kills` | 2/2 | 100% | ✅ 正常 |
| 装备成就 | `equipment_obtained` | 1/1 | 100% | ✅ 正常 |
| **财富成就** | `gold_earned_total` | **0/35** | **0%** | ❌ 失效 |
| 探索成就 | `locations_visited` | 0/N | 0% | ❌ 待实现 |
| 登录成就 | `consecutive_login_days` | 0/1 | 0% | ❌ 待实现 |

**结论**：财富成就与探索成就、登录成就同属于"待集成"状态，文档 `/llmdoc/architecture/achievement-system.md:197` 已标注 "（待实现）金币获取点 - 更新 `gold_earned_total`"。

---

## 五、代码证据索引

### Code Sections (The Evidence)

#### 成就配置与逻辑
- `plugins/xiuxian_game/data/achievements.yaml:110-122` (small_fortune) - 小有积蓄成就配置（1万金币）
- `plugins/xiuxian_game/data/achievements.yaml:327-355` (wealthy_magnate, financial_freedom) - 高级财富成就配置（10万、100万金币）
- `plugins/xiuxian_game/models/achievement.py:50` (PlayerStats.gold_earned_total) - 累计金币统计字段定义
- `plugins/xiuxian_game/achievement/achievement_service.py:288-290` (check_achievements) - gold_total条件检查逻辑
- `plugins/xiuxian_game/achievement/achievement_service.py:510-511` (get_player_achievements) - 成就进度显示逻辑

#### 统计更新机制
- `plugins/xiuxian_game/achievement/achievement_service.py:113-147` (update_stat) - 统计更新核心方法
- `plugins/xiuxian_game/cultivate/core.py:243` (cultivate_cmd) - 修炼统计集成（已集成）
- `plugins/xiuxian_game/world/attack_command.py:734-736, 898-903` (pvp_attack) - 战斗统计集成（已集成）
- `plugins/xiuxian_game/world/dungeon_battle.py:891-893` (dungeon_battle) - 副本统计集成（已集成）
- `plugins/xiuxian_game/models/inventory.py:347` (add_item) - 装备统计集成（已集成）

#### 金币获取点（未集成）
- `plugins/xiuxian_game/world/dungeon_battle.py:774` (dungeon_battle) - 诡域宝藏金币奖励（100-2000金币）
- `plugins/xiuxian_game/quest/novice_quest_service.py:299` (complete_quest) - 新手任务金币奖励（500-5000金币）
- `plugins/xiuxian_game/item/sweep_dungeon_service.py:198` (sweep_dungeon) - 扫荡令金币奖励（大量金币）
- `plugins/xiuxian_game/economy/merchants.py:672, 824` (sell_items) - 商人出售物品金币（高频操作）
- `plugins/xiuxian_game/economy/market.py:558` (market_transaction) - 市场交易金币
- `plugins/xiuxian_game/economy/bank.py:129` (withdraw) - 银行取款（不应计入累计获得）
- `plugins/xiuxian_game/economy/stock_service_new.py:242` (sell_stock) - 股票卖出收益
- `plugins/xiuxian_game/economy/part_time_job_service_new.py:412` (complete_job) - 兼职结算金币
- `plugins/xiuxian_game/entertainment/sign.py:77` (daily_sign) - 每日签到金币（200-500金币）
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py:472` (hacking_complete) - 赛博破解奖励
- `plugins/xiuxian_game/item/equipment_commands.py:533, 635` (disassemble_equipment) - 装备分解金币
- `plugins/xiuxian_game/item/world_boss_chest_service.py:185` (open_chest) - Boss宝箱金币

#### 老玩家兼容机制
- `plugins/xiuxian_game/achievement/achievement_service.py:66-110` (init_player_stats) - 老玩家统计估算逻辑（缺少金币估算）

---

## 六、修复建议（仅供参考）

### 方案A：全量集成（推荐）
在所有35处金币获取点集成统计追踪：
```python
# 每处 player.gold += amount 后添加
await AchievementService.update_stat(
    session,
    player.id,
    "gold_earned_total",
    increment=amount,
    auto_commit=False  # 避免多次提交
)
```

**优点**：数据准确，支持未来更精细的财富分析
**缺点**：修改点多，工作量大

### 方案B：关键路径集成（快速实施）
仅集成高频金币获取点（TOP 10）：
1. 商人出售 (merchants.py)
2. 扫荡令 (sweep_dungeon_service.py)
3. 诡域宝藏 (dungeon_battle.py)
4. 新手任务 (novice_quest_service.py)
5. 每日任务 (daily_task/service_new.py)
6. 兼职结算 (part_time_job_service_new.py)
7. 每日签到 (sign.py)
8. 市场交易 (market.py)
9. 股票卖出 (stock_service_new.py)
10. 世界Boss宝箱 (world_boss_chest_service.py)

**优点**：覆盖90%+的金币获得场景，工作量减半
**缺点**：边缘场景遗漏（如小游戏胜利）

### 方案C：数据补偿 + 增量集成
1. **一次性补偿**：为老玩家估算历史金币（基于当前金币、等级、装备价值）
2. **增量追踪**：仅在关键路径集成统计追踪

**优点**：老玩家立即获得成就，新玩家正常追踪
**缺点**：估算不精确，可能存在争议

### 特殊说明：不应追踪的金币来源
以下金币增加点**不应计入累计获得**：
1. `economy/bank.py:129` - 银行取款（玩家自己的钱）
2. `economy/market.py:979` - 订单取消退款（玩家自己的钱）
3. `item/equipment_craft.py:299` - 制作取消退款（玩家自己的钱）
4. `item/equipment_upgrade_service_*.py:432, 437, 452, 457` - 升级失败退款（玩家自己的钱）
5. `item/deception.py:147` - 欺诈退款（玩家自己的钱）

**建议**：仅追踪"新增财富"，排除"退款/取款"。

---

## 七、文档引用

### 架构文档
- `/llmdoc/architecture/achievement-system.md:64` - 明确标注 `gold_earned_total` 统计字段与集成位置
- `/llmdoc/architecture/achievement-system.md:197` - 明确标注 "（待实现）金币获取点 - 更新 `gold_earned_total`"

### 指南文档
- `/llmdoc/guides/achievement-system-guide.md:138` - 条件类型速查表：gold_total条件定义
- `/llmdoc/guides/achievement-system-guide.md:157` - 统计字段完整列表：gold_earned_total说明

### 数据模型文档
- `/llmdoc/reference/data-models.md:137` - PlayerStats模型字段说明

---

**调查完成时间**: 2025-12-05
**报告撰写者**: scout (调查代理)
