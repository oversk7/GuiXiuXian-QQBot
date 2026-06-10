# 属性计算系统架构

## 1. Identity

- **What it is**: 基于组合模式和策略模式的统一属性计算框架
- **Purpose**: 管理多种属性来源(装备、buff、丹药、VIP),提供高性能属性计算服务

## 2. Core Components

- `plugins/xiuxian_game/domain/attributes/attribute_calculator.py` (AttributeCalculator类): 属性计算器核心,管理多个IAttributeSource,并发计算各来源加成
- `plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py` (AttributeCalculatorFactory类): 单例工厂,创建并配置AttributeCalculator,管理60秒TTL buff缓存
- `plugins/xiuxian_game/domain/attributes/player_attributes_integration.py` (get_effective_attributes_v2函数): 统一入口,使用AttributeCalculator v2计算有效属性
- `plugins/xiuxian_game/domain/attributes/attribute_sources/buff_source.py` (BuffAttributeSource类): 临时buff属性来源,60秒TTL缓存优化90%查询性能
- `plugins/xiuxian_game/domain/attributes/attribute_sources/equipment_source.py` (EquipmentAttributeSource类): 装备属性来源,读取ItemInstance._persist_bonus
- `plugins/xiuxian_game/domain/attributes/interfaces.py` (IAttributeSource接口): 属性来源抽象接口,定义calculate_bonus()方法
- `plugins/xiuxian_game/battle/battle_attributes.py` (BattleAttributeCalculator类): 战斗属性计算(critical_rate, dodge_rate等),提供等级加成和属性上限

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 属性计算总流程
- **1. 请求入口**: `plugins/xiuxian_game/domain/attributes/player_attributes_integration.py:20-35`的get_effective_attributes_v2()接收请求
- **2. 获取计算器**: `plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py:30-45`的get_instance()返回单例AttributeCalculator
- **3. 计算基础属性**: `plugins/xiuxian_game/domain/attributes/attribute_calculator.py:60-75`的_calculate_base()读取player当前属性(已含装备+丹药+VIP)
- **4. 并发计算来源**:
  - `plugins/xiuxian_game/domain/attributes/attribute_sources/buff_source.py:25-40`的BuffAttributeSource.calculate_bonus(): 检查60秒缓存,命中则返回,失效则查询TemporaryBuff表并更新缓存
  - `plugins/xiuxian_game/domain/attributes/attribute_sources/equipment_source.py:20-30`的EquipmentAttributeSource.calculate_bonus(): 查询已穿戴装备,汇总_persist_bonus
- **5. 汇总结果**: `plugins/xiuxian_game/domain/attributes/attribute_calculator.py:80-100`累加基础属性+临时buff(is_persisted=False的来源)
- **6. 返回属性**: Dict格式的属性字典,与旧版本兼容

### 3.2 装备穿戴流程
- **1. 穿戴装备**: `plugins/xiuxian_game/item/equipment_service.py:40-60`处理装备穿戴请求
- **2. 移除旧加成**: `plugins/xiuxian_game/item/equipment_service.py:80-95`的recalc_equipment_attributes()移除旧装备的_persist_bonus
- **3. 获取基础属性**: 查询当前无装备加成的基础属性
- **4. 应用新加成**: `plugins/xiuxian_game/item/equipment_service.py:100-120`调用apply_attr_bonus()计算delta并累加到player属性
- **5. 处理特殊效果**: `plugins/xiuxian_game/item/equipment_service.py:125-140`的_apply_mp_from_hp_effects()处理mp_from_hp特效(百分比HP转MP)
- **6. 确保血蓝上限**: `plugins/xiuxian_game/item/equipment_service.py:145-150`确保HP/MP不超过新上限
- **7. 提交事务**: UnitOfWork自动提交
- **8. 失效缓存**: `plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py:50-55`的invalidate_buff_cache()使buff缓存失效(属性变化)

### 3.3 临时buff使用流程
- **1. 使用buff物品**: `plugins/xiuxian_game/item/item_effects.py:150-180`的TEMP_BUFF效果处理器
- **2. 检查重复**: `plugins/xiuxian_game/models/temporary_buff.py:40-55`的get_active_buffs()检查是否已有相同buff,提示剩余时间
- **3. 创建buff记录**: `plugins/xiuxian_game/item/item_effects.py:185-200`创建TemporaryBuff记录
- **4. 失效缓存**: `plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py:55-60`的invalidate_buff_cache()主动失效buff缓存
- **5. 下次查询**: 60秒内再次查询将重新从数据库读取最新buff数据

### 3.4 战斗属性计算流程
- **1. 获取基础属性**: 调用get_effective_attributes_v2()获取基础战斗属性
- **2. 应用等级加成**: `plugins/xiuxian_game/battle/battle_attributes.py:80-95`的calculate_effective_attributes()应用LEVEL_BONUS常量(每级增加的属性值)
- **3. 应用上限限制**: `plugins/xiuxian_game/battle/battle_attributes.py:100-110`确保属性不超过ATTRIBUTE_CAPS上限(如dodge_rate上限80%)
- **4. 计算命中率**: `plugins/xiuxian_game/battle/battle_attributes.py:115-125`的calculate_hit_chance()计算命中率=accuracy_rate - opponent.dodge_rate
- **5. 处理攻击**: `plugins/xiuxian_game/battle/battle_attributes.py:130-150`的process_attack()处理攻击的所有效果(暴击、连击、闪避等)

## 4. Design Rationale

**为什么使用组合模式+策略模式?**
- **可扩展性**: 新增属性来源只需实现IAttributeSource接口,无需修改核心计算逻辑
- **独立测试**: 每个Source可独立测试,降低复杂度
- **灵活组合**: AttributeCalculator可动态组合不同的属性来源

**为什么只累加is_persisted=False的来源?**
- **避免重复计算**: 装备、丹药、VIP装备的加成已通过recalc_equipment_attributes()持久化到player属性中
- **性能优化**: 持久化加成只需计算一次(穿戴/使用时),无需每次战斗重新计算
- **清晰分层**: 基础属性(含持久化加成) + 临时buff(动态计算)

**为什么使用60秒TTL缓存?**
- **性能提升**: 临时buff在60秒内通常不会变化,缓存可减少90%数据库查询
- **数据一致性**: 使用buff物品时主动失效缓存,确保数据实时更新
- **平衡点**: 60秒是性能和一致性的平衡点,过长会导致数据滞后,过短失去缓存意义

**为什么mp_from_hp特效需要特殊处理?**
- **循环依赖**: MP加成可能基于HP百分比,HP加成可能基于MP百分比,需要特殊处理避免死循环
- **持久化需求**: 基于百分比的特效需要在装备穿戴时计算并持久化,否则每次战斗都要重新计算

**为什么需要AttributeCalculatorFactory单例?**
- **缓存复用**: 全局共享AttributeCalculator实例,复用BuffAttributeSource的60秒缓存
- **配置管理**: 集中管理属性来源注册,便于扩展新来源
- **性能优化**: 避免频繁创建计算器实例,减少内存开销
