# Domain Layer - 领域逻辑

**子目录:** events/, effects/, attributes/, repositories/

## OVERVIEW

DDD领域层。纯业务逻辑，无基础设施依赖。EventBus发布订阅，效果系统适配器模式，属性计算策略模式。

## WHERE TO LOOK

| 子系统 | 目录 | 职责 |
|--------|------|------|
| Events | `events/` | EventBus, 20+领域事件 |
| Effects | `effects/` | IEffect接口, 触发器, 适配器 |
| Attributes | `attributes/` | IAttributeSource, 计算器 |
| Repositories | `repositories/` | Repository接口定义 |

## EVENTS

```python
# 发布事件
from .events import EventBus, PlayerLevelUpEvent

await EventBus.publish(PlayerLevelUpEvent(player_uid, old_level, new_level))

# 订阅事件
@EventBus.on(PlayerLevelUpEvent)
async def on_level_up(event: PlayerLevelUpEvent):
    # 处理逻辑
```

## EFFECTS

```python
# 效果类型
class EffectType(Enum):
    DAMAGE = "damage"
    HEAL = "heal"
    BUFF = "buff"
    # 20+种类型

# 触发类型
class TriggerType(Enum):
    ON_ATTACK = "on_attack"
    ON_HIT = "on_hit"
    ON_TURN_START = "on_turn_start"
    # 10+种类型

# 适配器注册
@register_item_effect_adapter("weapon_damage")
class WeaponDamageAdapter(IEffect):
    async def apply(self, context: EffectContext) -> EffectResult:
        ...
```

## ATTRIBUTES

```python
# 属性来源接口
class IAttributeSource(Protocol):
    def get_attributes(self, player: Player) -> dict[str, int]: ...
    def get_priority(self) -> int: ...

# 计算器
calculator = AttributeCalculator()
calculator.register_source(EquipmentSource())  # 装备
calculator.register_source(BuffSource())       # 临时buff
calculator.register_source(PillSource())       # 丹药

attrs = await calculator.get_effective_attributes_v2(player)
```

## ANTI-PATTERNS

- **禁止import infrastructure** → 保持领域纯净
- **禁止直接数据库操作** → 用Repository接口
