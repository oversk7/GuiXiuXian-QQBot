# 装备耐久度自动卸载机制调查报告

**调查日期**: 2025-12-02
**调查员**: scout agent
**调查范围**: 诡域战斗、扫荡令的装备耐久度扣减与自动卸载机制
**问题**: 装备耐久耗尽(durability=0)后是否有自动卸载机制，以及是否正确清理属性加成

---

## Code Sections (The Evidence)

### 1. 诡域战斗中的耐久度处理

- `plugins/xiuxian_game/world/dungeon_battle.py:35-58` (`check_equipment_durability`): 检查装备耐久度低于10时返回警告消息
- `plugins/xiuxian_game/world/dungeon_battle.py:1102-1127` (耐久度扣减与自动卸载): 在诡域战斗每一轮中扣减装备耐久度，耐久度降至0时自动卸下
  - **第1103行**: `if eq.lose_durability(1):` - 扣1点耐久，若耐久降至0返回True
  - **第1105-1107行**: 读取`_persist_bonus`并手动减去属性加成
  - **第1108行**: 标记`eq.equipped = False`
  - **问题**：只手动减去属性，**未调用`recalc_equipment_attributes()`**重新计算其他装备

### 2. 扫荡令中的耐久度处理

- `plugins/xiuxian_game/item/sweep_dungeon_service.py:470-528` (`_handle_equipment_durability`): 扫荡令执行后扣除装备耐久度并自动卸下
  - **第492-496行**: 计算耐久度损失，扣除耐久度
  - **第497-508行**: 耐久度降至0时自动卸下，减去`_persist_bonus`属性加成
  - **第518-527行**: 如果需要重算，调用`equipment_service.recalc_equipment_attributes(player)` **但未传入装备列表**
  - **问题**：调用recalc时未传入装备列表，recalc内部会重新查询所有`equipped=True`的装备

### 3. 灵活使用副本中的耐久度处理（item_effects.py）

- `plugins/xiuxian_game/item/item_effects.py:920-961` (灵活使用副本扣除耐久): 与扫荡令类似，但直接在item_effects中实现
  - **第927-942行**: 耐久度降至0时自动卸下，减去`_persist_bonus`
  - **第944-958行**: 调用recalc重新计算装备属性（同样未传入装备列表）

### 4. ItemInstance模型的耐久度处理

- `plugins/xiuxian_game/models/inventory.py:378-381` (`lose_durability` 方法):
  ```python
  def lose_durability(self, amount: int = 1) -> bool:
      """扣除耐久。返回 True 如果耐久降至0（已损坏，需要自动卸下）。"""
      self.durability = max(0, self.durability - amount)
      return self.durability == 0
  ```
  - 返回True表示耐久已降至0，调用者应自动卸下

### 5. 装备穿戴时的耐久度检查

- `plugins/xiuxian_game/item/equipment_commands.py:374-401` (`wear_equipment`命令):
  - **第383-386行**: 检查耐久度是否为0，若为0则阻止穿戴并显示提示
  - **第396行**: 穿戴时检查耐久是否为0，若为0自动卸下

### 6. 属性清理与重新计算的关键函数

- `plugins/xiuxian_game/item/equipment_service_new.py:41-215` (`EquipmentService.recalc_equipment_attributes`): 新版DI架构
  - **第54-58行**: 如果未传入装备列表，从Repository查询所有`equipped=True`的装备
  - **第69-79行**: 移除所有传入装备的`_persist_bonus`
  - **第81-90行**: 获取无装备状态的基础属性
  - **第92-115行**: 只重新应用`equipped=True`的装备

- `plugins/xiuxian_game/item/equipment_commands.py:96-175` (`recalc_equipment_attributes`旧版): 静态函数版本
  - 逻辑与新版相同

---

## Report (The Answers)

### result

#### 1. 诡域打怪时装备耐久耗尽(durability=0)是否有自动卸载机制？

**答案：✅ 有自动卸载机制，但存在关键问题**

**具体实现**:
- **代码位置**: `plugins/xiuxian_game/world/dungeon_battle.py:1102-1127`
- **触发条件**: 每一轮战斗中，调用`eq.lose_durability(1)`扣1点耐久，返回True表示已降至0
- **自动卸载过程**:
  1. 读取装备的`_persist_bonus`持久化加成 (第1105行)
  2. 手动从玩家属性中减去这些加成 (第1106-1107行)
  3. 标记`eq.equipped = False` (第1108行)
  4. 在战报中显示卸载信息 (第1109-1113行)
  5. 记录因max_hp/max_mp下降导致的HP/MP损失 (第1117-1127行)

**关键问题：未调用recalc重新计算**
- **缺失代码**: 没有在耐久度降至0后调用`recalc_equipment_attributes()`或`EquipmentService.recalc_equipment_attributes()`
- **风险**: 如果玩家穿戴多件装备，卸下其中一件后，**剩余装备的百分比加成可能不正确**（因为百分比是基于基础属性计算的）

**示例场景**:
- 玩家基础attack=100，穿戴装备A(固定+50)和装备B(百分比+20%)
- 装备A的`_persist_bonus = {attack: 50}`
- 装备B的`_persist_bonus = {attack: 20}` (基于100计算)
- 当前player.attack = 170

**如果装备A耐久耗尽卸载**:
1. 减去装备A加成: `player.attack = 170 - 50 = 120`
2. **问题**: 装备B的`_persist_bonus`仍然是20，但现在基础属性是120，应该重新计算为24
3. 正确值应该是: `120 + 24 = 144`，但实际值是: `120 + 20 = 140`

---

#### 2. 使用扫荡令时装备耐久耗尽后是否有自动卸载机制？

**答案：✅ 有自动卸载机制，并且调用了recalc，但recalc未正确传入装备列表**

**具体实现**:
- **代码位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:470-528` (`_handle_equipment_durability`方法)
- **触发条件**: 扫荡令执行后，基于怪物格子数扣除装备耐久度
- **自动卸载过程**:
  1. 计算耐久度损失 (第492行: `durability_loss = monster_tiles`)
  2. 实际扣除: `eq.durability -= actual_loss` (第496行)
  3. 若耐久度降至0 (第497行):
     - 读取`_persist_bonus`并减去 (第499-502行)
     - 标记`eq.equipped = False` (第503行)
     - 设置`needs_recalc = True` (第504行)
  4. 若需要重算 (第518-527行):
     - 若启用新版DI: `await self._equipment_service.recalc_equipment_attributes(player)` **未传入装备列表**
     - 若使用旧版: 调用静态函数 **同样未传入装备列表**

**重要改进点与问题**:
- ✅ **相比诡域战斗的改进**: 确实调用了recalc重新计算
- ❌ **问题**: recalc调用时**未传入已修改的装备列表**
- ✅ **实际影响有限**: 因为recalc内部会查询所有`equipped=True`的装备，卸下的装备已标记为False，所以不会被重新计算

**更详细的流程**:
1. 扣除所有装备的耐久度
2. 若有装备耗尽，手动减去其`_persist_bonus`并标记`equipped=False`
3. 调用recalc，recalc内部查询`equipped=True`的装备（已卸下的不会被查询）
4. recalc重新计算剩余装备的属性加成

**注意**: 虽然recalc未显式传入装备列表，但由于卸下的装备已标记为False，recalc的内部查询会自动过滤掉它们，所以逻辑上是正确的。

---

#### 3. 耐久度为0时是否正确移除了装备加成？

**诡域战斗的实现**:

✅ **是的，正确移除了加成**，但仅限于移除该件装备的加成：
```python
delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
for k, v in delta.items():
    setattr(player, k, getattr(player, k) - v)
eq.equipped = False
```

❌ **但没有重新计算剩余装备**，这可能导致属性计算错误。

**扫荡令的实现**:

✅ **是的，正确移除了加成**，并且调用了recalc重新计算：
```python
delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
for k, v in delta.items():
    current_value = getattr(player, k, 0)
    setattr(player, k, max(0, current_value - v))
eq.equipped = False
needs_recalc = True
...
if needs_recalc:
    await self._equipment_service.recalc_equipment_attributes(player)
```

✅ **recalc函数会正确处理**:
1. 移除所有传入装备的`_persist_bonus`（若传入了）
2. 获取无装备状态的基础属性
3. 重新应用所有`equipped=True`的装备

---

### conclusions

1. **诡域打怪时有自动卸载机制**:
   - **位置**: `plugins/xiuxian_game/world/dungeon_battle.py:1102-1127`
   - **实现**: 每轮扣1点耐久，耐久降至0时手动减去`_persist_bonus`并标记`equipped=False`
   - **关键问题**: ❌ **未调用recalc重新计算剩余装备**，可能导致百分比加成计算错误

2. **扫荡令使用时有自动卸载机制**:
   - **位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:470-528`
   - **实现**: 手动减去`_persist_bonus`后调用`recalc_equipment_attributes(player)`
   - **优点**: 确实调用了recalc重新计算
   - **注意**: 虽然未显式传入装备列表，但recalc内部查询会自动过滤掉`equipped=False`的装备，逻辑上是正确的

3. **灵活使用副本中也有自动卸载**:
   - **位置**: `plugins/xiuxian_game/item/item_effects.py:920-961`
   - **实现**: 与扫荡令相同，调用recalc重新计算

4. **装备加成的移除方式一致**:
   - 所有路径都通过读取`_persist_bonus`并减去的方式移除属性加成
   - `_persist_bonus`机制本身没有问题

5. **关键风险点**:
   - ❌ **诡域战斗未调用recalc**: 这是唯一主动战斗模式（对标战斗）中的自动卸载，缺少recalc调用可能导致属性计算不一致
   - ✅ **扫荡令和灵活副本都调用了recalc**: 这两个被动模式都有属性重新计算

6. **修复优先级**: P1 (中等)
   - 诡域战斗的自动卸载需要添加recalc调用
   - 建议在耐久度降至0后调用类似扫荡令的recalc逻辑

---

### relations

1. **诡域战斗自动卸载** → 手动减去`_persist_bonus` → **❌ 缺少调用recalc**
2. **扫荡令自动卸载** → 手动减去`_persist_bonus` → ✅ 调用`recalc_equipment_attributes(player)`
3. **灵活副本自动卸载** → 手动减去`_persist_bonus` → ✅ 调用`recalc_equipment_attributes(player)`
4. **recalc函数** → 移除所有装备的`_persist_bonus` → 获取基础属性 → 重新应用`equipped=True`的装备
5. **ItemInstance.lose_durability()** → 返回True表示耐久已降至0，调用者应自动卸下
6. **装备穿戴前检查** → 检查durability是否为0 → 若为0则阻止穿戴

---

## 修复建议

### 问题：诡域战斗缺少recalc调用

**当前代码** (`world/dungeon_battle.py:1102-1127`):
```python
for eq in equipped_items:
    if eq.lose_durability(1):
        # 耐久耗尽：自动卸下且不可穿戴
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            setattr(player, k, getattr(player, k) - v)
        eq.equipped = False
        # ... 显示消息 ...
        # ❌ 缺少recalc调用
```

**建议修复方案**:

添加recalc调用，与扫荡令的逻辑保持一致：

```python
# 在循环后添加
if broken_msgs:  # 如果有装备被损坏
    # 重新计算剩余装备的属性加成
    # 导入相关的service和repository
    if USE_NEW_EQUIPMENT_SERVICE:
        from ..item.equipment_service_new import EquipmentService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository

        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
    else:
        from ..item.equipment_commands import recalc_equipment_attributes
        await recalc_equipment_attributes(session, player)
```

**修复效果**:
- ✅ 诡域战斗自动卸载后会重新计算剩余装备的属性加成
- ✅ 与扫荡令的自动卸载逻辑保持一致
- ✅ 消除百分比加成计算错误的风险

---

## 测试场景

**场景1：诡域战斗中多装备耐久耗尽**

前置条件：
- 玩家基础attack=100
- 装备A: 固定+50，`_persist_bonus={attack:50}`，耐久度=1
- 装备B: 百分比+20%，`_persist_bonus={attack:20}`（基于100计算），耐久度>1
- 当前player.attack=170

战斗中装备A耐久耗尽：
- 修复前: player.attack=170-50=120，但装备B的加成仍是20，最终结果=120+20=140 ❌
- 修复后: 调用recalc后，recalc会重新计算装备B的加成为24(120×20%)，最终结果=120+24=144 ✅

**场景2：扫荡令自动卸载（验证现有逻辑）**

预期：已调用recalc，属性计算正确 ✅

---

## 相关文档

- `/llmdoc/architecture/attribute-system.md` - 属性系统架构，包含_persist_bonus机制说明
- `/llmdoc/reference/code-issues.md` - 代码问题清单
- `/llmdoc/agent/equipment_unequip_bug_reinvestigation_2025_12_01.md` - 装备卸载bug深度复查

---

**调查结论**:
- ✅ 诡域和扫荡令都实现了装备耐久耗尽的自动卸载机制
- ✅ 属性加成的移除方式都是正确的（通过`_persist_bonus`）
- ❌ 诡域战斗缺少耐久度降至0后的recalc调用
- ✅ 扫荡令和灵活副本都正确调用了recalc
- 🎯 建议为诡域战斗添加recalc调用，与其他模式保持一致
