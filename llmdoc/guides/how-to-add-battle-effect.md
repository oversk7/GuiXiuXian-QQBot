# 如何添加新战斗效果

本文档指导如何在战斗系统中添加新的效果类型。战斗效果系统高度可扩展,支持通过YAML配置添加新效果,无需修改核心代码。

## 1. 添加新效果类型(EffectType)

如果现有的效果类型无法满足需求,需要添加新的效果类型:

### 步骤1: 在枚举中注册

在`plugins/xiuxian_game/battle/battle_effects.py:29-76`的`EffectType`枚举中添加新类型:

```python
class EffectType(str, Enum):
    # ... 现有效果
    NEW_EFFECT = "new_effect"  # 新效果类型的描述
```

### 步骤2: 在引擎中处理效果

在`plugins/xiuxian_game/battle/enhanced_engine.py`的`_execute_enhanced_attack`方法中添加处理逻辑。找到类似效果的处理位置,添加新逻辑:

```python
# 处理新效果类型(示例: 伤害反弹的变体)
for effect in attack_effects:
    if effect.effect_type == EffectType.NEW_EFFECT:
        # 实现效果逻辑
        result["total_damage"] += int(damage * effect.value / 100)
        result["messages"].append(f"✨ 新效果触发！特殊效果+{effect.value}%")
```

参考位置:
- 伤害类效果: `enhanced_engine.py:679-713`
- 控制类效果: `enhanced_engine.py:715-726`
- 属性修正: `enhanced_engine.py:518-538`

### 步骤3: 在装备YAML中配置

在装备配置文件中添加新效果:

```yaml
special_effects:
  - trigger: "on_attack"
    chance: 30  # 30%触发概率
    effect: "new_effect"
    value: 20
    duration: 3  # 持续3回合(可选,0表示立即效果)
    description: "新效果: 攻击时触发,持续3回合"
```

## 2. 添加新触发类型(TriggerType)

如果需要在新的时机触发效果,需要添加新的触发类型:

### 步骤1: 在枚举中注册

在`plugins/xiuxian_game/battle/battle_effects.py:13-27`的`TriggerType`枚举中添加新类型:

```python
class TriggerType(str, Enum):
    # ... 现有触发类型
    NEW_TRIGGER = "new_trigger"  # 新触发类型的描述
```

### 步骤2: 在引擎中触发

在`EnhancedBattleEngine`的适当位置调用`check_triggers`:

```python
# 在适当的时机触发新类型效果
new_effects = self.effect_manager.check_triggers(
    attacker_id, TriggerType.NEW_TRIGGER, {
        "source": "触发来源",
        "current_hp": attacker_hp,
        "max_hp": attacker_max_hp,
        # 其他上下文信息
    }
)
for effect in new_effects:
    self.effect_manager.add_effect(attacker_id, effect)
```

参考位置:
- 攻击时触发: `enhanced_engine.py:670-677`
- 防御时触发: `enhanced_engine.py:735-743`
- 回合开始触发: `enhanced_engine.py:387-395`

## 3. 使用现有效果类型配置新装备

大多数情况下,可以通过组合现有的效果类型实现新装备,无需修改代码:

### 示例1: 吸血装备

```yaml
special_effects:
  - trigger: "on_hit"
    chance: 100
    effect: "lifesteal"
    value: 15
    description: "吸血: 命中时恢复造成伤害15%的HP"
```

### 示例2: 真伤状态装备

```yaml
special_effects:
  - trigger: "on_attack"
    chance: 50
    effect: "true_damage"
    value: 0
    duration: 3
    description: "真伤状态: 攻击时50%概率触发,持续3回合"
```

### 示例3: 低血量触发效果

```yaml
special_effects:
  - trigger: "low_hp"
    chance: 100
    effect: "buff_attack"
    value: 50
    duration: 5
    threshold: 30
    description: "绝境: HP≤30%时攻击力+50%,持续5回合"
```

### 示例4: 环境条件效果

```yaml
special_effects:
  - trigger: "on_attack"
    chance: 100
    effect: "damage_boost"
    value: 30
    ctx_mp_max: 50  # 仅当前理智≤50%时触发
    ctx_region_in: ["医院", "地铁"]  # 仅在这些区域触发
    description: "都市怪谈: 理智低下时,在特定区域伤害+30%"
```

## 4. 配置参数说明

### TriggerConfig参数

- `trigger`: 触发类型(`on_attack`, `on_hit`, `low_hp`等)
- `chance`: 触发概率(0-100)
- `effect`: 效果类型(`lifesteal`, `true_damage`, `buff_attack`等)
- `value`: 效果数值(百分比或固定值)
- `duration`: 持续回合数(0=立即效果,-1=永久)
- `max_stacks`: 最大叠加层数(默认1)
- `threshold`: 触发阈值(如低血量百分比)
- `is_percentage`: 是否为百分比值(默认True)
- `max_trigger_count`: 最大触发次数(0=无限制)
- `next_effect`: 失效后触发的下一个效果类型(用于连锁效果)
- `ctx_mp_max`: 理智上限条件(当前理智%≤阈值时触发)
- `ctx_region_in`: 区域白名单(列表,模糊匹配)
- `ctx_theme_in`: 周主题白名单(列表,模糊匹配)

### 触发类型列表

- `on_attack`: 攻击时
- `on_defense`/`on_attacked`: 被攻击时
- `on_hit`: 命中时
- `on_critical`: 暴击时
- `on_dodge`: 闪避时
- `on_kill`: 击杀时
- `first_turn`: 战斗首回合
- `each_turn`: 每回合开始
- `low_hp`: 低血量时
- `passive`: 被动效果(始终生效)

### 效果类型列表

- `lifesteal`: 吸血
- `true_damage`: 真伤状态
- `damage_boost`: 伤害提升
- `execute`: 处决
- `fear`: 恐惧
- `buff_attack`/`buff_defense`/`buff_critical`/`buff_dodge`/`buff_accuracy`: 属性增益
- `debuff_attack`/`debuff_defense`: 属性削弱
- `regen`: 每回合回血
- `heal`: 立即回血
- `shield`: 护盾
- `reflect`: 反弹伤害
- `invincible`: 无敌

## 5. 验证和测试

### 验证配置生效

1. 重启机器人使装备配置生效(战斗效果在战斗开始时由`enhanced_engine.py`直接从装备配置解析,无独立注册步骤)。

2. 使用`【我的装备】`命令查看装备效果是否正确显示。

3. 进入战斗(切磋或打怪),观察效果是否按预期触发。

### 测试效果触发

- 使用`【切磋 <UID>】`命令进行无损PvP测试
- 使用随机种子实现可重现的战斗,便于调试
- 检查战斗日志中的效果触发消息

### 常见问题排查

- **效果未触发:** 检查触发类型是否匹配、概率是否合理、条件是否满足
- **效果未生效:** 检查效果类型是否在引擎中处理、数值是否合理
- **效果未叠加:** 检查max_stacks配置、source是否相同
- **环境条件失效:** 检查区域名称、周主题名称是否匹配(支持模糊匹配)
