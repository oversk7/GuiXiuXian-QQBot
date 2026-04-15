# 修复玩家属性

修复出错的玩家属性。从 ElixirUsageLog 精确重建永久加成，重置加点并全额退还属性点，让玩家重新分配。

## 输入

用户需提供：
1. **玩家 UID** — 用于定位数据库记录
2. **（可选）正常面板截图** — 用于交叉校验

用户提供的参数: $ARGUMENTS

## 核心原理

属性存储值 = INIT + allocated（加点）+ permanent（丹药永久加成）+ equipment（装备加成）+ vip

- **INIT**: 固定初始值（max_hp=20, max_mp=20, attack=1, defense=0, agility=5, luck=1）
- **permanent**: 从 `ElixirUsageLog.attribute_changes` 精确累加（新版），或旧数据降级用 qty × 配置反推
- **equipment**: `_persist_bonus`，卸装备后为 0
- **vip**: `vip_equipment_bonus` 表

**修复策略**：不试图恢复出错前的加点分配，而是全部退点重来：
1. 永久加成 → 从 ElixirUsageLog 精确重建（可信）
2. 加点 → 全部清空，属性点全额退还
3. 正确存储值 = INIT + permanent + vip（不含加点和装备）
4. attribute_points = (current_level - 1) × pts_per_level
5. 每级属性点: `pts_per_level = int((reincarnation_level * 0.5 + 1) * 10)`

## 执行流程

### Step 1: 查询数据库 + 计算修复值

**1a. 查询玩家基本信息**
```sql
-- 数据库: ssh root@***REMOVED***, mysql -u root -p***REMOVED*** guixiuxian_db
SELECT uid, nickname, level, reincarnation_level,
       attack, defense, max_hp, hp, max_mp, mp, agility, luck, stamina,
       attribute_points
FROM player WHERE uid = {UID};
```

**1b. 查询 ElixirUsageLog 累计属性变动**
```sql
SELECT item_id, quantity, attribute_changes
FROM elixir_usage_log WHERE player_id = '{player_id}';
```
汇总所有记录的 attribute_changes（优先）或 qty × 配置反推，得到永久加成总和。

**1c. 查询 VIP 装备永久加成**
```sql
SELECT * FROM vip_equipment_bonus WHERE player_id = '{player_id}';
```

**1d. 查询已装备物品**
```sql
SELECT id, item_id, extra_attrs FROM inventory
WHERE player_id = '{player_id}' AND equipped = 1;
```

**1e. 计算修复值**
- 各属性正确裸装值: `INIT[attr] + permanent[attr] + vip[attr]`
- 总应得属性点: `(current_level - 1) * pts_per_level`

### Step 2: 展示修复方案，等待用户确认

用 AskUserQuestion **一次性展示**：
1. 从 ElixirUsageLog 重建的永久加成明细
2. 各属性：当前值 → 修复后裸装值
3. 退还的总属性点数

**只有用户确认后才进入 Step 3。**

### Step 3: 一口气执行全部修复操作（确认后自动完成，不再中途询问）

**3a. 卸下装备 + 清除 _persist_bonus**
```sql
UPDATE inventory SET equipped = 0
WHERE player_id = '{player_id}' AND equipped = 1;

UPDATE inventory SET extra_attrs = JSON_REMOVE(extra_attrs, '$._persist_bonus')
WHERE player_id = '{player_id}'
AND JSON_CONTAINS_PATH(extra_attrs, 'one', '$._persist_bonus');
```

**3b. 写回正确的裸装属性**
```sql
UPDATE player SET
    max_hp = {INIT + permanent + vip},
    hp = LEAST(hp, {new_max_hp}),
    max_mp = {INIT + permanent + vip},
    mp = LEAST(mp, {new_max_mp}),
    attack = {INIT + permanent + vip},
    defense = {INIT + permanent + vip},
    agility = {INIT + permanent + vip},
    luck = {INIT + permanent + vip},
    attribute_points = {total_earned_points}
WHERE uid = {UID};
```

**3c. 验证**
```sql
SELECT uid, nickname, level, attack, defense, max_hp, max_mp,
       agility, luck, stamina, attribute_points
FROM player WHERE uid = {UID};
```

告知用户修复完成，让玩家重新**穿装备 + 重新加点**。

## 注意事项

1. **必须先卸装备再改属性** — 否则装备加成重复计算
2. **战斗属性（暴击率等）也要检查** — 宝石加成可能也被多算
3. **INIT 值**: max_hp=20, max_mp=20, attack=1, defense=0, agility=5, luck=1
4. **战斗属性默认值**: critical_rate=5, accuracy_rate=80, 其余为 0
