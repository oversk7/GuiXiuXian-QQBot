# Domain Layer - 领域逻辑

**子目录:** events/, effects/, attributes/, repositories/

## OVERVIEW

DDD领域层。纯业务逻辑，无基础设施依赖。EventBus发布订阅，效果接口定义，属性读写收口。

## WHERE TO LOOK

| 子系统 | 目录 | 职责 |
|--------|------|------|
| Events | `events/` | EventBus, 20+领域事件 |
| Effects | `effects/` | IEffect/EffectContext/EffectResult 接口定义 |
| Attributes | `attributes/` | 永久属性写入收口, 宠物属性来源 |
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

`effects/` 只保留接口定义（IEffect, BaseItemEffect, BaseBattleEffect, EffectContext,
EffectResult, TriggerType）。物品效果实现在 `item/item_effects.py`，
战斗效果实现在 `battle/battle_effects.py`，各自直连，无适配层。

## ATTRIBUTES

```python
# 永久属性变更唯一写入口（改字段+记账+装备重算+hp/mp收口）
from .attributes.permanent_change import apply_permanent_change

await apply_permanent_change(session, player, {"attack": 5}, ledger_item_id=item_id)

# 读取两档:
# 全量真源（含装备/丹药/临时buff/宠物）
attrs = await player.get_effective_attributes(session)
# 战斗档（真源+词缀+ATTRIBUTE_CAPS上限）
from ..battle.battle_attributes import BattleAttributeCalculator
battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player, session)
```

## ANTI-PATTERNS

- **禁止import infrastructure** → 保持领域纯净
- **禁止直接数据库操作** → 用Repository接口
- **禁止绕过 apply_permanent_change 永久改属性** → 账实漂移且轮回时被吞
