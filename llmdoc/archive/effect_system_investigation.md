# 诡修仙效果系统调查报告

**调查日期**: 2025-11-26
**调查范围**: 装备效果、战斗效果、Buff效果、技能效果的实现与管理

---

## Code Sections (证据清单)

### 1. 装备效果系统

- `plugins/xiuxian_game/item/item_effects.py` (模块级注册表): 装饰器注册系统,使用全局字典`_REGISTRY`存储效果处理器
  - `register()` (装饰器函数): 将效果处理函数注册到`ItemEffectType`枚举类型
  - `apply_effect()` (效果应用函数): 根据物品配置调用对应的效果处理器
  - 具体效果实现: `_restore_hp`, `_restore_mp`, `_buff`, `_temporary_buff`, `_gain_exp`, `_reforge_attr`, `_reset_attr`, `_sweep_dungeon`, `_world_boss_chest`, `_divine_punishment`, `_monthly_card_box`等
  - `update_elixir_usage()` (丹药使用记录): 记录玩家丹药使用量用于耐药性和重置属性计算

- `plugins/xiuxian_game/models/inventory.py` (物品模型):
  - `ItemEffectType` (枚举类): 定义所有物品效果类型,包括`RESTORE_HP`, `BUFF`, `TEMPORARY_BUFF`, `GAIN_EXP`, `REFORGE_ATTR`等45+种效果
  - `ItemConfig` (配置类): 存储物品配置,包含`effect_type`和`effect_params`字段
  - `ItemInstance.apply_attr_bonus()` (装备属性加成): 计算装备提供的固定值和百分比属性加成,支持升阶倍率和宝石镶嵌

### 2. 战斗效果系统

- `plugins/xiuxian_game/battle/battle_effects.py` (战斗效果核心模块):
  - `TriggerType` (枚举类): 定义触发时机,包括`ON_ATTACK`, `ON_DEFENSE`, `ON_CRITICAL`, `ON_DODGE`, `ON_KILL`, `FIRST_TURN`, `EACH_TURN`, `LOW_HP`, `PASSIVE`等
  - `EffectType` (枚举类): 定义效果类型,包括`LIFESTEAL`, `TRUE_DAMAGE`, `DAMAGE_BOOST`, `FEAR`, `BUFF_ATTACK`, `DEBUFF_DEFENSE`, `REGEN`, `SHIELD`, `REFLECT`, `INVINCIBLE`, `EXECUTE`, `TIGER_BULLET`, `IGNORE_SPECIAL`, `GAIN_MP`, `IGNORE_DEFENSE`等75+种效果
  - `BattleEffect` (数据类): 表示单个战斗效果,包含效果类型、数值、持续时间、叠加层数、触发计数器等字段
  - `TriggerConfig` (配置类): 定义触发器配置,包含触发类型、概率、效果、阈值、环境条件(理智值、区域、时间、主题等)
  - `BattleEffectManager` (管理器类): 管理战斗单位的效果和触发器
    - `add_effect()`: 添加效果到单位,支持叠加和刷新
    - `check_triggers()`: 检查并触发效果,含环境条件判断
    - `tick_effects()`: 回合结算效果
    - `calculate_attribute_modifier()`: 计算属性修正值
  - `parse_triggers_from_yaml()`: 从YAML配置解析触发器,支持环境条件

- `plugins/xiuxian_game/battle/integration_helper.py` (战斗集成助手):
  - `BattleIntegrationHelper.enhanced_player_vs_player_battle()`: 增强版PVP战斗,集成装备特殊效果
  - `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2()`: 增强版PVE战斗,支持处决、反击、吸血等效果

### 3. 临时Buff系统

- `plugins/xiuxian_game/models/temporary_buff.py` (临时Buff模型):
  - `TemporaryBuff` (数据库模型): 存储临时buff状态,包含buff_id、buff_name、attribute_bonuses(属性加成JSON)、expires_at(过期时间)、source_item_id(来源物品)等字段
  - `TemporaryBuff.create_buff()`: 创建或刷新临时buff
  - `TemporaryBuff.get_active_buffs()`: 获取玩家激活的buff
  - `TemporaryBuff.cleanup_expired_buffs()`: 清理过期buff
  - `TemporaryBuff.get_total_attribute_bonuses()`: 获取所有buff的总属性加成

- `plugins/xiuxian_game/item/buff_commands.py` (Buff命令模块):
  - `buff_status_cmd` (查看增益状态指令): 调用`get_player_buff_status()`显示临时buff状态
  - `clear_buffs_cmd` (清理增益指令): 手动清理过期buff
  - `attribute_breakdown_cmd` (属性分解指令): 显示基础、装备、丹药、VIP装备、临时buff的属性加成分解

- `plugins/xiuxian_game/item/item_effects.py`:
  - `get_player_buff_status()`: 获取玩家临时buff状态信息,包含buff列表和总属性加成
  - `_temporary_buff()`: 创建有时间限制的临时buff效果
  - `_temporary_buff_percent()`: 创建临时百分比属性加成buff

### 4. 装备属性系统

- `plugins/xiuxian_game/item/equipment_commands.py` (装备命令模块):
  - `recalc_equipment_attributes()`: 重新计算玩家装备属性加成,支持`mp_from_hp`等全局被动
  - `_apply_mp_from_hp_effects()`: 将生命值转化为理智值的全局被动效果
  - `wear_equipment` (穿戴装备指令): 卸下所有装备→基于基础属性重新计算→穿戴所有装备
  - `unwear_equipment` (卸下装备指令): 移除属性加成并重新计算剩余装备

- `plugins/xiuxian_game/models/inventory.py`:
  - `ItemInstance.extra_attrs["_persist_bonus"]`: 存储装备持久化的属性加成,用于卸下时准确回退

### 5. 丹药系统

- `plugins/xiuxian_game/models/elixir_usage.py`:
  - `ElixirUsageLog` (数据库模型): 记录玩家丹药使用量,用于计算永久属性加成和重置属性时的保留

- `plugins/xiuxian_game/item/item_effects.py`:
  - `_buff()`: 永久固定值属性加成
  - `_buff_percent()`: 永久百分比属性加成
  - `_temporary_buff()`: 临时固定值属性加成
  - `_temporary_buff_percent()`: 临时百分比属性加成
  - `_reset_attr()`: 重置已分配属性点,保留装备、丹药、VIP装备加成

---

## Report (调查结果)

### result

#### 1. 效果系统的类型

诡修仙项目实现了**四种主要效果系统**,每种使用不同的实现方式:

**A. 装备效果 (item_effects.py) - 装饰器注册模式**
- **实现方式**: 使用`@register(ItemEffectType)`装饰器将效果处理函数注册到全局字典`_REGISTRY`
- **触发时机**: 玩家使用物品时调用`apply_effect()`
- **效果类型**: 45+种,包括恢复HP/MP、属性增益(永久/临时、固定值/百分比)、经验获取、洗髓、复活、扫荡、宝箱开启等
- **存储方式**:
  - 永久属性: 直接修改`Player`模型字段,使用`ElixirUsageLog`记录丹药使用量
  - 临时属性: 创建`TemporaryBuff`数据库记录,带过期时间

**B. 战斗效果 (battle_effects.py) - 管理器模式**
- **实现方式**: 使用`BattleEffectManager`类管理效果,`TriggerConfig`和`BattleEffect`数据类定义配置
- **触发时机**: 12种触发类型,包括攻击时、防御时、暴击时、闪避时、击杀时、死亡时、首回合、每回合、低血量、被攻击时、命中时、被动
- **效果类型**: 75+种,包括吸血、真伤、伤害提升、恐惧、属性增益/削弱、回复、护盾、反弹、无敌、处决、连锁效果等
- **存储方式**: 战斗期间存储在`BattleEffectManager.active_effects`字典中,战斗结束后清除

**C. Buff效果 (temporary_buff.py) - 数据库模型**
- **实现方式**: 使用`TemporaryBuff`数据库模型存储,包含buff_id、属性加成JSON、过期时间等字段
- **触发时机**: 使用临时buff类型的物品时创建,每次查询属性时自动合并所有激活buff的加成
- **效果类型**: 支持所有玩家属性的临时加成,包括max_hp、max_mp、attack、defense、agility、luck、critical_rate等15+种属性
- **存储方式**: 数据库持久化,按过期时间自动清理

**D. 技能效果 - 未独立实现**
- **当前状态**: 项目中未发现独立的技能系统,技能效果可能通过以下方式实现:
  1. 作为战斗效果的一种(EffectType中有`skill_crit_rate`等技能相关属性)
  2. 通过装备特殊效果(special_effects)实现
  3. 尚未完整实现

#### 2. 效果注册和管理

**装饰器注册模式 (item_effects.py)**:
```python
_REGISTRY: Dict[ItemEffectType, EffectHandler] = {}

def register(effect_type: ItemEffectType):
    def decorator(func: EffectHandler):
        _REGISTRY[effect_type] = func
        return func
    return decorator

@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player, cfg, qty, ctx, session):
    # 实现恢复HP逻辑
```
- **优点**: 简洁、易扩展、代码分离清晰
- **缺点**: 只支持静态注册,无法动态修改效果
- **使用场景**: 物品效果,每种效果类型对应一个处理函数

**管理器模式 (battle_effects.py)**:
```python
class BattleEffectManager:
    def __init__(self):
        self.active_effects: Dict[str, List[BattleEffect]] = {}
        self.trigger_configs: Dict[str, List[TriggerConfig]] = {}

    def add_effect(self, unit_id, effect):
        # 添加效果,支持叠加

    def check_triggers(self, unit_id, trigger_type, context):
        # 检查并触发效果
```
- **优点**: 灵活、支持运行时修改、支持复杂触发条件、支持效果叠加
- **缺点**: 实现复杂、需要手动管理生命周期
- **使用场景**: 战斗系统,需要动态管理多个单位的效果

**差异总结**:
| 特性 | 装饰器注册 | 管理器模式 |
|------|-----------|-----------|
| 复杂度 | 低 | 高 |
| 灵活性 | 低 | 高 |
| 效果叠加 | 不支持 | 支持 |
| 动态修改 | 不支持 | 支持 |
| 生命周期 | 永久/数据库 | 战斗期间 |
| 触发条件 | 简单(使用时) | 复杂(12种触发类型+环境条件) |

#### 3. 效果触发机制

**装备效果触发**:
- **触发时机**: 玩家使用物品时(`use_item`命令)
- **触发流程**: `use_item` → `apply_effect()` → 查找`_REGISTRY[effect_type]` → 执行效果处理函数
- **条件判断**:
  - 物品可用性检查(是否拥有、数量是否足够)
  - 效果生效条件(如血量是否已满、是否死亡、等级是否足够)
  - 每日使用限制(`daily_limit`)
- **执行流程**:
  1. 扣除物品
  2. 执行效果
  3. 如果效果失败(返回`success=False`),返还物品

**战斗效果触发**:
- **触发时机定义**:
  - `ON_ATTACK`: 攻击时触发
  - `ON_DEFENSE`/`ON_ATTACKED`: 被攻击时触发
  - `ON_CRITICAL`: 暴击时触发
  - `ON_DODGE`: 闪避成功时触发
  - `ON_KILL`: 击杀敌人时触发
  - `ON_DEATH`: 死亡时触发
  - `FIRST_TURN`: 战斗首回合触发
  - `EACH_TURN`: 每回合开始时触发
  - `LOW_HP`: 低血量时触发(≤30%)
  - `ON_HIT`: 命中时触发
  - `PASSIVE`: 被动效果(始终生效)

- **触发条件判断**:
  1. **触发类型匹配**: `trigger_config.trigger == trigger_type`
  2. **概率判定**: `random() * 100 <= trigger_config.chance`
  3. **阈值判定**: 如低血量阈值`hp_percentage <= threshold`
  4. **环境条件判定** (可选):
     - `ctx_mp_max`: 理智值上限(当前理智% ≤ 阈值)
     - `ctx_region_in`: 区域白名单(支持模糊匹配)
     - `ctx_theme_in`: 周主题白名单(支持模糊匹配)

- **执行流程**:
  1. `BattleEffectManager.check_triggers()` 检查所有注册的触发器
  2. 创建`BattleEffect`实例并添加到`active_effects`
  3. 在战斗流程中应用效果(如伤害计算、属性修正、回血等)
  4. 回合结束时`tick_effects()`减少持续时间,移除过期效果

**Buff效果触发**:
- **触发时机**: 使用临时buff类型的物品时(`ItemEffectType.TEMPORARY_BUFF`或`TEMPORARY_BUFF_PERCENT`)
- **触发流程**:
  1. 调用`_temporary_buff()`或`_temporary_buff_percent()`
  2. 创建或刷新`TemporaryBuff`数据库记录
  3. 查询玩家属性时自动合并所有激活buff的加成
- **条件判断**:
  - 是否已存在相同buff_id的激活buff(存在则延长时间并更新加成)
  - 过期时间检查(每次查询时自动清理过期buff)

#### 4. 效果组合

**多效果组合方式**:

**装备效果组合**:
- **不支持直接组合**: 每次使用物品只能触发一个效果类型
- **间接组合**:
  - 使用多个物品叠加永久属性(如多次使用`BUFF`类型丹药)
  - 使用多个临时buff物品叠加临时属性(不同buff_id可共存)
  - 装备+丹药+临时buff三层叠加

**战斗效果组合**:
- **支持多效果叠加**:
  - 同一单位可同时拥有多个不同类型的效果
  - 相同类型效果支持叠加(受`max_stacks`限制)
  - 装备可配置多个特殊效果(如斩龙闪同时拥有`IGNORE_DEFENSE`和`MP_FROM_HP`效果)

**属性加成组合**:
- **加成来源**: 基础属性 + 装备加成 + 丹药加成 + VIP装备加成 + 临时buff加成
- **计算顺序**:
  1. 基础属性(玩家等级、分配的属性点、丹药永久加成)
  2. 装备固定值加成
  3. 装备百分比加成(基于基础属性)
  4. 宝石镶嵌加成
  5. 临时buff加成(查询时实时计算)

**优先级和执行顺序**:

**战斗效果优先级**:
- **触发顺序**: 按触发类型的自然顺序执行
  1. `FIRST_TURN`: 战斗开始时
  2. `EACH_TURN`: 每回合开始时
  3. `ON_ATTACK`/`ON_CRITICAL`/`ON_HIT`: 攻击时
  4. `ON_DEFENSE`/`ON_ATTACKED`: 防御时
  5. `ON_DODGE`: 闪避时
  6. `ON_KILL`: 击杀时
  7. `ON_DEATH`: 死亡时
- **同类效果**: 按注册顺序执行(装备穿戴顺序)

**属性计算优先级**:
- **固定值优先**: 先加固定值,再计算百分比
- **基础属性优先**: 百分比加成基于基础属性(不含装备)
- **装备特殊效果**:
  - `mp_from_hp`在所有装备基础属性计算完成后执行
  - 排除自身装备对HP的加成,避免自我放大

**冲突解决机制**:

**效果叠加冲突**:
- **同类效果**:
  - 如果`max_stacks > 1`,叠加层数+1,数值累加
  - 如果已达最大层数,刷新持续时间
- **相互抵消**: 无明确的相互抵消机制(如增益和减益)
- **覆盖规则**:
  - 装备效果: 同名装备不可重复穿戴
  - 临时buff: 相同buff_id会延长时间并更新加成

**属性加成冲突**:
- **无冲突**: 所有加成来源直接累加,无上限限制
- **装备卸下**: 通过`_persist_bonus`准确回退属性加成
- **重置属性**: 重置时保留装备、丹药、VIP装备加成,仅退还分配的属性点

#### 5. 可扩展性评估

**添加新效果的难度**:

**装备效果(简单)**:
1. 在`ItemEffectType`枚举中添加新类型
2. 在`item_effects.py`中编写带`@register`装饰器的处理函数
3. 在`items.yaml`中配置物品,指定`effect_type`和`effect_params`
- **难度**: ⭐(非常简单)
- **代码量**: 10-50行

**战斗效果(中等)**:
1. 在`EffectType`枚举中添加新效果类型
2. 在`TriggerType`中添加新触发类型(如需要)
3. 在装备配置的`special_effects`中添加触发器配置
4. 在战斗引擎中实现效果逻辑(可能需要修改伤害计算、属性计算等)
- **难度**: ⭐⭐⭐(中等,需要理解战斗流程)
- **代码量**: 20-100行

**临时Buff效果(简单)**:
1. 复用现有`TEMPORARY_BUFF`或`TEMPORARY_BUFF_PERCENT`类型
2. 在`items.yaml`中配置物品,指定属性加成和持续时间
- **难度**: ⭐(非常简单,无需编码)
- **代码量**: 0行(仅配置)

**代码重复程度**:

**装备效果**:
- **重复度**: 低
- **原因**: 每种效果类型有独立的处理函数,共享部分逻辑(如属性加成、HP/MP恢复)通过辅助函数复用
- **示例**: `_restore_hp`和`_restore_mp`结构相似但独立实现

**战斗效果**:
- **重复度**: 中等
- **原因**: 效果触发和应用逻辑分散在多个战斗函数中,部分逻辑重复(如暴击判定、连击判定)
- **示例**: PVP和PVE战斗中都有相似的伤害计算和效果触发逻辑

**属性计算**:
- **重复度**: 低
- **原因**: 统一使用`apply_attr_bonus()`和`recalc_equipment_attributes()`计算,避免重复

**维护复杂度**:

**装备效果**: ⭐⭐(简单)
- **优点**: 装饰器模式清晰,每种效果独立,易于定位和修改
- **缺点**: 效果类型枚举和处理函数需同步维护

**战斗效果**: ⭐⭐⭐⭐(复杂)
- **优点**: 灵活、功能强大、支持复杂触发条件
- **缺点**:
  - 效果逻辑分散在多个文件(battle_effects.py、enhanced_engine.py、integration_helper.py)
  - 需要深入理解战斗流程才能正确添加或修改效果
  - 效果之间可能存在隐式依赖(如处决依赖于伤害计算)

**临时Buff**: ⭐⭐(简单)
- **优点**: 数据库模型清晰,自动清理过期buff,属性加成自动合并
- **缺点**: 需要确保所有查询属性的地方都调用`get_total_attribute_bonuses()`

**属性系统**: ⭐⭐⭐(中等)
- **优点**: 持久化加成(`_persist_bonus`)机制避免属性不一致
- **缺点**:
  - 穿脱装备时需要完整重算所有装备(性能开销)
  - `mp_from_hp`等特殊效果需要特殊处理,增加复杂度

### conclusions

1. **诡修仙项目使用了三种不同的效果系统架构**:
   - 装备效果采用**装饰器注册模式**,简单高效,适合静态效果
   - 战斗效果采用**管理器模式**,灵活强大,适合动态效果
   - 临时Buff采用**数据库模型**,持久化存储,支持自动过期

2. **效果系统支持丰富的触发机制**:
   - 装备效果: 物品使用时触发(45+种效果类型)
   - 战斗效果: 12种触发时机,支持概率、阈值、环境条件判断(75+种效果类型)
   - 临时Buff: 时间驱动,自动过期清理(15+种属性)

3. **属性加成系统采用多层叠加机制**:
   - 基础属性 + 装备加成 + 丹药加成 + VIP装备加成 + 临时buff加成
   - 使用`_persist_bonus`持久化装备加成,确保卸下时准确回退
   - 支持固定值和百分比两种加成方式

4. **效果组合方面**:
   - 战斗效果支持多效果叠加(受`max_stacks`限制)
   - 属性加成直接累加,无上限限制
   - 缺少明确的效果冲突解决机制(如增益和减益相互抵消)

5. **可扩展性评估**:
   - 装备效果: ⭐(非常简单) - 添加新效果仅需10-50行代码
   - 战斗效果: ⭐⭐⭐(中等) - 需要理解战斗流程,20-100行代码
   - 临时Buff: ⭐(非常简单) - 仅需配置,无需编码
   - 维护复杂度: 战斗效果最高(⭐⭐⭐⭐),装备效果和临时Buff较低(⭐⭐)

6. **代码质量**:
   - 代码重复度: 装备效果和属性计算重复度低,战斗效果中等
   - 维护性: 装备效果和临时Buff易维护,战斗效果需要更多文档和测试
   - 扩展性: 所有系统都支持添加新效果,但战斗效果添加难度较高

7. **特殊机制**:
   - 丹药耐药性: 通过`ElixirUsageLog`记录使用量,但当前代码中未见实际的耐药性计算
   - 装备升阶: 每阶提升20%属性
   - 宝石镶嵌: 支持多孔位镶嵌,自动计算属性加成
   - 环境条件触发: 战斗效果支持基于理智值、区域、主题的条件触发

8. **未完整实现的功能**:
   - 技能系统: 未发现独立的技能效果系统
   - 效果冲突解决: 缺少增益和减益相互抵消机制
   - 耐药性系统: 有记录机制但未见实际计算逻辑

### relations

**代码模块关系**:

```
item_effects.py (装备效果注册)
    ↓ 依赖
models/inventory.py (物品配置和枚举)
    ↑ 被依赖
item/equipment_commands.py (装备属性计算)
    ↓ 依赖
models/temporary_buff.py (临时Buff数据库模型)
    ↑ 被查询
item/buff_commands.py (Buff查询命令)

battle/battle_effects.py (战斗效果核心)
    ↓ 被使用
battle/enhanced_engine.py (战斗引擎)
    ↓ 被调用
battle/integration_helper.py (战斗集成)
    ↑ 调用
world/dungeon_battle.py (诡域战斗)
world/attack_command.py (PVP战斗)
```

**效果流程关系**:

**装备效果流程**:
```
use_item命令
  → apply_effect() (item_effects.py)
    → _REGISTRY[effect_type]() (效果处理函数)
      → 修改Player属性 / 创建TemporaryBuff
        → ElixirUsageLog.update (丹药使用记录)
```

**战斗效果流程**:
```
start_battle() (enhanced_engine.py)
  → _register_equipment_triggers() (注册装备触发器)
    → parse_triggers_from_yaml() (解析YAML配置)
  → execute_turn() (执行回合)
    → check_triggers() (检查触发器)
      → add_effect() (添加效果)
    → _execute_enhanced_attack() (执行攻击)
      → 应用效果 (吸血、真伤、伤害提升等)
    → tick_effects() (回合结算)
      → 移除过期效果
```

**属性计算流程**:
```
穿戴装备
  → recalc_equipment_attributes() (equipment_commands.py)
    → 卸下所有装备 (移除_persist_bonus)
    → 获取基础属性
    → apply_attr_bonus() (inventory.py) (逐个装备计算)
      → 固定值加成 + 百分比加成 + 宝石加成
      → 保存_persist_bonus
    → _apply_mp_from_hp_effects() (特殊效果)
    → 修正HP/MP上限
```

**临时Buff流程**:
```
使用临时buff物品
  → _temporary_buff() (item_effects.py)
    → TemporaryBuff.create_buff() (temporary_buff.py)
      → cleanup_expired_buffs() (清理过期)
      → 检查是否已存在 (延长时间/创建新buff)

查询属性
  → get_effective_attributes() (player.py)
    → get_total_attribute_bonuses() (temporary_buff.py)
      → 合并所有激活buff的加成
```

**数据流关系**:

```
items.yaml (物品配置)
  → ItemConfig (配置类)
    → ItemInstance (物品实例)
      → Player.item_instances (玩家背包)
        → 装备: extra_attrs["_persist_bonus"] (持久化加成)
        → 丹药: ElixirUsageLog (使用记录)

special_effects (装备特殊效果YAML配置)
  → TriggerConfig (触发器配置)
    → BattleEffectManager.trigger_configs (注册的触发器)
      → BattleEffect (效果实例)
        → BattleEffectManager.active_effects (激活的效果)

临时buff物品使用
  → TemporaryBuff (数据库记录)
    → attribute_bonuses (JSON字段)
      → Player属性查询时合并
```

**关键依赖**:

1. **item_effects.py → models/inventory.py**: 依赖`ItemEffectType`枚举和`ItemConfig`类
2. **battle/enhanced_engine.py → battle/battle_effects.py**: 依赖`BattleEffectManager`和`TriggerConfig`
3. **equipment_commands.py → models/inventory.py**: 依赖`ItemInstance.apply_attr_bonus()`
4. **buff_commands.py → models/temporary_buff.py**: 依赖`TemporaryBuff`查询方法
5. **所有效果 → models/player.py**: 最终都修改`Player`模型的属性

**循环依赖风险**:

- **低风险**: 代码结构清晰,大部分依赖是单向的
- **潜在风险**: `Player`模型、`ItemInstance`模型、战斗引擎之间存在相互引用,但通过运行时导入避免了循环依赖

---

## 调查总结

诡修仙项目的效果系统采用了**分层架构**,针对不同场景选择了合适的实现模式:

- **装备效果**: 装饰器注册模式 - 简洁高效
- **战斗效果**: 管理器模式 - 灵活强大
- **临时Buff**: 数据库模型 - 持久化存储

整体设计**可扩展性良好**,添加新效果的难度低至中等,但战斗效果系统的**维护复杂度较高**,建议:

1. **增加战斗效果文档**: 详细说明每种效果的触发时机、计算方式、依赖关系
2. **统一效果触发逻辑**: 减少PVP和PVE战斗中的重复代码
3. **实现效果冲突解决机制**: 支持增益和减益相互抵消
4. **完善技能系统**: 建立独立的技能效果系统
5. **实现耐药性计算**: 当前有记录机制但缺少实际计算逻辑
