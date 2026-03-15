# Battle UI 摘要优化实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `title`（折叠外可见大标题）改为简洁胜负说明，将 `hint`（底部一行文字）改为奖励/结果摘要，让玩家无需展开战斗日志就能看到关键信息。

**Architecture:** `battle_markdown.py` API **不变**（`title`/`hint` 参数保持）。只改各调用方传入的值。`world_boss/service_new.py` 返回新增 `boss_title`/`boss_hint` 两个字段。

**Tech Stack:** Python 3.10+, 已有 `build_battle_markdown()` helper

---

## 设计总览

模版渲染后的布局：
```
# {title}          ← 折叠外可见，改为：简洁胜负/关键事件
```bash
{desc = 完整战斗日志}   ← 折叠，玩家点开才看
```
***
> {hint}           ← 折叠外可见，改为：奖励/结果摘要
[btn1] [btn2] [btn3]
```

| 场景 | 旧 title | 新 title | 新 hint |
|------|---------|---------|--------|
| 切磋 (pvp) | `⚔️ 切磋结果 · A vs B` | `⚔️ A 胜！` | `切磋不影响数据` |
| 模拟战斗 | `🎮 模拟战斗 · A vs B` | `🎮 A 胜！` | `模拟 不影响数据` |
| 镜怨体质触发 | `⚔️ 战斗结果 · A vs B` | `⚔️ B 胜（镜怨反弹）` | drop_summary（掉落信息）|
| 龙影闪触发 | `⚔️ 战斗结果 · A vs B` | `⚔️ B 胜（虚界反噬）` | drop_summary |
| PvP主战城镇 | `🏘️ 城镇切磋 · A vs B` | `🏘️ A 胜！` | `城镇切磋 无掉落` |
| PvP死斗 | `⚔️/👹 荒野死斗 · A vs B` | `⚔️/👹 A 胜！` | drop_summary |
| PvE NPC胜利 | `⚔️ 战斗结果 · A vs NPC` | `⚔️ NPC已击倒！` | `+{exp}EXP +{gold}金` |
| PvE NPC失败 | `⚔️ 战斗结果 · A vs NPC` | `💀 败于 NPC` | `血量耗尽` |
| 讨伐BOSS | `🌑 讨伐结果 · BOSS名` | `🌑 造成 X 伤害` | `累计 Y · 余Z次` |
| 迎战英雄胜利 | `🏰 迎战结果 · 英雄名` | `🏰 英雄名 倒下！` | `+N天灾点` |
| 迎战英雄失败 | `🏰 迎战结果 · 英雄名` | `🏰 被 英雄名 击倒` | `封印24小时` |
| 里界战斗胜利 | `🌀 内界战斗结果` | `🌀 战斗胜利！` | `+{gold}金币` 或 `战斗胜利` |
| 里界战斗失败 | `🌀 内界战斗结果` | `🌀 战斗失败` | `继续探索里界` |

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| 修改 | `plugins/xiuxian_game/battle/pvp_commands.py` |
| 修改 | `plugins/xiuxian_game/world/attack_command.py` |
| 修改 | `plugins/xiuxian_game/world_boss/service_new.py` |
| 修改 | `plugins/xiuxian_game/world_boss/__init__.py` |
| 修改 | `plugins/xiuxian_game/lower_world/commands.py` |
| 修改 | `plugins/xiuxian_game/inner_realm/commands.py` |

---

## Task 1: 修改 `battle/pvp_commands.py`

**Files:**
- Modify: `plugins/xiuxian_game/battle/pvp_commands.py`

**上下文：**
- `handle_pvp()` 约第 94-112 行：`victory, battle_log, challenger_damage, target_damage = await BattleIntegrationHelper.compact_player_vs_player_battle(...)` 后直接调用 `build_battle_markdown()`
- `handle_simulate()` 类似结构，`player1`/`player2` 替代 `challenger`/`target_player`

- [ ] **Step 1: 修改 `handle_pvp()`**

找到当前 `build_battle_markdown()` 调用（在 `compact_player_vs_player_battle` 返回后），**在其上方**增加：

```python
winner = challenger if victory else target_player
```

将 `build_battle_markdown()` 调用中的参数改为：

```python
title=f"⚔️ {winner.nickname} 胜！",
hint="切磋不影响数据",
```

- [ ] **Step 2: 修改 `handle_simulate()`**

**注意：** `handle_simulate()` 中当前的解包写法为 `_, battle_log, p1_damage, p2_damage = await ...`，`_` 丢弃了 `victory` 值。需要**先把 `_` 改为 `victory`**，再在 `build_battle_markdown()` 上方增加：

```python
victory, battle_log, p1_damage, p2_damage = await ...  # 将 _ 改为 victory
...
winner = player1 if victory else player2
```

将参数改为：

```python
title=f"🎮 {winner.nickname} 胜！",
hint="模拟 不影响数据",
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/battle/pvp_commands.py
git commit -m "feat: 切磋/模拟战斗 title 改为胜者名，hint 改为结果说明"
```

---

## Task 2: 修改 `world/attack_command.py`（4 条路径）

**Files:**
- Modify: `plugins/xiuxian_game/world/attack_command.py`

**重要：先完整阅读 `attack_command.py`，确认各路径变量范围，再做修改。**

### 路径 1 — 镜怨体质前置判定（约第 520-593 行）

**上下文：**
- `winner = target` 和 `loser = attacker` 已在约第 521-522 行定义
- `drop_summary` 已在约第 539-547 行定义（`"🛡️ 掉落保护生效"` / `drop_msg.replace("\n", "；")` / `"无掉落"` 三种分支）
- `build_battle_markdown()` 在约第 586-593 行调用

找到路径1的 `build_battle_markdown()` 调用，将：
```python
title=f"⚔️ 战斗结果 · {attacker.nickname} vs {target.nickname}",
hint="快捷操作: 探索 | 面板 | 背包",
```
改为：
```python
title=f"⚔️ {winner.nickname} 胜（镜怨反弹）",
hint=drop_summary,
```

### 路径 2 — 龙影闪前置判定（约第 606-678 行）

**上下文：**
- `winner = target` 和 `loser = attacker` 已在约第 608-609 行定义
- `drop_summary` 在约第 625-633 行已定义

找到路径2的 `build_battle_markdown()` 调用，将：
```python
title=f"⚔️ 战斗结果 · {attacker.nickname} vs {target.nickname}",
hint="快捷操作: 探索 | 面板 | 背包",
```
改为：
```python
title=f"⚔️ {winner.nickname} 胜（虚界反噬）",
hint=drop_summary,
```

### 路径 3 — PvP 主战结果

**上下文：**
- 在 `if not in_town:` 块内（约第 870 行开始），`winner = attacker if victory else target` 在约第 887 行定义，但**仅在 `not in_town` 时有效**。
- `drop_summary = ""` 在约第 890 行初始化（`not in_town` 时），之后更新为具体值
- `in_town = True` 时 `winner` 和 `drop_summary` 未定义
- `build_battle_markdown()` 的 `finish()` 在 `if not in_town:` 块**之外**调用

在路径3的 `await attack_cmd.finish(build_battle_markdown(...))` 调用**之前**（新手任务/成就检查之后），添加：

```python
pvp_winner = attacker if victory else target
if in_town:
    pvp_hint = "城镇切磋 无掉落"
else:
    pvp_hint = drop_summary if drop_summary else "无物品掉落"
```

将 `build_battle_markdown()` 调用中的参数改为：

```python
title=f"{battle_type} · {pvp_winner.nickname} 胜！",
hint=pvp_hint,
```

### 路径 4 — PvE NPC 攻击结果（`handle_npc_attack` 函数）

**上下文：**
- `victory` 来自 `enhanced_player_vs_monster_battle_v2()` 返回
- `target_npc.name` 可用
- 普通鬼怪胜利时：`exp_gain = target_npc.level * 10`，`gold_gain = target_npc.level * 5`
- 活动鬼怪（knocker）有不同奖励逻辑，不走 `exp_gain`/`gold_gain` 分支

在 `result_lines = ["━━━━━━━━━━━━━"]` 初始化之后，添加：

```python
npc_reward_hint = ""
```

在普通鬼怪胜利奖励计算处（`exp_gain`/`gold_gain` 赋值之后），添加：

```python
npc_reward_hint = f"+{exp_gain}EXP +{gold_gain}金"
```

在败北处理（`else` 分支），添加：

```python
npc_reward_hint = "血量耗尽"
```

在路径4的 `await attack_cmd.finish(build_battle_markdown(...))` 之前，添加：

```python
npc_title = f"⚔️ {target_npc.name} 已击倒！" if victory else f"💀 败于 {target_npc.name}"
if not npc_reward_hint:
    npc_reward_hint = "获得战斗奖励" if victory else "血量耗尽"
```

将 `build_battle_markdown()` 调用中的参数改为：

```python
title=npc_title,
hint=npc_reward_hint,
```

- [ ] **Step 1: 修改路径 1（镜怨体质）**
- [ ] **Step 2: 修改路径 2（龙影闪）**
- [ ] **Step 3: 修改路径 3（PvP 主战）**
- [ ] **Step 4: 修改路径 4（PvE NPC）**

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/world/attack_command.py
git commit -m "feat: attack_command 4条路径 title 改为胜者说明，hint 改为奖励摘要"
```

---

## Task 3: 修改 `world_boss/service_new.py` + `world_boss/__init__.py`

**Files:**
- Modify: `plugins/xiuxian_game/world_boss/service_new.py`
- Modify: `plugins/xiuxian_game/world_boss/__init__.py`

**设计说明：**
- `attack_boss()` 目前返回 `Tuple[bool, list]`
- 改为返回 `Tuple[bool, list, str, str]`，第3/4个元素为 `boss_title` 和 `boss_hint`
- `ok=True` 时：`boss_title=f"🌑 造成 {damage_dealt:,} 伤害"`, `boss_hint=f"累计 {total_damage:,} · 余{remaining}次"`
- `ok=False` 时：`boss_title=""`, `boss_hint=""`

- [ ] **Step 1: 修改 `service_new.py` 的 `attack_boss()` 函数**

**1a. 修改函数签名注释中的 Returns 部分：**

```python
    Returns:
        (是否成功, 结果行列表, 标题字符串, 摘要字符串)
        ok=True:  list[str]，包含完整 battle_log 与摘要行; title=造成伤害; hint=累计/余次
        ok=False: list[str]，单行错误文字; title=""; hint=""
```

**1b. 修改所有 `return False, [...]` 路径**（共3处，约第 393、399、403 行），每处在 list 后加两个空字符串：

```python
return False, [f"...原有错误文字..."], "", ""
```

**1c. 在函数末尾（找到 `full_lines = list(battle_log) + ["━━━━━━━━━━━━━"] + lines` 一行），改为：**

```python
remaining_attacks = WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today
boss_title = f"🌑 造成 {damage_dealt:,} 伤害"
boss_hint = f"累计 {damage_record.total_damage:,} · 余{remaining_attacks}次"
full_lines = list(battle_log) + ["━━━━━━━━━━━━━"] + lines
return True, full_lines, boss_title, boss_hint
```

- [ ] **Step 2: 修改 `world_boss/__init__.py` 的 `handle_attack()`**

将：
```python
ok, lines = await service.attack_boss(cycle, player)
if ok:
    if tip:
        lines = [tip, "━━━━━━━━━━━━━"] + lines
    await attack_cmd.finish(build_battle_markdown(
        title=f"🌑 讨伐结果 · {cycle.boss_name}",
        battle_log=lines,
        hint="快捷操作: 讨伐BOSS | BOSS排行 | 面板",
        btn1="讨伐BOSS",
        btn2="BOSS排行",
        btn3="面板",
    ))
```

改为：
```python
ok, lines, boss_title, boss_hint = await service.attack_boss(cycle, player)
if ok:
    if tip:
        lines = [tip, "━━━━━━━━━━━━━"] + lines
    await attack_cmd.finish(build_battle_markdown(
        title=boss_title,
        battle_log=lines,
        hint=boss_hint,
        btn1="讨伐BOSS",
        btn2="BOSS排行",
        btn3="面板",
    ))
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/world_boss/service_new.py plugins/xiuxian_game/world_boss/__init__.py
git commit -m "feat: 讨伐BOSS title 改为造成伤害数，hint 改为累计/余次摘要"
```

---

## Task 4: 修改 `lower_world/commands.py`

**Files:**
- Modify: `plugins/xiuxian_game/lower_world/commands.py`

**上下文：**
- 胜利路径（约第 529 行的 `build_battle_markdown()` 调用）：变量 `hero['name']`、`points` 均已定义
- 失败路径（约第 676 行）：变量 `hero['name']` 已定义

- [ ] **Step 1: 修改胜利路径**

找到胜利路径的 `build_battle_markdown()` 调用，将：
```python
title=f"🏰 迎战结果 · {hero['name']}",
hint="快捷操作: 迎战 | 镇守 | 天灾商店",
```
改为：
```python
title=f"🏰 {hero['name']} 倒下！",
hint=f"+{points}天灾点",
```

- [ ] **Step 2: 修改失败路径**

找到失败路径的 `build_battle_markdown()` 调用，将：
```python
title=f"🏰 迎战结果 · {hero['name']}",
hint="快捷操作: 迎战 | 镇守 | 天灾商店",
```
改为：
```python
title=f"🏰 被 {hero['name']} 击倒",
hint="封印24小时",
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/lower_world/commands.py
git commit -m "feat: 迎战结果 title 改为胜负说明，hint 改为天灾点/封印摘要"
```

---

## Task 5: 修改 `inner_realm/commands.py`

**Files:**
- Modify: `plugins/xiuxian_game/inner_realm/commands.py`

**上下文（约第 541-553 行）：**
```python
victory, log_lines, result_lines, rewards = await service.start_battle_with_npc(
    player, current_tile, active_session
)
await attack_cmd.finish(build_battle_markdown(
    title="🌀 内界战斗结果",
    battle_log=log_lines + result_lines,
    hint="快捷操作: 攻击 | 里界信息 | 返回",
    btn1="攻击",
    btn2="里界信息",
    btn3="返回",
))
```

`rewards` 是一个 dict，结构为 `{"description": str, "gold": int, "items": list}`，通过 `rewards.get("gold", 0)` 获取金币。

- [ ] **Step 1: 在 `await service.start_battle_with_npc(...)` 返回后、`build_battle_markdown()` 之前**，添加：

```python
if victory:
    inner_title = "🌀 战斗胜利！"
    reward_gold = rewards.get("gold", 0)
    inner_hint = f"+{reward_gold}金币" if reward_gold > 0 else "战斗胜利"
else:
    inner_title = "🌀 战斗失败"
    inner_hint = "继续探索里界"
```

- [ ] **Step 2: 将 `build_battle_markdown()` 调用中的参数改为：**

```python
await attack_cmd.finish(build_battle_markdown(
    title=inner_title,
    battle_log=log_lines + result_lines,
    hint=inner_hint,
    btn1="攻击",
    btn2="里界信息",
    btn3="返回",
))
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/inner_realm/commands.py
git commit -m "feat: 里界攻击 title 改为胜败说明，hint 改为奖励摘要"
```

---

## 验证清单

完成所有 Task 后，逐一测试以下场景：

- [ ] `切磋 <UID>` — title 显示 "X 胜！"，hint 显示 "切磋不影响数据"
- [ ] `模拟战斗 <UID1> <UID2>` — title 显示 "X 胜！"，hint 显示 "模拟 不影响数据"
- [ ] 荒野/诡域 `攻击 <玩家>` 胜利 — title 显示 "X 胜！"，hint 显示 drop_summary
- [ ] 荒野/诡域 `攻击 <玩家>` 败北 — title 显示 "X 胜！"（对方名），hint 显示掉落摘要
- [ ] 城镇 `攻击 <玩家>` — hint 显示 "城镇切磋 无掉落"
- [ ] `攻击 <NPC>` 胜利 — title 显示 "NPC已击倒！"，hint 显示 "+EXP +金"
- [ ] `攻击 <NPC>` 失败 — title 显示 "败于 NPC"，hint 显示 "血量耗尽"
- [ ] `讨伐BOSS` — title 显示 "造成 X 伤害"，hint 显示 "累计 Y · 余Z次"
- [ ] `迎战` 胜利 — title 显示 "英雄名 倒下！"，hint 显示 "+N天灾点"
- [ ] `迎战` 失败 — title 显示 "被 英雄名 击倒"，hint 显示 "封印24小时"
- [ ] 里界 `攻击` 胜利 — title 显示 "战斗胜利！"，hint 显示奖励金币
- [ ] 里界 `攻击` 失败 — title 显示 "战斗失败"，hint 显示 "继续探索里界"
