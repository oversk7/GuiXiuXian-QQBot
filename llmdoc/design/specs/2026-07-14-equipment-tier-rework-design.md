# 装备档位重构（等级拉开·锻造/掉落分流·全量数值调整）

> 本文保留当时的存量装备方案。当前等级与品质已拆为两个配置维度，新增装备与存量保护规则见[装备等级与品质配置](../../guides/equipment-quality-stage-guide.md)；下文的颜色门槛表仅描述这批存量装备。

> 2026-07-14 · 动机：升级速度快导致过渡装备被跳过（没人锻造，直奔橙装）；
> 高比例严格碾压低比例，装备无选择空间；掉落池=锻造池，不存在"只能靠运气获得的东西"。
> 方向已拍板：不动升级速度，拉开装备档位（含转数门槛）；每档留一攻一防可锻造，
> 其余转纯掉落；本体等强、差异全靠词缀；只调存量装备数值，不加新装备。

## 1. 档位框架

| 档位 | 入门要求 | 在役区间 | 锻造 | 掉落 |
|---|---|---|---|---|
| ⚪ 白 | lv1~10 | 1→40 | 2件 | 2件 |
| 🟢 绿 | lv40 | 40→100 | 2件 | 8件 |
| 🔵 蓝 | lv100 | 100→200 | 2件 | 5件 |
| 🟣 紫 | lv200 | 200→300（0转毕业） | 2件 | 5件 |
| 🟠 橙 | **1转 + lv150** | 冥返后毕业 | 2件 | 2件 |

- 橙装新增 `required_reincarnation: 1` 字段。**穿戴检查必须用 `player.reincarnation_level >= required_reincarnation`（≥，二转/三转均可穿），禁止用 ==**。
- 0转玩家可持有/拍卖橙装掉落，只是穿不上——给冥返（耗怨念=镇厄×10）加硬动机。
- 等级/转数检查只在【穿戴】动作时执行，**不追溯**：已穿戴的装备不强制卸下；
  冥返重算装备加成时保持穿戴状态（reincarnation_service._recalculate_equipment_bonus 现状即如此，勿改）。
- 锻造/掉落划分原则：锻造件=每档一攻一防"基本盘"；掉落件=特化方向+套装件。
  本体数值同档等强（同一 ratio 总预算，只换方向），掉落件的溢价完全来自词缀
  （锻造出素装、掉落按稀有度带2~4条词缀，现有词缀系统不动）。

## 2. 全量数值表（32件非红装备）

通用规则：ratio 总预算 绿0.25 / 蓝0.50 / 紫0.90 / 橙1.40（白档无 ratio）；
gem_slots 统一 白1/绿2/蓝3/紫4/橙5；durability 统一 白(保持)/绿100/蓝140/紫180/橙250；
repair_cost 统一 白5/绿15/蓝50/紫120/橙200。price 数值定稿后跑 `tools/price_calibration.py` 校准。

### ⚪ 白档（等级保持 1/5/7/10，0转，纯固定值）

| 装备 | 获取 | 定位 | attr_bonus |
|---|---|---|---|
| 白骨护甲 lv1 | 锻造 | 防 | hp 50, defense 10 |
| 鬼泪吊坠 lv5 | 掉落 | 法运 | mp 45, luck 10 |
| 破眼镜 lv7 | 掉落 | 攻运 | attack 14, luck 10 |
| 锈蚀刀刃 lv10 | 锻造 | 攻敏 | attack 18, agility 8 |

### 🟢 绿档（全部 required_level: 40）

| 装备 | 获取 | 定位 | attr_bonus | attr_ratio |
|---|---|---|---|---|
| 病号服 | 锻造 | 防 | hp 100, defense 25 | hp 0.15, defense 0.10 |
| 菜刀 | 锻造 | 攻 | attack 35, agility 15 | attack 0.18, agility 0.07 |
| 溺水者外衣 | 掉落 | 纯血 | hp 150 | hp 0.25 |
| 旧大衣 | 掉落 | 防血 | defense 25, hp 80 | defense 0.13, hp 0.12 |
| 污血绷带 | 掉落 | 硬防 | defense 32, hp 55 | defense 0.17, hp 0.08 |
| 结婚照 | 掉落 | 运法 | mp 70, luck 20 | luck 0.14, mp 0.11 |
| 自知力钥匙 | 掉落 | 纯法 | mp 110 | mp 0.20, luck 0.05 |
| 校服 | 掉落 | 敏法 | mp 65, agility 18 | agility 0.14, mp 0.11 |
| 八音盒 | 掉落 | 法运 | mp 85, luck 15 | mp 0.17, luck 0.08 |
| 花圈 | 掉落 | 血法 | mp 70, hp 60 | mp 0.13, hp 0.12 |

### 🔵 蓝档（全部 required_level: 100）

| 装备 | 获取 | 定位 | attr_bonus | attr_ratio |
|---|---|---|---|---|
| 镜片战甲 | 锻造 | 防 | hp 150, defense 45 | hp 0.30, defense 0.20 |
| 镇魂幡 | 锻造 | 攻法 | attack 50, mp 90 | attack 0.30, mp 0.20 |
| 幽魂斗篷 | 掉落 | 纯敏 | agility 45 | agility 0.40, luck 0.10 |
| 雾都风衣 | 掉落 | 敏运 | agility 32, luck 18 | agility 0.28, luck 0.22 |
| 幸运剪刀 | 掉落 | 运敏 | luck 32, agility 18 | luck 0.32, agility 0.18 |
| 哭泣的磁带 | 掉落 | 法运 | mp 100, luck 22 | mp 0.32, luck 0.18 |
| 老爷钟 | 掉落 | 防法 | defense 45, mp 80 | mp 0.28, defense 0.22 |

### 🟣 紫档（全部 required_level: 200）

| 装备 | 获取 | 定位 | attr_bonus | attr_ratio |
|---|---|---|---|---|
| 抽屉 | 锻造 | 血攻 | hp 180, attack 55 | hp 0.50, attack 0.40 |
| 嫁衣 | 锻造 | 攻敏 | attack 75, agility 45 | attack 0.55, agility 0.35 |
| 黑色信封 | 掉落 | 攻运 | attack 70, luck 35 | attack 0.55, luck 0.35 |
| 无脸制服 | 掉落 | 法敏 | mp 130, agility 55 | mp 0.55, agility 0.35 |
| 碎颅制服 | 掉落 | 攻防 | attack 80, defense 45 | attack 0.55, defense 0.35 |
| 虚无之冠 | 掉落 | 法运攻 | mp 110, luck 50, attack 45 | mp 0.40, luck 0.30, attack 0.20 |
| 电击治疗仪 | 掉落 | 攻敏 | attack 85, agility 60 | attack 0.50, agility 0.40 |

### 🟠 橙档（全部 required_level: 150 + required_reincarnation: 1）

| 装备 | 获取 | 定位 | attr_bonus | attr_ratio |
|---|---|---|---|---|
| 寿衣 | 锻造 | 纯防 | hp 300, defense 110 | hp 0.80, defense 0.60 |
| 神泪护符 | 锻造 | 防辅 | hp 200, mp 180, defense 80 | hp 0.50, mp 0.50, defense 0.40 |
| 现实遗书 | 掉落 | 攻法 | attack 180, mp 240 | attack 0.80, mp 0.60 |
| 世界碎片之刃 | 掉落 | 攻敏运 | attack 140, agility 80 | attack 0.70, agility 0.42, luck 0.28 |

不动：炼丹炉（功能装备）、13件红色VIP定制装备。
套装配置（equipment_sets.yaml）不改，件数关系自然变为：凌晨3:33/雾都猎手/疯人院全靠掉落凑，
金陵魇、崩塌纪元为锻造+掉落混合。

## 3. 掉落分段（dungeon_generation_service）

与新档位对齐（`required_level <= monster_level` 过滤保持）：

| 怪物等级 | 普通怪池 | 精英怪池 |
|---|---|---|
| ≤40 | white | white |
| 41~100 | white, green | green |
| 101~200 | green, blue | blue |
| 200+ | blue, purple | purple, purple, orange |

- 掉率微调（掉落已是18件装备唯一来源，属获取路径转移非放水）：精英 8%→按段 8/9/10/12%，普通保持 1%~2.5%。
- **候选池为空时按稀有度降档回退**（现状是直接不掉，浪费掉率判定；如 lv150 精英抽中 blue 正常，
  但 200+ 精英抽中 orange 而 monster_level<orange 要求时需回退）。

## 4. 兼容与迁移

- 删配方的18件：自动进入稀有装备升阶通道（1件本体+特殊材料，equipment_upgrade_service.is_rare_equipment 按"无recipe"判定，零代码改动）。已锻造/已持有的实例不受影响。
- required_level 提升不追溯：lv85 穿着幸运剪刀的玩家照常穿，卸下后需 lv100 才能再穿。
- 0转 175+ 玩家已穿的橙装照常穿；新穿需 1转。
- 更新公告要点：档位重划表、"已持有/已穿戴完全不受影响"、哪些装备转掉落、橙装转数门槛。

## 5. 实现清单

1. `data/items.yaml`：32件数值/required_level/gem_slots/durability/repair_cost；18件删 recipe；4件橙装加 required_reincarnation
2. `models/inventory.py` ItemConfig：解析 `required_reincarnation`（默认0）
3. `item/equipment_commands.py:497`（单穿）与 `:595`（一键穿戴）：加转数检查，
   `player.reincarnation_level < (cfg.required_reincarnation or 0)` 时拒绝，提示"需X转"；**用 >= 语义，二转以上必须能穿**
4. `world/dungeon_generation_service.py:534`：掉落分段表 + 空池降档回退
5. 展示层：装备详情（equipment_commands.py:292）、图鉴（catalog.py:491/702）、锻造列表（equipment_craft.py）显示转数要求
6. `data/knowledge/equip_system_help.yaml`：档位/获取途径帮助文案
7. `tools/price_calibration.py` 跑价格校准，回填 price
8. 更新公告（QQ内【发消息 系统】）

验证：0/1/2转玩家穿橙装的三态用例（0转拒绝、1转/2转通过）；冥返后已穿橙装不掉；
锻造列表只剩10件+炼丹炉；空池降档回退不再空掉。
