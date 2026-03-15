<!-- 这份文件是面向其他LLM Agent的原始调查报告，非最终用户文档。 -->

# 下位世界/天灾系统深度调查报告

**日期**: 2026-03-15
**调查范围**: 下位世界天灾玩法的完整实现
**调查者**: scout

---

### Code Sections (The Evidence)

- `plugins/xiuxian_game/lower_world/__init__.py` (`lower_world`): 模块入口，仅加载 commands 和 scheduler 两个子模块。
- `plugins/xiuxian_game/lower_world/commands.py` (`handle_descend`, `handle_guard`, `handle_battle_hero`, `handle_calamity_shop`, `handle_redeem`, `_show_stronghold_status`): 所有命令处理器。注意：`_show_stronghold_status` 内部所有 `finish()` 均硬编码为 `descend_cmd.finish`，但此函数也被 `guard_cmd` 调用。
- `plugins/xiuxian_game/lower_world/service.py` (`get_wave_reward`, `get_or_create_stronghold`, `is_sealed`, `has_pending_hero`, `schedule_next_wave`, `process_battle_victory`, `process_battle_defeat`, `get_shop_display`, `SHOP_ITEMS`): 核心业务逻辑。
- `plugins/xiuxian_game/lower_world/hero_generator.py` (`calculate_hero_level`, `calculate_hero_stats`, `generate_hero`, `apply_affixes`, `AFFIXES`, `NORMAL_HERO_CLASSES`, `HERO_CLASSES`): 英雄生成器，含词缀池实现。
- `plugins/xiuxian_game/lower_world/scheduler.py` (`generate_hero_waves`): 每2小时定时任务，不发送私聊通知（注释说明"QQ不支持主动发消息"）。
- `plugins/xiuxian_game/models/lower_world.py` (`LowerWorldStronghold`): 数据模型，含字段 `last_battle_at`（战斗冷却），这是设计文档中未列出的新增字段。
- `plugins/xiuxian_game/infrastructure/repositories/lower_world_repository.py` (`LowerWorldRepository`): 仅含 `get_by_player_id`、`create`、`get_all` 三个方法，无分页/条件查询。
- `plugins/xiuxian_game/battle/integration_helper.py` (`enhanced_player_vs_monster_battle_v2`, `_process_monster_turn`): 战斗引擎。怪物的 `counter_rate`、`crit_rate`、`combo_rate` 在此处处理；**`ignore_defense` 和 `lifesteal` 字段在怪物攻击路径中未被处理**。
- `plugins/xiuxian_game/models/temporary_buff.py` (`TemporaryBuff`): 临时Buff模型，`extra_data.cultivation_efficiency` 用于修炼加速。
- `plugins/xiuxian_game/cultivate/core.py`: 修炼核心，在约183行显式读取 `extra_data.cultivation_efficiency`，天灾修炼加速buff **已经真正实装并生效**。
- `docs/plans/2026-02-21-lower-world-design.md`: 原始设计文档v1.0。
- `docs/plans/2026-02-21-lower-world-impl.md`: 实现计划，与实际代码基本吻合，部分细节有扩展。

---

### Report (The Answers)

#### result

**1. 波次机制——永远递增无上限无重置**

- `service.py` `process_battle_victory` 在每次胜利后执行 `stronghold.wave_number += 1`，没有任何上限检查，没有重置逻辑。
- `process_battle_defeat` 不重置 `wave_number`，失败后波次停留原地不退步，仅封印24小时。
- 等级公式 `0.6 + wave_number * 0.04`：第100波时英雄等级为玩家等级的 **4.6倍**，必定无法战胜，系统会在高波次进入永久卡死状态。
- 设计文档中提到的"第20波→130级（开始艰难）"是合理假设，但未设计上限和循环机制。

**2. 英雄属性缩放公式的平衡性**

- 基础公式：`英雄等级 = 玩家等级 × (0.6 + 波次 × 0.04)`。
- 第10波：比率 = 1.0（与玩家同级），属性基本相当。
- 第15波（勇者期）：比率 = 1.2，叠加勇者职业倍率（最高2.0倍攻击的炮勇者），实际攻击约为玩家的 1.2 × 2.0 = **2.4倍**，极难应对。
- 词缀叠加（21+波）在职业倍率基础上再乘以词缀倍率，且`狂暴之怒`词缀攻击1.5倍、`炮勇者`atk_mult=2.0叠加后攻击翻3倍，远超玩家可承受范围。
- **`apply_affixes` 的特殊属性（`crit_rate`、`combo_rate`等）取的是 `max` 而非累加**，这是合理的防溢出设计，但`hp_mult`、`atk_mult`等数值型属性是连乘叠加的，高波次极度膨胀。

**3. 天灾点经济的合理性**

- 奖励：1-5波 5点/波，6-10波 10点/波，11-20波 20点/波，21+波 30点/波。
- 商店定价：修炼加速50点（≈2-10波），战意加持30点（≈3-6波），称号200点（≈40波最高段或66波普通段）。
- 达成称号需要连续胜利约40场21+波或更多低波次胜利，时间成本约 40场 × 2小时间隔 = **80小时**以上。
- 对新手（1-10波）：50天灾点 = 需赢10场，修炼加速仅2小时，性价比偏低。
- 整体天灾点稀缺，商店物品价格偏贵，称号定价200点对中等波次玩家压力较大。

**4. 天灾商店内容的充实度**

- 实装商品只有3个：修炼加速、战意加持、称号「第四天灾」。
- 设计文档中第4个商品"大都会特供丹药（80点）"在实际 `SHOP_ITEMS` 中**完全未实现**，仅设计文档中有描述（"待扩展"）。
- 三个商品功能方向有限：修炼（PvE成长）、战斗buff（当次迎战用）、永久称号（一次性）。缺乏物品获取类、经济类商品。

**5. 失败惩罚是否过重**

- 失败后封印24小时，期间无法进行任何下位世界操作。
- 每2小时才有一波英雄，24小时 = 12波次机会损失。
- 没有任何减轻封印的机制（道具、消耗天灾点缩短等）。
- 封印期间波次不推进，玩家回来后需重新等2小时才有英雄。
- 设计文档叙事强调内疚感，但从游玩体验看，24小时封印对普通玩家而言体验很差，缺乏缓冲选项。

**6. 战斗机制的策略性**

- 战斗完全复用 `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2`，1v1无策略选择。
- 玩家没有任何主动干预手段（无技能选择、无装备切换、无逃跑机会）。
- 战意加持（30点）是唯一战前可用的增强手段，且仅+10%属性，效果有限。
- **`has_debuff: True` 字段在 `HERO_CLASSES` 的书勇者中定义了，但战斗引擎和命令处理器中均未对此字段做任何处理**，即书勇者的debuff效果是纸面设计，实际上不存在。
- 同理，英雄的 `lifesteal` 和 `ignore_defense` 字段被写入JSON存储并传入 `monster_stats`，但经验证 `integration_helper.py` 的怪物攻击路径中**不读取 `lifesteal` 字段**，**`ignore_defense` 字段也未被怪物攻击路径使用**（该字段仅在玩家装备触发的 `IGNORE_DEFENSE` Effect类型时使用）。

**7. 词缀系统的深度**

- 共8个词缀（`AFFIXES`），分别对应神圣、狂暴、守护、疾风、神明、诅咒、百战、破釜。
- 21-30波1个词缀，31+波2个词缀（无上限）。
- 词缀属性倍率设计多样，视觉效果（flavour_suffix）丰富。
- **问题**：词缀的 `lifesteal: 25`（诅咒之刃）字段由于战斗引擎不处理怪物的 `lifesteal`，这个词缀效果**实际上是哑的**，只是文案展示。
- 词缀特殊属性取 max 值防溢出，但数值叠乘可能在高波次造成属性溢出（如 `破釜沉舟` atk_mult=1.5 + 职业atk_mult=2.0 = 3.0倍攻击，再乘以等级膨胀，数值过大）。

**8. 文案和玩家体验**

- 文案质量高，叙事风格统一，有内疚感和人文关怀设计。
- 实现版本的 `commands.py` 中胜利/失败文案已大幅扩展（各8条普通/勇者文案池），优于设计文档中的单条文案，是正向改进。
- 按波次呈现不同叙事深度（1-5/6-10/11-20/21+波）的随机narrative设计已实现。
- 调用 `build_battle_markdown` 渲染战斗结果，说明接入了QQ平台的Markdown格式。
- **scheduler.py 注释明确说明 QQ 不支持主动私聊推送**，与设计文档中"推送通知"的设计有差距，玩家只能主动查询。

**9. 未实现的设计文档内容**

| 设计内容 | 实现状态 |
|---------|---------|
| 大都会特供丹药（80点商店物品） | ❌ 未实现，代码无此商品 |
| 英雄到达时发送QQ通知 | ❌ 未实现（QQ限制，改为玩家主动查询） |
| 书勇者debuff效果 | ❌ `has_debuff` 字段未被战斗引擎读取 |
| 弓勇者 ignore_defense | ❌ 字段存储但怪物攻击不读取 |
| 镰勇者/诅咒词缀 lifesteal | ❌ 字段存储但怪物攻击不读取 |
| 独立 shop.py 文件 | ❌ 设计文档规划独立文件，实际并入 service.py |

**10. Bug与逻辑漏洞**

- **严重Bug（commands.py 126/155/178/227行）**：`_show_stronghold_status` 函数内所有 `await cmd.finish()` 均硬编码为 `descend_cmd.finish`，但此函数被 `guard_cmd.handle_guard` 调用。当玩家通过【镇守】触发时，会使用 `descend_cmd.finish` 而非 `guard_cmd.finish`，导致 NoneBot2 的 Matcher 状态异常（finish 应该属于当前 Matcher），可能引发意外行为。
- **逻辑漏洞（wave_number 判断时机）**：`commands.py` 371行和545行在 `process_battle_victory` 调用之后才判断 `wave_number <= 10`，而 `process_battle_victory` 已将 `wave_number += 1`。因此第10波胜利后 wave_number 变为11，但文案判断仍走 `<= 10` 的分支（因为371行在 process_battle_victory 返回的 `points` 之后，而 stronghold.wave_number 已更新为11，所以实际是 `11 <= 10` = False，正确走勇者文案）。实际验证：胜利逻辑调用顺序是先 `process_battle_victory`（wave_number变11），再判断 `stronghold.wave_number <= 10`（11<=10为False），**文案切换发生在第10波胜利后，这是正确的**。这里不是bug，但代码逻辑不直观。
- **逻辑漏洞（封印结束后无自动恢复）**：`process_battle_defeat` 将 `next_wave_at` 设为None，封印结束后需玩家主动触发【镇守】或【迎战】才能重新安排下一波，定时任务 `scheduler.py` 会处理此情况（有检查 `next_wave_at` 的逻辑）。但【迎战】命令在 `next_wave_at is None` 且未超时时，执行 `time_until_next = stronghold.next_wave_at - datetime.now()` 会抛出 `TypeError`（NoneType - datetime），因为代码第289行 `time_until_next = stronghold.next_wave_at - datetime.now()` 在 `next_wave_at is None` 时会崩溃。封印结束时若定时器尚未触发，玩家使用【迎战】可能触发此错误。
- **战斗冷却字段缺失迁移**：`last_battle_at` 字段在 `models/lower_world.py` 中定义，但设计文档和实现计划均未提及，说明是后期加入的。若数据库已有旧数据，需要通过 `auto_migrate.py` 的 `REQUIRED_FIELDS` 添加迁移，否则读取 `stronghold.last_battle_at` 可能报错（字段不存在）。需确认此字段是否已加入 `auto_migrate.py`。

---

#### conclusions

- 波次机制设计为永远递增，无上限无重置，长期运行必然进入英雄无法击败的局面。
- 英雄属性缩放在高波次（15波以上勇者+词缀）膨胀过快，与玩家等级差距形成不可逾越的鸿沟。
- 天灾点奖励经济偏紧，商店物品3个，设计文档的第4个商品（丹药80点）未实现。
- 24小时封印无缓冲机制，惩罚较重，缺乏减免选项。
- 战斗无策略性，玩家唯一可做的事是等待+发命令，战意加持是唯一主动干预手段。
- 词缀系统文案丰富，但 `lifesteal`、`ignore_defense`、`has_debuff` 等词缀效果未被战斗引擎真正执行，是纸面功能。
- 文案质量是该系统最大亮点，比设计文档更丰富（各8条随机文案池，按波次切换叙事深度）。
- `_show_stronghold_status` 中所有 finish 硬编码为 `descend_cmd.finish` 是一个会导致 Matcher 异常的严重 Bug。
- 封印结束后 `next_wave_at` 为 None 时，玩家使用【迎战】命令存在 TypeError 崩溃风险。
- QQ私聊通知推送设计被放弃（平台限制），玩家体验变为被动轮询，丢失了波次到达的即时感。

---

#### relations

- `commands.py` (`_show_stronghold_status`) 调用 `service.py` (`is_sealed`, `has_pending_hero`, `format_time_remaining`)，并在内部开启新的 UnitOfWork 以安排下一波——这是在 UoW 外层再嵌套新 UoW，属于反模式但功能可行。
- `commands.py` (`handle_battle_hero`) 调用 `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2`，传入 `monster_stats` 字典（含 `crit_rate`、`combo_rate`、`counter_rate`），然后调用 `service.process_battle_victory` 或 `process_battle_defeat`。
- `service.py` (`process_battle_victory`) 调用 `schedule_next_wave`，后者调用 `hero_generator.generate_hero`，生成包含词缀的完整英雄JSON存入 `pending_hero` 字段。
- `commands.py` (`handle_redeem`) 对 `battle_boost` 商品：写入 `TemporaryBuff` 记录，在迎战命令的 `handle_battle_hero` 中通过直接SQL查询读取并消耗（标记 `is_active=False`）。`attribute_bonuses` 字段通过 `BuffAttributeSource` 由属性计算系统自动应用到战斗属性。
- `commands.py` (`handle_redeem`) 对 `cultivate_boost` 商品：写入 `TemporaryBuff`，`extra_data.cultivation_efficiency=0.5`，在 `cultivate/core.py` 约183行读取并叠加到修炼经验计算中，**此效果已实装**。
- `commands.py` (`handle_redeem`) 对 `title_calamity` 商品：通过 `KnockerEventService._get_player_data/_set_player_data` 读写 `player.extra` 字段的JSON数据，将称号写入 `owned_titles` 列表。
- `scheduler.py` (`generate_hero_waves`) 每2小时全表扫描 `LowerWorldStronghold`，跳过封印中/有英雄的/未到时间的山寨，其余调用 `schedule_next_wave`，无私聊通知。
