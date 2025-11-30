# 如何创建战斗效果桥接器

本指南提供创建、测试和排查战斗效果桥接器的分步操作说明。

## 步骤1: 确定效果需求

**操作**: 分析装备配置YAML，确定需要创建的效果类型。

**示例**:
```yaml
# config/items_config.yaml
wedding_dress:
  name: "嫁衣"
  special_effects:
    - trigger: "on_hit"
      chance: 100
      effect: "lifesteal"
      value: 12
      duration: 0
      description: "吸血12%"
```

**确认信息**:
- 触发类型: `on_hit`
- 效果类型: `lifesteal`
- 触发概率: `100%`
- 效果值: `12%`
- 持续时间: `0`（瞬时效果）

## 步骤2: 检查触发类型映射

**操作**: 查看 `battle_effect_bridge.py:21-33` 的 `_TRIGGER_TYPE_MAPPING`，确认触发类型是否已映射。

**参考**:
```python
_TRIGGER_TYPE_MAPPING = {
    TriggerType.ON_ATTACK: BattleTriggerType.ON_ATTACK,
    TriggerType.ON_HIT: BattleTriggerType.ON_HIT,  # ✅ 已支持
    # ...
}
```

**如果缺失**: 添加新的映射关系（参见步骤6）。

## 步骤3: 选择创建方式

### 方式A: 使用示例工厂函数（推荐）

**适用场景**: 创建常见的效果类型（吸血、buff、护盾等）。

**操作**: 调用 `battle_effect_examples.py` 中的工厂函数。

**示例**:
```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_examples import (
    create_lifesteal_bridge
)

# 创建吸血效果桥接器
bridge = create_lifesteal_bridge(
    lifesteal_percent=0.12,  # 12%吸血
    effect_id_suffix="嫁衣"
)
```

**可用工厂函数**:
- `create_lifesteal_bridge()` - 吸血效果
- `create_attack_buff_bridge()` - 攻击力提升
- `create_shield_bridge()` - 护盾
- `create_reflect_bridge()` - 伤害反弹
- `create_fear_bridge()` - 恐惧
- `create_low_hp_damage_boost_bridge()` - 低血量增益
- `create_region_restricted_buff_bridge()` - 区域限定增益

**参考**: `battle_effect_examples.py:15-422`

### 方式B: 手动创建TriggerConfig

**适用场景**: 创建复杂的自定义效果。

**操作**:
```python
from plugins.xiuxian_game.battle.battle_effects import (
    TriggerConfig,
    TriggerType,
    EffectType
)
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_bridge import (
    create_bridge_for_trigger_config
)

# 1. 创建TriggerConfig
trigger_config = TriggerConfig(
    trigger=TriggerType.ON_HIT,
    effect=EffectType.LIFESTEAL,
    value=0.12,
    chance=1.0,
    duration=0,
    description="吸血12%"
)

# 2. 创建桥接器
bridge = create_bridge_for_trigger_config(
    trigger_config=trigger_config,
    base_effect_id="wedding_dress_0"
)
```

**参考**: `battle_effect_bridge.py:308-329`

### 方式C: 从装备配置批量创建

**适用场景**: 批量处理多个装备的效果。

**操作**:
```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import (
    create_bridges_from_equipment_config
)

# 从装备配置创建所有效果的桥接器
bridges = create_bridges_from_equipment_config(
    item_id="wedding_dress",
    item_name="嫁衣",
    special_effects=item_config.special_effects  # YAML配置列表
)

# bridges是列表，包含该装备的所有效果桥接器
for bridge in bridges:
    print(f"创建桥接器: {bridge.effect_id}")
```

**参考**: `battle_effect_register.py:22-87`

## 步骤4: 注册到效果注册中心

**操作**: 将创建的桥接器注册到全局效果注册中心。

**手动注册**:
```python
from plugins.xiuxian_game.domain.effects.registry import get_effect_registry

registry = get_effect_registry()

# 注册单个桥接器
registry.register_class(
    bridge.effect_id,
    type(bridge),
    singleton=False  # 每次战斗创建新实例
)
```

**批量注册** (推荐):
```python
from plugins.xiuxian_game.domain.effects.adapters import (
    register_all_battle_effect_bridges
)

# 遍历所有装备配置并批量注册
bridges = register_all_battle_effect_bridges()
print(f"注册了 {len(bridges)} 个桥接器")
```

**启动时自动注册**: 已在 `plugins/xiuxian_game/__init__.py:58-60` 配置，无需额外操作。

**参考**: `battle_effect_register.py:90-187`

## 步骤5: 验证注册成功

**操作**: 启动bot，检查日志输出。

**预期日志**:
```
[INFO] [BattleEffectRegister] 开始批量注册战斗效果桥接器...
[DEBUG] [BattleEffectRegister] 为装备 嫁衣(wedding_dress) 创建桥接器 1/1: battle_lifesteal_wedding_dress_0 (效果: lifesteal)
[DEBUG] [BattleEffectRegister] 注册桥接器: battle_lifesteal_wedding_dress_0 (装备: 嫁衣, 效果: lifesteal)
[SUCCESS] [BattleEffectRegister] 批量注册完成: 扫描 252 个装备配置, 发现 12 个装备有特殊效果, 成功注册 23 个战斗效果桥接器
[SUCCESS] [EffectSystem] 成功注册 23 个战斗效果桥接器
```

**检查注册**:
```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import (
    is_bridge_registered,
    get_bridge_count,
    get_bridge_statistics
)

# 检查特定桥接器
if is_bridge_registered("battle_lifesteal_wedding_dress_0"):
    print("✅ 桥接器已注册")

# 获取总数
count = get_bridge_count()
print(f"总共注册了 {count} 个桥接器")

# 获取统计
stats = get_bridge_statistics()
print(f"统计: {stats}")
# 输出: {'total_bridges': 23, 'total_equipment': 12, 'avg_effects_per_equipment': 1.92}
```

**参考**: `battle_effect_register.py:190-280`

## 步骤6: 添加新的触发类型映射（高级）

**适用场景**: 需要支持新的触发类型，且当前 `_TRIGGER_TYPE_MAPPING` 中未定义。

**操作**:

**6.1 定位映射表**:
打开 `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:21-33`

**6.2 添加映射**:
```python
_TRIGGER_TYPE_MAPPING = {
    # ... 现有映射
    TriggerType.YOUR_NEW_TYPE: BattleTriggerType.CORRESPONDING_TYPE,
}
```

**6.3 确认映射逻辑**:
- **直接映射**: IEffect和BattleEffect的枚举值完全一致
- **语义映射**: 功能相同但命名不同（如 `ON_ROUND_START` → `EACH_TURN`）

**6.4 测试映射**:
创建使用新触发类型的桥接器并验证 `can_trigger()` 行为。

## 步骤7: 排查常见问题

### 问题1: 桥接器未触发

**症状**: `can_trigger()` 总是返回False。

**排查步骤**:

**7.1 检查触发类型映射**:
```python
# 在can_trigger中添加日志
battle_trigger_type = _TRIGGER_TYPE_MAPPING.get(context.trigger_type)
if battle_trigger_type is None:
    print(f"❌ 不支持的触发类型: {context.trigger_type}")
```

**7.2 检查概率判定**:
```python
# 查看TriggerConfig.chance
print(f"触发概率: {bridge.trigger_config.chance}")
# 如果chance=0.2，只有20%概率触发
```

**7.3 检查条件**:
```python
# 检查是否有condition
if bridge.trigger_config.condition:
    print(f"效果有条件限制: {bridge.trigger_config.condition}")
    # 示例: {"low_hp": True, "threshold": 0.3} - 需要血量<30%
```

**7.4 检查环境**:
```python
# 检查白名单
if bridge.trigger_config.region_whitelist:
    print(f"区域白名单: {bridge.trigger_config.region_whitelist}")
    print(f"当前区域: {context.metadata.get('region')}")

if bridge.trigger_config.week_theme_whitelist:
    print(f"周主题白名单: {bridge.trigger_config.week_theme_whitelist}")
    print(f"当前周主题: {context.metadata.get('week_theme')}")
```

**参考**: `battle_effect_bridge.py:112-161`

### 问题2: 条件检查失败

**症状**: 带条件的效果（低血量、理智上限）无法触发。

**排查步骤**:

**7.5 检查上下文数据**:
```python
# 确保EffectContext包含必要数据
print(f"player对象: {context.player}")
print(f"battle_state: {context.metadata.get('battle_state')}")
print(f"unit_id: {context.metadata.get('unit_id')}")
```

**7.6 检查属性存在**:
```python
# 低血量检查需要
if hasattr(context.player, "current_hp") and hasattr(context.player, "max_hp"):
    print(f"✅ 血量属性存在: {context.player.current_hp}/{context.player.max_hp}")
else:
    print(f"❌ 缺少血量属性")
```

**7.7 计算阈值**:
```python
# 检查是否真的满足条件
threshold = bridge.trigger_config.condition.get("threshold", 0.3)
hp_percent = context.player.current_hp / context.player.max_hp
print(f"当前血量百分比: {hp_percent:.2%}, 阈值: {threshold:.2%}")
if hp_percent > threshold:
    print(f"❌ 血量过高，不触发")
```

**参考**: `battle_effect_bridge.py:213-271`

### 问题3: 重复注册错误

**症状**: 启动时报错 "桥接器已注册"。

**原因**: `register_all_battle_effect_bridges()` 被调用了两次。

**解决**:
```python
# 检查是否已注册
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import (
    get_registered_bridges
)

if not get_registered_bridges():
    # 仅在未注册时执行
    bridges = register_all_battle_effect_bridges()
```

**内置防护**: `register_all_battle_effect_bridges()` 已实现幂等性检查 (`battle_effect_register.py:122-127`)，第二次调用会直接返回。

### 问题4: 配置访问错误

**症状**: 遍历 `config.items_config.items()` 导致类型错误。

**原因**: `items_config` 是多索引字典，包含 `by_id`, `by_type`, `by_name` 等索引键。

**错误代码**:
```python
# ❌ 错误：会遍历索引本身
for item_id, item_config in config.items_config.items():
    # item_id可能是 "by_id", "by_type" 等字符串
```

**正确代码**:
```python
# ✅ 正确：仅遍历by_id索引
items_by_id = config.items_config.get("by_id", {})
for item_id, item_config in items_by_id.items():
    # item_id是实际的装备ID（如 "wedding_dress"）
```

**参考**: `battle_effect_register.py:143` 的bug修复

### 问题5: 效果未应用到战斗

**症状**: 桥接器触发了，但战斗中没有效果。

**原因**: `execute()` 返回的BattleEffect未被添加到BattleEffectManager。

**解决**:

**5.1 检查是否提供了effect_manager**:
```python
# 创建桥接器时提供effect_manager
bridge = BattleEffectBridge(
    effect_id="...",
    trigger_config=trigger_config,
    effect_manager=battle_state.effect_manager  # ✅ 提供管理器
)

# 或者手动添加效果
result = await bridge.execute(context)
battle_effect = result.extra_data["battle_effect"]
effect_manager.add_effect(unit_id, battle_effect)
```

**5.2 确认BattleEffectManager工作正常**:
```python
# 检查效果是否被添加
effects = effect_manager.get_effects(unit_id)
print(f"单位 {unit_id} 的效果列表: {effects}")
```

**参考**: `battle_effect_bridge.py:193-200`

---

**最后一步**: 运行 `面板` 或战斗命令，观察日志确认效果正常触发。

**成功标志**:
- ✅ 启动日志显示桥接器注册成功
- ✅ `can_trigger()` 返回True
- ✅ `execute()` 创建BattleEffect对象
- ✅ BattleEffectManager包含该效果
- ✅ 战斗中效果正常应用

---

**相关文档**:
- API参考: `/llmdoc/reference/battle-effect-bridge-api.md`
- 架构文档: `/llmdoc/architecture/battle-effect-bridge.md`
- 设计文档: `plugins/xiuxian_game/domain/effects/adapters/BATTLE_EFFECT_ADAPTER_DESIGN.md`
- 示例代码: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_examples.py`
