# 战斗效果桥接器架构

## 1. Identity

- **What it is**: 使用桥接模式将现有的TriggerConfig系统适配到IEffect统一接口的架构层
- **Purpose**: 在保留优秀的BattleEffectManager设计的前提下，实现战斗效果与物品效果的接口统一

## 2. Core Components

### 核心类

- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:36-305` (BattleEffectBridge): 桥接器核心类，包装TriggerConfig并实现IEffect接口
- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:308-329` (create_bridge_for_trigger_config): 工厂函数，为单个TriggerConfig创建桥接器
- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_examples.py:15-422` (7个示例桥接器): 吸血、攻击buff、护盾、反弹、恐惧、低血量增益、区域限定
- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:22-87` (create_bridges_from_equipment_config): 从装备配置批量创建桥接器
- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:90-187` (register_all_battle_effect_bridges): 遍历所有装备并批量注册

### 触发类型映射

- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:21-33` (_TRIGGER_TYPE_MAPPING): IEffect.TriggerType → BattleEffect.TriggerType的枚举转换表

### 启动集成

- `plugins/xiuxian_game/__init__.py:46-64` (on_startup): 在bot启动时注册所有战斗效果桥接器

## 3. Execution Flow (LLM Retrieval Map)

### 桥接器创建流程

**1. 启动扫描**: `register_all_battle_effect_bridges()` 遍历装备配置 (`battle_effect_register.py:143`)
**2. 获取配置**: 从 `config.items_config.get("by_id")` 读取装备配置 (`battle_effect_register.py:143`)
**3. 检查效果**: 检查 `item_config.special_effects` 是否存在 (`battle_effect_register.py:148`)
**4. 解析配置**: 调用 `parse_triggers_from_yaml(special_effects)` 解析YAML (`battle_effect_register.py:65`)
**5. 创建桥接器**: 为每个TriggerConfig调用 `create_bridge_for_trigger_config()` (`battle_effect_register.py:74`)
**6. 注册到中心**: 调用 `registry.register_class(bridge.effect_id, BattleEffectBridge)` (`battle_effect_register.py:164`)

### 桥接器触发流程

**1. 检查触发类型**: `can_trigger()` 映射IEffect.TriggerType到BattleTriggerType (`battle_effect_bridge.py:129-135`)
**2. 概率判定**: 如果 `chance < 1.0`，执行 `random.random()` 判定 (`battle_effect_bridge.py:138-144`)
**3. 条件检查**: 调用 `_check_condition()` 验证低血量、理智上限等条件 (`battle_effect_bridge.py:147-152`)
**4. 环境检查**: 调用 `_check_environment()` 验证区域和周主题白名单 (`battle_effect_bridge.py:155-159`)
**5. 执行效果**: `execute()` 创建BattleEffect对象并返回 (`battle_effect_bridge.py:183-191`)
**6. 返回结果**: 在 `EffectResult.extra_data` 中包含BattleEffect对象 (`battle_effect_bridge.py:206-210`)

### 条件检查逻辑

**低血量检查** (`battle_effect_bridge.py:232-249`):
- 尝试从 `context.player.current_hp` 获取
- 或从 `context.metadata["battle_state"].get_unit(unit_id).current_hp` 获取
- 与 `threshold * max_hp` 比较

**理智上限检查** (`battle_effect_bridge.py:252-269`):
- 尝试从 `context.player.max_mp` 获取
- 或从 `context.metadata["battle_state"].get_unit(unit_id).max_mp` 获取
- 与 `required_mp` 比较

**区域白名单检查** (`battle_effect_bridge.py:284-292`):
- 从 `context.metadata["region"]` 获取当前区域
- 与 `trigger_config.region_whitelist` 比较

**周主题白名单检查** (`battle_effect_bridge.py:295-303`):
- 从 `context.metadata["week_theme"]` 获取当前周主题
- 与 `trigger_config.week_theme_whitelist` 比较

## 4. Design Rationale

### 为什么选择桥接模式而非适配器模式？

**ItemEffect vs BattleEffect的本质区别**:

| 特性 | ItemEffect | BattleEffect |
|------|-----------|-------------|
| 执行模式 | 无状态函数 | 有状态对象 (duration, stacks) |
| 生命周期 | 瞬时（调用即结束） | 持续性（跨多回合） |
| 触发方式 | 显式调用 | 被动检查 (16处调用) |
| 效果应用 | 集中在函数内 | 分散在战斗引擎各处 |

**参考文档**: `plugins/xiuxian_game/domain/effects/adapters/BATTLE_EFFECT_ADAPTER_DESIGN.md:9-19`

**核心决策** (`BATTLE_EFFECT_ADAPTER_DESIGN.md:495-503`):
1. ✅ 保留BattleEffectManager和BattleEffect（已验证优秀的设计）
2. ✅ 提供IEffect接口访问层（统一接口）
3. ✅ 向后兼容（新旧系统并存）
4. ✅ 渐进迁移（Feature Flag控制）

### 桥接器的职责边界

**桥接器做什么**:
- ✅ 包装TriggerConfig为IEffect接口
- ✅ 执行触发条件检查（概率、条件、环境）
- ✅ 创建BattleEffect对象并返回

**桥接器不做什么**:
- ❌ 不直接应用效果到战斗状态
- ❌ 不管理效果的持续时间和堆叠
- ❌ 不替代BattleEffectManager

**原因**: 效果应用逻辑已分散在 `enhanced_engine.py` 的16处不同位置，重写成本过高且风险大。桥接模式保持最小改动。

### TriggerType映射机制

**设计原因**:
- IEffect接口定义了统一的TriggerType枚举（13种）
- BattleEffect使用独立的TriggerType枚举（不同命名）
- 需要在两者之间转换

**映射表** (`battle_effect_bridge.py:21-33`):
```python
_TRIGGER_TYPE_MAPPING = {
    TriggerType.ON_ATTACK: BattleTriggerType.ON_ATTACK,
    TriggerType.ON_DEFENSE: BattleTriggerType.ON_DEFENSE,
    TriggerType.ON_ROUND_START: BattleTriggerType.EACH_TURN,  # 映射
    TriggerType.ON_BATTLE_START: BattleTriggerType.FIRST_TURN,  # 映射
    TriggerType.ON_DAMAGED: BattleTriggerType.ON_ATTACKED,  # 映射
    # ...
}
```

**映射策略**:
- 直接映射：枚举值完全一致（如ON_ATTACK）
- 语义映射：功能相同但命名不同（如ON_ROUND_START → EACH_TURN）
- 缺失兜底：不支持的触发类型返回False (`battle_effect_bridge.py:130-132`)

### 批量注册的配置访问模式

**Bug修复** (`battle_effect_register.py:143`):
```python
# ❌ 错误方式（会遍历所有索引）
for item_id, item_config in config.items_config.items():
    # 这会遍历 "by_id", "by_type", "by_name" 等索引

# ✅ 正确方式（仅遍历by_id索引）
items_by_id = config.items_config.get("by_id", {})
for item_id, item_config in items_by_id.items():
    # 仅遍历实际的装备配置
```

**原因**: `config.items_config` 是多索引字典，包含 `by_id`, `by_type`, `by_name` 等键。直接 `.items()` 会遍历索引本身，导致重复注册和类型错误。

### 注册结果统计

**启动日志证据** (`__init__.py:60`):
```
[EffectSystem] 成功注册 23 个战斗效果桥接器
```

**详细统计** (`battle_effect_register.py:180-185`):
- 扫描装备: 252个
- 有特殊效果: 12个
- 注册桥接器: 23个

**12个装备清单**:
1. 魂旗 (soul_flag) - 1个效果
2. 抽屉 (drawer) - 1个效果
3. 嫁衣 (wedding_dress) - 1个效果
4. 虚无之冠 (void_essence_crown) - 1个效果
5. 电击治疗仪 (shock_therapy_device) - 1个效果
6. 现实遗书 (reality_suicide_note) - 2个效果
7. 神泪护符 (god_tear_amulet) - 1个效果
8. 世界碎片之刃 (world_fragment_blade) - 2个效果
9. 退天星刃 (heaven_retreat_star_blade) - 3个效果
10. 永夜裹尸布 (shroud_of_eternity) - 1个效果
11. 斩龙闪 (vip_blade_zhanlongshan) - 6个效果
12. 镜源之衣 (vip_robe_jingyuanzhiyi) - 3个效果

**平均**: 23 / 12 ≈ 1.92 个效果/装备

---

**相关文档**:
- 设计文档: `plugins/xiuxian_game/domain/effects/adapters/BATTLE_EFFECT_ADAPTER_DESIGN.md`
- API参考: `/reference/battle-effect-bridge-api.md`
- 操作指南: `/guides/how-to-create-battle-effect-bridge.md`
- 效果系统概览: `/architecture/effect-system.md`
