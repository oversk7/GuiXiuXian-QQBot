# 玩家实力组成审计报告（2026-07-03）

> 三路并行调研的汇总：实力来源全景、读取路径与重复代码、战力/面板口径。
> 结论：2026-06 属性收口后"读写核心"健康，乱点集中在战斗结算层的复制粘贴、生效通道旁路、展示口径不一致。

## 一、五条生效通道（全景）

| 通道 | 载体 | 记账 | 现状 |
|---|---|---|---|
| A. 永久写入 | `apply_permanent_change` → player 字段 | ElixirUsageLog | 健康。丹药/洗髓/剧情奖励走此口 |
| B. 装备快照 | `_persist_bonus`（含宝石加成） | 装备 extra_attrs 快照 | 收口正确；但重算逻辑被拷贝 4 份（见三.4） |
| C. VIP 独立账本 | `VIPEquipmentBonus.add_bonus` + 直改字段 | VIPEquipmentBonus 表 | 合法独立通道（轮回重放依赖），但无统一入口，3 份拷贝 |
| D. 读取时叠加 | 真源叠临时buff/宠物；战斗档叠 T1词缀/套装 | 不落库 | 有静默丢失 bug（见二.1） |
| E. 战斗时特判 | enhanced_engine 触发器/VIP体质，战后回退 | 不持久 | 有绕上限/双口径问题 |

- 轮回重建 = INIT + ElixirUsageLog 回放 + VIPEquipmentBonus 回放 + 装备 recalc（`cultivate/reincarnation_service.py:111-129`）。不在账内的永久写入轮回时被静默吞掉。
- 加点不记账，是对账脚本"base 残差"的合法组成。
- 境界/成就只发属性点；月卡/公会建筑/称号无属性加成。
- 无全局"战力分"：唯一综合评分在 `daily_task/service.py:587`（裸字段口径，仅调 PVE 难度，不展示不排行）。天梯用 ELO，排行榜按单字段。

## 二、现症数值 bug（✅ 已全部修复，2026-07-03，回归测试 `tests/test_stat_battle_attrs_wiring.py`）

1. ✅ **T1词缀4属性静默丢弃**：战斗档（同步/异步/无session回退）补齐 lifesteal/immobilize/true_damage/regen 4键；引擎新增 `_unit_battle_attr()` 读缓存，接通4个消费点：定身改读缓存、吸血=伤害×rate%（两份攻击效果块）、回复=每回合max_hp×rate%、真伤=按率roll。**此修复使这4种T1词缀/宝石/宠物饰品数值型来源开始实际生效，属玩法数值变化，上线宜公告。**
2. ✅ **世界BOSS预计算抄漏**：补 `get_set_t1_bonuses` 与 `_cached_max_hp/_cached_max_mp/_cached_agility`。
3. ✅ **反击判定语义统一**：`BattleEffectProcessor.check_counter_attack` 增加 `attacker_anti_counter` 参数。**勘误**：原报告称"抗反玉佩PVE疑似无效"不实——两个怪物反击块均已减玩家抗反击率；实际缺口仅为玩家反击怪物时未减怪物侧抗反（怪物无此属性，无实际影响）。
4. ✅ **战斗内裸 max_hp 双口径**：新增 `_effective_max_hp()` 统一 HEAL/SHIELD/REGEN 百分比基数与全部触发上下文；灵影体质战斗内改 max_hp 时同步增减 `_cached_max_hp`（含回退）。
5. ✅ **绕 ATTRIBUTE_CAPS 直写缓存**：`_sync_unit_attr` 缓存镜像写入时对 ATTRIBUTE_CAPS 明确列出的属性套上限（critical_power 等不在表内的保持原语义）。
6. ✅ **烹饪 luck 记账**：走 `apply_permanent_change`（新账目 `LEDGER_COOKING_LUCK`）；新增 `REBIRTH_VOLATILE_LEDGER_IDS` 机制保留"本轮回有效"语义——冥返重放排除、洗髓池排除（两处 REFORGE + `_get_elixir_bonus`）。存量未记账的烹饪 luck 仍在 base 残差中（不迁移）。
7. ✅ **签到勋章补装备重算**：`sign.py` 天帝勋章直改后调 `recalc_equipment_attributes`。VIP击杀成长三处拷贝的同样问题待统一入口时一并解决（见五.2）。
8. ✅ **两处怪物反击块对齐**：`integration_helper.py` 第二块补 ignore_defense 穿透。

## 三、重复实现清单（维护债）

1. **攻击判定流程（命中→穿透→暴击→连击→暴伤→减伤）4份**：`battle_attributes.py:306-403`（BattleEffectProcessor.process_attack，**死代码**，且裸读绕缓存）、`enhanced_engine.py:1533-1674`（PVP）、`:1676-1788`（怪物，与前者几乎逐行同）、`integration_helper.py:1312-1429`（怪→玩家）。
2. **两套PVP战斗循环并行**：`integration_helper.py:63-471`（enhanced，世界PVP用）vs `:934-1311`（compact，切磋/天梯用）；各自内部再复制 2-4 段攻击结算。
3. **开战预计算5份**：`integration_helper.py:84-159 / 486-542 / 940-1028 / 1523-1546`（面板）、`world_boss/service.py:533-552`（抄漏版=bug二.2）。
4. **装备重算逻辑4份内联拷贝**：`reset_attr_service.py:137-188`、`cultivate/core.py:1239-1301`（加点）、`:1456-1506`（洗点）、`reincarnation_service.py:212` 附近；正版在 `equipment_service.py:82-127`。
5. **绝魔真伤拆分4份**：`enhanced_engine.py:1626-1648`、`integration_helper.py:657-669 / 877-889 / 1398-1417`。
6. **VIP击杀成长3份**：`world/attack_command.py:780-909`、`world/dungeon_battle_service.py:325-649`、扫荡部分。
7. **属性英文键→中文名映射 ≥20份**，译名不一致（attack=攻击力/攻击/力量/力）。分布：item_effects(6)、buff_commands、temporary_buff、equipment_service、catalog(2)、inventory(2)、reset_attr_service、enhanced_engine、cultivate/core(2)、attack_command(2)、dungeon_battle_service(2)、mentorship、pet/config、ai_guide。
8. ✅ **死代码已删**（2026-07-03）：同步版 `get_battle_attribute_display` 与 `BattleEffectProcessor.process_attack`。

## 四、展示口径不一致

- 属性分解（`get_attribute_breakdown`）不含 T1词缀/套装、不截断上限，与"战力"面板数字对不上。
- 击杀统计面板（`world/attack_command.py:1444`）裸字段。
- `ai_guide.py` 教管理员 AI 直接 SQL 改字段，是绕账本的第三套读写口径（对账非零头号嫌疑，已知）。

## 五、优化方向与进度（2026-07-03 更新）

1. ✅ **修现症bug**：二.1~8 已全部修复，82项测试通过（新增 `tests/test_stat_battle_attrs_wiring.py` 7项）。**注意：T1词缀4属性生效属玩法数值变化，部署时宜公告。**
2. ⏳ **机械清理**（下次继续）：
   - 死代码已删（三.8 ✅）
   - **属性中文映射收口**：≥20份字典（分布见三.7）。注意译名不一致意味着统一后部分面板文案会变（改现役UX需谨慎），建议先建常量表、只替换完全同义的场景
   - **装备重算拷贝改调正版**：`reset_attr_service.py:137-188`（替换后记得删掉其后对正版的重复调用）、`cultivate/core.py:1239-1301`（加点）、`:1456-1506`（洗点）、`reincarnation_service.py:212` 附近 → 改调 `EquipmentService.recalc_equipment_attributes`
   - **VIP击杀成长统一入口**：三处拷贝提取统一函数，入口内统一补装备重算（解决二.7遗留）
3. **战斗结算收口**（中风险，治本，未开始）：攻击判定4→1、开战预计算5→1、绝魔拆分提函数。回归测试基础已扩充。
4. **两套PVP循环合并**（高风险）：业余项目标准下可缓行。
