# 如何使用和扩展成就系统

## 1. 快速开始：如何添加新成就

### Step 1: 在配置文件中定义成就

编辑 `plugins/xiuxian_game/data/achievements.yaml`:

```yaml
basic_achievements:
  your_new_achievement:
    id: "your_new_achievement"
    title: "成就标题"
    description: "成就描述文本"
    icon: "🎯"  # Emoji图标
    condition_type: "command_count"  # 见下方条件类型表
    condition_target: "修炼"
    condition_value: 50
    rewards:
      gold: 10000
      exp: 2000
      attribute_points: 10
      items:  # 可选，物品奖励
        - item_id: "sweep_order"
          quantity: 5
    flavor_text: "你的励志文案"
    hidden: false  # true=隐藏成就，解锁前不可见
```

### Step 2: 添加到分类（可选）

在同一文件的 `categories` 部分添加：

```yaml
categories:
  cultivation: ["first_cultivation", "cultivation_adept", "your_new_achievement"]
```

### Step 3: 集成统计追踪

在对应的命令处理器中调用统计更新：

```python
from plugins.xiuxian_game.achievement.achievement_service import AchievementService

# 在命令执行后更新统计
async def handle_command(player_id: str):
    # ... 命令逻辑

    # 更新统计（会自动检查相关成就）
    unlocked = await AchievementService.update_stat(
        player_id=player_id,
        stat_name="cultivation_count",  # 统计字段名
        increment=1  # 增量（默认=1）
    )

    # 如果解锁了新成就，返回通知消息
    if unlocked:
        return f"原命令结果\n\n{unlocked}"
```

### Step 4: 重启机器人

修改配置文件后，重启机器人加载新成就定义。数据库表会自动迁移（无需手动执行SQL）。

---

## 2. 条件类型速查表

| condition_type | condition_target | condition_value | 说明 | 统计字段 |
|---------------|------------------|----------------|------|---------|
| `command_count` | 命令名（如"修炼"） | 次数 | 执行某命令N次 | `cultivation_count` |
| `level_reached` | `"level"` | 等级 | 达到某等级 | 玩家当前等级 |
| `battle_win` | `"total_wins"` | 次数 | 战斗胜利N次 | `total_wins` |
| `kill_count` | `"total_kills"` | 次数 | 击杀N个敌人 | `total_kills` |
| `gold_total` | `"gold_earned"` | 金额 | 累计获得N金币 | `gold_earned_total` |
| `equipment_obtained` | `"any_equipment"` | 件数 | 获得N件装备 | `equipment_obtained` |
| `locations_visited` | `"unique_locations"` | 地点数 | 访问N个地点 | `locations_visited` |
| `login_streak` | `"consecutive_days"` | 天数 | 连续登录N天 | `consecutive_login_days` |

---

## 3. 统计字段完整列表

**修炼相关**:
- `cultivation_count` - 累计修炼次数

**战斗相关**:
- `total_battles` - 总战斗次数
- `total_wins` - 总胜利次数
- `total_kills` - 总击杀数

**财富相关**:
- `gold_earned_total` - 累计获得金币
- `gold_spent_total` - 累计花费金币

**探索相关**:
- `locations_visited` - 探索过的地点数
- `locations_visited_list` - 地点列表（逗号分隔字符串）

**装备相关**:
- `equipment_obtained` - 获得过的装备数

**登录相关**:
- `last_login_date` - 最后登录日期
- `consecutive_login_days` - 连续登录天数
- `total_login_days` - 总登录天数

---

## 4. 高级用法：手动触发成就检查

某些成就无法通过统计追踪（如等级提升），需要手动触发检查：

```python
from plugins.xiuxian_game.achievement.achievement_service import AchievementService

# 等级提升后检查成就
async def on_level_up(player_id: str, new_level: int):
    unlocked = await AchievementService.check_level_achievements(
        player_id=player_id,
        current_level=new_level
    )
    if unlocked:
        await send_message(unlocked)
```

---

## 5. 奖励配置详解

### 5.1 基础奖励

```yaml
rewards:
  gold: 5000        # 金币
  exp: 1000         # 经验
  attribute_points: 10  # 属性点
```

### 5.2 物品奖励

```yaml
rewards:
  items:
    - item_id: "heal_potion"  # 物品ID（参考items.yaml）
      quantity: 10            # 数量
    - item_id: "sweep_order"
      quantity: 3
```

### 5.3 多重奖励组合

```yaml
rewards:
  gold: 10000
  exp: 2000
  attribute_points: 15
  items:
    - item_id: "mystery_box"
      quantity: 1
```

---

## 6. 常见问题排查

### Q1: 新成就不生效？
- **检查1**: 确认配置文件无YAML语法错误（缩进、引号）
- **检查2**: 重启机器人加载新配置
- **检查3**: 查看日志是否有加载错误

### Q2: 统计数据不更新？
- **检查1**: 确认已在命令处理器中调用 `update_stat()`
- **检查2**: 检查 `stat_name` 是否与PlayerStats字段名匹配
- **检查3**: 查询数据库 `player_stats` 表验证数据

### Q3: 成就重复解锁？
- **原因**: `is_completed` 标记未正确设置
- **解决**: 检查 `AchievementService.check_achievements()` 逻辑
- **临时修复**: 手动更新数据库 `UPDATE player_achievement SET is_completed=1`

---

## 7. 最佳实践

### 7.1 成就难度梯度设计

```yaml
# 入门成就（1-5分钟完成）
first_xxx:
  condition_value: 1
  rewards: { gold: 500, exp: 100 }

# 初级成就（10-30分钟完成）
beginner_xxx:
  condition_value: 10
  rewards: { gold: 2000, exp: 500 }

# 中级成就（1-3小时完成）
intermediate_xxx:
  condition_value: 50
  rewards: { gold: 10000, exp: 3000 }

# 高级成就（1周+完成）
advanced_xxx:
  condition_value: 500
  rewards: { gold: 100000, exp: 50000, attribute_points: 50 }
```

### 7.2 奖励价值参考

| 成就难度 | 金币奖励 | 经验奖励 | 属性点 | 物品奖励 |
|---------|---------|---------|-------|---------|
| 入门（<5分钟） | 500-1000 | 100-300 | 0-5 | 常见物品×10 |
| 初级（10-30分钟） | 2000-5000 | 500-1000 | 5-10 | 稀有物品×5 |
| 中级（1-3小时） | 10000-30000 | 3000-10000 | 10-20 | 史诗物品×3 |
| 高级（1周+） | 100000+ | 50000+ | 50+ | 传说物品×1 |

### 7.3 文案撰写建议

```yaml
title: "简短有力（4-6字）"
description: "清晰说明完成条件（15-30字）"
flavor_text: "有氛围感的励志文案（10-20字）"
```

**示例**:
```yaml
title: "百战老兵"
description: "击败100个敌人，积累战斗经验"
flavor_text: "经百战而不殆，历磨难而愈强"
```

---

**相关文档**:
- 架构设计: `/llmdoc/architecture/achievement-system.md`
- 数据模型: `/llmdoc/reference/data-models.md#新手体验系统`
- 配置文件: `plugins/xiuxian_game/data/achievements.yaml`
