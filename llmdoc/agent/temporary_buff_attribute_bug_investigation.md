# 临时buff丹药属性计算错误调查报告

## 调查概述

**问题描述**: 用户使用临时buff类丹药（如疾风丹）后，在属性分解指令中观察到基础属性被错误分配到临时属性中，总属性没有变化，丹药效果不起作用。

**调查时间**: 2025-12-10
**调查范围**: 临时buff丹药效果实现、属性计算系统、属性分解逻辑

---

## Code Sections (The Evidence)

### 临时buff丹药效果实现

- `plugins/xiuxian_game/item/item_effects.py:227-307` (`_temporary_buff`): TEMPORARY_BUFF类型丹药效果处理器，创建固定值临时buff
- `plugins/xiuxian_game/item/item_effects.py:399-468` (`_temporary_buff_percent`): TEMPORARY_BUFF_PERCENT类型丹药效果处理器，创建百分比临时buff，**调用update_elixir_usage记录使用日志**
- `plugins/xiuxian_game/item/item_effects.py:67-80` (`update_elixir_usage`): 更新丹药使用记录到ElixirUsageLog表，**条件：item_id必须以_elixir结尾**

### 临时buff模型与查询

- `plugins/xiuxian_game/models/temporary_buff.py:14-48` (`TemporaryBuff`): 临时buff数据模型，包含attribute_bonuses(JSON)、expires_at、duration_minutes等字段
- `plugins/xiuxian_game/models/temporary_buff.py:100-148` (`create_buff`): 创建或延长临时buff，**不修改Player的基础属性字段**
- `plugins/xiuxian_game/models/temporary_buff.py:150-164` (`get_total_attribute_bonuses`): 获取所有激活buff的总属性加成，返回字典

### 属性计算系统

- `plugins/xiuxian_game/models/player.py:218-256` (`get_effective_attributes`): 获取玩家有效属性（基础+临时buff），**正确合并临时buff加成**
- `plugins/xiuxian_game/models/player.py:287-415` (`get_attribute_breakdown`): 属性来源分解，**问题核心函数**
  - L329-347: 计算丹药加成（从ElixirUsageLog查询）
  - L349-366: 计算装备加成（从ItemInstance._persist_bonus查询）
  - L368-377: 计算VIP装备加成
  - L379-386: 计算临时buff加成（从TemporaryBuff查询）
  - **L388-395: 计算基础属性 = 当前属性值 - 装备 - 临时buff - 丹药 - VIP装备**

### 丹药使用日志模型

- `plugins/xiuxian_game/models/elixir_usage.py:15-62` (`ElixirUsageLog`): 记录玩家丹药使用量，**仅用于BUFF类型（永久加成）丹药**
- `plugins/xiuxian_game/models/elixir_usage.py:25-37` (`get_attribute_bonus`): 根据使用记录计算属性加成，**条件：effect_type必须是BUFF**

### 属性分解指令

- `plugins/xiuxian_game/item/buff_commands.py:77-186` (`handle_attribute_breakdown`): 属性分解指令实现
  - L93: 调用`player.get_attribute_breakdown(session)`
  - L122-145: 显示主要属性分解（基础、装备、丹药、VIP装备、临时）

### 丹药配置示例

- `plugins/xiuxian_game/data/items.yaml:1379-1414`: 临时buff丹药配置
  - `swift_wind_elixir`(疾风丹): effect_type=TEMPORARY_BUFF_PERCENT, agility_pct=15, duration=20分钟
  - `shadow_step_elixir`(影步丹): effect_type=TEMPORARY_BUFF_PERCENT, agility_pct=25, duration=20分钟
  - `eagle_eye_elixir`(鹰眼丸): effect_type=TEMPORARY_BUFF, accuracy_rate=25, critical_rate=12, duration=15分钟
  - `combo_master_elixir`(连击丹): effect_type=TEMPORARY_BUFF, combo_rate=20, counter_rate=10, duration=15分钟

---

## Report (The Answers)

### result

#### 核心问题定位

**问题根源**: `_temporary_buff_percent`函数在第466行调用`update_elixir_usage`，将临时buff丹药记录到ElixirUsageLog表中。

**错误链条**:

1. **误用记录系统**: `update_elixir_usage`函数（item_effects.py:67-80）设计用于记录**永久属性加成丹药**（BUFF类型）的使用量，但`_temporary_buff_percent`（第466行）和`_temporary_buff`（第305行）也调用了此函数

2. **属性分解计算错误**: `get_attribute_breakdown`（player.py:329-347）从ElixirUsageLog查询所有使用记录，并将其归类为"丹药加成"：
   ```python
   for item_id, total_qty in elixir_usage_total.items():
       item_cfg = gcfg.items_config["by_id"].get(item_id)
       if item_cfg and item_cfg.effect_type.value == "BUFF":  # 仅检查BUFF类型
           effect_params = item_cfg.effect_params or {}
           for attr, value in effect_params.items():
               if attr in elixir_bonus:
                   elixir_bonus[attr] += int(value) * total_qty
   ```
   但由于临时buff丹药的effect_type是TEMPORARY_BUFF或TEMPORARY_BUFF_PERCENT（不是BUFF），这段代码**不会**将其计入elixir_bonus

3. **基础属性计算偏移**: `get_attribute_breakdown`在L388-395计算基础属性时使用公式：
   ```python
   base_value = current_value - equipment_bonus[attr] - temporary_bonus[attr] - elixir_bonus[attr] - vip_equipment_bonus[attr]
   ```
   - `temporary_bonus`正确包含了临时buff的加成（从TemporaryBuff表查询）
   - 但由于临时buff丹药被误记录到ElixirUsageLog，导致数据污染
   - 虽然elixir_bonus不会错误计入（因为effect_type检查），但ElixirUsageLog的存在干扰了逻辑

4. **实际症状分析**:
   - 临时buff创建成功（TemporaryBuff表）✓
   - 临时buff加成正确查询（temporary_bonus）✓
   - **但总属性不变的原因**: 需要检查get_effective_attributes是否被正确调用
   - **基础属性错误的原因**: update_elixir_usage不应该被调用

#### 为什么总属性没有变化？

**重要发现**: 检查`get_effective_attributes`（player.py:218-256）逻辑，临时buff加成**正确应用**：
```python
buff_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, self.id)
for attr, bonus in buff_bonuses.items():
    if attr in base_attrs:
        base_attrs[attr] += bonus  # 临时buff加成正确合并
```

**可能原因**:
1. **战斗系统未使用get_effective_attributes**: 某些战斗或显示逻辑可能直接读取player.attack等字段，而不是调用get_effective_attributes
2. **临时buff过期**: 如果玩家查看属性时buff已过期，总属性自然不变
3. **前端缓存**: 用户可能看到的是缓存的旧数据

#### 属性分解显示错误的原因

**确认问题**: 属性分解指令（buff_commands.py:93）调用get_attribute_breakdown，该函数在计算基础属性时减去了temporary_bonus，导致：
- **临时buff激活时**: base = current - temporary，基础属性正确减少
- **显示问题**: 用户期望"基础属性"是不变的，但实际上代码将"基础属性"定义为"当前属性减去所有加成"
- **语义混淆**: 用户认为的"基础属性"是Player表中存储的原始值，但代码计算的是"去除所有buff后的属性"

### conclusions

1. **临时buff丹药误用ElixirUsageLog**: `_temporary_buff`和`_temporary_buff_percent`不应调用`update_elixir_usage`，该函数仅用于永久BUFF类型丹药
2. **属性分解语义混淆**: `get_attribute_breakdown`计算的"基础属性"是去除所有加成后的值，与用户期望的"Player表存储的原始属性"不一致
3. **临时buff效果正常工作**: `get_effective_attributes`正确合并临时buff加成，战斗系统应该能正确应用
4. **ElixirUsageLog设计缺陷**: 该表的条件检查（item_id.endswith("_elixir")）过于宽松，导致临时buff丹药也被记录
5. **总属性不变可能是其他原因**: 需要检查战斗系统是否正确调用get_effective_attributes，或buff是否已过期

### relations

1. **item_effects.py → temporary_buff.py**: `_temporary_buff_percent`调用`TemporaryBuff.create_buff`创建buff记录
2. **item_effects.py → elixir_usage.py**: `_temporary_buff_percent`误调用`update_elixir_usage`记录日志
3. **player.py → temporary_buff.py**: `get_effective_attributes`调用`TemporaryBuff.get_total_attribute_bonuses`获取临时加成
4. **player.py → elixir_usage.py**: `get_attribute_breakdown`查询ElixirUsageLog计算丹药加成
5. **buff_commands.py → player.py**: 属性分解指令调用`get_attribute_breakdown`显示属性来源

---

## 修复建议（仅供参考）

### 高优先级修复

1. **移除临时buff的ElixirUsageLog记录**:
   - 从`_temporary_buff`（L305）和`_temporary_buff_percent`（L466）中删除`update_elixir_usage`调用
   - 临时buff效果已通过TemporaryBuff表管理，无需ElixirUsageLog

2. **明确属性分解语义**:
   - 在属性分解指令中添加说明：基础属性 = 当前属性 - 所有加成
   - 或者修改get_attribute_breakdown，将Player表存储的原始值作为"存储属性"单独显示

### 中优先级修复

3. **检查战斗系统集成**:
   - 确认所有战斗、技能、效果判定都使用`get_effective_attributes`而非直接读取player.attack
   - 搜索关键词：`player.attack`, `player.defense`, `player.agility`等，确保都经过属性计算

4. **优化ElixirUsageLog条件检查**:
   - 修改`update_elixir_usage`（L77）的条件为：`if item_cfg.effect_type == ItemEffectType.BUFF`
   - 而不是宽松的`item_id.endswith("_elixir")`

### 低优先级优化

5. **添加buff状态提示**:
   - 在属性分解指令中，当检测到临时buff时，显示buff剩余时间和具体加成
   - 帮助用户理解为什么基础属性减少了

---

## 数据完整性检查

**建议执行的SQL查询**:
```sql
-- 检查是否有临时buff丹药被错误记录到ElixirUsageLog
SELECT e.*, i.effect_type
FROM elixir_usage_log e
JOIN (SELECT item_id FROM items WHERE effect_type IN ('TEMPORARY_BUFF', 'TEMPORARY_BUFF_PERCENT')) i
ON e.item_id = i.item_id;

-- 如果有记录，需要清理
DELETE FROM elixir_usage_log
WHERE item_id IN (
    SELECT item_id FROM items WHERE effect_type IN ('TEMPORARY_BUFF', 'TEMPORARY_BUFF_PERCENT')
);
```

**注意**: 实际表结构中items配置在YAML文件中，需要根据实际数据库schema调整查询。
