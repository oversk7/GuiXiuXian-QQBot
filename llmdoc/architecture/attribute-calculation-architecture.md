# 属性计算系统架构

## 1. Identity

- **What it is**: 两档收口的属性读取体系 + 唯一写入口（2026-06-10 收敛，删除了旧 AttributeCalculator v2 双轨框架）
- **Purpose**: 保证全库读到的属性一致（同一真源），战斗数值受统一上限约束，永久变更账实相符

## 2. Core Components

**读取（两档）:**
- `plugins/xiuxian_game/models/player.py` (Player.get_effective_attributes): **全量真源**。返回 21 项属性（六维 + 15 项战斗属性），= 存储字段值（已含装备 _persist_bonus / 永久丹药 / VIP）+ 临时buff + 宠物加成。所有展示面板（角色/战力/查看面板）直接用它
- `plugins/xiuxian_game/battle/battle_attributes.py` (BattleAttributeCalculator): **战斗档**。
  - `calculate_effective_attributes_async(player, session, equipment_bonus)`: 真源 + T1词缀加成 + ATTRIBUTE_CAPS 上限收口，开战预计算与战力面板战斗属性显示用它
  - `effective_attrs_in_battle(player)`(同步): **战斗循环内取玩家战斗属性的唯一正确方式**——优先返回开战时预计算的 `_cached_battle_attrs`（含临时buff/宠物/词缀），无缓存时回退裸字段计算
  - `calculate_effective_attributes(player)`(同步): 直读 player 存储字段 + 上限，不含临时buff/宠物。战斗循环内禁止直接调用（历史 bug：6 处判定裸读导致 buff 在怪物战/PVP连击/反击中不生效，2026-06-11 修复）
- `plugins/xiuxian_game/models/player.py` (Player.get_attribute_breakdown): 来源分解（base/equipment/permanent/vip/temporary/pet），保留未截断的来源总和；base 为初始、加点及历史未归类残差，permanent 包含本轮有效的烹饪幸运，不能全部视为跨轮回保留。
- `plugins/xiuxian_game/battle/attribute_summary.py`: 只读展示汇总，在真源上补齐 T1 词缀与套装来源；`summarize_battle_attributes` / `get_battle_attribute_summary` 返回原始值、开战生效值、硬上限、溢出和来源。`战力`、`属性分解` 与换装预览共用。
- `BattleAttributeCalculator.calculate_attribute_breakdown`: 战斗同步/异步读取和展示共用的上限计算入口；对手抗性与战斗触发效果另行结算。命中或暴击超过 100 不等于硬上限溢出，暴击力不额外设上限。

**属性上限（单源）:**
- `BattleAttributeCalculator.ATTRIBUTE_CAPS`: 战斗属性上限字典（连击60/反击80/灵爆70/穿透100/暴击·闪避·命中·抗暴500）。战斗档两个方法、enhanced_engine 战斗内buff修正(`_get_effective_battle_attributes`)与 `_sync_unit_attr` 缓存镜像写入共用此常量。六维（攻防体敏运血蓝）无上限概念
- 战斗档 2026-07-03 起为 15 键：11 基础判定键 + lifesteal_rate/immobilize_rate/true_damage_rate/regen_rate（数值型吸血/定身/真伤/回复，引擎经 `enhanced_engine._unit_battle_attr()` 消费）
- `enhanced_engine._effective_max_hp(unit)`: 战斗内血量上限唯一读取口（缓存优先，HEAL/SHIELD/REGEN 百分比基数与触发上下文统一走它；灵影体质战斗内改 max_hp 会同步增减 `_cached_max_hp`）

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
- **5. 战斗属性子面板**: `battle/integration_helper.py` 的 get_battle_attribute_display_async() 经 `attribute_summary` 收集词缀与套装，使用战斗档同一上限计算显示 15 项原始/生效/溢出值；防御说明使用本次真源，不读取旧战斗缓存。
- **6. 来源解释**: `item/buff_commands.py` 的属性分解显示正负来源、词缀、套装、宠物小数与装备比例合计；帮助正文唯一来源为 `data/knowledge/battle_attribute_help.yaml`（战力说明/战力介绍）。

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

### 3.4 只读收益预览
- `item/attribute_preview_service.py` 在脱离 session 的装备副本上复用 `ItemInstance.apply_attr_bonus`，与正式重算共享逐件加成和转换分摊；嵌套装备数据深拷贝，预览不修改玩家、装备或持久化记录。
- `换装预览 <穿上编号> [卸下编号]` 使用装备栏短编号，先校验真实的卸下/穿戴顺序（含扩槽限制），再比较基础属性、战斗属性的原始/生效/溢出与套装变化。当前宠物和临时增益保持同一时点，触发型机制不折算进面板。
- `ReincarnationService.preview_reincarnation` 复用永久来源读取与直接装备加成；`冥返信息`（别名`冥返预览`）显示六维前后与本轮重置部分。保留现有执行语义：只重建六维、保留穿戴，不重新检查穿戴等级，冥返重算不执行普通装备重算的生命/攻击转换；预览不顺带改变这些规则。
- 回归：`tests/test_attribute_explanations.py` 验证来源合计与开战值一致；`tests/test_attribute_previews.py` 验证预览/执行一致及无写入副作用。

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
