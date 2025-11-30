# BattleEffectAdapter 设计文档

**创建日期**: 2025-11-27
**目标**: 将现有的BattleEffect系统适配到IEffect接口，实现战斗效果的统一管理

---

## 1. 核心挑战分析

### 1.1 ItemEffect vs BattleEffect 的本质区别

| 特性 | ItemEffect | BattleEffect | 适配难度 |
|------|-----------|-------------|---------|
| **执行模式** | 一次性函数调用 | 有状态数据对象 | ⭐⭐⭐⭐ |
| **生命周期** | 瞬时（调用即生效） | 持续性（跨多回合） | ⭐⭐⭐⭐⭐ |
| **触发方式** | 显式调用`apply_effect()` | 被动检查`check_triggers()` | ⭐⭐⭐⭐ |
| **效果应用** | 效果函数内部实现 | 分散在战斗引擎各处 | ⭐⭐⭐⭐⭐ |
| **参数传递** | ItemConfig字典 | TriggerConfig结构化对象 | ⭐⭐ |

**结论**: 战斗效果不能像物品效果那样简单包装，需要**桥接模式**而非适配器模式。

### 1.2 现有架构的优秀之处（不应破坏）

✅ **保留的设计**:
- `BattleEffectManager` 管理器模式 - 集中管理所有战斗单位的效果
- `BattleEffect` 数据类 - 清晰的状态表示（持续时间、堆叠、值）
- `TriggerConfig` 触发配置 - 灵活的触发条件（概率、环境、条件）
- `check_triggers()` 触发检查 - 16处调用覆盖战斗全流程

❌ **不要重写的部分**:
- 效果应用逻辑（已分散在enhanced_engine.py的各个位置）
- 效果管理器（BattleEffectManager工作良好）
- 触发流程（已优化且稳定）

---

## 2. 适配策略：桥接模式

### 2.1 设计思路

**核心原则**: **保留现有系统，提供IEffect接口的访问层**

```
原有系统（保留）:
  TriggerConfig → BattleEffectManager.check_triggers() → BattleEffect →
  EnhancedBattleEngine应用效果

新增桥接层:
  IEffect接口 → BattleEffectBridge → 委托给现有的TriggerConfig/BattleEffect
```

### 2.2 BattleEffectBridge 职责

1. **包装TriggerConfig**: 将触发配置暴露为IEffect接口
2. **委托触发检查**: `can_trigger()` 委托给 `BattleEffectManager.check_triggers()`
3. **延迟效果应用**: `execute()` 不直接应用效果，而是返回需要应用的BattleEffect列表
4. **保持兼容性**: 新旧系统可并存

---

## 3. 接口设计

### 3.1 IEffect 接口扩展

为支持战斗效果，需要扩展EffectContext：

```python
@dataclass
class EffectContext:
    """效果执行上下文（扩展以支持战斗效果）"""
    # 通用字段
    player: Any
    session: Optional[Any] = None
    trigger_type: TriggerType = TriggerType.ON_USE

    # 物品效果专用
    item_config: Optional[Any] = None
    quantity: Optional[int] = None

    # 战斗效果专用（新增）
    battle_state: Optional[Any] = None      # 战斗状态对象
    unit_id: Optional[str] = None           # 战斗单位ID
    target_unit: Optional[Any] = None       # 目标单位
    damage_dealt: Optional[int] = None      # 已造成的伤害
    is_critical: bool = False               # 是否暴击
    is_dodge: bool = False                  # 是否闪避

    # 环境条件（新增）
    current_turn: int = 0                   # 当前回合数
    region: Optional[str] = None            # 当前区域
    week_theme: Optional[str] = None        # 当前周主题

    # 扩展字段
    context_type: str = "world"
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.2 BattleEffectBridge 基类

```python
class BattleEffectBridge(IEffect):
    """
    战斗效果桥接器 - 将TriggerConfig桥接到IEffect接口

    职责：
    1. 包装现有的TriggerConfig
    2. 委托触发检查给BattleEffectManager
    3. 返回需要应用的BattleEffect（而非直接应用）
    """

    def __init__(
        self,
        effect_id: str,
        trigger_config: TriggerConfig,
        effect_manager: Optional[BattleEffectManager] = None
    ):
        self._effect_id = effect_id
        self._trigger_config = trigger_config
        self._effect_manager = effect_manager  # 可选注入

    @property
    def effect_id(self) -> str:
        return self._effect_id

    @property
    def trigger_config(self) -> TriggerConfig:
        """暴露原始TriggerConfig供兼容性使用"""
        return self._trigger_config

    def can_trigger(self, context: EffectContext) -> bool:
        """
        判断是否可以触发

        委托给原有的TriggerConfig判断逻辑
        """
        # 1. 检查触发类型匹配
        if self._trigger_config.trigger != context.trigger_type:
            return False

        # 2. 检查概率
        if self._trigger_config.chance < 1.0:
            if random.random() > self._trigger_config.chance:
                return False

        # 3. 检查条件
        if self._trigger_config.condition:
            if not self._check_condition(context):
                return False

        # 4. 检查环境条件
        if not self._check_environment(context):
            return False

        return True

    async def execute(self, context: EffectContext) -> EffectResult:
        """
        执行效果 - 返回应该添加的BattleEffect

        注意：此方法不直接修改战斗状态，而是返回效果描述
        实际的效果应用由EnhancedBattleEngine完成
        """
        # 创建BattleEffect实例
        effect = BattleEffect(
            effect_type=self._trigger_config.effect,
            value=self._trigger_config.value,
            duration=self._trigger_config.duration,
            max_stacks=self._trigger_config.max_stacks,
            stackable=self._trigger_config.stackable,
            source_unit_id=context.unit_id,
            description=self._trigger_config.description
        )

        # 返回效果结果（包含需要添加的效果）
        return EffectResult(
            success=True,
            message=f"触发效果: {self._trigger_config.description}",
            metadata={
                "battle_effect": effect,  # 返回BattleEffect对象
                "apply_to_manager": True  # 标记需要添加到管理器
            }
        )

    def _check_condition(self, context: EffectContext) -> bool:
        """检查条件（如低血量）"""
        condition = self._trigger_config.condition

        # 低血量检查
        if condition.get("low_hp"):
            threshold = condition.get("threshold", 0.3)
            if context.battle_state:
                unit = context.battle_state.get_unit(context.unit_id)
                if unit and unit.current_hp > unit.max_hp * threshold:
                    return False

        # 理智上限检查
        if condition.get("mp_cap"):
            required_mp = condition.get("min_mp", 0)
            if context.battle_state:
                unit = context.battle_state.get_unit(context.unit_id)
                if unit and unit.max_mp < required_mp:
                    return False

        return True

    def _check_environment(self, context: EffectContext) -> bool:
        """检查环境条件（区域白名单、周主题白名单）"""
        # 区域白名单
        region_whitelist = self._trigger_config.region_whitelist
        if region_whitelist and context.region not in region_whitelist:
            return False

        # 周主题白名单
        week_theme_whitelist = self._trigger_config.week_theme_whitelist
        if week_theme_whitelist and context.week_theme not in week_theme_whitelist:
            return False

        return True
```

### 3.3 使用示例

```python
# 示例：包装一个吸血效果

# 1. 创建TriggerConfig（来自装备配置）
lifesteal_config = TriggerConfig(
    trigger=TriggerType.ON_HIT,
    effect=EffectType.LIFESTEAL,
    value=0.15,  # 15%吸血
    chance=1.0,
    duration=0,  # 瞬时效果
    description="吸血 15%"
)

# 2. 创建桥接器
lifesteal_bridge = BattleEffectBridge(
    effect_id="battle_lifesteal",
    trigger_config=lifesteal_config
)

# 3. 注册到效果注册中心（可选）
effect_registry.register_class("battle_lifesteal", BattleEffectBridge)

# 4. 在战斗中使用（兼容新旧接口）
## 旧方式（保留）
battle_effects = effect_manager.check_triggers(
    unit_id="player",
    trigger_type=TriggerType.ON_HIT,
    context={}
)

## 新方式（通过IEffect接口）
context = EffectContext(
    player=player,
    trigger_type=TriggerType.ON_HIT,
    battle_state=battle_state,
    unit_id="player",
    damage_dealt=50
)

if lifesteal_bridge.can_trigger(context):
    result = await lifesteal_bridge.execute(context)
    battle_effect = result.metadata["battle_effect"]
    # 添加到管理器
    effect_manager.add_effect("player", battle_effect)
```

---

## 4. 批量注册策略

### 4.1 从装备配置自动创建桥接器

```python
def create_bridge_for_trigger_config(
    trigger_config: TriggerConfig,
    base_effect_id: str
) -> BattleEffectBridge:
    """
    为单个TriggerConfig创建桥接器

    Args:
        trigger_config: 触发配置对象
        base_effect_id: 基础效果ID（如"斩龙闪_吸血"）

    Returns:
        BattleEffectBridge: 桥接器实例
    """
    effect_id = f"battle_{trigger_config.effect.value}_{base_effect_id}"
    return BattleEffectBridge(
        effect_id=effect_id,
        trigger_config=trigger_config
    )


def create_bridges_from_equipment(
    equipment_config: ItemConfig
) -> List[BattleEffectBridge]:
    """
    从装备配置创建所有效果的桥接器

    Args:
        equipment_config: 装备配置对象（包含special_effects字段）

    Returns:
        List[BattleEffectBridge]: 桥接器列表
    """
    if not equipment_config.special_effects:
        return []

    # 解析YAML配置
    from plugins.xiuxian_game.battle.battle_effects import parse_triggers_from_yaml

    trigger_configs = parse_triggers_from_yaml(
        equipment_config.special_effects
    )

    # 为每个触发器创建桥接器
    bridges = []
    for i, trigger_config in enumerate(trigger_configs):
        effect_id = f"{equipment_config.item_id}_{i}"
        bridge = create_bridge_for_trigger_config(trigger_config, effect_id)
        bridges.append(bridge)

    return bridges
```

### 4.2 批量注册到效果注册中心

```python
def register_all_battle_effect_bridges() -> Dict[str, Type[BattleEffectBridge]]:
    """
    批量注册所有战斗效果桥接器

    策略：
    1. 遍历所有装备配置
    2. 提取special_effects
    3. 创建桥接器
    4. 注册到效果注册中心

    Returns:
        Dict[effect_id, BattleEffectBridge类]: 已注册的桥接器映射
    """
    from plugins.xiuxian_game.config import config
    from ..registry import get_effect_registry

    registry = get_effect_registry()
    registered_bridges = {}

    # 遍历所有装备
    for item_id, item_config in config.items_config.items():
        if not item_config.special_effects:
            continue

        # 创建桥接器
        bridges = create_bridges_from_equipment(item_config)

        # 注册
        for bridge in bridges:
            # 注册为单例（同一装备的效果可复用）
            registry.register_class(
                bridge.effect_id,
                BattleEffectBridge,
                singleton=True
            )
            registered_bridges[bridge.effect_id] = type(bridge)

            logger.debug(
                f"[BattleEffectBridge] 注册桥接器: {bridge.effect_id} "
                f"(装备: {item_config.name}, 效果: {bridge.trigger_config.effect.value})"
            )

    return registered_bridges
```

---

## 5. 集成策略

### 5.1 向后兼容的集成路径

**阶段1**: 并行运行（当前阶段）
- 保留现有BattleEffectManager
- 新增BattleEffectBridge桥接层
- 两套系统同时工作，互不干扰

**阶段2**: 选择性迁移
- Feature Flag控制是否使用桥接器
- 逐步将效果检查迁移到IEffect接口
- 保留旧接口作为fallback

**阶段3**: 完全统一
- 所有效果通过IEffect接口访问
- BattleEffectManager作为基础设施保留
- 删除直接的TriggerConfig调用

### 5.2 集成到EnhancedBattleEngine

```python
# enhanced_engine.py 修改示例

class EnhancedBattleEngine:
    def __init__(self):
        self.effect_manager = BattleEffectManager()

        # 新增：效果注册中心引用
        from plugins.xiuxian_game.domain.effects.registry import get_effect_registry
        self.effect_registry = get_effect_registry()

    def _register_equipment_triggers(self, unit_id: str, equipment: List[ItemInstance]):
        """注册装备触发器（兼容新旧系统）"""
        # 旧方式（保留）
        for equip in equipment:
            item_config = config.items_config.get(equip.item_id)
            if not item_config or not item_config.special_effects:
                continue

            triggers = parse_triggers_from_yaml(item_config.special_effects)
            self.effect_manager.register_triggers(unit_id, triggers)

        # 新方式（可选启用）
        if USE_NEW_EFFECT_SYSTEM:
            for equip in equipment:
                item_config = config.items_config.get(equip.item_id)
                bridges = create_bridges_from_equipment(item_config)

                # 将桥接器添加到某个列表，供后续触发检查使用
                # （具体实现待定，取决于如何替换check_triggers调用）
```

---

## 6. 不采用完全适配的原因

### 6.1 为什么不像ItemEffectAdapter那样完全包装？

**ItemEffectAdapter成功的原因**:
- ✅ 物品效果是**无状态的函数**，可以直接包装
- ✅ 执行逻辑集中在一个函数（`apply_effect()`），易于拦截
- ✅ 生命周期简单（调用即结束），无需管理状态

**BattleEffect不适合完全包装的原因**:
- ❌ 战斗效果是**有状态的对象**（持续时间、堆叠数、value）
- ❌ 执行逻辑分散在EnhancedBattleEngine的16处不同位置
- ❌ 生命周期复杂（跨多回合、条件移除、tick更新）
- ❌ 与战斗流程深度耦合（无法独立执行）

### 6.2 桥接模式的优势

1. **保留优秀设计**: BattleEffectManager的管理器模式非常适合战斗场景
2. **最小改动**: 不需要重写战斗引擎的效果应用逻辑
3. **灵活扩展**: 新效果可以选择使用IEffect接口或传统方式
4. **向后兼容**: 旧代码无需修改即可继续工作
5. **渐进迁移**: 可以逐步迁移到新接口，降低风险

---

## 7. 实施计划

### 7.1 第一步：实现BattleEffectBridge基类
- [x] 设计文档（本文档）
- [ ] 实现BattleEffectBridge类
- [ ] 单元测试（模拟触发检查）

### 7.2 第二步：创建示例桥接器
- [ ] 吸血效果桥接器
- [ ] Buff效果桥接器（攻击力提升）
- [ ] 护盾效果桥接器

### 7.3 第三步：批量注册功能
- [ ] `create_bridge_for_trigger_config()`
- [ ] `create_bridges_from_equipment()`
- [ ] `register_all_battle_effect_bridges()`

### 7.4 第四步：集成验证
- [ ] Feature Flag支持
- [ ] 集成到EnhancedBattleEngine
- [ ] 运行时测试

---

## 8. 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| **破坏现有战斗逻辑** | 低 | 高 | 使用桥接模式，不修改现有代码 |
| **性能下降** | 低 | 中 | 桥接层很薄，几乎无额外开销 |
| **接口不匹配** | 中 | 中 | EffectContext扩展字段支持战斗场景 |
| **迁移成本高** | 高 | 低 | 不强制迁移，新旧系统并存 |

---

## 9. 总结

**核心决策**: 使用**桥接模式**而非适配器模式

**设计原则**:
1. ✅ 保留BattleEffectManager和BattleEffect（已验证优秀的设计）
2. ✅ 提供IEffect接口访问层（统一接口）
3. ✅ 向后兼容（新旧系统并存）
4. ✅ 渐进迁移（Feature Flag控制）

**预期收益**:
- 效果系统接口统一
- 保持现有战斗系统稳定性
- 支持未来的效果扩展
- 降低重构风险

---

**文档版本**: v1.0
**最后更新**: 2025-11-27
**下一步**: 实现BattleEffectBridge基类
