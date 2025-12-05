# 微成就系统架构

## 1. Identity

- **What it is**: 配置驱动的微成就系统，为新手玩家提供渐进式成就感
- **Purpose**: 提升新手留存率，通过即时反馈和小型奖励引导玩家探索游戏功能

## 2. Core Components

- `plugins/xiuxian_game/achievement/achievement_service.py` (AchievementService): 成就检查、进度更新、奖励发放核心服务
- `plugins/xiuxian_game/achievement/commands.py` (成就查询命令): 玩家查询成就列表和进度
- `plugins/xiuxian_game/data/achievements.yaml` (成就配置): 11个基础成就定义（条件、奖励、文案）
- `plugins/xiuxian_game/models/achievement.py` (PlayerAchievement, PlayerStats): 成就关联表和统计数据表
- `plugins/xiuxian_game/models/auto_migrate.py` (自动迁移): 自动创建player_achievement和player_stats表

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 成就检查流程

1. **触发点**: 玩家执行关键操作（修炼、战斗、突破等）
2. **统计更新**:
   - 命令处理器调用 `AchievementService.update_stat(player_id, stat_name, value)`
   - 例: `cultivate/core.py:120` 修炼后更新 `cultivation_count`
3. **成就检查**:
   - Service自动查询 `achievements.yaml` 中所有相关成就
   - 检查条件是否满足（例: `cultivation_count >= 10`）
4. **完成通知**:
   - 首次完成时自动发放奖励（金币、经验、属性点）
   - 返回成就解锁消息（带图标和奖励文案）

### 3.2 配置驱动设计

**achievements.yaml 结构**:
```yaml
first_cultivation:
  id: "first_cultivation"
  title: "初窥门径"
  condition_type: "command_count"        # 条件类型
  condition_target: "修炼"               # 监控目标
  condition_value: 1                    # 触发阈值
  rewards:                              # 奖励配置
    gold: 500
    exp: 100
```

**条件类型**:
- `command_count`: 命令执行次数（如修炼10次）
- `level_reached`: 等级达成（如10级）
- `battle_win`: 战斗胜利次数
- `kill_count`: 击杀数
- `gold_total`: 累计金币
- `locations_visited`: 地点探索数
- `login_streak`: 连续登录天数
- `account_age`: 账号创建时间（用于周年庆典等时间限定成就）

### 3.3 统计追踪机制

**PlayerStats表字段映射**:
| 统计字段 | 追踪内容 | 集成位置 |
|---------|---------|---------|
| `cultivation_count` | 修炼次数 | `cultivate/core.py:120` |
| `total_wins` | 战斗胜利 | `world/attack_command.py:85` |
| `total_kills` | 击杀数 | `world/attack_command.py:90` |
| `gold_earned_total` | 累计金币 | 各金币获取点 |
| `equipment_obtained` | 获得装备 | `models/inventory.py:150` |
| `locations_visited` | 探索地点 | `world/real_world_explore.py:45` |
| `consecutive_login_days` | 连续登录 | 登录检查点（待实现） |

### 3.4 老玩家兼容机制

**问题**: 成就系统是新功能，老玩家的 `PlayerStats` 表为空。

**解决方案**: 懒加载的历史统计估算机制（`achievement_service.py:156-196`）

**估算规则**:
- `cultivation_count = (player.level - 1) * 7.5` - 假设每级平均修炼7.5次
- `total_battles = player.total_battles` - 使用Player表现有字段
- `total_wins = player.total_wins` - 使用Player表现有字段
- `equipment_obtained` - 通过 `ItemInstance.is_equipment` 计算属性统计

**触发时机**: 首次查询成就/成就详情/执行成就检查时自动初始化

### 3.5 成就列表翻页机制

**背景**: 成就数量持续增长，单页显示所有成就会导致界面过长。

**分页规则** (`commands.py:17-95`):
- **每页显示**: 15个成就
- **命令格式**:
  - `【成就】` - 查看第1页（默认）
  - `【成就 2】` - 查看第2页（数字参数=页码）
  - `【成就 初窥门径】` - 查看成就详情（文字参数=成就名）
- **显示信息**: 页码 "第 X/Y 页 | 总计 M/N 已解锁"
- **排序规则**: 已解锁成就在前，未解锁在后（优先展示玩家成就）

**智能参数解析**:
```python
if arg_text.isdigit():
    page = int(arg_text)  # 数字 → 页码
else:
    await show_achievement_detail(...)  # 文字 → 成就名
```

**边界处理**:
- 页码超出范围自动调整到有效范围
- 页码 ≤ 0 → 第1页
- 页码 > 总页数 → 最后一页

### 3.6 账号年龄条件（account_age）与限定成就显示优化

**用途**: 基于玩家创建时间的成就检查（周年庆典、特殊纪念）

**配置格式**:
```yaml
first_anniversary:
  condition_type: "account_age"
  condition_target: "created_before"
  condition_value: "2025-10-04"  # YYYY-MM-DD格式
```

**检查逻辑** (`achievement_service.py:487-492`):
```python
elif condition_type == "account_age":
    cutoff_date = datetime.strptime(achievement_data.get("condition_value"), "%Y-%m-%d")
    current_progress = 1 if player.created_at < cutoff_date else 0
```

**进度显示优化** (`commands.py:90-110`):

为提升用户体验，成就列表中限定成就（account_age类型）采用特殊显示逻辑，避免显示 "0/2025-10-04" 等不友好的进度信息：

**新玩家**（不符合条件）:
```
🔒 🎂 元老见证者 - ❌ 限定成就（需2025-10-04前创建）
```

**老玩家**（符合条件）:
```
✅ 🎂 元老见证者 - 进度: 1/1 (已完成)
```

**显示逻辑**:
- 检查 `condition_type == "account_age"`
- 若满足条件：显示 "✅ 已完成"
- 若不满足：显示 "❌ 限定成就（需 DATE 前创建）"

**应用场景**:
- 周年庆典成就（元老见证者）
- 限定时期注册奖励
- 早期测试玩家特权

## 4. Design Rationale

### 4.1 为什么选择配置驱动？

- **易于扩展**: 新增成就无需修改代码，只需编辑YAML
- **策划友好**: 游戏策划可直接调整成就条件和奖励
- **热更新**: 未来可支持运行时重载配置

### 4.2 为什么分离PlayerStats表？

- **解耦统计与成就**: 统计数据可用于其他分析（排行榜、数据看板）
- **性能优化**: 高频统计更新不影响PlayerAchievement表查询
- **独立索引**: 可为统计字段单独建立索引优化查询

### 4.3 11个基础成就的设计意图

| 成就ID | 设计意图 | 预期触发时机 |
|-------|---------|-------------|
| `first_cultivation` | 完成首次修炼 | 注册后1分钟内 |
| `cultivation_adept` | 建立修炼习惯 | 注册后1小时内 |
| `first_breakthrough` | 理解突破机制 | Lv.1→2（注册后30分钟） |
| `level_ten_warrior` | 突破新手期 | Lv.10（约2-3小时） |
| `first_victory` | 首次战斗胜利 | 完成新手任务第8步 |
| `veteran_fighter` | 战斗经验积累 | 10次战斗（约1-2小时） |
| `first_equipment` | 理解装备系统 | 首次获得装备（战利品/商店） |
| `small_fortune` | 财富积累里程碑 | 累计1万金币（约5-8小时） |
| `world_explorer` | 鼓励探索 | 访问3个地点（完成新手任务后） |
| `loyal_believer` | 提升留存率 | 连续登录3天 |
| `first_anniversary` | 一周年庆典 | 2025.10.4前创建（老玩家特权） |

### 4.4 周年成就设计理念

**元老见证者（🎂 first_anniversary）**:
- **目标群体**: 诡修仙运行一年以来的早期玩家
- **奖励设计**: 金币50000、经验10000、属性点30（周年特别奖励，非常丰厚）
- **情感价值**: "一年相伴，感谢有你同行" - 体现对老玩家的感谢
- **实现方式**: `scripts/unlock_anniversary_achievement.py` 一次性解锁脚本

## 5. Integration Points

### 5.1 已完整集成的统计追踪

**修炼类成就** (100% 集成):
1. `cultivate/core.py:120` - 修炼后更新 `cultivation_count`

**战斗类成就** (100% 集成):
2. `world/attack_command.py:734-736` - PVP战斗后更新 `total_battles`, `total_wins`, `total_kills`
3. `world/dungeon_battle.py:891-893` - 副本战斗后更新 `total_battles`, `total_wins`, `total_kills`
4. `world/dungeon_battle.py:895-898` - 副本战斗后检查成就（新增 2025-12-05）

**装备类成就** (100% 集成):
5. `models/inventory.py:150` - 获得装备时更新 `equipment_obtained`

**连续登录类成就** (100% 集成，新增 2025-12-05):
6. `entertainment/sign.py:86-87` - 签到后更新 `consecutive_login_days` 和 `total_login_days`
7. `entertainment/sign.py:205-206` - 签到后检查并触发成就

**财富类成就** (31% 集成，关键路径，新增 2025-12-05):
8. `entertainment/sign.py:79-81` - 每日签到金币 (200-500)
9. `world/dungeon_battle.py:775-777` - 诡域宝藏金币 (100-2000)
10. `quest/novice_quest_service.py:300-302` - 新手任务金币 (500-5000)
11. `item/sweep_dungeon_service.py:199-201` - 扫荡令金币 (大量)
12. `economy/merchants.py:673-675` - 商人出售物品金币（高频）
13. `economy/merchants.py:828-830` - 批量出售物品金币（高频）
14. `economy/part_time_job_service_new.py:413-415` - 兼职结算金币 (100-1000)
15. `economy/market.py:953-955` - 市场交易金币 (用户交易)
16. `economy/stock_service_new.py:243-245` - 股票卖出收益 (可变)
17. `item/world_boss_chest_service.py:186-188` - Boss宝箱金币 (高频)
18. `daily_task/service_new.py:244-246` - 每日任务金币 (300-1000)

### 5.2 待实现的统计追踪

**探索类成就** (0% 集成):
- （待实现）`locations_visited` - 地点探索统计

**其他低频成就** (部分集成):
- 小游戏胜利 (5处，低频，暂未集成)
- 邀请新人 (2处，低频，暂未集成)
- 管理员操作 (3处，特殊权限，暂未集成)

### 5.3 集成覆盖率统计

| 成就类型 | 触发点总数 | 已集成点数 | 覆盖率 | 玩家场景覆盖 |
|---------|----------|----------|-------|-----------|
| 修炼成就 | 1 | 1 | 100% | 100% |
| 战斗成就 | 2 | 2 | 100% | 100% |
| 装备成就 | 1 | 1 | 100% | 100% |
| 连续登录 | 1 | 1 | 100% | 100% |
| **财富成就** | **35** | **11** | **31%** | **90%+** |
| 探索成就 | N | 0 | 0% | 0% |

## 6. API Reference

**核心方法**:
```python
# 更新统计数据
await AchievementService.update_stat(player_id: str, stat_name: str, value: int)

# 检查并解锁成就
unlocked = await AchievementService.check_achievements(player_id: str, stat_name: str)

# 查询玩家成就列表
achievements = await AchievementService.get_player_achievements(player_id: str)

# 手动触发成就检查（用于登录、等级提升等事件）
await AchievementService.check_level_achievements(player_id: str, current_level: int)
```

**命令接口**:
- `【成就】` / `【成就 1】` - 查询成就列表第1页（默认）
- `【成就 2】` - 查询成就列表第2页（数字参数=页码）
- `【成就 成就名】` - 查询单个成就的详细信息（支持成就名或成就ID）
- 输出格式: 分页显示（15个/页），标注完成/未完成，显示进度和奖励

## 7. Future Enhancements

1. **隐藏成就**: `hidden: true` 的成就不在列表中显示，解锁后惊喜感
2. **成就系列**: 多阶段成就（青铜/白银/黄金）
3. **成就称号**: 完成特定成就解锁专属称号
4. **成就点数**: 累计成就点数兑换特殊奖励
5. **社交分享**: 成就解锁时推送到公会频道

---

**相关文档**:
- 使用指南: `/llmdoc/guides/achievement-system-guide.md`
- 数据模型: `/llmdoc/reference/data-models.md#新手体验系统`
- 设计方案: `/llmdoc/design/game_system_redesign_2025_12_02.md#Phase 2`
