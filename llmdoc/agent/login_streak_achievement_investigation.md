# 连续登录类成就(login_streak)触发失败调查报告

## 调查概述

**调查时间**: 2025-12-05
**调查目标**: 连续登录类成就（login_streak）为何触发不了或统计不上
**调查结论**: ❌ **未集成** - 签到系统存在但未调用成就系统的统计追踪方法

---

## 代码证据 (Code Sections)

### 1. 成就配置 (achievements.yaml)

- `plugins/xiuxian_game/data/achievements.yaml:140-153` (loyal_believer成就): 连续登录3天成就配置正确
  - condition_type: "login_streak"
  - condition_target: "consecutive_days"
  - condition_value: 3
  - rewards: 金币3000, 经验1000, 属性点5

- `plugins/xiuxian_game/data/achievements.yaml:389-417` (weekly_devotee成就): 连续登录7天成就配置正确
  - condition_type: "login_streak"
  - condition_value: 7

- `plugins/xiuxian_game/data/achievements.yaml:404-432` (monthly_devotee成就): 连续登录30天成就配置正确
  - condition_type: "login_streak"
  - condition_value: 30

- `plugins/xiuxian_game/data/achievements.yaml:419-432` (lifetime_achievement成就): 累计登录100天成就配置正确
  - condition_type: "total_login_days"
  - condition_value: 100

### 2. 成就检查逻辑 (AchievementService)

- `plugins/xiuxian_game/achievement/achievement_service.py:149-187` (update_login_streak方法): **已实现**登录连续天数更新逻辑
  - 检查last_login_date与今天的差值
  - 连续登录: consecutive_login_days += 1
  - 中断登录: consecutive_login_days = 1
  - 更新last_login_date和total_login_days

- `plugins/xiuxian_game/achievement/achievement_service.py:294-299` (login_streak条件检查): **已实现**成就检查逻辑
  - 检查 `stats.consecutive_login_days >= condition_value`
  - 支持 total_login_days 检查(line 297-299)

### 3. 数据模型 (PlayerStats)

- `plugins/xiuxian_game/models/achievement.py:60-63` (登录统计字段): **已定义**所有必要字段
  - last_login_date: 最后登录日期 (DateTime, nullable)
  - consecutive_login_days: 连续登录天数 (Integer, default=0)
  - total_login_days: 总登录天数 (Integer, default=0)

### 4. 签到系统 (sign.py) - **问题根源**

- `plugins/xiuxian_game/entertainment/sign.py:1-206` (签到命令处理器): ❌ **未集成成就系统**
  - Line 34-46: 有签到检查逻辑（使用 Player.last_sign 和 Player.sign_streak）
  - Line 80: 更新 player.last_sign = now
  - **缺失**: 无任何 AchievementService 导入或调用

- `plugins/xiuxian_game/models/player.py:76-77` (Player模型): 签到字段存在
  - last_sign: 上次签到日期 (DateTime)
  - sign_streak: 连续签到天数 (Integer)
  - **注意**: 这些字段与 PlayerStats 的登录字段是**分离的两套系统**

### 5. 已集成的参考示例

- `plugins/xiuxian_game/cultivate/core.py:243-244` (修炼系统集成): ✅ 正确集成
  ```python
  await AchievementService.update_stat(session, player.id, "cultivation_count")
  achievement_msgs = await AchievementService.check_achievements(session, player)
  ```

- `plugins/xiuxian_game/world/attack_command.py:734-736` (战斗系统集成): ✅ 正确集成
  ```python
  await AchievementService.update_stat(session, attacker.id, "total_battles", auto_commit=False)
  await AchievementService.update_stat(session, attacker.id, "total_wins", auto_commit=False)
  await AchievementService.update_stat(session, attacker.id, "total_kills", auto_commit=True)
  ```

---

## 调查报告 (Report)

### 问题根因分析 (Root Cause)

**核心问题**: 签到系统（`sign.py`）与成就系统（`achievement_service.py`）**完全未集成**

1. **数据孤岛**:
   - Player模型有 `last_sign` + `sign_streak` 字段（仅用于签到逻辑）
   - PlayerStats模型有 `last_login_date` + `consecutive_login_days` 字段（用于成就系统）
   - **两套字段互不通信**，导致成就系统无法感知签到行为

2. **缺失的调用链**:
   - 签到命令处理器（`sign.py`）在更新签到记录后，**没有调用** `AchievementService.update_login_streak()`
   - 成就检查逻辑已完善，但**永远不会被触发**

3. **语义不一致**:
   - 签到（sign）≈ 登录（login），但代码中将其视为两个独立概念
   - 用户"签到"时，应该被识别为"登录"行为并追踪连续登录天数

### 具体集成缺失点

**文件**: `plugins/xiuxian_game/entertainment/sign.py`
**位置**: Line 80-82（更新签到日期之后）

**当前代码**:
```python
# 更新签到日期
player.last_sign = now
# ... 后续逻辑
await session.commit()
```

**缺失逻辑**:
```python
# 更新签到日期
player.last_sign = now

# ❌ 缺失: 同步到成就系统
# await AchievementService.update_login_streak(session, player.id)
# achievement_msgs = await AchievementService.check_achievements(session, player)
```

---

## 结论 (Conclusions)

### 关键事实

1. ✅ **配置完整**: achievements.yaml 中连续登录类成就（loyal_believer, weekly_devotee, monthly_devotee）配置正确
2. ✅ **逻辑完善**: `AchievementService.update_login_streak()` 和 `check_achievements()` 已实现且逻辑正确
3. ✅ **字段就绪**: `PlayerStats` 模型包含所有必要的登录统计字段
4. ❌ **集成缺失**: 签到系统（`sign.py`）完全未调用成就系统方法
5. ⚠️ **数据孤岛**: `Player.sign_streak` 与 `PlayerStats.consecutive_login_days` 是两套独立系统

### 影响范围

- **4个连续登录类成就**: loyal_believer (3天), weekly_devotee (7天), monthly_devotee (30天), lifetime_achievement (100天)
- **所有玩家**: 无论老玩家还是新玩家，连续登录成就永远无法解锁
- **玩家留存目标**: 成就系统设计的"提升留存率"目标无法达成

---

## 关系图 (Relations)

### 当前架构（断裂）

```
[sign.py 签到命令]
    ↓ 更新
[Player.last_sign, Player.sign_streak]
    ↓ (❌ 断裂)
[AchievementService]
    ↓ 永远不会调用
[PlayerStats.consecutive_login_days]
    ↓ 永远为0
[login_streak成就] ← ❌ 永远无法解锁
```

### 预期架构（完整）

```
[sign.py 签到命令]
    ↓ 更新
[Player.last_sign, Player.sign_streak]
    ↓ 同步 (✅ 需补充)
[AchievementService.update_login_streak()]
    ↓ 更新
[PlayerStats.consecutive_login_days]
    ↓ 触发检查
[AchievementService.check_achievements()]
    ↓ 解锁
[login_streak成就] ← ✅ 正常触发
```

### 已集成系统参考

- `cultivate/core.py:243-244` → `AchievementService.update_stat("cultivation_count")` → cultivation成就 ✅
- `world/attack_command.py:734-736` → `AchievementService.update_stat("total_wins")` → battle成就 ✅
- `sign.py:80` → ❌ **缺失调用** → login_streak成就 ❌

---

## 修复方案摘要 (Solution Summary)

### 集成点

**文件**: `plugins/xiuxian_game/entertainment/sign.py`
**位置**: Line 80-82 之后，commit 之前
**方法**: 添加两行代码

### 必要步骤

1. **导入成就服务** (文件顶部):
   ```python
   from ..achievement.achievement_service import AchievementService
   ```

2. **更新登录统计** (Line 80后):
   ```python
   # 更新签到日期
   player.last_sign = now

   # 同步到成就系统
   await AchievementService.update_login_streak(session, player.id)
   ```

3. **检查并解锁成就** (commit前):
   ```python
   # 检查成就
   achievement_msgs = await AchievementService.check_achievements(session, player)

   await session.commit()
   ```

4. **显示成就消息** (响应消息中):
   ```python
   # 构建完整消息
   full_message = f"...签到消息..."
   if achievement_msgs:
       full_message += "\n\n" + "\n".join(achievement_msgs)

   await sign.send(full_message)
   ```

### 预期效果

- 玩家每次签到后，`PlayerStats.consecutive_login_days` 会正确更新
- 连续签到3/7/30天后，对应成就会自动解锁并发放奖励
- 累计签到100天后，lifetime_achievement成就会解锁

---

## 相关文档

- 成就系统架构: `/llmdoc/architecture/achievement-system.md`
- 成就系统指南: `/llmdoc/guides/achievement-system-guide.md`
- 数据模型参考: `/llmdoc/reference/data-models.md`
