# 属性计算系统架构

## 1. Identity

- **What it is**: 两档收口的属性读取体系 + 唯一写入口（2026-06-10 收敛，删除了旧 AttributeCalculator v2 双轨框架）
- **Purpose**: 保证全库读到的属性一致（同一真源），战斗数值受统一上限约束，永久变更账实相符

## 2. Core Components

**读取（两档）:**
- `plugins/xiuxian_game/models/player.py` (Player.get_effective_attributes): **全量真源**。返回 19 项属性（六维 + 13 项战斗属性），= 存储字段值（已含装备 _persist_bonus / 永久丹药 / VIP）+ 临时buff + 宠物加成。所有展示面板（角色/战力/查看面板）直接用它
- `plugins/xiuxian_game/battle/battle_attributes.py` (BattleAttributeCalculator): **战斗档**。
  - `calculate_effective_attributes_async(player, session, equipment_bonus)`: 真源 + T1词缀加成 + ATTRIBUTE_CAPS 上限收口，开战预计算与战力面板战斗属性显示用它
  - `effective_attrs_in_battle(player)`(同步): **战斗循环内取玩家战斗属性的唯一正确方式**——优先返回开战时预计算的 `_cached_battle_attrs`（含临时buff/宠物/词缀），无缓存时回退裸字段计算
  - `calculate_effective_attributes(player)`(同步): 直读 player 存储字段 + 上限，不含临时buff/宠物。战斗循环内禁止直接调用（历史 bug：6 处判定裸读导致 buff 在怪物战/PVP连击/反击中不生效，2026-06-11 修复）
- `plugins/xiuxian_game/models/player.py` (Player.get_attribute_breakdown): 来源分解展示（base/equipment/permanent/vip/temporary/pet），增益状态命令用

**属性上限（单源）:**
- `BattleAttributeCalculator.ATTRIBUTE_CAPS`: 战斗属性上限字典（连击60/反击80/灵爆70/穿透100/暴击·闪避·命中·抗暴500）。战斗档两个方法与 enhanced_engine 战斗内buff修正(`_get_effective_battle_attributes`)共用此常量。六维（攻防体敏运血蓝）无上限概念

**辅助来源:**
- `plugins/xiuxian_game/domain/attributes/attribute_sources/pet_source.py`: 宠物加成（未持久化，60秒TTL缓存）。模块级单例 `get_pet_source()` / `invalidate_pet_cache(player_id)`，由真源内部调用

**写入（单口）:**
- `plugins/xiuxian_game/domain/attributes/permanent_change.py` (apply_permanent_change): 永久属性变更唯一入口，见 coding-conventions.md §6.3

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 面板展示流程（角色/战力/查看面板）
- **1. 入口**: `player/info.py`、`player/battle_info.py`、`queries/player_queries.py` 调用 `player.get_effective_attributes(session)`
- **2. 基础值**: 直读 player 存储字段（已含装备/永久丹/VIP 持久化加成）
- **3. 叠加临时buff**: `models/temporary_buff.py` 的 get_total_attribute_bonuses()，键名 = Player 字段名，直通累加
- **4. 叠加宠物**: `attribute_sources/pet_source.py` 的 calculate_full_bonus()（60秒缓存）
- **5. 战斗属性子面板**: `battle/integration_helper.py` 的 get_battle_attribute_display_async() 走战斗档（含词缀与上限）

### 3.2 战斗开场预计算流程
- **1. 入口**: `battle/integration_helper.py` PVP/PVE 开战处、`world_boss/service.py` 讨伐开战处
- **2. 基础属性**: `player.get_effective_attributes(session)`（attack/defense/max_hp 等缓存到 `_cached_*`）
- **3. 战斗属性**: `calculate_effective_attributes_async()` = 真源 + T1词缀 + 上限，缓存到 `_cached_battle_attrs`
- **4. 循环内读取**: 战斗属性判定（攻击/反击/闪避/抗暴/理智侵蚀）经 `effective_attrs_in_battle()` 读缓存；
  六维取值（先手敏捷/伤害攻击力/减伤防御力）用 `getattr(player, '_cached_attack', player.attack)` 模式读 `_cached_*`
- **5. 战斗内修正**: `battle/enhanced_engine.py` 的 `_get_effective_battle_attributes()` 在缓存值上叠加战斗内buff效果，再次应用 ATTRIBUTE_CAPS

### 3.3 临时buff生效流程
- **1. 创建**: `item/item_effects.py` TEMP_BUFF 处理器创建 TemporaryBuff 记录
- **2. 读取**: 真源每次查询 TemporaryBuff 表实时累加（无缓存层，键名直通）
- **3. 过期**: cleanup_expired_buffs() 批量置 is_active=False

## 4. Design Rationale

**为什么收敛为两档而不是统一一个入口?**
- 战斗档需要"词缀加成 + 上限收口"，展示档需要"原始有效值"；强行合一会让面板显示被上限截断、或战斗绕过上限
- 引擎内部多处无 session（怪物判定、反击判定），靠"开战预计算 + `effective_attrs_in_battle` 读缓存"模式让 buff 在同步路径生效（回归锁: `tests/test_battle_buff_effectiveness.py`）

**为什么删除 AttributeCalculator v2 框架?（2026-06-10）**
- 双轨计算：v2 与真源各算一套，字段名错位（critical_rate vs crit_rate）导致 buff 战斗属性在 v2 中被静默丢弃
- 缺 9 项战斗字段且无上限，谁用它的战斗字段就绕开 ATTRIBUTE_CAPS
- 其 60 秒 buff 缓存收益落空：高频战斗路径不走它，走它的只有 3 个低频面板命令
- 删除后面板与战斗读同一真源，键名直通，回归测试 `tests/test_effective_attributes_passthrough.py` 锁定

**为什么临时buff读取不再带缓存?**
- buff 查询只发生在面板命令与开战预计算（每场 1-2 次轻量 select），缓存带来的失效一致性维护成本大于收益

**为什么宠物加成保留缓存?**
- 宠物加成计算涉及 PetInstance 查询 + 配置心情倍率 + 饰品累加，且喂食/换宠等失效点集中（pet_service 统一调 invalidate_pet_cache）
