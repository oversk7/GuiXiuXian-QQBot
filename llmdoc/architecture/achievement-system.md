# 微成就系统架构

## 1. Identity

- **What it is**: 配置驱动的微成就系统，为新手玩家提供渐进式成就感
- **Purpose**: 提升新手留存率，通过即时反馈和小型奖励引导玩家探索游戏功能

## 2. Core Components

- `plugins/xiuxian_game/achievement/achievement_service.py` (AchievementService): 成就检查、进度更新、奖励发放核心服务
- `plugins/xiuxian_game/achievement/commands.py` (成就查询命令): 玩家查询成就列表和进度
- `plugins/xiuxian_game/data/achievements.yaml` (成就配置): 10个基础成就定义（条件、奖励、文案）
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

## 4. Design Rationale

### 4.1 为什么选择配置驱动？

- **易于扩展**: 新增成就无需修改代码，只需编辑YAML
- **策划友好**: 游戏策划可直接调整成就条件和奖励
- **热更新**: 未来可支持运行时重载配置

### 4.2 为什么分离PlayerStats表？

- **解耦统计与成就**: 统计数据可用于其他分析（排行榜、数据看板）
- **性能优化**: 高频统计更新不影响PlayerAchievement表查询
- **独立索引**: 可为统计字段单独建立索引优化查询

### 4.3 10个基础成就的设计意图

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

## 5. Integration Points

**已集成的命令处理器** (Phase 2完成):
1. `cultivate/core.py:120` - 修炼后更新 `cultivation_count`
2. `world/attack_command.py:85,90` - 战斗后更新 `total_wins` 和 `total_kills`
3. `models/inventory.py:150` - 获得装备时更新 `equipment_obtained`
4. （待实现）登录检查点 - 更新 `consecutive_login_days`
5. （待实现）金币获取点 - 更新 `gold_earned_total`
6. （待实现）地点探索 - 更新 `locations_visited`

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
- `【成就】` / `【成就列表】` / `【我的成就】` - 查询成就列表和完成进度
- 输出格式: 分类显示，标注完成/未完成，显示进度和奖励

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
