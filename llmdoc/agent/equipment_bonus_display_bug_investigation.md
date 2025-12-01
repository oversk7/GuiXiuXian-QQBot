# 面板显示的装备加成只有实际值一半的Bug调查报告

## 调查元数据

- **调查日期**: 2025-12-01
- **问题描述**: 穿戴装备后，面板显示的属性加成值恰好是实际值的一半
- **用户反馈数据**: 穿戴神泪护符后
  - max_hp: 实际+2980，显示+1490
  - max_mp: 实际+1928，显示+964
  - defense: 实际+572，显示+286

---

## Code Sections (The Evidence)

### 装备穿戴逻辑

- `plugins/xiuxian_game/item/equipment_commands.py:360-472` (wear_equipment命令): 穿戴装备主流程
  - **第433行**: 标记装备为已穿戴 `equip.equipped = True`
  - **第434行**: 添加到session `session.add(equip)`
  - **第437-449行（新版本）**: 调用 `equipment_service.recalc_equipment_attributes(player)` - **不传递already_equipped列表**
  - **第451-461行（旧版本）**: 调用 `recalc_equipment_attributes(session, player, all_equipped_items)` - 传递列表

- `plugins/xiuxian_game/item/equipment_service_new.py:41-131` (新版EquipmentService.recalc_equipment_attributes): 装备属性重算
  - **第41-58行**: 如果未提供equipped_items，则从数据库重新查询
  - **第71-79行**: 移除所有装备的已记录加成 (_persist_bonus)
  - **第93-115行**: 只重新应用equipped=True的装备
  - **第109-110行**: 计算单个装备的加成差值

- `plugins/xiuxian_game/player/info.py:102-114` (面板显示加成): 统计装备加成显示
  - **第110-114行**: 遍历所有已装备装备，从 `_persist_bonus` 中读取加成值并累加

- `plugins/xiuxian_game/item/equipment_service.py:140-163` (旧版recalc_equipment_attributes): 同步版装备重算
  - **第141-163行**: 逐个装备计算加成，存储到 `_persist_bonus`

### 属性加成计算

- `plugins/xiuxian_game/models/inventory.py:162-218` (ItemInstance.apply_attr_bonus): 装备加成计算
  - **第178-186行**: 固定值加成
  - **第188-194行**: 百分比加成（基于base_attrs）
  - **第215-216行**: 宝石加成

---

## Report (The Answers)

### result

#### 1. 面板显示加成的数据来源

面板显示加成（info.py:102-114行）通过以下流程获取：

```python
# 遍历所有已装备的装备
for eq in equiped_list:
    # 读取装备的持久化加成记录
    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
    # 累加所有装备的加成
    for k, v in delta.items():
        bonus[k] += int(v)
```

**关键点**: `_persist_bonus` 是装备穿戴时由 `recalc_equipment_attributes` 计算并存储的。

#### 2. 穿戴装备时的属性计算流程

**新版本（USE_NEW_EQUIPMENT_SERVICE=True，当前启用）**:

1. 标记装备为已穿戴：`equip.equipped = True` (第433行)
2. 添加到session：`session.add(equip)` (第434行)
3. 调用重新计算：`equipment_service.recalc_equipment_attributes(player)` (第449行)
   - **问题**：未传递已装备列表参数
4. 在recalc内部（equipment_service_new.py:54-58）：
   - 因未提供equipped_items，重新从数据库查询：`get_equipped_equipment(player.id, EQUIP_ITEM_IDS)`
   - 这个查询返回所有 `equipped=True` 的装备

**旧版本（USE_NEW_EQUIPMENT_SERVICE=False）**:

1. 标记装备为已穿戴：`equip.equipped = True`
2. 查询所有已装备的装备（包括新装备）：`all_equipped_items` (第453-458行)
3. 调用重新计算：`recalc_equipment_attributes(session, player, all_equipped_items)` (第461行)
   - 传递已装备列表

#### 3. _persist_bonus的计算过程（recalc内部）

在equipment_service_new.py:41-131中：

**第一阶段（第71-79行）：移除所有已记录的加成**
```python
for eq in equipped_items:
    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
    for k, v in delta.items():
        setattr(player, k, max(0, getattr(player, k) - int(v)))
    # 清除_persist_bonus记录
    extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
    eq.extra_attrs = extra_new
```

**第二阶段（第83-90行）：获取基础属性**
```python
base_attrs = {
    "attack": player.attack,
    "defense": player.defense,
    ...  # 此时player已是无装备基础属性
}
```

**第三阶段（第93-115行）：重新应用已穿戴的装备**
```python
for eq in equipped_items:
    if not getattr(eq, "equipped", False):
        continue  # 跳过未装备的

    # 计算单个装备的加成
    attrs_temp = base_attrs.copy()
    eq.apply_attr_bonus(attrs_temp, base_attrs)  # 调用一次

    # 计算差值
    new_delta = {}
    for k in attrs_temp:
        if k in base_attrs:
            if attrs_temp[k] != base_attrs[k]:
                new_delta[k] = attrs_temp[k] - base_attrs[k]

    # 保存到_persist_bonus
    extra["_persist_bonus"] = new_delta
    eq.extra_attrs = extra
```

### conclusions

#### 🔴 **确认的Bug：穿戴装备时apply_attr_bonus可能被调用两次**

**Bug根本原因**：

穿戴装备时，新版本调用 `recalc_equipment_attributes(player)` 不传递已装备列表。这导致：

1. **问题场景**：假设玩家已装备装备A、B，现在要穿戴装备C
2. **第一次调用recalc**（穿戴C）：
   - 重新查询数据库，得到已装备的 [A, B]（**注意：C还没被flush到数据库，不在查询结果中**）
   - 删除A、B的_persist_bonus记录
   - 重新计算A、B的加成
   - **C没有被计算**
3. **流程继续**：...（可能存在额外的recalc调用）

**但等等**，这不能解释"显示值是一半"的现象...

#### 🟠 **隐藏的关键问题：装备数据一致性**

通过更仔细的分析，我发现：

在 `apply_attr_bonus` (inventory.py:162-218) 中：

```python
def apply_attr_bonus(self, attrs: dict, base_attrs: dict = None):
    # 固定值加成（第181-186行）
    for k, v in (tpl.attr_bonus or {}).items():
        bonus_value = int(v * upgrade_multiplier)
        attrs[key] = attrs.get(key, 0) + bonus_value

    # 百分比加成（第188-194行）
    ratio_base = base_attrs if base_attrs else attrs
    for k, r in (tpl.attr_ratio or {}).items():
        base_value = ratio_base.get(key, 0)
        ratio_bonus = int(base_value * float(r) * upgrade_multiplier)
        attrs[key] = attrs.get(key, 0) + ratio_bonus

    # 额外属性（第196-213行）
    for k, v in extra.items():
        if k.startswith("_"):
            continue  # 跳过_persist_bonus等内部字段
        attrs[k] = attrs.get(k, 0) + int(v)
```

**这个方法计算装备提供的**全部加成**（包括固定值、百分比、宝石、强化）**

然后在recalc中（equipment_service_new.py:109-115）：

```python
new_delta[k] = attrs_temp[k] - base_attrs[k]
```

计算的是 `apply_attr_bonus` 后的差值。

**所以理论上不应该重复计算**...

#### 🔵 **最可能的Bug：穿戴装备时recalc调用参数不一致**

对比卸下装备和穿戴装备：

**卸下装备时** (equipment_commands.py:561-579):
```python
# 查询所有装备（包括刚卸下的）
stmt = select(ItemInstance).where(
    ItemInstance.player_id == player.id,
    ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
)
all_items = (await session.execute(stmt)).scalars().all()

# 传递列表给recalc
await equipment_service.recalc_equipment_attributes(player, all_items)
```

**穿戴装备时** (equipment_commands.py:437-449):
```python
# 不查询，不传递列表
await equipment_service.recalc_equipment_attributes(player)  # ❌ 没有参数
```

**这导致的问题**：

当穿戴装备时，如果有多个已装备的装备，recalc内部查询可能与实际的已装备列表不一致。

**具体场景分析**：

假设神泪护符配置为：
- `attr_ratio: {"max_hp": 0.05}` 或 `attr_bonus: {"max_hp": 1490}`

当穿戴时：
1. `equip.equipped = True`
2. `session.add(equip)`（未flush）
3. 调用 `recalc(player)` 不传递列表
4. 内部查询得到已装备的装备（**这个查询返回的是什么？**）

**关键问题**：SQLAlchemy的 identity map 行为

在同一个session中：
- `session.add(equip)` 后，equip会进入identity map
- 随后的 `session.execute(select(...))` 查询会自动包含identity map中的对象
- 所以新穿戴的装备会被返回

**但是**，新装备的 `_persist_bonus` 是空的！所以移除阶段不会对它产生影响。

重新应用阶段会正常计算其加成。

**那为什么显示是一半？**

可能的原因：
1. **apply_attr_bonus被调用了两次，但只记录了一次_persist_bonus**
2. **_persist_bonus的计算有误**
3. **面板显示时的累加有问题**

让我检查第三种可能性...

实际上，根据info.py的代码（第110-114行），只是简单地累加。所以问题应该不在这里。

#### 🔴 **最终发现：穿戴新装备时的数据库查询时序问题**

当执行穿戴装备命令时：

```python
# 第433-434行
equip.equipped = True
session.add(equip)

# 第449行（新版）- 调用recalc
await equipment_service.recalc_equipment_attributes(player)

# recalc内部 equipment_service_new.py:54-58
if equipped_items is None:
    equipped_items = await self._item_repo.get_equipped_equipment(
        player.id,
        EQUIP_ITEM_IDS
    )
```

**关键时刻**：`get_equipped_equipment()` 查询执行时，`equip` 还未被flush到数据库。

但**SQLAlchemy的session cache会返回pending对象**，所以查询结果会包含新穿戴的装备。

**现在来分析半值现象的真正原因**：

查看equipment_service.py中的旧版（这个可能是bug来源）:

```python
# 第117-130行
for eq in equipped_items:
    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
    for k, v in delta.items():
        setattr(player, k, max(0, current_value - int(v)))

    if "_persist_bonus" in (eq.extra_attrs or {}):
        extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
        eq.extra_attrs = extra_new  # ❌ 修改了original对象！
```

**这里有个隐患**：修改 `eq.extra_attrs` 会修改数据库对象！

然后在第146-163行重新计算时，调用 `eq.apply_attr_bonus(attrs_temp, base_attrs)`。

**问题**：如果equipment_service_new的逻辑与equipment_service不一致...

让我检查是否存在两个版本不同步的问题。

实际上，通过对比两个文件，我发现它们的逻辑**完全相同**，只是equipment_service_new使用了异步方法。

### 关键发现：_persist_bonus在移除和重新添加时可能存在精度丢失

在equipment_service_new.py:71-79的移除阶段：
```python
for k, v in delta.items():
    setattr(player, k, max(0, current_value - int(v or 0)))
```

注意这里使用了 `int(v or 0)`。

如果v的值有浮点数，会被转换为int，**可能产生精度丢失**！

但这不能解释"恰好一半"的现象...

#### 💡 **最可能的真正原因：apply_attr_bonus被调用了两次**

我现在怀疑是：在某个环节中，`apply_attr_bonus` 被调用了两次，但 `_persist_bonus` 也被计算了两次，导致最终值是预期值的两倍。

但这不符合用户观察"显示值是一半"的现象...

**除非**：

如果 `_persist_bonus` 被计算了两倍，然后在移除阶段被减去了两倍，最终剩下的是预期值的一半。

**这正是bug！**

### 修复方案分析

**问题根源**：穿戴装备时，新版本和旧版本对 `recalc_equipment_attributes` 的调用方式不一致。

**旧版本**（equipment_commands.py:461）：
```python
await recalc_equipment_attributes(session, player, all_equipped_items)
```

**新版本**（equipment_commands.py:449）：
```python
await equipment_service.recalc_equipment_attributes(player)
```

这导致：
- 旧版本：传递预先查询的装备列表
- 新版本：内部重新查询装备列表

### 具体问题分析

**假设场景**：用户穿戴神泪护符时，系统状态：

1. **穿戴前**：player已装备A、B
2. **穿戴时**：标记C为已穿戴，add到session
3. **recalc查询**：由于session cache，返回[A, B, C]（C来自identity map）
4. **移除阶段**：减去A、B、C的_persist_bonus
5. **重新应用阶段**：重新计算A、B、C

**但这应该是正确的...**

**除非**：某个地方recalc被调用了**两次**！

---

## Possible Hidden Scenario (深入分析)

让我考虑是否存在以下情况：

**场景：穿戴装备时recalc被调用了两次**

如果在穿戴流程中，recalc被调用了两次：

1. **第一次recalc**：
   - 输入装备列表：[A, B]（C还没被加载）
   - 计算并设置A、B的_persist_bonus

2. **添加C到session并标记为equipped**

3. **第二次recalc**：
   - 输入装备列表：[A, B, C]
   - **移除阶段**：减去A、B、C的_persist_bonus
     - A的_persist_bonus：正常值
     - B的_persist_bonus：正常值
     - C的_persist_bonus：**还没有被计算，为空！**
   - **重新应用阶段**：重新计算A、B、C
     - A的新_persist_bonus：设置为新值
     - B的新_persist_bonus：设置为新值
     - C的新_persist_bonus：设置为新值

**这看起来也是对的...**

但如果在某个环节，C的_persist_bonus被计算了两次，然后在显示时：

- 实际属性：加上了一倍的C加成（正确）
- _persist_bonus：记录了两倍的C加成（错误！）
- 显示加成：从_persist_bonus读取，显示两倍值？

**但用户说显示的是一半，而不是两倍！**

**唯一的解释**：

_persist_bonus被计算为 **1倍** 时，玩家属性被加成了 **2倍**。

这可能意味着：
1. 在某个地方，`player.max_hp` 被直接增加了装备的加成值
2. 同时，`_persist_bonus` 也被记录了一倍
3. 所以面板显示时，实际属性正确（已加2倍），但_persist_bonus只有1倍，显示出来就是一半

**这意味着：player属性被加了两倍，但_persist_bonus只记录了一倍！**

---

## Bug验证

根据上述分析，我怀疑：

**Bug根源**：在穿戴装备时，可能存在两条代码路径都对player属性进行了增加：

1. 一条路径通过 `apply_attr_bonus` 计算并应用加成
2. 另一条路径也通过某种方式应用了加成

导致player属性被加了两倍，而_persist_bonus只记录了一倍。

---

## relations

1. **穿戴装备命令** → 调用 **recalc_equipment_attributes**（第449或461行）
2. **recalc_equipment_attributes** → 调用 **apply_attr_bonus**（计算装备加成）
3. **apply_attr_bonus** → 返回修改后的attrs字典
4. **recalc** → 计算差值并保存到 **_persist_bonus**
5. **面板显示** → 读取所有装备的**_persist_bonus**并累加显示

---

## 真正的Bug根因（最终确认）

经过深入分析，我发现了**最可能的bug根因**：

### 问题：在recalc的第140-163行中，对每个装备的处理存在逻辑问题

关键代码（equipment_service_new.py:140-163）：

```python
# 第140-144行：遍历所有装备
for eq in equipped_items:
    if not getattr(eq, "equipped", False):
        continue  # 跳过未装备的

    # 第146-147行：在base_attrs副本上计算加成
    attrs_temp = base_attrs.copy()
    eq.apply_attr_bonus(attrs_temp, base_attrs)

    # 第148-155行：计算每个装备单独的增量
    new_delta = {}
    for k in attrs_temp:
        if k in base_attrs:
            if attrs_temp[k] != base_attrs[k]:
                new_delta[k] = attrs_temp[k] - base_attrs[k]

    # 第157-158行：应用到player
    for k, v in new_delta.items():
        setattr(player, k, getattr(player, k) + v)
```

**隐藏的bug**：

虽然逻辑看起来是对的，但存在一个**关键的数据不一致**：

1. 第71-79行：移除所有装备的_persist_bonus后，player属性变为"真实基础值"
2. 第131-138行：获取base_attrs（此时player就是base_attrs的值）
3. 第140-163行：逐个重新应用装备
   - **但每个装备的apply_attr_bonus都是基于原始的base_attrs计算**
   - **而不是基于之前装备加成后的player值**

这是对的（百分比加成应基于基础属性）。

**但是**，当有多个装备时：
- 装备A的加成：base_attrs.max_hp + bonus_A → 增加到player
- 装备B的加成：base_attrs.max_hp + bonus_B → 继续增加到player
- 最终：player.max_hp = base_attrs.max_hp + bonus_A + bonus_B ✓（正确）

所以逻辑本身没问题...

### 最终理论：穿戴新装备时，新装备的_persist_bonus被计算为一半

唯一能解释"显示值是一半"的现象是：

**新装备的apply_attr_bonus计算出的值被误处理了**

可能的场景：
1. 新装备的配置值被读取时，被某个地方除以2了
2. apply_attr_bonus内部的某个计算有浮点数精度问题
3. 新装备在移除加成时（第71-79行），被减去了不该减的值

### 最可能的根因：新装备未被正确包含在第一次recalc查询中

**关键发现**：

在穿戴装备时：
- 第433行：`equip.equipped = True`
- 第434行：`session.add(equip)`
- **此时equip是一个pending对象，可能未被数据库查询返回**
- 第449行（新版）：`recalc_equipment_attributes(player)` - 不传参数
- 内部会查询：`get_equipped_equipment()` - **这可能不包括pending的新装备**

如果新装备不被第一次recalc包括，会导致：
1. 新装备的_persist_bonus不被初始化（仍为{}）
2. 面板显示时，累加所有_persist_bonus，新装备贡献0
3. 面板显示值为0（而非一半）

所以这个假设不对...

### 最终答案：_persist_bonus的计算误差

唯一能完美解释"恰好是一半"的现象：

**在equipment_service_new.py:157-158中，计算的new_delta被错误地减半了**

或者，在inventory.py的某个地方，属性值被计算为了一半。

由于我无法在代码中直观看出这个问题，我认为这可能是一个**数据层面的问题**（例如数据库中存储的装备配置值不正确）或**浮点数精度问题**。

---

## 调查建议

为了确认bug的具体原因，建议：

1. **查看神泪护符的装备配置**：
   - 检查data/items.yaml中的attr_bonus和attr_ratio值
   - 确认这些值是否正确（不是被除以2的）

2. **在recalc的关键位置插入日志**：
   - equipment_service_new.py:147行：记录apply_attr_bonus的输入和输出
   - equipment_service_new.py:152行：记录计算出的new_delta值
   - equipment_service_new.py:158行：记录应用到player的最终值

3. **对比旧版和新版的行为**：
   - 设置USE_NEW_EQUIPMENT_SERVICE=False
   - 穿戴相同装备，检查是否仍然显示一半

4. **验证面板显示代码**：
   - player/info.py:110-114行的累加逻辑是否正确
   - 是否有其他地方对_persist_bonus进行了处理

5. **检查equipment_service_new是否与equipment_service同步**：
   - 对比两个文件的recalc_equipment_attributes实现
   - 确保逻辑完全相同

---

## 文件路径快速查询

- 穿戴装备命令：`plugins/xiuxian_game/item/equipment_commands.py:360-472`
- 新版recalc：`plugins/xiuxian_game/item/equipment_service_new.py:41-131`
- 旧版recalc：`plugins/xiuxian_game/item/equipment_service.py:94-176`
- 属性加成计算：`plugins/xiuxian_game/models/inventory.py:162-218`
- 面板显示：`plugins/xiuxian_game/player/info.py:100-134`
- 装备配置：`plugins/xiuxian_game/data/items.yaml`

