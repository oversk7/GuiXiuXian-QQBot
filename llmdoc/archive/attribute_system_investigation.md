# 诡修仙属性计算系统调查报告

> **调查时间**: 2025-11-26
> **调查范围**: 属性计算的所有位置、计算流程、属性类型定义、性能瓶颈识别
> **文档类型**: 技术调研报告

---

## Code Sections (The Evidence)

### 核心属性计算位置

- `plugins/xiuxian_game/models/player.py` (`Player.get_effective_attributes`, line 218-256): 计算玩家的最终有效属性，包含装备加成、丹药加成和临时buff加成。返回包含所有属性的字典。
- `plugins/xiuxian_game/models/player.py` (`Player.get_effective_battle_attributes`, line 258-285): 从有效属性中提取战斗相关属性子集，供战斗系统使用。
- `plugins/xiuxian_game/models/player.py` (`Player.get_attribute_breakdown`, line 287-415): 获取属性来源分解，返回基础、装备、丹药、VIP装备永久加成、临时buff的详细分解。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.calculate_effective_attributes`, line 39-85): 战斗属性计算器，计算玩家的有效战斗属性（百分比值），应用等级加成、装备加成和属性上限。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.calculate_effective_attributes_async`, line 88-152): 异步版本的战斗属性计算，包含临时buff加成。调用 `player.get_effective_attributes()` 获取基础数据。
- `plugins/xiuxian_game/item/equipment_commands.py` (`recalc_equipment_attributes`, line 96-175): 重新计算玩家装备属性加成的核心函数。先移除所有已记录的装备加成，然后基于基础属性重新计算，最后处理 mp_from_hp 特效。
- `plugins/xiuxian_game/models/inventory.py` (`ItemInstance.apply_attr_bonus`, line 162-218): 将装备的属性加成应用到属性字典。计算固定值加成、百分比加成、强化属性和宝石镶嵌加成。

### 属性来源计算

- `plugins/xiuxian_game/models/temporary_buff.py` (`TemporaryBuff.get_total_attribute_bonuses`, line 151-164): 计算玩家所有激活临时buff的总属性加成。遍历所有激活buff，累加属性值。
- `plugins/xiuxian_game/item/item_effects.py` (`_buff`, line 176-218): 永久BUFF效果处理，直接累加属性到玩家本体。处理后调用 `_recalculate_equipment_bonus` 重新计算装备加成。
- `plugins/xiuxian_game/item/item_effects.py` (`_temporary_buff`, line 221-301): 临时BUFF效果处理，创建有时间限制的临时buff记录。
- `plugins/xiuxian_game/item/item_effects.py` (`_recalculate_equipment_bonus`, line 1131-1136): 重新计算装备持久化加成，确保百分比加成与最新基础属性同步。调用 `recalc_equipment_attributes`。

### 属性持久化机制

- `plugins/xiuxian_game/models/inventory.py` (`ItemInstance.extra_attrs["_persist_bonus"]`): 装备的持久化属性加成存储。每次穿戴装备时计算并存储实际加成值，避免重复计算。
- `plugins/xiuxian_game/item/equipment_commands.py` (`_apply_mp_from_hp_effects`, line 23-93): 处理 mp_from_hp 特效，将生命值按百分比或固定值转换为理智上限加成。

### 属性类型定义

- `plugins/xiuxian_game/models/player.py` (基础属性字段, line 33-62):
  - 基础属性: `hp`, `max_hp`, `mp`, `max_mp`, `attack`, `defense`, `agility`, `stamina`, `luck`, `resentment`
  - 特殊属性: `critical_rate`, `critical_power`, `combo_rate`, `counter_rate`, `dodge_rate`, `accuracy_rate`, `skill_crit_rate`, `penetration_rate`, `anti_crit_rate`, `lifesteal_rate`, `immobilize_rate`, `true_damage_rate`, `regen_rate`

### 战斗属性判定

- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.calculate_hit_chance`, line 155-169): 计算命中概率，基于攻击者命中率和防御者闪避率。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.roll_critical_hit`, line 172-185): 暴击判定，基于暴击率。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.roll_combo_attack`, line 188-205): 连击判定，基于连击率，返回连击次数(2-4)。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.roll_counter_attack`, line 208-221): 反击判定，基于反击率。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator.calculate_critical_damage`, line 237-249): 计算暴击伤害，基础1.5倍+暴击力×0.1倍。

### 配置和上限

- `plugins/xiuxian_game/battle/battle_attributes.py` (`ATTRIBUTE_CAPS`, line 16-25): 战斗属性上限配置，例如暴击率500%、连击率60%、反击率80%等。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`LEVEL_BONUS`, line 28-36): 等级加成配置（已移除，改为装备驱动）。

---

## Report (The Answers)

### result

#### 1. 属性计算的所有位置

属性计算在以下**5个主要位置**发生，存在分散和重复计算的问题:

1. **Player.get_effective_attributes** (`models/player.py:218-256`)
   - **职责**: 计算玩家最终有效属性的**主入口**
   - **逻辑**: 基础属性 + 临时buff加成
   - **注意**: 装备加成和丹药加成已通过 `_persist_bonus` 机制直接应用到玩家属性上，此方法只需叠加临时buff

2. **Player.get_attribute_breakdown** (`models/player.py:287-415`)
   - **职责**: 提供属性来源的详细分解（调试和展示用）
   - **逻辑**: 反向计算各来源加成（基础、装备、丹药、VIP、临时buff）
   - **计算量**: 较大，需要查询装备记录、丹药使用记录、VIP记录、临时buff记录

3. **BattleAttributeCalculator.calculate_effective_attributes** (`battle/battle_attributes.py:39-85`)
   - **职责**: 计算战斗属性（同步版本，已弃用）
   - **逻辑**: 基础属性 + 等级加成 + 装备加成 + 属性上限
   - **问题**: 不包含临时buff，与Player模型的计算不一致

4. **BattleAttributeCalculator.calculate_effective_attributes_async** (`battle/battle_attributes.py:88-152`)
   - **职责**: 计算战斗属性（异步版本，推荐使用）
   - **逻辑**: 调用 `player.get_effective_attributes()` 获取包含临时buff的属性，然后应用等级加成和上限
   - **问题**: 存在与Player模型重复计算的风险

5. **recalc_equipment_attributes** (`item/equipment_commands.py:96-175`)
   - **职责**: 装备穿戴/卸下时重新计算属性加成
   - **逻辑**:
     1. 移除所有已记录的装备加成（从 `_persist_bonus` 中读取）
     2. 基于基础属性重新计算每件装备的加成
     3. 应用 `mp_from_hp` 特效
     4. 更新玩家属性和 `_persist_bonus` 记录

#### 2. 属性类型和定义

**基础属性** (存储在 Player 模型中):
- **生存属性**: `hp`, `max_hp`, `mp`, `max_mp`
- **战斗属性**: `attack`, `defense`, `agility`, `stamina`, `luck`
- **特殊属性**: `resentment` (怨念值), `reincarnation_level` (转数), `attribute_points` (可分配属性点)

**战斗专属属性** (存储在 Player 模型中):
- **暴击系统**: `critical_rate` (暴击率), `critical_power` (暴击力), `anti_crit_rate` (抗暴率)
- **触发效果**: `combo_rate` (连击率), `counter_rate` (反击率/反弹率), `dodge_rate` (闪避率), `accuracy_rate` (命中率)
- **技能系统**: `skill_crit_rate` (灵爆率), `penetration_rate` (穿透率)
- **战斗强化**: `lifesteal_rate` (吸血率), `immobilize_rate` (定身率), `true_damage_rate` (真伤率), `regen_rate` (回血率)

**属性加成来源**:
1. **基础属性**: 初始值 + 加点 (不含装备、丹药、VIP、buff)
2. **装备加成**: 通过 `_persist_bonus` 持久化，包括固定值、百分比、升阶、宝石镶嵌
3. **丹药加成**: 永久属性提升，存储在 `ElixirUsageLog` 表中
4. **VIP装备永久加成**: 存储在 `VIPEquipmentBonus` 表中
5. **临时buff加成**: 有时间限制，存储在 `TemporaryBuff` 表中

#### 3. 计算流程

**装备穿戴流程**:
```
1. 获取玩家基础属性（无装备加成）
2. 对每件装备:
   a. 调用 ItemInstance.apply_attr_bonus 计算理论加成
   b. 计算固定值加成（考虑升阶倍率）
   c. 计算百分比加成（基于基础属性）
   d. 应用宝石镶嵌加成
   e. 将加成差值存入 _persist_bonus
   f. 应用加成到玩家属性
3. 处理 mp_from_hp 特效（将生命值转为理智）
4. 限制当前HP/MP不超过新上限
```

**战斗属性计算流程**:
```
1. 调用 player.get_effective_attributes(session)
   -> 返回基础属性 + 临时buff
2. (可选) BattleAttributeCalculator.calculate_effective_attributes_async
   -> 应用等级加成（当前为0）
   -> 应用属性上限（暴击500%、连击60%等）
3. 战斗判定：
   - 命中判定: (命中率 - 闪避率) / 100
   - 暴击判定: (暴击率 - 抗暴率) -> roll
   - 连击判定: 连击率 -> roll (2-4次)
   - 反击判定: 反击率 -> roll
```

**属性修改触发重算**:
- 装备穿戴/卸下: `recalc_equipment_attributes`
- 使用丹药: `_recalculate_equipment_bonus` (确保百分比加成基于最新基础值)
- 重置属性: 重新计算所有装备加成

#### 4. 问题识别

**计算逻辑不一致**:
- ✅ **Player.get_effective_attributes**: 只加临时buff（装备和丹药已持久化）
- ✅ **BattleAttributeCalculator.calculate_effective_attributes_async**: 调用上述方法后应用上限
- ❌ **BattleAttributeCalculator.calculate_effective_attributes**: 同步版本不包含临时buff，**存在不一致**

**重复计算风险**:
- `get_attribute_breakdown` 每次都要查询多张表（装备、丹药、VIP、临时buff），**性能开销大**
- `recalc_equipment_attributes` 需要遍历所有装备逐个计算，频繁调用会有性能问题
- ❌ **循环依赖**: `item_effects.py` 导入 `equipment_commands.recalc_equipment_attributes`，违反模块分层

**缓存机制**:
- ✅ **装备加成缓存**: 通过 `_persist_bonus` 持久化，避免每次战斗都重新计算
- ❌ **无属性计算缓存**: `get_effective_attributes` 每次都要查询临时buff表
- ❌ **无战斗属性缓存**: `BattleAttributeCalculator` 每次战斗都要重新计算

**性能瓶颈**:
1. **get_attribute_breakdown**: 查询4张表，适合低频调用（查看面板）
2. **TemporaryBuff.get_total_attribute_bonuses**: 每次战斗都要查询，建议增加缓存
3. **recalc_equipment_attributes**: 装备操作频繁时开销大（穿戴、卸下、升级、镶嵌）

---

### conclusions

1. **属性计算分散在5个位置**，存在职责不清和重复计算的问题。
2. **Player模型是属性计算的核心**，`get_effective_attributes` 是主入口，已包含装备、丹药、VIP、临时buff。
3. **装备加成通过 `_persist_bonus` 持久化**，避免了每次战斗重新计算装备属性。
4. **BattleAttributeCalculator 的同步版本存在逻辑不一致**，不包含临时buff，建议废弃。
5. **临时buff每次都要查询数据库**，高频战斗场景下会成为性能瓶颈。
6. **get_attribute_breakdown 查询开销大**，仅适合低频调用（查看面板、调试）。
7. **循环依赖问题**: `item_effects.py` 直接导入 `equipment_commands.recalc_equipment_attributes`，违反分层原则。

---

### relations

1. **Player.get_effective_attributes** 是最终属性计算的入口，被以下模块调用:
   - `BattleAttributeCalculator.calculate_effective_attributes_async` (战斗系统)
   - `item_effects.py` 各种道具效果（恢复HP/MP时需要知道上限）
   - `Player.get_effective_battle_attributes` (获取战斗属性子集)

2. **recalc_equipment_attributes** 被以下场景调用:
   - 装备穿戴/卸下 (`equipment_commands.py`)
   - 使用永久属性丹药后 (`item_effects._recalculate_equipment_bonus`)
   - 重置属性 (`item_effects._reset_attr`)
   - 装备耐久耗尽自动卸下 (`item_effects._sweep_dungeon`)

3. **TemporaryBuff.get_total_attribute_bonuses** 被调用:
   - `Player.get_effective_attributes` (叠加临时buff)
   - `Player.get_attribute_breakdown` (分解属性来源)

4. **ItemInstance.apply_attr_bonus** 被调用:
   - `recalc_equipment_attributes` (重新计算装备加成)
   - `_reset_attr` (重置属性时重新穿戴装备)

5. **循环依赖**:
   - `item_effects.py` (line 13) 导入 `equipment_commands.recalc_equipment_attributes`
   - 应通过事件系统或依赖注入解耦

---

**建议优化方向**:

1. **统一属性计算入口**: 废弃 `BattleAttributeCalculator.calculate_effective_attributes`，统一使用异步版本。
2. **增加临时buff缓存**: 在玩家会话期间缓存临时buff，避免频繁查询数据库。
3. **解除循环依赖**: 使用事件系统替代直接调用 `recalc_equipment_attributes`。
4. **属性计算器重构**: 参考 `REFACTORING_PLAN.md` 中的设计，引入 `AttributeCalculator` 和 `IAttributeSource` 接口。
5. **性能监控**: 对 `get_attribute_breakdown` 和 `recalc_equipment_attributes` 添加性能监控，识别热点。
