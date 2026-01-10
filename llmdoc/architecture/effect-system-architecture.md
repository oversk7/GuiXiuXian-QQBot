# 效果系统架构

## 1. Identity

- **What it is:** 统一的效果管理系统,集成物品效果和战斗效果,提供可扩展的触发机制和效果叠加机制。
- **Purpose:** 管理所有类型的效果(物品效果、战斗buff/debuff、装备特殊效果),提供统一的注册、触发、应用和生命周期管理。

## 2. Core Components

- **`plugins/xiuxian_game/battle/battle_effects.py` (BattleEffectManager + 数据类):** 战斗效果管理器和数据结构。定义TriggerType(触发类型枚举)、EffectType(效果类型枚举)、BattleEffect(效果数据类)、TriggerConfig(触发配置类)。提供效果注册、触发检查、效果添加、回合结算、属性修正计算等功能。
- **`plugins/xiuxian_game/domain/effects/interfaces.py` (IEffect接口):** 统一效果接口。定义IEffect抽象基类、EffectContext(效果执行上下文)、EffectResult(效果执行结果)、TriggerType(统一触发类型枚举)、BaseItemEffect(物品效果基类)、BaseBattleEffect(战斗效果基类)。
- **`plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py` (BattleEffectBridge):** 战斗效果桥接器。采用桥接模式将TriggerConfig包装为IEffect接口,提供触发类型映射、概率判定、条件检查、环境条件检查,返回BattleEffect对象供引擎应用。
- **`plugins/xiuxian_game/domain/effects/registry.py` (EffectRegistry):** 效果注册中心。支持装饰器注册效果类(`@register_effect`),支持按效果ID或触发类型查找,支持效果实例的创建和缓存,单例模式支持。

## 3. Execution Flow (LLM Retrieval Map)

### 效果注册流程(启动时)

1. **启动触发:** 在`plugins/xiuxian_game/__init__.py`的启动钩子中调用。
2. **批量注册:** 调用`register_all_battle_effect_bridges`遍历所有装备配置(`domain/effects/adapters/battle_effect_register.py`)。
3. **解析YAML:** 检查装备配置的`special_effects`字段,解析为`TriggerConfig`列表(`battle_effects.py:parse_triggers_from_yaml`)。
4. **创建桥接器:** 为每个`TriggerConfig`创建`BattleEffectBridge`实例(`battle_effect_bridge.py:84-100`)。
5. **注册到中心:** 调用`EffectRegistry.register`注册桥接器类(`registry.py`)。
6. **建立索引:** 调用`EffectRegistry.index_by_trigger`为效果建立触发类型索引,便于快速查找(`registry.py:114-131`)。

### 效果触发流程(战斗时)

1. **触发检查:** `EnhancedBattleEngine`调用`BattleEffectManager.check_triggers:197-232`:
   - 匹配触发类型(TriggerType)
   - 检查触发条件(低血量、理智上限等)(`battle_effects.py:234-269`)
   - 概率判定(`random.random() * 100 > chance`)
   - 环境条件检查(区域白名单、周主题白名单,支持模糊匹配)
2. **效果创建:** 创建`BattleEffect`实例,包含效果类型、数值、持续时间、叠加层数、来源等信息(`battle_effects.py:218-228`)。
3. **效果应用:** 调用`BattleEffectManager.add_effect:151-170`:
   - 检查是否已存在相同类型+相同来源的效果
   - 尝试叠加层数(`apply_stack`)(`battle_effects.py:93-100`)
   - 无法叠加则刷新持续时间
   - 深拷贝效果对象,避免多个单位共享状态
4. **效果执行:** `EnhancedBattleEngine`根据效果类型执行具体逻辑:
   - 吸血(LIFESTEAL): 恢复HP
   - 真伤(TRUE_DAMAGE): 设置真伤状态
   - 伤害提升(DAMAGE_BOOST): 修正伤害值
   - 恐惧(FEAR): 设置控制状态
   - 反弹(REFLECT): 对攻击者造成伤害
   - 护盾(SHIELD): 抵挡伤害
   - 属性修正(BUFF_*/DEBUFF_*): 修改战斗属性

### 回合结算流程

1. **效果过期检查:** 调用`BattleEffectManager.tick_effects:281-299`:
   - 调用每个效果的`tick()`方法递减持续时间
   - `duration=0`: 立即效果,已在触发时处理
   - `duration>0`: 持续效果,每回合-1
   - `duration=-1`: 永久效果,直到战斗结束
2. **移除过期效果:** 移除`duration`归零的效果,生成日志消息。
3. **连锁效果激活:** 检查计数型效果的触发次数是否耗尽(如虎标弹→猛虎标弹→刚气-心)。

### 桥接器执行流程

1. **触发类型映射:** `BattleEffectBridge.can_trigger:112-161`将IEffect的TriggerType映射到BattleEffect的TriggerType(`battle_effect_bridge.py:22-33`)。
2. **条件检查:** 委托给原有的`TriggerConfig`判断逻辑,包括触发类型匹配、概率判定、条件检查、环境条件检查。
3. **效果执行:** `BattleEffectBridge.execute:163-219`创建`BattleEffect`实例并返回在`EffectResult.extra_data`中,委托给`EnhancedBattleEngine`应用,不直接修改战斗状态。

## 4. Design Rationale

**桥接模式而非适配器:** 保留现有的`BattleEffectManager`优秀设计,提供`IEffect`统一接口,新旧系统可以并存,逐步迁移。桥接器委托触发检查给原有逻辑,返回`BattleEffect`对象供引擎应用。

**触发类型与效果类型分离:** TriggerType定义何时触发(ON_ATTACK, ON_HIT等),EffectType定义触发后产生什么效果(LIFESTEAL, TRUE_DAMAGE等),一个`TriggerConfig`关联一个`TriggerType`和一个`EffectType`,提供最大的灵活性。

**效果叠加机制:** 相同类型+相同来源的效果尝试叠加层数,无法叠加则刷新持续时间,不同来源可以共存(如多个装备都提供吸血)。

**环境条件支持:** 支持理智上限条件(`ctx_mp_max`)、区域白名单(`ctx_region_in`)、周主题白名单(`ctx_theme_in`),采用模糊匹配(如"医院"可匹配"废弃医院"),实现都市怪谈风味。

**计数型效果:** 支持虎标弹连锁效果(虎标弹→猛虎标弹→刚气-心),通过`trigger_count`和`max_trigger_count`实现计数机制。

**深拷贝隔离:** 效果对象在添加到单位时深拷贝,避免多个单位共享同一个效果实例(如护盾值)。

**装备效果解锁:** 普通装备每+2阶解锁1个效果,VIP定制装备(斩龙闪、镜怨之衣)0阶即解锁全部效果。
