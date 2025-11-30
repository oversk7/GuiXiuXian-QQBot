# 属性系统架构

## 1. Identity

- **What it is**: 诡修仙项目属性计算系统的架构分析
- **Purpose**: 为LLM代理提供属性计算的精确检索路径,理解多层属性叠加机制

## 2. Core Components

### 属性计算入口(分散在5处)

- `plugins/xiuxian_game/models/player.py:218-256` (Player.get_effective_attributes): 主入口,返回基础属性+临时buff
- `plugins/xiuxian_game/models/player.py:287-415` (Player.get_attribute_breakdown): 详细分解各来源加成(基础、装备、丹药、VIP、临时buff)
- `plugins/xiuxian_game/battle/battle_attributes.py:39-85` (BattleAttributeCalculator.calculate_effective_attributes): 同步版本,不含临时buff,已弃用
- `plugins/xiuxian_game/battle/battle_attributes.py:88-152` (BattleAttributeCalculator.calculate_effective_attributes_async): 异步版本,调用Player.get_effective_attributes
- `plugins/xiuxian_game/item/equipment_commands.py:96-175` (recalc_equipment_attributes): 装备穿戴时重算属性加成

### 属性来源实现

- `plugins/xiuxian_game/models/inventory.py:162-218` (ItemInstance.apply_attr_bonus): 计算装备属性加成(固定值+百分比+宝石)
- `plugins/xiuxian_game/models/temporary_buff.py:151-164` (TemporaryBuff.get_total_attribute_bonuses): 计算所有激活buff的总加成
- `plugins/xiuxian_game/item/item_effects.py:176-218` (_buff): 永久属性加成处理
- `plugins/xiuxian_game/item/item_effects.py:221-301` (_temporary_buff): 临时属性加成处理

### 属性持久化机制

- `plugins/xiuxian_game/models/inventory.py` (ItemInstance.extra_attrs["_persist_bonus"]): 装备持久化加成存储
- `plugins/xiuxian_game/item/equipment_commands.py:23-93` (_apply_mp_from_hp_effects): mp_from_hp特效处理

## 3. Execution Flow (LLM Retrieval Map)

### 查询属性流程

**1. 入口调用**: `attrs = await player.get_effective_attributes(session)` (`player.py:218`)
**2. 初始化结果字典**: 复制基础属性到result (`player.py:220-237`)
   - 基础属性已包含装备和丹药的_persist_bonus
**3. 查询临时buff**: `buff_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, player.id)` (`player.py:241`)
**4. 数据库查询**: 查询所有激活的TemporaryBuff记录 (`temporary_buff.py:154`)
**5. 累加buff**: 遍历buff,合并attribute_bonuses JSON字段 (`temporary_buff.py:157-162`)
**6. 合并到结果**: result += buff_bonuses (`player.py:244-254`)
**7. 返回**: 返回最终有效属性字典

### 装备穿戴属性计算流程

**1. 重算入口**: `recalc_equipment_attributes(session, player)` (`equipment_commands.py:96`)
**2. 卸下所有装备**:
   - 遍历已穿戴装备 (`equipment_commands.py:102`)
   - 读取 `item.extra_attrs.get("_persist_bonus", {})` (`equipment_commands.py:111`)
   - 从player属性中减去_persist_bonus (`equipment_commands.py:113-120`)
**3. 获取基础属性**: 计算无装备状态的base_attrs (`equipment_commands.py:124-138`)
**4. 逐个装备计算**:
   - 遍历装备列表 (`equipment_commands.py:140`)
   - 调用 `item.apply_attr_bonus(player, base_attrs, result_dict)` (`equipment_commands.py:148`)
   - 计算固定值加成: `cfg_value * (1 + 0.2 * upgrade_level)` (`inventory.py:180`)
   - 计算百分比加成: `base_attrs[attr] * cfg_percent / 100` (`inventory.py:197`)
   - 计算宝石加成: 遍历gem_slots_data (`inventory.py:205-216`)
   - 计算加成差值: `delta = new_value - old_value` (`inventory.py:189`)
   - 保存_persist_bonus: `item.extra_attrs["_persist_bonus"][attr] = delta` (`inventory.py:191`)
   - 应用到玩家: `result_dict[attr] += delta` (`inventory.py:192`)
**5. mp_from_hp特效**: `_apply_mp_from_hp_effects(player, equipped_items)` (`equipment_commands.py:156`)
**6. 修正上限**: 限制当前HP/MP不超过新上限 (`equipment_commands.py:166-173`)

### 永久属性加成流程

**1. 使用丹药**: 物品effect_type为BUFF (`item_effects.py:176`)
**2. 读取加成配置**: `cfg.effect_params` 获取属性和数值 (`item_effects.py:179`)
**3. 直接修改player**: `setattr(player, attr, getattr(player, attr) + value)` (`item_effects.py:188`)
**4. 记录丹药使用**: `update_elixir_usage(session, player, cfg)` (`item_effects.py:204`)
**5. 重新计算装备**: `_recalculate_equipment_bonus(session, player)` (`item_effects.py:209`)
   - 调用 `recalc_equipment_attributes` 重新计算百分比加成 (`item_effects.py:1134`)

### 临时buff加成流程

**1. 使用临时buff物品**: effect_type为TEMPORARY_BUFF (`item_effects.py:221`)
**2. 创建buff记录**: `TemporaryBuff.create_buff(session, player.id, buff_config)` (`item_effects.py:267`)
**3. 清理过期buff**: 自动删除is_expired的记录 (`temporary_buff.py:96`)
**4. 检查已存在**: 查询相同buff_id的激活buff (`temporary_buff.py:101`)
**5. 延长时间或创建**: 存在则更新expires_at,否则创建新记录 (`temporary_buff.py:104-113`)
**6. 查询时合并**: `get_effective_attributes` 自动合并所有激活buff

## 4. Design Rationale

### _persist_bonus机制的优势

**问题**: 装备百分比加成基于基础属性,但玩家可以:
1. 使用丹药提升基础属性
2. 穿戴多件装备
3. 卸下装备

**解决方案**: 持久化每件装备的实际加成值
```python
# 穿戴时记录
item.extra_attrs["_persist_bonus"] = {"attack": 120, "defense": 80}

# 卸下时准确回退
for attr, value in item.extra_attrs.get("_persist_bonus", {}).items():
    setattr(player, attr, getattr(player, attr) - value)
```

**收益**:
- 避免每次战斗重新计算装备加成
- 卸下装备时属性准确回退
- 使用丹药后自动重算装备百分比加成

### 为什么需要5处属性计算?

| 位置 | 用途 | 频率 |
|------|------|------|
| Player.get_effective_attributes | 战斗、技能、效果判定 | 高频 |
| Player.get_attribute_breakdown | 查看面板、调试 | 低频 |
| BattleAttributeCalculator.async | 战斗系统(应用上限) | 高频 |
| recalc_equipment_attributes | 穿戴/卸下装备 | 中频 |

**问题**: 同步版本calculate_effective_attributes不含临时buff,导致逻辑不一致

### 临时buff为什么不用_persist_bonus?

**原因**:
1. 临时buff有过期时间,需要数据库存储
2. buff可以叠加,同一玩家可有多个激活buff
3. buff由定时任务清理,不由玩家主动移除

**设计**: 使用TemporaryBuff表 + JSON字段存储attribute_bonuses

**性能问题**: 每次查询属性都要查询数据库,高频战斗场景下成为瓶颈

**优化方向**: 增加60秒TTL本地缓存

---

**相关文档**:
- 当前架构: `/architecture/current-architecture.md`
- 效果系统: `/architecture/effect-system.md`
- 重构方案: `/architecture/target-architecture.md`
- 优化指南: `/guides/how-to-optimize-query.md`
