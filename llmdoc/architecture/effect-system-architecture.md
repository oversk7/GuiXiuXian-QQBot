# 效果系统架构

## 1. Identity

- **What it is:** 统一的效果管理系统,集成物品效果和战斗效果,提供可扩展的触发机制和效果叠加机制。
- **Purpose:** 管理所有类型的效果(物品效果、战斗buff/debuff、装备特殊效果),提供统一的注册、触发、应用和生命周期管理。

## 2. Core Components

- **`plugins/xiuxian_game/battle/battle_effects.py` (BattleEffectManager + 数据类):** 战斗效果管理器和数据结构。定义TriggerType(触发类型枚举)、EffectType(效果类型枚举)、BattleEffect(效果数据类)、TriggerConfig(触发配置类)。提供效果注册、触发检查、效果添加、回合结算、属性修正计算等功能。
- **`plugins/xiuxian_game/domain/effects/interfaces.py` (IEffect接口):** 统一效果接口。定义IEffect抽象基类、EffectContext(效果执行上下文)、EffectResult(效果执行结果)、TriggerType(统一触发类型枚举)、BaseItemEffect(物品效果基类)、BaseBattleEffect(战斗效果基类)。
- **`plugins/xiuxian_game/domain/effects/registry.py` (EffectRegistry):** 效果注册中心。支持装饰器注册效果类(`@register_effect`),支持按效果ID或触发类型查找,支持效果实例的创建和缓存,单例模式支持。仅服务于物品效果适配器;战斗效果不经过注册中心。

## 3. Execution Flow (LLM Retrieval Map)

### 效果注册流程(启动时)

1. **启动触发:** 在`plugins/xiuxian_game/__init__.py`的启动钩子中调用`register_all_item_effect_adapters`(`domain/effects/adapters/register_all.py`)。
2. **包装旧效果:** 扫描`item_effects.py`中的旧物品效果,为每个效果创建`ItemEffectAdapter`适配器类(`domain/effects/adapters/item_effect_adapter.py`)。
3. **注册到中心:** 通过`@register_effect`装饰器注册到`EffectRegistry`(`registry.py`)。

注: 战斗效果(装备`special_effects`)不在启动时注册——战斗开始时由`EnhancedBattleEngine`直接从装备配置解析(见下)。

### 效果触发流程(战斗时)

1. **解析装备效果:** 战斗初始化时,`EnhancedBattleEngine`读取参战单位装备配置的`special_effects`字段,按升阶解锁数截取后调用`parse_triggers_from_yaml`解析为`TriggerConfig`列表,注册到`BattleEffectManager`(`enhanced_engine.py:373-393`)。
2. **触发检查:** `EnhancedBattleEngine`调用`BattleEffectManager.check_triggers:197-232`:
   - 匹配触发类型(TriggerType)
   - 检查触发条件(低血量、理智上限等)(`battle_effects.py:234-269`)
   - 概率判定(`random.random() * 100 > chance`)
   - 环境条件检查(区域白名单、周主题白名单,支持模糊匹配)
3. **效果创建:** 创建`BattleEffect`实例,包含效果类型、数值、持续时间、叠加层数、来源等信息(`battle_effects.py:218-228`)。
4. **效果应用:** 调用`BattleEffectManager.add_effect:151-170`:
   - 检查是否已存在相同类型+相同来源的效果
   - 尝试叠加层数(`apply_stack`)(`battle_effects.py:93-100`)
   - 无法叠加则刷新持续时间
   - 深拷贝效果对象,避免多个单位共享状态
5. **效果执行:** `EnhancedBattleEngine`根据效果类型执行具体逻辑:
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

## 4. Design Rationale

**战斗效果直连引擎:** 装备`special_effects`由`EnhancedBattleEngine`在战斗时直接解析,不经过`EffectRegistry`——曾存在的`BattleEffectBridge`桥接层(将`TriggerConfig`包装为`IEffect`)注册后从未被消费,已于2026-06-10删除。

**触发类型与效果类型分离:** TriggerType定义何时触发(ON_ATTACK, ON_HIT等),EffectType定义触发后产生什么效果(LIFESTEAL, TRUE_DAMAGE等),一个`TriggerConfig`关联一个`TriggerType`和一个`EffectType`,提供最大的灵活性。

**效果叠加机制:** 相同类型+相同来源的效果尝试叠加层数,无法叠加则刷新持续时间,不同来源可以共存(如多个装备都提供吸血)。

**环境条件支持:** 支持理智上限条件(`ctx_mp_max`)、区域白名单(`ctx_region_in`)、周主题白名单(`ctx_theme_in`),采用模糊匹配(如"医院"可匹配"废弃医院"),实现都市怪谈风味。

**计数型效果:** 支持虎标弹连锁效果(虎标弹→猛虎标弹→刚气-心),通过`trigger_count`和`max_trigger_count`实现计数机制。

**深拷贝隔离:** 效果对象在添加到单位时深拷贝,避免多个单位共享同一个效果实例(如护盾值)。

**装备效果解锁:** 普通装备每+2阶解锁1个效果,VIP定制装备(斩龙闪、镜怨之衣)0阶即解锁全部效果。
