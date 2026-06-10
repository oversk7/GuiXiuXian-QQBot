# 效果系统架构

## 1. Identity

- **What it is:** 游戏的两套效果机制总览——物品/丹药效果(`item_effects.py`装饰器注册表)与战斗效果(`BattleEffectManager`触发/叠加机制),二者各自直连、无统一注册中心。
- **Purpose:** 说明物品效果与战斗buff/debuff、装备特殊效果各自的注册、触发、应用和生命周期管理。

## 2. Core Components

- **`plugins/xiuxian_game/battle/battle_effects.py` (BattleEffectManager + 数据类):** 战斗效果管理器和数据结构。定义TriggerType(触发类型枚举)、EffectType(效果类型枚举)、BattleEffect(效果数据类)、TriggerConfig(触发配置类)。提供效果注册、触发检查、效果添加、回合结算、属性修正计算等功能。
- **`plugins/xiuxian_game/item/item_effects.py` (物品效果注册表):** 物品/丹药效果的唯一实现。按`ItemEffectType`枚举用`@register`装饰器注册处理函数到模块级`_REGISTRY`,入口为`apply_effect(player, item_cfg, quantity, ctx, session)`(`item_effects.py:39-64`),由`item/inventory.py`的使用命令直接调用。
- **`plugins/xiuxian_game/domain/effects/interfaces.py` (数据结构):** 定义EffectResult(效果执行结果,被扫荡/洗髓/宝箱服务用作返回值)、EffectContext、IEffect等接口定义。

## 3. Execution Flow (LLM Retrieval Map)

### 效果注册流程

- **物品效果:** `item_effects.py`模块导入时通过`@register(ItemEffectType.X)`装饰器注册,无启动注册步骤。
- **战斗效果:** 装备`special_effects`不注册——战斗开始时由`EnhancedBattleEngine`直接从装备配置解析(见下)。

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

**两套效果系统各自直连,无注册中心:** 物品效果走`item_effects.py`装饰器注册表,战斗效果由`EnhancedBattleEngine`在战斗时直接解析装备配置。曾存在的"统一效果系统"(EffectRegistry注册中心+ItemEffectAdapter物品适配层+BattleEffectBridge战斗桥接层)只是把调用原样转发回旧实现、无任何独立效果,已于2026-06-10删除。

**触发类型与效果类型分离:** TriggerType定义何时触发(ON_ATTACK, ON_HIT等),EffectType定义触发后产生什么效果(LIFESTEAL, TRUE_DAMAGE等),一个`TriggerConfig`关联一个`TriggerType`和一个`EffectType`,提供最大的灵活性。

**效果叠加机制:** 相同类型+相同来源的效果尝试叠加层数,无法叠加则刷新持续时间,不同来源可以共存(如多个装备都提供吸血)。

**环境条件支持:** 支持理智上限条件(`ctx_mp_max`)、区域白名单(`ctx_region_in`)、周主题白名单(`ctx_theme_in`),采用模糊匹配(如"医院"可匹配"废弃医院"),实现都市怪谈风味。

**计数型效果:** 支持虎标弹连锁效果(虎标弹→猛虎标弹→刚气-心),通过`trigger_count`和`max_trigger_count`实现计数机制。

**深拷贝隔离:** 效果对象在添加到单位时深拷贝,避免多个单位共享同一个效果实例(如护盾值)。

**装备效果解锁:** 普通装备每+2阶解锁1个效果,VIP定制装备(斩龙闪、镜怨之衣)0阶即解锁全部效果。
