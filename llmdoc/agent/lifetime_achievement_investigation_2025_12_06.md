# 签到类成就中"终身成就"进度没有跟随签到更新的问题调查报告

**调查日期**: 2025-12-06
**调查对象**: 终身成就（lifetime_achievement）进度更新问题
**发现严重级别**: 高（成就无法正确显示进度）

---

## 1. Code Sections (The Evidence)

### 成就配置
- `plugins/xiuxian_game/data/achievements.yaml:419-432` (lifetime_achievement成就定义): 条件类型为 `total_login_days`，目标为 `total_days`，阈值为100天

### PlayerStats数据模型
- `plugins/xiuxian_game/models/achievement.py:35-69` (PlayerStats类):
  - 第63行：`total_login_days` 字段（总登录天数）
  - 第62行：`consecutive_login_days` 字段（连续登录天数）

### 成就检查流程 - 条件判断
- `plugins/xiuxian_game/achievement/achievement_service.py:221-327` (check_achievements方法):
  - 第297-299行：正确实现了 `total_login_days` 条件检查：`is_unlocked = stats.total_login_days >= condition_value`

### 签到系统集成
- `plugins/xiuxian_game/entertainment/sign.py:86-87` (签到处理): 调用 `update_login_streak()` 更新登录统计
- `plugins/xiuxian_game/entertainment/sign.py:209` (签到处理): 调用 `check_achievements()` 检查成就解锁

### 登录统计更新逻辑
- `plugins/xiuxian_game/achievement/achievement_service.py:148-187` (update_login_streak方法):
  - 第185行：`stats.total_login_days += 1` - 在签到时正确递增
  - 第176、179、182行：正确维护 `consecutive_login_days`（连续登录天数）

### 成就进度显示缺陷 - 关键问题
- `plugins/xiuxian_game/achievement/achievement_service.py:431-529` (get_player_achievements方法):
  - **第514-515行**：处理 `login_streak` 条件类型的进度显示
  - **第516-521行**：处理 `account_age` 条件类型的进度显示
  - **缺失**：**没有处理 `total_login_days` 条件类型的进度显示**！
  - 结果：当玩家查看成就列表时，"终身成就"的进度会显示为0（初始值）

---

## 2. Report

### result

**问题描述**: "终身成就"（lifetime_achievement）的进度没有在查看成就列表时更新。

**根本原因**: 代码存在两处分离的逻辑：
1. **成就解锁检查** (`check_achievements` 第297-299行)：✅ 正确实现了 `total_login_days >= 100` 的判断
2. **成就列表显示** (`get_player_achievements` 第495-523行)：❌ **缺少对 `total_login_days` 的进度计算**

**影响范围**:
- 所有使用 `condition_type: "total_login_days"` 的成就（目前只有"终身成就"）
- 玩家无法在成就列表中看到正确的进度（始终显示0）
- 实际上成就可能已经达成，但玩家看不到进度

**具体表现**:
- 签到时：`update_login_streak()` 正确更新了 `player_stats.total_login_days`
- 成就检查时：`check_achievements()` 正确判断并解锁成就
- 成就查询时：`get_player_achievements()` 因缺少对应的进度计算分支，显示进度为0

### conclusions

1. **签到系统与成就系统的集成是完成的**（sign.py:86-87 和 sign.py:209）
   - 已调用 `update_login_streak()` 更新统计
   - 已调用 `check_achievements()` 检查解锁

2. **PlayerStats模型正确包含 `total_login_days` 字段**（achievement.py:63）
   - 字段类型：Integer
   - 默认值：0
   - 注释：总登录天数

3. **update_login_streak() 方法正确更新 `total_login_days`**（achievement_service.py:185）
   - 每次签到时递增1

4. **check_achievements() 正确处理 `total_login_days` 条件**（achievement_service.py:297-299）
   - 判断逻辑：`stats.total_login_days >= condition_value`
   - 这是完全正确的

5. **get_player_achievements() 缺少进度显示分支**（achievement_service.py:495-523）
   - **缺失的代码分支**：在第514-515行处理完 `login_streak` 后，应该添加对 `total_login_days` 的处理
   - 当前：跳过直接进入 `account_age` 处理（第516行）
   - 结果：使用默认的 `current_progress = 0`

6. **所有签到类成就的进度显示模式**：
   - `login_streak`（连续登录）：显示连续天数 ✅
   - `total_login_days`（累计登录）：**缺失处理** ❌

### relations

**数据流关系**:
1. 玩家签到 (sign.py)
   ↓
2. 调用 `update_login_streak()` (achievement_service.py:149-187)
   ├─ 更新 `consecutive_login_days`（连续天数）
   └─ 更新 `total_login_days`（累计天数）✅ 正确
   ↓
3. 调用 `check_achievements()` (achievement_service.py:221-327)
   ├─ 检查 `condition_type == "total_login_days"` (第297-299行)
   └─ 正确判断并解锁成就 ✅
   ↓
4. 玩家查看成就列表 (`【成就】` 命令)
   ↓
5. 调用 `get_player_achievements()` (achievement_service.py:431-529)
   ├─ 第514-515行：处理 `login_streak` 进度
   ├─ **第516行：跳过 `total_login_days` 分支**（缺失！）
   └─ 显示 `current_progress = 0`（默认值）❌

**受影响的成就配置**:
- `lifetime_achievement` (achievements.yaml:419-432)
  - condition_type: `total_login_days`
  - condition_target: `total_days`
  - condition_value: 100
  - 该成就无法在列表中显示正确的进度

**类似的成就进度处理对比**:
- `login_streak`（连续登录）：第514-515行 ✅ 有处理
- `gold_total`（累计金币）：第510-511行 ✅ 有处理
- `total_login_days`（累计登录）：❌ 没有处理
- `account_age`（账号年龄）：第516-521行 ✅ 有处理

---

## 3. 修复建议

在 `achievement_service.py` 的 `get_player_achievements` 方法中，第515行之后添加对 `total_login_days` 的处理：

```python
elif condition_type == "login_streak":
    current_progress = stats.consecutive_login_days
elif condition_type == "total_login_days":  # <-- 新增此分支
    current_progress = stats.total_login_days  # <-- 新增此行
elif condition_type == "account_age":
    # ... 现有代码
```

**修改位置**: `plugins/xiuxian_game/achievement/achievement_service.py:514-521`

**预期效果**: 玩家查看成就列表时，"终身成就"的进度会正确显示当前的累计登录天数

---

## 4. 验证步骤

1. **签到逻辑验证**：✅ 已确认在sign.py中调用了 `update_login_streak()`
2. **数据更新验证**：✅ 已确认 `total_login_days` 在签到时正确递增
3. **成就解锁检查**：✅ 已确认 `check_achievements()` 正确处理100天阈值
4. **进度显示缺陷**：❌ 已确认 `get_player_achievements()` 缺少 `total_login_days` 的分支

---

## 5. 补充说明

### 为什么只影响"终身成就"？

因为在当前的 `achievements.yaml` 配置中，只有一个成就使用了 `condition_type: "total_login_days"`：

```yaml
lifetime_achievement:
  condition_type: "total_login_days"  # 只有这一个
  condition_value: 100
```

其他登录类成就使用的是 `login_streak`（连续登录），那个类型在 `get_player_achievements` 中是有处理的。

### 数据一致性分析

**在数据库层面**：
- `PlayerStats.total_login_days` 字段：✅ 存在且正确
- 每次签到更新：✅ 正确
- 成就条件判断：✅ 正确

**在展示层面**：
- 成就解锁消息：✅ 正确（通过 `check_achievements` 的返回值）
- 成就列表查询：❌ 缺少进度显示

### 相关系统对比

| 成就类型 | 条件类型 | 统计字段 | check_achievements | get_player_achievements |
|---------|---------|---------|-------------------|----------------------|
| 连续登录 | login_streak | consecutive_login_days | ✅ 第294-296行 | ✅ 第514-515行 |
| 累计登录 | total_login_days | total_login_days | ✅ 第297-299行 | ❌ **缺失** |
| 累计金币 | gold_total | gold_earned_total | ✅ 第288-290行 | ✅ 第510-511行 |
| 修炼次数 | command_count | cultivation_count | ✅ 第273-275行 | ✅ 第500-501行 |
| 击杀数 | kill_count | total_kills | ✅ 第282-284行 | ✅ 第506-507行 |
| 账号年龄 | account_age | player.created_at | ✅ 第314-320行 | ✅ 第516-521行 |

从对比表可以看出，`total_login_days` 是唯一缺少进度显示处理的条件类型。

---

**相关文档**:
- 成就系统架构: `/llmdoc/architecture/achievement-system.md`
- 成就系统集成修复: `/llmdoc/agent/achievement_integration_fix_2025_12_05.md`
- 登录成就调查: `/llmdoc/agent/login_streak_achievement_investigation.md`
