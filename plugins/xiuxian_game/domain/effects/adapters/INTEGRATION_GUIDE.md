# 物品效果适配器集成指南

## 概述

本指南介绍如何使用**ItemEffectAdapter**将旧的物品效果系统迁移到新的IEffect接口，实现渐进式重构。

**目标**:
- ✅ 保持向后兼容，不破坏现有代码
- ✅ 统一物品效果和战斗效果接口
- ✅ 支持渐进式迁移，逐步替换旧代码
- ✅ 提供详细的属性变化和状态变化信息

---

## 核心概念

### 1. 旧系统 vs 新系统

| 特性 | 旧系统 (item_effects.py) | 新系统 (IEffect) |
|------|-------------------------|-----------------|
| **接口** | `async def handler(player, cfg, qty, ctx, session) -> (bool, str)` | `async def execute(context: EffectContext) -> EffectResult` |
| **注册** | `@register(ItemEffectType.XXX)` | `@register_effect("effect_id")` |
| **返回值** | `(success: bool, message: str)` | `EffectResult(success, message, attribute_changes, ...)` |
| **扩展性** | ❌ 难以扩展 | ✅ 丰富的元数据 |
| **统一性** | ❌ 与战斗效果分离 | ✅ 统一接口 |

### 2. 适配器模式

```
旧效果函数 → ItemEffectAdapter → IEffect接口
     ↓              ↓                  ↓
  装饰器注册    自动适配          统一使用
```

---

## 使用方法

### 方法1: 自动适配（推荐用于快速迁移）

**适用场景**: 批量迁移现有效果，无需修改旧代码

```python
from domain.effects.adapters import wrap_legacy_item_effect
from domain.effects import register_effect
from item.item_effects import _restore_hp

# 自动包装旧效果
RestoreHPEffect = wrap_legacy_item_effect(
    effect_id="item_restore_hp",
    legacy_handler=_restore_hp,
    description="恢复固定值生命"
)

# 注册到新系统
register_effect("item_restore_hp")(RestoreHPEffect)

# 现在可以使用新接口
registry = get_effect_registry()
effect = registry.create("item_restore_hp")
result = await effect.execute(context)
```

### 方法2: 手动重写（推荐用于新效果）

**适用场景**: 新增效果或需要完全利用新接口特性

```python
from domain.effects import BaseItemEffect, EffectContext, EffectResult, register_effect

@register_effect("item_custom_heal")
class CustomHealEffect(BaseItemEffect):
    """自定义治疗效果"""

    def __init__(self):
        super().__init__("item_custom_heal")

    async def execute(self, context: EffectContext) -> EffectResult:
        player = context.player
        value = context.item_config.effect_params.get("value", 100)

        # 执行逻辑
        old_hp = player.hp
        player.hp = min(player.hp + value, player.max_hp)
        actual_heal = player.hp - old_hp

        # 返回详细结果
        return EffectResult(
            success=True,
            message=f"恢复了{actual_heal}点生命",
            attribute_changes={"hp": actual_heal},  # 详细的属性变化
            status_changes=[],
            extra_data={"old_hp": old_hp, "new_hp": player.hp}
        )
```

### 方法3: 批量自动适配（用于系统迁移）

**适用场景**: 一次性迁移所有旧效果

```python
from domain.effects.adapters.item_effect_adapter import create_adapter_for_all_legacy_effects
from domain.effects import register_effect

# 自动为所有旧效果创建适配器
adapters = create_adapter_for_all_legacy_effects()

# 批量注册（20个效果）
for effect_id, adapter_class in adapters.items():
    register_effect(effect_id)(adapter_class)

print(f"✅ 成功注册 {len(adapters)} 个适配器")
```

---

## 迁移示例

### 示例1: RESTORE_HP（恢复生命值）

**旧代码** (`item_effects.py:78-93`):
```python
@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None):
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"

    effective_max_hp = player.max_hp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_hp = effective_attrs.get("max_hp", effective_max_hp)

    if player.hp >= effective_max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"

    player.hp = min(effective_max_hp, player.hp + value)
    return True, f"❤️ 恢复 {value} 点生命值 (当前 {player.hp}/{effective_max_hp})"
```

**新代码** (`adapters/examples.py:18-85`):
```python
@register_effect("example_restore_hp")
class ExampleRestoreHPEffect(BaseItemEffect):
    def __init__(self):
        super().__init__("example_restore_hp")

    async def execute(self, context: EffectContext) -> EffectResult:
        player = context.player
        value = int(context.item_config.effect_params.get("value", 0)) * context.quantity

        # ... 逻辑检查 ...

        old_hp = player.hp
        player.hp = min(effective_max_hp, player.hp + value)
        actual_restore = player.hp - old_hp

        return EffectResult(
            success=True,
            message=f"❤️ 恢复 {actual_restore} 点生命值",
            attribute_changes={"hp": actual_restore},  # ← 新增：详细的属性变化
            extra_data={"old_hp": old_hp, "new_hp": player.hp}  # ← 新增：额外数据
        )
```

**改进点**:
- ✅ 返回详细的`attribute_changes`，便于后续统计
- ✅ 提供`extra_data`，便于调试和日志
- ✅ 使用`AttributeCalculator v2`获取有效属性

### 示例2: TEMPORARY_BUFF（临时Buff）

**旧代码** (`item_effects.py:269-307`):
```python
@register(ItemEffectType.TEMPORARY_BUFF)
async def _temporary_buff(player, cfg, qty, ctx, session):
    # ... 参数解析 ...
    new_buff = TemporaryBuff(
        player_id=player.id,
        buff_name=buff_name,
        attack_bonus=attack_bonus,
        # ...
    )
    session.add(new_buff)
    return True, f"✨ 获得临时增益【{buff_name}】..."
```

**新代码** (`adapters/examples.py:88-168`):
```python
@register_effect("example_temporary_buff")
class ExampleTemporaryBuffEffect(BaseItemEffect):
    async def execute(self, context: EffectContext) -> EffectResult:
        # ... 创建buff ...
        session.add(new_buff)
        await session.flush()

        # ← 新增：使缓存失效
        from domain.attributes import invalidate_player_buff_cache
        invalidate_player_buff_cache(player.id)

        return EffectResult(
            success=True,
            message=f"✨ 获得临时增益【{buff_name}】",
            attribute_changes=bonuses,  # ← 新增：详细的属性加成
            status_changes=[f"添加临时buff: {buff_name}"],  # ← 新增：状态变化
            extra_data={"buff_id": new_buff.id, "duration_minutes": duration}
        )
```

**改进点**:
- ✅ 自动使buff缓存失效，确保属性计算正确
- ✅ 返回详细的加成信息
- ✅ 记录buff ID，便于后续操作

### 示例3: GAIN_EXP（获得经验）

**旧代码** (`item_effects.py:336-360`):
```python
@register(ItemEffectType.GAIN_EXP)
async def _gain_exp(player, cfg, qty, ctx, session):
    value = int(cfg.effect_params.get("value", 0)) * qty
    # ... 检查等级上限 ...
    player.exp += value
    # ... 升级逻辑 ...
    return True, msg
```

**新代码** (`adapters/examples.py:171-260`):
```python
@register_effect("example_gain_exp")
class ExampleGainExpEffect(BaseItemEffect):
    async def execute(self, context: EffectContext) -> EffectResult:
        # ... 添加经验和升级逻辑 ...

        return EffectResult(
            success=True,
            message=main_message,
            attribute_changes={
                "exp": exp_value,
                "level": level_up_count,
                "attribute_points": level_up_count * 3
            },  # ← 新增：详细的属性变化
            status_changes=[f"升级{level_up_count}次"] if level_up_count > 0 else [],
            extra_data={
                "old_level": old_level,
                "new_level": player.level,
                "level_up_count": level_up_count
            }  # ← 新增：升级详情
        )
```

**改进点**:
- ✅ 详细记录经验、等级、属性点变化
- ✅ 提供升级次数信息
- ✅ 便于后续实现成就系统

---

## 集成步骤

### 阶段1: 测试适配器（已完成✅）

1. 创建`ItemEffectAdapter`基类
2. 实现`wrap_legacy_item_effect`工厂函数
3. 创建3个示例适配器

### 阶段2: 批量迁移（进行中🚧）

**Step 1**: 自动创建适配器
```python
# 在启动时执行
from domain.effects.adapters.item_effect_adapter import create_adapter_for_all_legacy_effects
from domain.effects import register_effect

adapters = create_adapter_for_all_legacy_effects()
for effect_id, adapter_class in adapters.items():
    register_effect(effect_id)(adapter_class)
```

**Step 2**: 修改物品使用入口
```python
# 旧代码 (item/use_item.py)
from item.item_effects import apply_effect
success, message = await apply_effect(player, item_cfg, quantity, "world", session)

# 新代码（渐进式）
from domain.effects import get_effect_registry

registry = get_effect_registry()
effect_id = f"item_{item_cfg.effect_type.name.lower()}"

if registry.has(effect_id):
    # 使用新系统
    effect = registry.create(effect_id)
    context = EffectContext(player=player, session=session, ...)
    result = await effect.execute(context)
    success, message = result.success, result.message
else:
    # 回退到旧系统
    success, message = await apply_effect(player, item_cfg, quantity, "world", session)
```

### 阶段3: 逐步替换（待定⏳）

1. 选择高频效果（如RESTORE_HP、RESTORE_MP）
2. 用新代码完全重写
3. 添加单元测试
4. 性能对比测试
5. 逐步替换所有效果

---

## 优势对比

### 新系统的优势

| 特性 | 旧系统 | 新系统 |
|------|--------|--------|
| **返回信息** | 仅success和message | 详细的属性变化、状态变化、额外数据 |
| **扩展性** | 难以扩展 | 易于添加新字段 |
| **统一性** | 与战斗效果分离 | 统一接口，便于管理 |
| **调试** | 信息不足 | 丰富的日志和元数据 |
| **缓存管理** | 手动处理 | 自动失效buff缓存 |
| **属性计算** | 旧版本 | AttributeCalculator v2 |

### 性能影响

- ✅ **无性能损失**: 适配器仅是简单的函数调用包装
- ✅ **缓存优化**: 自动管理buff缓存失效
- ✅ **统一会话**: 支持UnitOfWork模式

---

## 常见问题

### Q1: 旧代码会被删除吗？
**A**: 不会。适配器方案保持向后兼容，旧代码可以继续工作。迁移是渐进式的。

### Q2: 如何处理循环依赖？
**A**: 适配器可以延迟导入依赖，避免循环依赖。参考`examples.py`中的导入方式。

### Q3: 是否必须全部迁移？
**A**: 不必须。可以优先迁移高频效果，低频效果保持原样。

### Q4: 如何测试适配器？
**A**: 使用独立测试脚本（见下节），确保新旧系统行为一致。

---

## 测试方法

### 创建测试脚本

```python
# tests/test_item_effect_adapters.py
import asyncio
from domain.effects import get_effect_registry, EffectContext, TriggerType

async def test_restore_hp_adapter():
    """测试恢复生命值适配器"""
    registry = get_effect_registry()

    # 创建mock对象
    class MockPlayer:
        def __init__(self):
            self.id = "test_player"
            self.hp = 50
            self.max_hp = 100

    class MockItemConfig:
        def __init__(self):
            self.item_id = "test_item"
            self.effect_params = {"value": 30}

    player = MockPlayer()
    item_cfg = MockItemConfig()

    # 创建上下文
    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    # 执行效果
    effect = registry.create("item_restore_hp")
    result = await effect.execute(context)

    # 验证结果
    assert result.success is True
    assert player.hp == 80
    assert result.attribute_changes["hp"] == 30
    print("✅ 测试通过：恢复生命值适配器工作正常")

if __name__ == "__main__":
    asyncio.run(test_restore_hp_adapter())
```

---

## 下一步

1. **运行测试**: 执行测试脚本，验证适配器工作正常
2. **批量注册**: 在启动代码中批量注册所有适配器
3. **监控日志**: 观察调试日志，确保适配器正确执行
4. **逐步迁移**: 优先迁移RESTORE_HP、RESTORE_MP等高频效果

---

**文档位置**: `domain/effects/adapters/INTEGRATION_GUIDE.md`
**创建时间**: 2025-11-27
**维护者**: Claude Code + 开发团队
**相关文件**:
- `item_effect_adapter.py` - 适配器基类
- `examples.py` - 示例适配器
- `../USAGE_EXAMPLES.md` - IEffect接口使用指南
