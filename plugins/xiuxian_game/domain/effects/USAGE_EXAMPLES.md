# 效果系统使用指南

## 概述

本模块提供了统一的效果接口（IEffect），用于统一物品效果和战斗效果的实现。

## 核心概念

### 1. IEffect接口

所有效果都实现`IEffect`接口：

```python
class IEffect(ABC):
    @property
    @abstractmethod
    def effect_id(self) -> str:
        """效果唯一标识"""
        pass

    @abstractmethod
    def can_trigger(self, context: EffectContext) -> bool:
        """判断是否可以触发"""
        pass

    @abstractmethod
    async def execute(self, context: EffectContext) -> EffectResult:
        """执行效果"""
        pass

    def tick(self) -> bool:
        """回合结算（持续性效果）"""
        return True
```

### 2. 基类

- **BaseItemEffect**: 物品效果基类（一次性效果）
- **BaseBattleEffect**: 战斗效果基类（持续性效果，支持叠加）

### 3. 数据结构

- **EffectContext**: 效果执行上下文（包含player、session、trigger_type等）
- **EffectResult**: 效果执行结果（包含success、message、attribute_changes等）
- **TriggerType**: 触发类型枚举（ON_USE、ON_ATTACK、ON_DEFENSE等）

## 使用示例

### 示例1：创建简单的物品效果

```python
from domain.effects import BaseItemEffect, EffectContext, EffectResult, register_effect

@register_effect("item_restore_hp")
class RestoreHPEffect(BaseItemEffect):
    """恢复生命值效果"""

    def __init__(self):
        super().__init__("item_restore_hp")

    async def execute(self, context: EffectContext) -> EffectResult:
        # 获取恢复量
        restore_amount = context.item_config.params.get("value", 100)

        # 恢复生命值
        old_hp = context.player.hp
        context.player.hp = min(context.player.hp + restore_amount, context.player.max_hp)
        actual_restore = context.player.hp - old_hp

        return EffectResult(
            success=True,
            message=f"恢复了{actual_restore}点生命值",
            attribute_changes={"hp": actual_restore}
        )
```

### 示例2：创建战斗效果

```python
from domain.effects import BaseBattleEffect, TriggerType, EffectContext, EffectResult, register_effect

@register_effect("battle_lifesteal")
class LifestealEffect(BaseBattleEffect):
    """吸血效果：攻击时恢复造成伤害的X%生命值"""

    def __init__(self, lifesteal_percent: float = 0.2, duration: int = 3):
        super().__init__(
            effect_id="battle_lifesteal",
            trigger_type=TriggerType.ON_ATTACK,
            duration=duration,  # 持续3回合
            max_stacks=1
        )
        self.lifesteal_percent = lifesteal_percent

    async def execute(self, context: EffectContext) -> EffectResult:
        # 计算吸血量
        damage = context.damage_dealt or 0
        heal_amount = int(damage * self.lifesteal_percent)

        # 恢复生命值
        context.attacker.hp = min(
            context.attacker.hp + heal_amount,
            context.attacker.max_hp
        )

        return EffectResult(
            success=True,
            message=f"吸血{heal_amount}点生命值",
            attribute_changes={"hp": heal_amount}
        )
```

### 示例3：使用效果注册中心

```python
from domain.effects import get_effect_registry, EffectContext, TriggerType

# 获取全局注册中心
registry = get_effect_registry()

# 创建效果实例
restore_hp_effect = registry.create("item_restore_hp")

# 准备上下文
context = EffectContext(
    player=player,
    session=session,
    trigger_type=TriggerType.ON_USE,
    item_config=item_config,
    quantity=1
)

# 检查是否可以触发
if restore_hp_effect.can_trigger(context):
    # 执行效果
    result = await restore_hp_effect.execute(context)
    print(result.message)
```

### 示例4：批量执行效果

```python
from domain.effects import get_effect_registry, EffectContext, TriggerType

async def trigger_effects(player, trigger_type: TriggerType, session, **kwargs):
    """触发指定类型的所有效果"""

    registry = get_effect_registry()

    # 获取所有匹配触发类型的效果ID
    effect_ids = registry.get_by_trigger(trigger_type)

    # 准备上下文
    context = EffectContext(
        player=player,
        session=session,
        trigger_type=trigger_type,
        **kwargs
    )

    results = []
    for effect_id in effect_ids:
        effect = registry.create(effect_id)
        if effect.can_trigger(context):
            result = await effect.execute(context)
            results.append(result)

    return results
```

## 迁移指南

### 从旧的物品效果系统迁移

**旧代码**:
```python
# item_effects.py
@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player, cfg, qty, ctx, session):
    restore_amount = cfg.params.get("value", 100)
    player.hp = min(player.hp + restore_amount, player.max_hp)
    return True, f"恢复了{restore_amount}点生命值"
```

**新代码**:
```python
# effects/item_effects.py
@register_effect("item_restore_hp")
class RestoreHPEffect(BaseItemEffect):
    async def execute(self, context: EffectContext) -> EffectResult:
        restore_amount = context.item_config.params.get("value", 100)
        context.player.hp = min(context.player.hp + restore_amount, context.player.max_hp)
        return EffectResult(
            success=True,
            message=f"恢复了{restore_amount}点生命值"
        )
```

### 从旧的战斗效果系统迁移

**旧代码**:
```python
# battle_effects.py
effect = BattleEffect(
    effect_type=EffectType.LIFESTEAL,
    trigger_type=TriggerType.ON_ATTACK,
    value=20,  # 20%吸血
    duration=3
)
```

**新代码**:
```python
# effects/battle_effects.py
@register_effect("battle_lifesteal")
class LifestealEffect(BaseBattleEffect):
    def __init__(self, lifesteal_percent: float = 0.2, duration: int = 3):
        super().__init__(
            effect_id="battle_lifesteal",
            trigger_type=TriggerType.ON_ATTACK,
            duration=duration
        )
        self.lifesteal_percent = lifesteal_percent
```

## 优势

1. **统一接口**: 物品效果和战斗效果使用相同的接口
2. **类型安全**: 使用数据类和类型提示
3. **易于扩展**: 通过继承基类快速实现新效果
4. **灵活触发**: 支持多种触发类型和条件判断
5. **持续性管理**: BaseBattleEffect自动管理持续时间和叠加
6. **向后兼容**: 可以逐步迁移旧代码

## 下一步

1. **第2阶段**: 创建物品效果适配器，将旧的item_effects.py适配到新接口
2. **第3阶段**: 创建战斗效果适配器，将旧的battle_effects.py适配到新接口
3. **第4阶段**: 系统集成，统一触发机制和效果管理

---

**文档位置**: `domain/effects/USAGE_EXAMPLES.md`
**创建时间**: 2025-11-26
**维护者**: Claude Code + 开发团队
