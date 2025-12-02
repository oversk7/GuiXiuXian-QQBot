# 扫荡令装备属性减少Bug调查报告

**调查日期**: 2025-12-02
**问题类型**: 装备属性减少
**严重程度**: 🔴 高
**根本原因**: _persist_bonus清理不完整 + recalc_equipment_attributes未调用

---

## 1. 问题描述

**用户报告**:
- 使用扫荡令后，系统会自动卸下耐久度为0的装备
- 再重新穿戴装备时，属性就会变少

---

## 2. Code Sections (调查证据)

### 2.1 扫荡令实现

- `plugins/xiuxian_game/data/items.yaml:72-77` (扫荡令物品配置): 物品ID为"sweep_token"，效果类型为SWEEP_DUNGEON，价格100000
- `plugins/xiuxian_game/item/item_effects.py:623-641` (_sweep_dungeon): 注册SWEEP_DUNGEON效果处理函数，创建SweepDungeonService执行扫荡逻辑
- `plugins/xiuxian_game/item/sweep_dungeon_service.py:53-250` (SweepDungeonService.execute): 扫荡诡域核心逻辑，包含格子分配、奖励计算、装备耐久度扣除

### 2.2 装备耐久度扣除和自动卸下

- `plugins/xiuxian_game/item/sweep_dungeon_service.py:469-520` (_handle_equipment_durability): 扣除装备耐久度，当耐久度降至0时自动卸下装备
  - **第498行**: 读取装备的`_persist_bonus`
  - **第499-501行**: 手动回退属性加成（直接减去`_persist_bonus`）
  - **第502行**: 设置`eq.equipped = False`
  - **第503行**: 设置`needs_recalc = True`
  - **第517-519行**: 如果`needs_recalc=True`，调用`equipment_service.recalc_equipment_attributes(player)`

### 2.3 装备属性重算函数

- `plugins/xiuxian_game/item/equipment_service_new.py:41-133` (EquipmentService.recalc_equipment_attributes): DI架构版本的装备属性重算函数
  - **第69-84行**: 移除所有已装备的`_persist_bonus`，并将`eq.equipped`设置为False
  - **第86-95行**: 获取无装备状态的基础属性
  - **第97-118行**: 逐个重新应用装备加成，计算新的`_persist_bonus`，设置`eq.equipped = True`
  - **第122-124行**: 处理mp_from_hp特效
  - **第126-133行**: 修正HP/MP上限，更新玩家

- `plugins/xiuxian_game/item/equipment_service.py:91-175` (recalc_equipment_attributes): 旧版本（非DI架构）的装备属性重算函数，逻辑与新版本一致

### 2.4 一键卸下Bug的修复（参考案例）

- `llmdoc/reference/code-issues.md:282-316` (装备卸载属性清零Bug): 2025-12-01已修复的类似bug
  - **根本原因**: 卸载装备时仅减去属性加成，未清理`_persist_bonus`，未调用`recalc_equipment_attributes()`
  - **修复方法**: 清除`_persist_bonus` + 调用`recalc_equipment_attributes()`

---

## 3. Report (调查结论)

### 3.1 result - 问题根本原因

**Bug定位**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:469-520` (_handle_equipment_durability)

**根本原因**: 当装备耐久度降至0时自动卸下装备的逻辑存在缺陷

**问题分析**:

1. **手动回退属性加成的方式不完整**（第498-501行）:
   ```python
   delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
   for k, v in delta.items():
       current_value = getattr(player, k, 0)
       setattr(player, k, max(0, current_value - v))
   ```
   - 此代码仅手动减去装备的属性加成
   - 未清理装备的`_persist_bonus`持久化记录
   - 导致装备对象中仍保留旧的`_persist_bonus`

2. **recalc_equipment_attributes调用时机正确，但传入的装备列表有问题**（第517-519行）:
   ```python
   if needs_recalc:
       await self._equipment_service.recalc_equipment_attributes(player)
   ```
   - 这里调用了`recalc_equipment_attributes(player)`，未传入`equipped_items`参数
   - 函数内部会重新查询所有`equipped=True`的装备（第54-58行）
   - **但是**，被自动卸下的装备已经设置为`equipped=False`（第502行），所以不会被查询到
   - **问题**：查询到的装备列表可能还包含其他旧的`_persist_bonus`未清理的装备

3. **缺少清理_persist_bonus的步骤**:
   - 参考"一键卸下"bug的修复方案（code-issues.md:295-298）
   - 卸下装备时必须清除`_persist_bonus`，否则下次穿戴时会基于旧的加成值计算

**属性减少的机制**:

假设玩家初始攻击力100，装备A提供+50攻击（_persist_bonus记录为50）：

1. **扫荡令使用前**: player.attack = 150，eq_A._persist_bonus = {attack: 50}
2. **耐久度降至0，自动卸下**:
   - 手动减去50攻击：player.attack = 100
   - 设置eq_A.equipped = False
   - **但eq_A._persist_bonus = {attack: 50}仍然存在**
3. **调用recalc_equipment_attributes(player)**:
   - 查询equipped=True的装备（不包含eq_A，因为已经是False）
   - 对其他装备重新计算_persist_bonus
   - **如果其他装备也有旧的_persist_bonus未清理，会导致属性计算错误**
4. **玩家重新穿戴eq_A**:
   - 系统尝试穿戴eq_A
   - 调用recalc_equipment_attributes()
   - **由于eq_A的_persist_bonus未清理，可能导致计算基础错误**

### 3.2 conclusions - 关键事实

1. **扫荡令会自动卸下耐久度为0的装备**（设计如此，非bug）
2. **自动卸下时，仅手动减去属性，未清理_persist_bonus**（bug根源）
3. **recalc_equipment_attributes已调用，但时机和逻辑有问题**
4. **这是与"一键卸下"bug完全相同的问题模式**
5. **_persist_bonus机制要求：卸装备时必须清理，重新穿戴时重新计算**

### 3.3 relations - 代码关系

调用流程:
```
item_effects.py:_sweep_dungeon (623-641)
    └─> SweepDungeonService.execute (53-250)
        └─> _handle_equipment_durability (469-520)
            ├─> 手动回退属性 (498-501) ❌ 不完整
            ├─> 设置equipped=False (502)
            └─> recalc_equipment_attributes (517-519) ⚠️ 时机正确但逻辑有缺陷
```

装备属性计算依赖链:
```
Player.attack/defense/etc (基础属性)
    └─> _persist_bonus (装备加成持久化记录)
        └─> recalc_equipment_attributes() (重新计算入口)
            ├─> 清除所有_persist_bonus (69-84)
            ├─> 获取基础属性 (86-95)
            └─> 重新应用装备加成 (97-118)
```

---

## 4. 修复建议

### 4.1 修复方案（参考"一键卸下"bug修复）

**修复位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:496-503`

**当前代码**:
```python
if eq.durability == 0:
    # 自动卸下并回退属性加成
    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
    for k, v in delta.items():
        current_value = getattr(player, k, 0)
        setattr(player, k, max(0, current_value - v))
    eq.equipped = False
    needs_recalc = True
```

**修复后代码**:
```python
if eq.durability == 0:
    # 自动卸下并回退属性加成
    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
    for k, v in delta.items():
        current_value = getattr(player, k, 0)
        setattr(player, k, max(0, current_value - v))

    # 清除_persist_bonus持久化记录
    if "_persist_bonus" in (eq.extra_attrs or {}):
        extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
        eq.extra_attrs = extra_new

    eq.equipped = False
    needs_recalc = True
```

**关键改动**:
1. 添加清除`_persist_bonus`的逻辑（第9-11行）
2. 确保装备对象中不保留旧的加成记录
3. `recalc_equipment_attributes`的调用保持不变（第517-519行）

### 4.2 验证方法

**测试步骤**:
1. 穿戴多件装备，记录攻击力A
2. 使用扫荡令，直到某件装备耐久度降至0被自动卸下
3. 查看攻击力B，应该等于 A - 该装备的加成
4. 修理该装备
5. 重新穿戴该装备
6. 查看攻击力C，**应该等于A**（而非小于A）

**预期结果**:
- 修复前：C < A（属性减少bug）
- 修复后：C = A（正常）

### 4.3 影响范围

- **受影响功能**: 扫荡令自动卸下装备
- **受影响玩家**: 所有使用扫荡令导致装备耐久度降至0的玩家
- **严重程度**: 🔴 高（属性永久性减少，影响游戏体验）
- **修复难度**: 🟢 低（3行代码，逻辑清晰）
- **回滚风险**: 🟢 低（仅影响扫荡令，可快速回滚）

---

## 5. 与已修复Bug的对比

| 特征 | 一键卸下Bug (已修复) | 扫荡令Bug (待修复) |
|------|---------------------|-------------------|
| **问题位置** | equipment_commands.py:669-692 | sweep_dungeon_service.py:496-503 |
| **触发条件** | 使用"一键卸下"命令 | 使用扫荡令导致耐久度为0 |
| **根本原因** | 未清理_persist_bonus + 未调用recalc | 未清理_persist_bonus（已调用recalc但有缺陷） |
| **修复方法** | 添加_persist_bonus清理 + 调用recalc | 添加_persist_bonus清理（recalc已存在但需完善） |
| **修复日期** | 2025-12-01 | 待修复 |

---

## 6. 相关文档

- **属性系统架构**: `/llmdoc/architecture/attribute-system.md`
- **代码问题清单**: `/llmdoc/reference/code-issues.md`
- **游戏平衡分析**: `/llmdoc/agent/game_balance_analysis_2025_12_01.md`
- **一键卸下Bug修复记录**: `/llmdoc/reference/code-issues.md:282-316`

---

**调查者**: scout代理
**调查完成时间**: 2025-12-02
