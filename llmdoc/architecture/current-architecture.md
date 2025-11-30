# 当前架构详细分析

## 1. Identity

- **What it is**: 诡修仙项目当前代码库的架构详细分析
- **Purpose**: 为LLM代理提供精确的代码检索地图,定位模块、理解依赖关系和识别问题

## 2. Core Components

### 入口和框架层
- `bot.py` (main, driver): Nonebot2主程序入口,注册QQ适配器,从pyproject.toml加载插件
- `plugins/xiuxian_game/__init__.py` (PluginMetadata, on_startup): 插件元数据定义,注册15个子模块,启动钩子调用init_db

### 数据层核心
- `plugins/xiuxian_game/models/db.py` (engine, AsyncSessionLocal, safe_session, get_session, retry_session): 数据库引擎配置,三种会话管理器,支持MySQL/SQLite双引擎
- `plugins/xiuxian_game/models/player.py` (Player, get_effective_attributes, get_attribute_breakdown): Player模型(87字段),属性计算主入口,属性来源分解
- `plugins/xiuxian_game/models/inventory.py` (ItemInstance, add_item, consume_item, apply_attr_bonus): 物品实例模型,背包管理,装备属性加成计算
- `plugins/xiuxian_game/models/guild.py` (Guild, GuildMember, GuildBuilding): 公会三表结构,cascade级联删除
- `plugins/xiuxian_game/models/temporary_buff.py` (TemporaryBuff, create_buff, get_total_attribute_bonuses): 临时buff模型,JSON存储属性加成,自动过期清理

### 配置管理
- `plugins/xiuxian_game/config.py` (Config, game_config, items_config, map_config): 单例配置管理器,lru_cache缓存,加载5个YAML配置文件
- `plugins/xiuxian_game/data/database.yaml`: 数据库配置(当前MySQL),连接池配置
- `plugins/xiuxian_game/alembic/env.py`: 迁移配置(硬编码SQLite路径,与database.yaml不一致)

### 业务层核心
- `plugins/xiuxian_game/item/item_effects.py` (_REGISTRY, register, apply_effect, 45+效果处理函数): 物品效果装饰器注册系统
- `plugins/xiuxian_game/battle/battle_effects.py` (BattleEffectManager, TriggerConfig, BattleEffect): 战斗效果管理器,75+效果类型,12种触发类型
- `plugins/xiuxian_game/battle/enhanced_engine.py` (EnhancedBattleEngine, execute_turn, _execute_enhanced_attack): 增强战斗引擎,集成装备特殊效果
- `plugins/xiuxian_game/item/equipment_commands.py` (recalc_equipment_attributes, _apply_mp_from_hp_effects): 装备属性重算,mp_from_hp特效处理
- `plugins/xiuxian_game/guild/guild_service.py` (GuildService, create_guild, join_guild): 公会服务类(静态方法模式)

### 子系统模块
- `plugins/xiuxian_game/cultivate/` - 修炼系统(突破、闭关、冥返)
- `plugins/xiuxian_game/battle/` - 战斗系统(PVP、PVE、世界BOSS)
- `plugins/xiuxian_game/economy/` - 经济系统(市场、银行、股票)
- `plugins/xiuxian_game/social/` - 社交系统(婚姻、师徒)
- `plugins/xiuxian_game/world/` - 世界探索(双层坐标、诡域)

## 3. Execution Flow (LLM Retrieval Map)

### 命令处理流程

**1. 入口**: 用户QQ消息 → QQ适配器 → Nonebot2事件系统
**2. 路由**: `on_command("装备", block=True, priority=3)` 装饰器注册 (`equipment_commands.py:189`)
**3. 处理器**: `equip_view.handle()` 异步函数执行 (`equipment_commands.py:192-230`)
**4. 会话**: `async with safe_session() as session:` 打开自动提交会话 (`equipment_commands.py:193`)
**5. 查询**: `player = await get_player(session, event)` 获取玩家对象 (`equipment_commands.py:194`)
**6. 业务逻辑**: 查询装备列表、格式化输出 (`equipment_commands.py:196-225`)
**7. 响应**: `await equip_view.send(msg)` 返回消息 (`equipment_commands.py:227`)
**8. 提交**: 会话上下文退出时自动commit/rollback (`db.py:159-164`)

### 属性计算流程

**1. 入口**: 查询属性时调用 `Player.get_effective_attributes(session)` (`player.py:218`)
**2. 基础属性**: 直接读取Player字段(已包含装备和丹药的_persist_bonus) (`player.py:220-237`)
**3. 临时buff查询**: `TemporaryBuff.get_total_attribute_bonuses(session, player_id)` (`temporary_buff.py:151`)
**4. Buff合并**: 遍历所有激活buff,累加attribute_bonuses (`temporary_buff.py:157-162`)
**5. 最终属性**: 基础属性 + 临时buff加成 (`player.py:244-254`)

### 装备穿戴流程

**1. 命令**: `wear_equipment` 命令触发 (`equipment_commands.py:472`)
**2. 会话**: 打开safe_session (`equipment_commands.py:474`)
**3. 预处理**: 检查装备可用性、等级限制、职业限制 (`equipment_commands.py:476-510`)
**4. 重算入口**: 调用 `recalc_equipment_attributes(session, player)` (`equipment_commands.py:515`)
**5. 卸下所有**: 遍历已穿戴装备,移除_persist_bonus记录的加成 (`equipment_commands.py:102-122`)
**6. 获取基础**: 计算无装备状态的基础属性 (`equipment_commands.py:124-138`)
**7. 逐个计算**: 遍历装备,调用 `ItemInstance.apply_attr_bonus()` (`equipment_commands.py:140-154`)
**8. 应用加成**: 固定值+百分比+宝石,保存_persist_bonus (`inventory.py:162-218`)
**9. 特效处理**: `_apply_mp_from_hp_effects()` 将HP转为MP (`equipment_commands.py:156`)
**10. 修正上限**: 限制当前HP/MP不超过新上限 (`equipment_commands.py:166-173`)
**11. 提交**: safe_session自动提交

### 效果触发流程

**物品效果**:
**1. 使用物品**: `use_item` 命令 → `item_commands.py:245`
**2. 效果分发**: `apply_effect(player, cfg, qty, ctx, session)` (`item_effects.py:37`)
**3. 查找处理器**: `_REGISTRY[cfg.effect_type]` 获取效果函数 (`item_effects.py:48`)
**4. 执行效果**: 调用注册的效果处理函数(如 `_restore_hp`) (`item_effects.py:51`)
**5. 扣除物品**: `ItemInstance.consume_item()` (`item_effects.py:56`)

**战斗效果**:
**1. 战斗开始**: `EnhancedBattleEngine.start_battle()` (`enhanced_engine.py:87`)
**2. 注册触发器**: `_register_equipment_triggers()` 从装备special_effects解析 (`enhanced_engine.py:123`)
**3. 回合执行**: `execute_turn()` 处理回合逻辑 (`enhanced_engine.py:205`)
**4. 检查触发**: `BattleEffectManager.check_triggers(unit_id, ON_ATTACK, context)` (`battle_effects.py:302`)
**5. 概率判定**: 检查trigger_config.chance (`battle_effects.py:312`)
**6. 添加效果**: `BattleEffectManager.add_effect(unit_id, effect)` (`battle_effects.py:226`)
**7. 应用效果**: 在伤害计算、属性修正等位置应用效果 (`enhanced_engine.py:350-380`)
**8. 回合结算**: `tick_effects()` 减少持续时间,移除过期效果 (`battle_effects.py:352`)

## 4. Design Rationale

### 为什么使用三种会话管理器?

- **get_session**: 基础版本,需要手动控制事务,用于复杂事务流程
- **safe_session**: 主流使用,自动提交成功事务,异常自动回滚,确保资源清理
- **retry_session**: 专门处理数据库锁定问题,最多3次重试,指数退避延迟

设计理由: 平衡易用性(safe_session)和灵活性(get_session),同时处理高并发场景的锁定问题(retry_session)

### 为什么保留_persist_bonus机制?

装备属性加成持久化存储在 `ItemInstance.extra_attrs["_persist_bonus"]`,避免:
- 每次战斗重新计算装备加成(性能优化)
- 百分比加成与基础属性不同步(一致性保证)
- 卸下装备时无法准确回退属性(可靠性保证)

设计理由: 用存储空间换计算时间,确保属性计算的性能和正确性

### 为什么效果系统有两套实现?

- **物品效果**(装饰器注册): 简单、静态、易扩展,适合45+种物品效果
- **战斗效果**(管理器模式): 复杂、动态、支持叠加,适合75+种战斗效果

设计理由: 针对不同场景选择合适的模式,物品效果使用时触发一次,战斗效果需要管理生命周期和叠加

### 为什么Service采用静态方法?

当前26个Service类全部采用静态方法+外部会话注入模式:
```python
class GuildService:
    @staticmethod
    async def create_guild(session, player_id, name):
        # 直接使用传入的session
```

设计理由(推测): 简化调用,无需实例化Service对象,直接传递session参数

**问题**: 硬编码依赖,无法进行单元测试,难以替换实现

---

**相关文档**:
- 目标架构: `/architecture/target-architecture.md`
- 属性系统: `/architecture/attribute-system.md`
- 效果系统: `/architecture/effect-system.md`
- 数据访问层: `/architecture/data-access-layer.md`
- 问题清单: `/reference/code-issues.md`
