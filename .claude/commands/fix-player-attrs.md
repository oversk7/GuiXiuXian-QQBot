# 修复玩家属性

修复出错的玩家属性。以用户提供的“正常面板”为准，反推出当时的裸装属性，卸下所有装备并清理装备持久化加成，只退还异常期间新增等级对应的属性点。

## 输入

用户需提供：
1. **玩家 UID** — 用于定位数据库记录
2. **正常面板** — 必须包含面板等级、六项主属性总值，以及括号中的装备加成

正常面板示例：
```text
Lv.1469
❤️生命 47436/61762 (+41813)
🧠理智 85191/85191 (+59452)
⚔️力 67147 (+55445)　🛡️防 13947 (+10085)
👟敏 9271 (+4790)　🍀运 2602 (+1140)
```

用户提供的参数: $ARGUMENTS

## 核心原理

面板显示总值 = 玩家存储属性（裸装、已含加点/永久/VIP） + 装备加成 + 临时 buff 加成

- 面板括号 `(+N)` 是装备加成展示，来源是已穿戴装备的 `_persist_bonus`
- 玩家表中的 `max_hp/max_mp/attack/defense/agility/luck` 已经持久化包含装备加成，所以异常时可能被重复写大
- 修复时不要从 `ElixirUsageLog` 重建加点，也不要默认全额退点
- 用户给出的正常面板才是可信基准

**修复策略**：
1. 从正常面板反推裸装属性：`裸装属性 = 面板总值 - 括号装备加成`
2. 卸下所有装备，并清除该玩家装备上的 `_persist_bonus`
3. 写回反推得到的裸装属性
4. 只退还“当前等级 - 正常面板等级”这段异常期间多出的属性点
5. 每级属性点：`pts_per_level = int((reincarnation_level * 0.5 + 1) * 10)`
6. 退还点数：`(current_level - panel_level) * pts_per_level`

## 执行流程

### Step 1: 查询数据库 + 反推修复值

**1a. 查询玩家基本信息**
```sql
-- 数据库: ssh root@***REMOVED***, mysql -u root -p***REMOVED*** guixiuxian_db
SELECT uid, nickname, level, reincarnation_level,
       attack, defense, max_hp, hp, max_mp, mp, agility, luck, stamina,
       attribute_points
FROM player WHERE uid = {UID};
```

**1b. 查询已装备物品和装备加成**
```sql
SELECT id, item_id, extra_attrs FROM inventory
WHERE player_id = '{player_id}' AND equipped = 1;
```

**1c. 从用户正常面板反推裸装属性**

对六项主属性分别计算：
```text
max_hp  = 正常面板生命上限 - 生命括号装备加成
max_mp  = 正常面板理智上限 - 理智括号装备加成
attack  = 正常面板力       - 力括号装备加成
defense = 正常面板防       - 防括号装备加成
agility = 正常面板敏       - 敏括号装备加成
luck    = 正常面板运       - 运括号装备加成
```

示例：
```text
生命上限：61762 - 41813 = 19949
理智上限：85191 - 59452 = 25739
力：67147 - 55445 = 11702
防：13947 - 10085 = 3862
敏：9271 - 4790 = 4481
运：2602 - 1140 = 1462
```

**1d. 计算退还点数**
```text
pts_per_level = int((reincarnation_level * 0.5 + 1) * 10)
refund_points = max(0, current_level - panel_level) * pts_per_level
```

### Step 2: 展示修复方案，等待用户确认

用 AskUserQuestion **一次性展示**：
1. 当前数据库等级、用户正常面板等级、每级属性点
2. 六项主属性：当前值 → 修复后裸装值
3. 即将卸下的装备数量
4. 退还属性点数

**只有用户确认后才进入 Step 3。**

### Step 3: 一口气执行全部修复操作（确认后自动完成，不再中途询问）

使用事务执行，避免半修复状态：

```sql
START TRANSACTION;

-- 写回按正常面板反推出来的裸装属性。
-- hp/mp 必须压到新上限内，避免当前血蓝超过上限。
UPDATE player SET
    max_hp = {panel_max_hp_minus_equipment_bonus},
    hp = LEAST(hp, {panel_max_hp_minus_equipment_bonus}),
    max_mp = {panel_max_mp_minus_equipment_bonus},
    mp = LEAST(mp, {panel_max_mp_minus_equipment_bonus}),
    attack = {panel_attack_minus_equipment_bonus},
    defense = {panel_defense_minus_equipment_bonus},
    agility = {panel_agility_minus_equipment_bonus},
    luck = {panel_luck_minus_equipment_bonus},
    attribute_points = attribute_points + {refund_points}
WHERE uid = {UID} AND id = '{player_id}';

-- 卸下所有装备。
UPDATE inventory SET equipped = 0
WHERE player_id = '{player_id}' AND equipped = 1;

-- 清理该玩家所有装备/物品上的 _persist_bonus，避免之后重穿时重复扣减或重复叠加。
UPDATE inventory SET extra_attrs = JSON_REMOVE(extra_attrs, '$._persist_bonus')
WHERE player_id = '{player_id}'
AND extra_attrs IS NOT NULL
AND JSON_CONTAINS_PATH(extra_attrs, 'one', '$._persist_bonus');

COMMIT;
```

### Step 4: 验证

```sql
SELECT uid, nickname, level, attack, defense, max_hp, max_mp,
       agility, luck, stamina, attribute_points
FROM player WHERE uid = {UID};

SELECT COUNT(*) FROM inventory
WHERE player_id = '{player_id}' AND equipped = 1;

SELECT COUNT(*) FROM inventory
WHERE player_id = '{player_id}'
AND extra_attrs IS NOT NULL
AND JSON_CONTAINS_PATH(extra_attrs, 'one', '$._persist_bonus');
```

验证要求：
- 已穿戴装备数为 `0`
- 残留 `_persist_bonus` 数为 `0`
- 六项主属性等于正常面板反推出来的裸装值
- `attribute_points` 增加了本次计算的 `refund_points`

告知用户修复完成，让玩家重新穿装备；不要提示“重新加点”，除非确实退还了额外点数需要分配。

## 注意事项

1. **不要默认按 ElixirUsageLog 重建裸装值**。正常面板能反推出加点后的裸装状态，优先用用户提供的正常面板。
2. **不要默认全额退还属性点**。只退还当前等级与正常面板等级之间的差额点数。
3. **不要改等级**，除非用户明确要求回滚等级。
4. **不要改咒抗、金币、积分、怨念等非本任务字段**，除非用户明确要求。
5. **必须清理 `_persist_bonus`**，否则之后装备重穿可能继续污染属性。
6. 如果正常面板缺少括号装备加成，必须先向用户确认，不能凭 ElixirUsageLog 猜加点分配。
