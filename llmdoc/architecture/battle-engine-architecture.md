# 战斗引擎架构

## 1. Identity

- **What it is:** 回合制战斗引擎的核心执行层,负责战斗流程控制、伤害计算和胜负判定。
- **Purpose:** 提供完整的战斗逻辑实现,包括回合执行、攻击判定、效果触发和结果计算。

## 2. Core Components

- **`plugins/xiuxian_game/battle/enhanced_engine.py` (EnhancedBattleEngine):** 核心战斗引擎类。控制战斗初始化、回合执行、伤害计算流程。支持装备触发器注册、首回合效果应用、灵影体质系统、斩龙闪20%必中伤害拆分。
- **`plugins/xiuxian_game/battle/battle_attributes.py` (BattleAttributeCalculator):** 战斗属性计算器。计算有效战斗属性(暴击率、连击率、反击率、闪避率、命中率、穿透率等),应用属性上限,提供命中判定、暴击判定、连击判定、反击判定、先手判定等功能。
- **`plugins/xiuxian_game/utils.py` (apply_defense_mitigation):** 防御减伤计算函数。综合计算数值减伤与比例减伤,公式为`final_damage = max(1, base_damage - min(defense, base_damage * defense / (defense + 100)))`。
- **`plugins/xiuxian_game/battle/integration_helper.py` (BattleIntegrationHelper):** 战斗集成辅助类。提供PvP和PvE战斗的高层接口,处理装备获取、属性缓存、回合循环和胜负判定。

## 3. Execution Flow (LLM Retrieval Map)

### 战斗初始化流程

1. **装备获取:** 通过`BattleIntegrationHelper.enhanced_player_vs_player_battle:88-102`查询双方装备。
2. **引擎创建:** 创建`EnhancedBattleEngine`实例(`enhanced_engine.py:19-41`),初始化随机数生成器、效果管理器、回合计数器。
3. **属性缓存:** 将包含临时buff的有效属性缓存到player对象(`integration_helper.py:119-138`)。
4. **战斗开始:** 调用`EnhancedBattleEngine.start_battle:44-282`:
   - 清除旧效果(`enhanced_engine.py:55-62`)
   - 注册装备触发器,按升阶等级解锁效果(`enhanced_engine.py:283-330`)
   - 应用被动效果(PASSIVE,始终生效)(`enhanced_engine.py:69-85`)
   - 触发首回合效果(FIRST_TURN)(`enhanced_engine.py:88-100`)
   - 应用灵影体质系统(HP_FROM_MP/MP_FROM_HP)(`enhanced_engine.py:112-153`)

### 回合执行流程

1. **回合开始:** 调用`EnhancedBattleEngine.execute_turn`:
   - 回合计数+1
   - 处理回合开始效果(EACH_TURN,回血buff)
   - 检查控制效果(恐惧等)
2. **攻击执行:** 调用`EnhancedBattleEngine._execute_enhanced_attack`:
   - 计算基础攻击力(含攻击修正)(`enhanced_engine.py:447-469`)
   - 检查真伤状态(TRUE_DAMAGE)
   - 提取无视类效果(IGNORE_SPECIAL/IGNORE_DEFENSE)
   - 执行基础攻击判定(`_process_pvp_attack`或`_process_monster_attack`)(`enhanced_engine.py:471-646`)
   - 应用虎标弹连锁效果(计数型伤害加成)
   - 检查防御方无敌状态(INVINCIBLE)
   - 恐惧状态增伤(+20%)
   - 检查护盾(SHIELD)
   - 触发攻击时效果(ON_ATTACK, ON_HIT, ON_CRITICAL): 吸血、真伤状态、恐惧、伤害提升
   - 触发防御时效果(ON_DEFENSE, ON_ATTACKED): 反弹伤害、反射死亡、护盾、回血
   - 执行连击(递归调用,85%攻击力)
   - 返回攻击结果
3. **回合结算:** 调用`BattleEffectManager.tick_effects`移除过期效果。

### PvP攻击判定流程

1. **命中判定:** 调用`BattleAttributeCalculator.calculate_hit_chance:155-169`,计算`命中率-闪避率`,限制在0.1-1.0之间。
2. **穿透判定:** 根据穿透率削减防御力,`effective_defense = defense * (1 - penetration_rate / 100)`。
3. **暴击判定:** 调用`BattleAttributeCalculator.roll_critical_hit:172-185`,暴击倍数`1.5 + critical_power * 0.1`。
4. **连击判定:** 调用`BattleAttributeCalculator.roll_combo_attack:188-218`,随机2-4次攻击,伤害为85%基础攻击力。
5. **防御减伤:** 调用`apply_defense_mitigation`计算最终伤害。
6. **斩龙闪20%必中拆分:** 20%部分绕过命中判定(必中),80%部分常规判定,最终伤害=20%部分+80%部分。

### 胜负判定流程

1. **血量检查:** 一方HP≤0则战斗结束。
2. **回合限制:** PvP最多30回合,超时则平局。
3. **击杀效果:** 调用`trigger_on_kill`处理击杀效果(噬灵者、刃之魔灵等)。

## 4. Design Rationale

**回合制设计:** 采用回合制而非即时战斗,便于实现复杂的效果触发逻辑和策略深度。支持先手判定(基于敏捷)、连击机制、反击机制。

**伤害计算分阶段:** 伤害计算分为基础伤害→修正→暴击→穿透→防御减伤→护盾多个阶段,每个阶段都可以被装备效果影响,提供了丰富的扩展点。

**属性上限机制:** 关键战斗属性设置上限(如暴击率500%、连击率60%),防止属性溢出破坏平衡。

**随机种子支持:** 支持随机种子实现确定性战斗,便于测试和战斗回放。

**缓存优化:** 将包含临时buff的有效属性缓存到player对象,避免重复查询数据库。

**无损切磋:** PvP使用缓存的HP值,不修改实际HP,战毕不保存状态,纯粹切磋交流。
