# BattleEffectBridge API参考

## 1. Core Summary

BattleEffectBridge是战斗效果桥接器的核心类，负责将现有的TriggerConfig系统桥接到IEffect统一接口。它不直接应用效果，而是返回需要添加到BattleEffectManager的BattleEffect对象。

**关键特性**:
- 实现IEffect接口
- 包装TriggerConfig对象
- 委托触发检查逻辑
- 返回BattleEffect对象而非直接应用

## 2. Source of Truth

### 主要代码

- **桥接器核心**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py`
  - BattleEffectBridge类 (305行)
  - TriggerType映射表
  - 条件检查逻辑
  - 工厂函数

- **示例实现**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_examples.py`
  - 7个常见战斗效果桥接器 (370行)
  - 吸血、buff、护盾、反弹、恐惧、条件效果、环境限定

- **批量注册**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py`
  - 从装备配置创建桥接器 (240行)
  - 批量注册到效果注册中心
  - 统计和查询函数

### 相关架构

- **IEffect接口定义**: `plugins/xiuxian_game/domain/effects/interfaces.py`
- **效果注册中心**: `plugins/xiuxian_game/domain/effects/registry.py`
- **BattleEffect原始系统**: `plugins/xiuxian_game/battle/battle_effects.py`
- **战斗引擎**: `plugins/xiuxian_game/battle/enhanced_engine.py`

### 设计文档

- **BATTLE_EFFECT_ADAPTER_DESIGN.md**: `plugins/xiuxian_game/domain/effects/adapters/BATTLE_EFFECT_ADAPTER_DESIGN.md`
  - 详细设计文档 (600行)
  - 桥接模式vs适配器模式的选择理由
  - 完整的集成策略

### 相关架构文档

- **战斗效果桥接器架构**: `/llmdoc/architecture/battle-effect-bridge.md`
- **操作指南**: `/llmdoc/guides/how-to-create-battle-effect-bridge.md`

---

## 3. API Reference

### 3.1 BattleEffectBridge类

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:36-305`

**构造函数**:
```python
def __init__(
    self,
    effect_id: str,
    trigger_config: TriggerConfig,
    effect_manager: Optional[BattleEffectManager] = None
)
```

**参数**:
- `effect_id: str` - 效果唯一标识（如"battle_lifesteal_wedding_dress_0"）
- `trigger_config: TriggerConfig` - 触发配置对象（来自装备YAML）
- `effect_manager: Optional[BattleEffectManager]` - 效果管理器实例（可选）

**属性**:
- `effect_id: str` - 效果唯一标识（只读）
- `trigger_config: TriggerConfig` - 暴露原始TriggerConfig供兼容性使用（只读）

**核心方法**:

#### can_trigger(context: EffectContext) -> bool

判断效果是否可以触发。

**参数**:
- `context: EffectContext` - 效果执行上下文，必须包含：
  - `context.trigger_type` - 触发类型（IEffect.TriggerType）
  - `context.metadata["unit_id"]` - 战斗单位ID
  - `context.metadata["battle_state"]` - 战斗状态对象（可选，条件检查需要）
  - `context.metadata["region"]` - 当前区域（可选，白名单检查需要）
  - `context.metadata["week_theme"]` - 当前周主题（可选，白名单检查需要）

**返回**: `bool` - 是否可以触发

**检查流程**:
1. 触发类型映射 (`battle_effect_bridge.py:129-135`)
2. 概率判定 (`battle_effect_bridge.py:138-144`)
3. 条件检查 (`battle_effect_bridge.py:147-152`)
4. 环境检查 (`battle_effect_bridge.py:155-159`)

#### execute(context: EffectContext) -> EffectResult

执行效果，返回需要应用的BattleEffect对象。

**参数**:
- `context: EffectContext` - 效果执行上下文

**返回**: `EffectResult` - 效果执行结果，包含：
- `success: bool` - 固定为True
- `message: str` - 描述信息（如"触发效果: 吸血 15%"）
- `extra_data: Dict` - 包含以下字段：
  - `"battle_effect": BattleEffect` - 创建的BattleEffect对象
  - `"apply_to_manager": bool` - 固定为True
  - `"trigger_config": TriggerConfig` - 原始配置

**副作用**: 如果在构造时提供了 `effect_manager`，会自动调用 `effect_manager.add_effect()`

**实现位置**: `battle_effect_bridge.py:163-211`

---

### 3.2 工厂函数

#### create_bridge_for_trigger_config

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:308-329`

为单个TriggerConfig创建桥接器。

**签名**:
```python
def create_bridge_for_trigger_config(
    trigger_config: TriggerConfig,
    base_effect_id: str,
    effect_manager: Optional[BattleEffectManager] = None
) -> BattleEffectBridge
```

**参数**:
- `trigger_config: TriggerConfig` - 触发配置对象
- `base_effect_id: str` - 基础效果ID（如"wedding_dress_0"）
- `effect_manager: Optional[BattleEffectManager]` - 可选的效果管理器

**返回**: `BattleEffectBridge` - 桥接器实例

**效果ID生成规则**:
```python
effect_id = f"battle_{trigger_config.effect.value}_{base_effect_id}"
# 示例: "battle_lifesteal_wedding_dress_0"
```

#### create_bridges_from_equipment_config

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:22-87`

从单个装备配置创建所有战斗效果桥接器。

**签名**:
```python
def create_bridges_from_equipment_config(
    item_id: str,
    item_name: str,
    special_effects: List[Dict]
) -> List[BattleEffectBridge]
```

**参数**:
- `item_id: str` - 装备ID（如"wedding_dress"）
- `item_name: str` - 装备名称（如"嫁衣"）
- `special_effects: List[Dict]` - YAML配置中的special_effects列表

**返回**: `List[BattleEffectBridge]` - 桥接器列表

**实现逻辑**:
1. 调用 `parse_triggers_from_yaml(special_effects)` 解析YAML
2. 为每个TriggerConfig调用 `create_bridge_for_trigger_config()`
3. 效果ID格式: `"{item_id}_{index}"`

#### register_all_battle_effect_bridges

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:90-187`

批量注册所有战斗效果桥接器（从所有装备配置）。

**签名**:
```python
def register_all_battle_effect_bridges() -> Dict[str, Type[BattleEffectBridge]]
```

**返回**: `Dict[effect_id, BattleEffectBridge类型]` - 已注册的桥接器映射

**副作用**:
- 注册所有桥接器到效果注册中心
- 保存到全局 `_registered_bridges` 字典
- 输出日志统计信息

**幂等性**: 第二次调用会直接返回缓存的结果，不会重复注册

**配置访问**: 使用 `config.items_config.get("by_id", {})` 而非 `.items()` 避免遍历索引

---

### 3.3 查询和统计函数

#### get_registered_bridges

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:190-197`

获取已注册的桥接器列表。

**签名**:
```python
def get_registered_bridges() -> Dict[str, Type[BattleEffectBridge]]
```

**返回**: 桥接器映射的副本

#### is_bridge_registered

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:200-210`

检查指定桥接器是否已注册。

**签名**:
```python
def is_bridge_registered(effect_id: str) -> bool
```

#### get_bridge_count

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:213-220`

获取已注册的桥接器数量。

**签名**:
```python
def get_bridge_count() -> int
```

#### get_equipment_bridge_mapping

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:223-255`

获取装备到桥接器的映射关系。

**签名**:
```python
def get_equipment_bridge_mapping() -> Dict[str, List[str]]
```

**返回**: `{item_id: [effect_id1, effect_id2, ...]}`

**示例**:
```python
{
    "wedding_dress": ["battle_lifesteal_wedding_dress_0"],
    "vip_blade_zhanlongshan": [
        "battle_lifesteal_vip_blade_zhanlongshan_0",
        "battle_buff_attack_vip_blade_zhanlongshan_1",
        # ... 共6个效果
    ]
}
```

#### get_bridge_statistics

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_register.py:258-280`

获取桥接器统计信息。

**签名**:
```python
def get_bridge_statistics() -> Dict[str, int]
```

**返回**:
```python
{
    "total_bridges": int,  # 总桥接器数（如23）
    "total_equipment": int,  # 有效果的装备数（如12）
    "avg_effects_per_equipment": float  # 平均每装备效果数（如1.92）
}
```

---

### 3.4 TriggerType映射

**位置**: `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py:21-33`

IEffect.TriggerType到BattleEffect.TriggerType的映射表。

**映射规则**:

| IEffect触发类型 | BattleEffect触发类型 | 说明 |
|----------------|---------------------|------|
| ON_ATTACK | ON_ATTACK | 直接映射 |
| ON_DEFENSE | ON_DEFENSE | 直接映射 |
| ON_CRITICAL | ON_CRITICAL | 直接映射 |
| ON_DODGE | ON_DODGE | 直接映射 |
| ON_HIT | ON_HIT | 直接映射 |
| ON_KILL | ON_KILL | 直接映射 |
| ON_ROUND_START | EACH_TURN | 语义映射 |
| ON_ROUND_END | EACH_TURN | 语义映射 |
| ON_BATTLE_START | FIRST_TURN | 语义映射 |
| ON_DAMAGED | ON_ATTACKED | 语义映射 |

**不支持的触发类型**: `ON_USE`, `PASSIVE`, `ON_SKILL` - 返回None触发失败

---

## 4. 使用示例

### 4.1 创建单个桥接器

```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_examples import (
    create_lifesteal_bridge
)

# 创建15%吸血效果
lifesteal = create_lifesteal_bridge(
    lifesteal_percent=0.15,
    effect_id_suffix="嫁衣"
)

# 效果ID: "battle_lifesteal_lifesteal_嫁衣"
print(lifesteal.effect_id)
```

### 4.2 检查和执行效果

```python
from plugins.xiuxian_game.domain.effects.interfaces import EffectContext, TriggerType

# 创建上下文
context = EffectContext(
    player=player,
    trigger_type=TriggerType.ON_HIT,
    session=session,
    metadata={
        "unit_id": "player_123",
        "battle_state": battle_state,
        "damage_dealt": 100
    }
)

# 检查是否触发
if lifesteal.can_trigger(context):
    # 执行效果
    result = await lifesteal.execute(context)

    # 获取BattleEffect对象
    battle_effect = result.extra_data["battle_effect"]

    # 添加到管理器（如果未自动添加）
    if result.extra_data["apply_to_manager"]:
        effect_manager.add_effect("player_123", battle_effect)
```

### 4.3 从装备配置批量创建

```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import (
    create_bridges_from_equipment_config
)

# 装备YAML配置
special_effects = [
    {
        "trigger": "on_hit",
        "chance": 100,
        "effect": "lifesteal",
        "value": 12,
        "duration": 0,
        "description": "吸血12%"
    },
    {
        "trigger": "on_critical",
        "chance": 20,
        "effect": "fear",
        "value": 1,
        "duration": 1,
        "description": "恐惧1回合"
    }
]

# 创建桥接器
bridges = create_bridges_from_equipment_config(
    item_id="wedding_dress",
    item_name="嫁衣",
    special_effects=special_effects
)

# bridges[0].effect_id = "battle_lifesteal_wedding_dress_0"
# bridges[1].effect_id = "battle_fear_wedding_dress_1"
```

### 4.4 启动时批量注册

```python
# 在 plugins/xiuxian_game/__init__.py:58-60
from .domain.effects.adapters import register_all_battle_effect_bridges

# 注册所有战斗效果桥接器
bridges = register_all_battle_effect_bridges()
logger.success(f"[EffectSystem] 成功注册 {len(bridges)} 个战斗效果桥接器")
# 输出: 成功注册 23 个战斗效果桥接器
```

---

## 5. 常见问题

### Q1: 为什么execute()不直接应用效果？

**A**: 桥接模式保留现有架构。实际的效果应用逻辑分散在 `enhanced_engine.py` 的16处不同位置，由BattleEffectManager管理。桥接器仅负责创建BattleEffect对象并返回。

### Q2: 如何处理条件效果（低血量、理智上限）？

**A**: TriggerConfig的 `condition` 字段会被 `_check_condition()` 检查。需要在EffectContext中提供：
- `context.player` 或 `context.metadata["battle_state"]`
- 包含 `current_hp`, `max_hp`, `max_mp` 等属性

### Q3: 环境限制（区域、周主题）如何生效？

**A**: TriggerConfig的 `region_whitelist` 和 `week_theme_whitelist` 会被 `_check_environment()` 检查。需要在EffectContext中提供：
- `context.metadata["region"]` - 当前区域
- `context.metadata["week_theme"]` - 当前周主题

### Q4: 如何添加新的触发类型映射？

**A**: 在 `battle_effect_bridge.py:21-33` 的 `_TRIGGER_TYPE_MAPPING` 字典中添加映射关系：
```python
_TRIGGER_TYPE_MAPPING = {
    # ... 现有映射
    TriggerType.YOUR_NEW_TYPE: BattleTriggerType.CORRESPONDING_TYPE,
}
```

### Q5: 为什么使用config.items_config.get("by_id")而非.items()？

**A**: `config.items_config` 是多索引字典，包含 `by_id`, `by_type`, `by_name` 等索引键。直接 `.items()` 会遍历索引本身，导致重复注册和类型错误。必须使用 `.get("by_id")` 仅遍历实际装备。

**参考**: `battle_effect_register.py:143` 的bug修复

---

## 6. 限制和注意事项

### 不支持的特性

1. **ON_USE触发**: 物品使用触发不适用于战斗效果
2. **PASSIVE触发**: 被动效果需要特殊处理，当前未映射
3. **ON_SKILL触发**: 技能触发当前未映射

### 性能考虑

1. **概率判定**: 每次触发都会执行 `random.random()`，高频触发时注意性能
2. **条件检查**: 需要访问 `battle_state` 或 `player` 对象，确保上下文完整
3. **环境检查**: 字符串比较，白名单不宜过长

### 线程安全

- `_registered_bridges` 全局字典在启动时一次性填充，之后只读，线程安全
- 单个BattleEffectBridge实例是无状态的，可安全复用

---

**相关文档**:
- 架构文档: `/llmdoc/architecture/battle-effect-bridge.md`
- 操作指南: `/llmdoc/guides/how-to-create-battle-effect-bridge.md`
- 设计文档: `plugins/xiuxian_game/domain/effects/adapters/BATTLE_EFFECT_ADAPTER_DESIGN.md`
