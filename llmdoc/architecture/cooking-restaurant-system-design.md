# 烹饪与餐厅经营系统设计

> **状态**: 设计完成，待实现
> **创建日期**: 2026-02-08
> **设计者**: 头脑风暴 (Claude Code + 用户)

---

## 1. 核心定位

**"当老板开餐厅"** — 侧重娱乐体验 + 经济循环。

玩家经营一家餐厅，雇佣不同等级的厨师NPC，供应从钓鱼/跑商/诡域获取的食材，按小时自动经营获取收入。玩家负责宏观管理（补货、雇佣、查看日志），不亲自下厨。

### 设计决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 系统定位 | 娱乐+经济循环 | 让鱼类有价值转化渠道 |
| 复杂度 | 食谱配方+多层进阶 | 有成长深度 |
| 材料来源 | 鱼+新增调料+现有材料 | 联动钓鱼/跑商/诡域 |
| 吃鱼命令 | 泛用【吃】替代【吃鱼】 | 支持吃所有食物 |
| 餐厅位置 | 抽象不绑地图 | 降低复杂度 |
| 厨师获取 | 随机招募→选择雇佣 | 有趣+有策略 |
| 经营节奏 | 按小时更新 | 适合挂机经营 |
| 食谱获取 | 默认食谱+购买食谱道具 | 可扩展氪金食谱 |
| 烹饪品质 | 可失败+品质浮动 | 增加刺激感 |
| 厨师等级 | 厨师NPC有独立等级 | 致敬神厨小福贵 |
| 菜肴buff | 高级菜有小buff(如回复理智) | 不喧宾夺主 |

---

## 2. 餐厅系统

### 2.1 餐厅属性

餐厅为玩家拥有的抽象实体（不绑定地图坐标），一个玩家只有一家餐厅。

| 属性 | 说明 | 初始值 | 升级效果 |
|------|------|--------|----------|
| level | 餐厅总等级(1-10) | 1 | 解锁功能和升级其他属性的前提 |
| area | 面积/席位数 | 10 | 每次扩张+5席，影响每小时客流上限 |
| kitchen_level | 厨房等级(1-5) | 1 | 解锁更高级食谱的制作 |
| reputation | 声望(0-10000) | 0 | 通过经营积累，影响客流量和顾客消费意愿 |
| max_chefs | 厨师上限 | 1 | 每2个餐厅等级+1，最高6人 |
| storage_capacity | 食材仓库容量 | 50 | 可升级扩展 |

### 2.2 升级消耗

```
等级1→2: 5,000金 + 灵骨×5
等级2→3: 15,000金 + 灵骨×10 + 铁锈×10
等级3→4: 50,000金 + 阴煞精华×5 + 梦魇丝线×3
等级4→5: 150,000金 + 血肉结晶×3
等级5→6: 300,000金 + 血肉结晶×5 + 魂魄结晶×2
等级6→7: 500,000金 + 魂魄结晶×3 + 诅咒镜片×2
等级7→8: 800,000金 + 恶魔之心×1 + 虚无精华×1
等级8→9: 1,200,000金 + 恶魔之心×2
等级9→10: 2,000,000金 + 神明之泪×1
```

### 2.3 面积扩张

每次扩张+5席位，消耗金币递增：
```
10→15席: 2,000金
15→20席: 5,000金
20→25席: 10,000金
... 以此类推，每次消耗×2
最大: 50席
```

### 2.4 厨房升级

厨房等级决定可制作的食谱等级：
```
厨房Lv1: 可制作白色家常菜
厨房Lv2: 可制作绿色特色菜（需餐厅等级≥3）
厨房Lv3: 可制作蓝色招牌菜（需餐厅等级≥5）
厨房Lv4: 可制作紫色宴席菜（需餐厅等级≥7）
厨房Lv5: 可制作橙色传说菜（需餐厅等级≥9）
```

---

## 3. 厨师系统

### 3.1 厨师等级

致敬《神厨小福贵》，厨师NPC分5个等级：

| 等级 | 稀有度 | 成功率 | 精致率 | 完美率 | 速度(菜/时) | 时薪(金币) |
|------|--------|--------|--------|--------|-------------|-----------|
| 学徒厨师 | 白 | 70% | 10% | 2% | 2 | 20 |
| 帮厨 | 绿 | 80% | 18% | 5% | 3 | 50 |
| 厨师 | 蓝 | 88% | 25% | 10% | 4 | 120 |
| 大厨 | 紫 | 94% | 35% | 18% | 5 | 300 |
| 特级厨师 | 橙 | 98% | 45% | 28% | 6 | 800 |

### 3.2 厨师属性

每个厨师NPC是独立实体，具有：
- **name**: 随机生成的名字
- **tier**: 等级（学徒/帮厨/厨师/大厨/特级厨师）
- **skill**: 厨艺值（影响成功率和品质，同等级内有浮动±5%）
- **speed**: 速度值（每小时可制作菜肴数）
- **specialty**: 擅长类别（鱼类/汤类/烤制/蒸煮/甜点，随机分配）
  - 做擅长类菜品时：成功率+10%、精致率+15%
- **personality**: 性格标签（勤劳/懒散/完美主义/节俭/话痨），影响日志文本风格
- **salary**: 时薪

### 3.3 招募机制

1. 玩家使用【招募厨师】，消耗 500 金币招募费
2. 系统生成 3~5 个随机厨师候选，展示属性
3. 候选池稀有度概率：白60% / 绿25% / 蓝10% / 紫4% / 橙1%
4. 玩家使用【雇佣 编号】选择其中一个，支付签约费：
   - 白: 500金 / 绿: 2,000金 / 蓝: 8,000金 / 紫: 30,000金 / 橙: 100,000金
5. 候选列表在下次招募时刷新
6. 可使用【解雇 厨师名】释放名额（不退签约费）

### 3.4 厨师性格对日志的影响

性格标签影响经营日志中厨师的"旁白"文案，纯娱乐效果：
```
勤劳: "小福贵擦了擦汗，又熟练地开始准备下一道菜。"
懒散: "阿旺打了个哈欠，慢悠悠地拿起了锅铲。"
完美主义: "陈大厨对摆盘不满意，重新调整了三次。"
节俭: "老王心疼地看着用掉的灵芝粉，嘟囔着太浪费了。"
话痨: "小李一边炒菜一边给顾客讲自己当年学艺的故事。"
```

---

## 4. 食谱系统

### 4.1 食谱等级

| 等级 | 稀有度 | 厨房等级要求 | 获取方式 |
|------|--------|-------------|---------|
| 家常菜 | 白 | 1 | 开餐厅默认自带 |
| 特色菜 | 绿 | 2 | 商店购买 (500-1500金) |
| 招牌菜 | 蓝 | 3 | 商店购买/NPC好感度奖励 (3000-8000金) |
| 宴席菜 | 紫 | 4 | 诡域掉落/特殊任务 |
| 传说菜 | 橙 | 5 | 氪金/极稀有掉落 |

### 4.2 食谱道具

食谱为 `RECIPE` 类型物品，使用后永久学会，可在市场交易。

### 4.3 菜品分类

每道菜有一个烹饪类别，对应厨师擅长系统：
- **鱼鲜类**: 以鱼类为主料
- **汤煲类**: 汤、粥、煲
- **烤制类**: 烧烤、炙烤
- **蒸煮类**: 清蒸、水煮
- **甜点类**: 甜品、点心

### 4.4 默认食谱列表（家常菜 - 白色）

开餐厅时自动获得：

```yaml
- recipe_id: "braised_carp"
  name: "红烧鲤鱼"
  category: "鱼鲜"
  tier: "white"
  ingredients:
    common_carp: 1    # 鲤鱼
    soy_sauce: 1      # 酱油
  base_price: 120     # 基础售价
  description: "色泽红亮，肉质鲜嫩的经典家常菜"

- recipe_id: "steamed_crucian"
  name: "清蒸鲫鱼"
  category: "蒸煮"
  tier: "white"
  ingredients:
    crucian_carp: 1   # 鲫鱼
    salt: 1           # 盐
  base_price: 95
  description: "清淡鲜美，保留鱼肉原汁原味"

- recipe_id: "grass_carp_soup"
  name: "草鱼豆腐汤"
  category: "汤煲"
  tier: "white"
  ingredients:
    grass_carp: 1     # 草鱼
    salt: 1           # 盐
  base_price: 130
  description: "汤白如乳，鲜美无比"

- recipe_id: "silver_carp_head_soup"
  name: "鲢鱼头汤"
  category: "汤煲"
  tier: "white"
  ingredients:
    silver_carp: 1    # 鲢鱼
    salt: 1
    sugar: 1
  base_price: 110
  description: "浓郁鲜香的鱼头汤"

- recipe_id: "fried_catfish"
  name: "香煎鲶鱼"
  category: "烤制"
  tier: "white"
  ingredients:
    catfish: 1        # 鲶鱼
    salt: 1
  base_price: 150
  description: "外酥里嫩，香气四溢"
```

### 4.5 商店食谱示例（特色菜 - 绿色）

```yaml
- recipe_id: "sweet_sour_bass"
  name: "糖醋鲈鱼"
  category: "鱼鲜"
  tier: "green"
  ingredients:
    bass: 1           # 鲈鱼
    vinegar: 1        # 醋
    sugar: 1          # 糖
  base_price: 320
  description: "酸甜适口，外酥内嫩"

- recipe_id: "braised_mandarin_fish"
  name: "酱焖桂鱼"
  category: "鱼鲜"
  tier: "green"
  ingredients:
    mandarin_fish: 1  # 桂鱼
    soy_sauce: 2      # 酱油×2
    spice: 1          # 香料
  base_price: 420
  description: "浓郁酱香，肉质细嫩"

- recipe_id: "yellow_croaker_soup"
  name: "黄花鱼羹"
  category: "汤煲"
  tier: "green"
  ingredients:
    yellow_croaker: 1 # 黄花鱼
    salt: 1
    spice: 1
  base_price: 450
  description: "鲜美浓稠的鱼羹"

- recipe_id: "steamed_pomfret"
  name: "清蒸鲳鱼"
  category: "蒸煮"
  tier: "green"
  ingredients:
    pomfret: 1        # 鲳鱼
    soy_sauce: 1
    spice: 1
  base_price: 380
  description: "鲜嫩爽滑，回味无穷"

- recipe_id: "grilled_snapper"
  name: "炭烤鲷鱼"
  category: "烤制"
  tier: "green"
  ingredients:
    snapper: 1        # 鲷鱼
    salt: 1
    spice: 1
  base_price: 500
  description: "表面焦香，内里多汁"
```

### 4.6 高级食谱示例（招牌菜 - 蓝色）

```yaml
- recipe_id: "salmon_sashimi"
  name: "三文鱼刺身"
  category: "鱼鲜"
  tier: "blue"
  ingredients:
    salmon: 1         # 三文鱼
    wasabi: 1         # 芥末
    soy_sauce: 1
  base_price: 900
  description: "新鲜肥美的顶级刺身"

- recipe_id: "tuna_sushi"
  name: "金枪鱼寿司"
  category: "鱼鲜"
  tier: "blue"
  ingredients:
    tuna: 1           # 金枪鱼
    vinegar: 1
    sugar: 1
    wasabi: 1
  base_price: 1050
  description: "口感绝佳的握寿司"

- recipe_id: "grouper_hotpot"
  name: "石斑鱼火锅"
  category: "汤煲"
  tier: "blue"
  ingredients:
    grouper: 1        # 石斑鱼
    spice: 2
    lingzhi_powder: 1 # 灵芝粉
  base_price: 1200
  description: "鲜美滚烫，暖身补气"

- recipe_id: "grilled_eel"
  name: "蒲烧鳗鱼"
  category: "烤制"
  tier: "blue"
  ingredients:
    eel: 1            # 鳗鱼
    soy_sauce: 2
    sugar: 1
    spice: 1
  base_price: 980
  description: "酱汁浓郁，肉质绵密"

- recipe_id: "turbot_feast"
  name: "清蒸多宝鱼"
  category: "蒸煮"
  tier: "blue"
  ingredients:
    turbot: 1         # 多宝鱼
    spice: 1
    lingzhi_powder: 1
  base_price: 1100
  description: "原汁原味的高端海鲜"
```

### 4.7 宴席菜示例（紫色）

```yaml
- recipe_id: "sturgeon_banquet"
  name: "鲟鱼全席"
  category: "鱼鲜"
  tier: "purple"
  ingredients:
    chinese_sturgeon: 1   # 中华鲟
    lingzhi_powder: 2     # 灵芝粉×2
    spice: 2
    secret_sauce: 1       # 秘制酱料
  base_price: 3500
  buff: { sanity: 8 }    # 完美品质时回复8点理智
  description: "以珍稀中华鲟为主料的豪华宴席"

- recipe_id: "arowana_feast"
  name: "龙鱼宴"
  category: "鱼鲜"
  tier: "purple"
  ingredients:
    arowana: 1            # 龙鱼
    lingzhi_powder: 1
    spice: 2
    flesh_crystal: 1      # 血肉结晶(现有材料)
  base_price: 4200
  buff: { sanity: 10 }
  description: "龙鱼入馔，尊贵非凡"

- recipe_id: "giant_catfish_stew"
  name: "巨鲶秘炖"
  category: "汤煲"
  tier: "purple"
  ingredients:
    giant_catfish: 1      # 巨型鲶鱼
    lingzhi_powder: 1
    secret_sauce: 1
    soul_crystal: 1       # 魂魄结晶(现有材料)
  base_price: 3800
  buff: { sanity: 6 }
  description: "用深渊食材慢炖的神秘汤品"

- recipe_id: "bluefin_tuna_omakase"
  name: "蓝鳍料理长"
  category: "鱼鲜"
  tier: "purple"
  ingredients:
    bluefin_tuna: 1       # 蓝鳍金枪鱼
    wasabi: 2
    soy_sauce: 2
    secret_sauce: 1
  base_price: 3200
  buff: { sanity: 5 }
  description: "极致鲜美的蓝鳍盛宴"
```

### 4.8 传说菜示例（橙色）

```yaml
- recipe_id: "golden_dragon_feast"
  name: "金龙盛宴"
  category: "鱼鲜"
  tier: "orange"
  ingredients:
    golden_dragon_fish: 1 # 金龙鱼
    god_tear: 1           # 神明之泪(现有材料)
    lingzhi_powder: 2
    secret_sauce: 2
    immortal_oil: 1       # 仙厨秘油
  base_price: 15000
  buff: { sanity: 20, luck: 5, duration: 30 }  # 回复20理智 + 30分钟幸运+5
  description: "以金龙鱼和神明之泪烹制的天界珍馐"

- recipe_id: "phoenix_nirvana_fish"
  name: "凤凰涅槃鱼"
  category: "烤制"
  tier: "orange"
  ingredients:
    phoenix_fish: 1       # 凤凰鱼
    lingzhi_powder: 2
    secret_sauce: 2
    immortal_oil: 1
    demon_heart: 1        # 恶魔之心(现有材料)
  base_price: 18000
  buff: { sanity: 15, max_hp: 200, duration: 60 }
  description: "浴火重生的传说料理，食之如获新生"

- recipe_id: "void_fish_enigma"
  name: "虚空秘境鱼"
  category: "蒸煮"
  tier: "orange"
  ingredients:
    void_fish: 1          # 虚空鱼
    void_essence: 1       # 虚无精华(现有材料)
    immortal_oil: 1
    secret_sauce: 1
    lingzhi_powder: 2
  base_price: 20000
  buff: { sanity: 25, luck: 8, duration: 45 }
  description: "超越现实的诡异料理，品尝者将短暂触碰虚空的真相"
```

---

## 5. 食材/调料系统

### 5.1 新增调料物品

在 `items.yaml` 中新增 `seasonings` 分类，类型为 `SEASONING`：

```yaml
seasonings:
  # ========== 白色（基础调料，NPC商店常驻） ==========
  - item_id: "salt"
    name: "盐"
    type: "SEASONING"
    rarity: "white"
    price: 5
    description: "基础调味料，百味之首"

  - item_id: "soy_sauce"
    name: "酱油"
    type: "SEASONING"
    rarity: "white"
    price: 8
    description: "酿造酱油，增色提鲜"

  - item_id: "vinegar"
    name: "醋"
    type: "SEASONING"
    rarity: "white"
    price: 8
    description: "陈年老醋，酸香醇厚"

  - item_id: "sugar"
    name: "糖"
    type: "SEASONING"
    rarity: "white"
    price: 6
    description: "甜蜜调味，中和苦涩"

  # ========== 绿色（进阶调料，NPC商店/跑商市集） ==========
  - item_id: "spice"
    name: "香料"
    type: "SEASONING"
    rarity: "green"
    price: 30
    description: "混合香辛料，增添风味层次"

  - item_id: "wasabi"
    name: "芥末"
    type: "SEASONING"
    rarity: "green"
    price: 40
    description: "冲鼻辛辣，刺身绝配，舟山特产"

  # ========== 蓝色（高级调料，跑商/诡域） ==========
  - item_id: "lingzhi_powder"
    name: "灵芝粉"
    type: "SEASONING"
    rarity: "blue"
    price: 150
    description: "磨碎的灵芝粉末，入菜可增益身心"

  # ========== 紫色（稀有调料） ==========
  - item_id: "secret_sauce"
    name: "秘制酱料"
    type: "SEASONING"
    rarity: "purple"
    price: 500
    description: "以十二味珍稀食材秘制而成的神秘酱料"

  # ========== 橙色（传说调料） ==========
  - item_id: "immortal_oil"
    name: "仙厨秘油"
    type: "SEASONING"
    rarity: "orange"
    price: 2000
    description: "传说中仙人炼制的烹饪用油，沾之生香"
```

### 5.2 食材来源汇总

| 来源 | 食材类型 | 说明 |
|------|---------|------|
| 钓鱼系统 | 鱼类(22种) | 5个稀有度，主要食材 |
| NPC商店(新增) | 基础调料(盐/酱油/醋/糖) | 低价常驻，金币购买 |
| 跑商市集 | 进阶调料(香料/芥末) | 特定市集特产，如舟山的芥末 |
| 诡域掉落 | 高级调料(灵芝粉/秘制酱料) | 稀有掉落 |
| 现有材料 | 血肉结晶/魂魄结晶/恶魔之心等 | 紫/橙色食谱需要 |
| 氪金/极稀有 | 仙厨秘油 | 传说食谱专用 |

---

## 6. 菜肴品质系统

### 6.1 品质等级

| 品质 | 产出条件 | 售价倍率 | 特殊效果 |
|------|---------|---------|---------|
| 黑暗料理 | 烹饪失败 | 0.1x | 吃了扣2理智(娱乐效果) |
| 普通 | 成功但未触发精致/完美 | 1.0x | 无 |
| 精致 | 触发厨师精致率 | 1.5x | 无 |
| 完美 | 触发厨师完美率 | 2.5x | 紫/橙菜肴附带buff |

### 6.2 品质判定流程

```
1. 先判定成功/失败（厨师成功率 + 擅长加成）
2. 若失败 → 产出黑暗料理，消耗50%食材
3. 若成功 → 判定品质：
   a. roll完美率 → 完美品质
   b. roll精致率 → 精致品质
   c. 否则 → 普通品质
```

### 6.3 菜肴作为物品

烹饪产出的菜肴是 `DISH` 类型物品，存储在玩家背包或餐厅食材仓库中：
- 可通过【吃 菜名】食用
- 可在市场挂牌交易
- 餐厅经营时自动消耗并卖给NPC顾客

### 6.4 高级菜buff效果

仅当菜肴品质为"完美"且食谱等级≥紫色时触发：
- 紫色完美菜：回复 5~10 点理智
- 橙色完美菜：回复 15~25 点理智 + 临时buff（幸运/生命等，持续30~60分钟）

---

## 7. 餐厅经营循环

### 7.1 每小时自动结算

餐厅营业状态下，系统每小时执行一次结算：

```
1. 计算客流量
   客流 = min(面积席位, 基础客流 × 声望系数)
   基础客流 = 5 + 餐厅等级 × 2
   声望系数 = 1.0 + (声望 / 2000)  # 最高6.0倍

2. 厨师制作菜品
   for 每个厨师:
     for i in range(厨师速度):
       从菜单中随机选一道菜
       检查食材库存是否足够
       若不足 → 跳过，记录"缺货"
       判定成功/品质
       产出菜肴

3. 顾客消费
   for 每位顾客:
     从产出的菜肴中选择一道消费
     收入 = 菜肴售价 × 品质倍率 × (1 + 声望/5000)

4. 扣除成本
   厨师工资 = sum(各厨师时薪)

5. 声望变化
   成功服务 → 声望+1~3/顾客
   缺货/黑暗料理 → 声望-2~5
   完美菜肴 → 额外声望+5

6. 记录经营日志
```

### 7.2 营业与打烊

- 【开店】开始营业，消耗食材仓库中的食材
- 【打烊】暂停营业，停止消耗
- 默认状态为打烊，需手动开店

### 7.3 食材仓库

玩家使用【补货 食材名 数量】将背包/鱼栏中的食材转移到餐厅仓库。
仓库有容量限制（可升级），每种食材独立计数。

### 7.4 经营日志

保留最近24小时（24条）日志记录，每条包含：
- 时间段
- 各厨师的制作详情（成功/失败/品质）
- 收入、支出、净利润
- 顾客数
- 库存预警

### 7.5 经营报表

汇总统计：
- 今日/本周总收入、总支出、净利润
- 最受欢迎菜品 TOP3
- 厨师绩效排名
- 食材消耗排名
- 声望变化趋势

---

## 8. 【吃】指令

### 8.1 替代现有【吃鱼】

新的【吃】指令为泛用食物食用指令，替代现有的【吃鱼】命令：

```
用法：吃 [食物名称] [数量]
示例：吃 红烧鲤鱼 1
示例：吃 鲤鱼 2        （直接吃生鱼，保留原有功能）
```

### 8.2 食用效果

- **生鱼**：纯娱乐文本（保留原吃鱼的风味描述），无实际效果
- **普通/精致菜肴**：恢复少量理智(1~3)（低级菜无效果）+ 风味文本
- **完美紫/橙菜肴**：回复理智 + 可能的临时buff
- **黑暗料理**：扣2点理智 + 搞笑文本

### 8.3 向后兼容

- 保留【吃鱼】作为【吃】的别名
- 【吃掉鱼】【品尝鱼】也作为别名

---

## 9. 指令总览

| 指令 | 说明 | 优先级 |
|------|------|--------|
| 【烹饪 菜名 数量】 | 手动制作菜肴（存入背包） | 5 |
| 【吃 食物名 数量】 | 食用任何食物 | 5 |
| 【餐厅】 | 查看餐厅状态 | 5 |
| 【开店】 | 开始营业 | 5 |
| 【打烊】 | 暂停营业 | 5 |
| 【餐厅升级】 | 升级餐厅等级 | 5 |
| 【扩张餐厅】 | 扩展面积 | 5 |
| 【升级厨房】 | 升级厨房等级 | 5 |
| 【招募厨师】 | 生成随机厨师候选 | 5 |
| 【雇佣 编号】 | 从候选中选择雇佣 | 5 |
| 【解雇 厨师名】 | 解雇厨师 | 5 |
| 【我的厨师】 | 查看已雇佣厨师列表 | 5 |
| 【补货 食材名 数量】 | 从背包转移食材到餐厅仓库 | 5 |
| 【菜单】 | 查看当前营业菜单 | 5 |
| 【设置菜单 菜名1 菜名2...】 | 设定营业菜品 | 5 |
| 【经营报表】 | 查看收入统计和日志 | 5 |
| 【食谱】 | 查看已学会的食谱列表 | 5 |
| 【食谱图鉴】 | 查看所有食谱（含未解锁） | 5 |

---

## 10. 数据模型设计

### 10.1 新增 ORM 模型

需要新建以下模型文件：

#### Restaurant 模型 (`models/restaurant.py`)

```python
class Restaurant(Base):
    __tablename__ = "restaurant"

    id: Mapped[int]                    # 主键
    player_id: Mapped[str]             # 玩家ID (unique)
    level: Mapped[int]                 # 餐厅等级 (1-10)
    area: Mapped[int]                  # 面积/席位 (默认10)
    kitchen_level: Mapped[int]         # 厨房等级 (1-5)
    reputation: Mapped[int]            # 声望 (0-10000)
    max_chefs: Mapped[int]             # 厨师上限
    storage_capacity: Mapped[int]      # 仓库容量
    is_open: Mapped[bool]              # 是否营业中
    total_income: Mapped[int]          # 累计总收入
    total_expense: Mapped[int]         # 累计总支出
    created_at: Mapped[datetime]       # 创建时间
    last_settlement: Mapped[datetime]  # 上次结算时间
```

#### Chef 模型 (`models/chef.py`)

```python
class Chef(Base):
    __tablename__ = "chef"

    id: Mapped[int]                    # 主键
    restaurant_id: Mapped[int]         # 所属餐厅ID (FK)
    name: Mapped[str]                  # 厨师名字
    tier: Mapped[str]                  # 等级: apprentice/helper/cook/head_chef/master_chef
    skill: Mapped[int]                 # 厨艺值
    speed: Mapped[int]                 # 速度（菜/时）
    specialty: Mapped[str]             # 擅长: fish/soup/grill/steam/dessert
    personality: Mapped[str]           # 性格: diligent/lazy/perfectionist/frugal/talkative
    salary: Mapped[int]               # 时薪
    hired_at: Mapped[datetime]         # 雇佣时间
```

#### ChefCandidate 模型（临时，可用缓存代替）

```python
class ChefCandidate(Base):
    __tablename__ = "chef_candidate"

    id: Mapped[int]
    player_id: Mapped[str]             # 招募发起人
    name: Mapped[str]
    tier: Mapped[str]
    skill: Mapped[int]
    speed: Mapped[int]
    specialty: Mapped[str]
    personality: Mapped[str]
    salary: Mapped[int]
    created_at: Mapped[datetime]       # 过期后可清理
```

#### RestaurantStorage 模型 (`models/restaurant.py` 或独立)

```python
class RestaurantStorage(Base):
    __tablename__ = "restaurant_storage"

    id: Mapped[int]
    restaurant_id: Mapped[int]         # FK
    item_id: Mapped[str]               # 食材物品ID
    quantity: Mapped[int]              # 数量
```

#### RestaurantMenu 模型

```python
class RestaurantMenu(Base):
    __tablename__ = "restaurant_menu"

    id: Mapped[int]
    restaurant_id: Mapped[int]         # FK
    recipe_id: Mapped[str]             # 食谱ID
    is_active: Mapped[bool]            # 是否在当前菜单上
```

#### RestaurantLog 模型

```python
class RestaurantLog(Base):
    __tablename__ = "restaurant_log"

    id: Mapped[int]
    restaurant_id: Mapped[int]         # FK
    period_start: Mapped[datetime]     # 时段开始
    period_end: Mapped[datetime]       # 时段结束
    income: Mapped[int]                # 本时段收入
    expense: Mapped[int]               # 本时段支出
    customers: Mapped[int]             # 顾客数
    dishes_made: Mapped[int]           # 制作菜品数
    dishes_failed: Mapped[int]         # 失败数
    details_json: Mapped[str]          # JSON详细日志
    reputation_change: Mapped[int]     # 声望变化
```

#### PlayerRecipe 模型

```python
class PlayerRecipe(Base):
    __tablename__ = "player_recipe"

    id: Mapped[int]
    player_id: Mapped[str]             # 玩家ID
    recipe_id: Mapped[str]             # 食谱ID
    learned_at: Mapped[datetime]       # 学会时间
```

### 10.2 新增枚举类型

```python
# 在 inventory.py 的 ItemType 枚举中新增：
class ItemType(str, PyEnum):
    ...
    SEASONING = "SEASONING"    # 调料
    DISH = "DISH"              # 菜肴
    RECIPE = "RECIPE"          # 食谱

# 厨师等级枚举
class ChefTier(str, PyEnum):
    APPRENTICE = "apprentice"      # 学徒厨师
    HELPER = "helper"              # 帮厨
    COOK = "cook"                  # 厨师
    HEAD_CHEF = "head_chef"        # 大厨
    MASTER_CHEF = "master_chef"    # 特级厨师

# 菜品分类枚举
class CookingCategory(str, PyEnum):
    FISH = "fish"          # 鱼鲜类
    SOUP = "soup"          # 汤煲类
    GRILL = "grill"        # 烤制类
    STEAM = "steam"        # 蒸煮类
    DESSERT = "dessert"    # 甜点类

# 菜肴品质枚举
class DishQuality(str, PyEnum):
    DARK = "dark"          # 黑暗料理
    NORMAL = "normal"      # 普通
    FINE = "fine"          # 精致
    PERFECT = "perfect"    # 完美
```

---

## 11. 文件结构

```
plugins/xiuxian_game/
├── cooking/                          # 烹饪与餐厅系统(新增)
│   ├── __init__.py                   # 模块初始化
│   ├── commands.py                   # 指令处理器（所有烹饪/餐厅指令）
│   ├── restaurant_service_new.py     # 餐厅经营服务（DI架构）
│   ├── cooking_service_new.py        # 烹饪核心服务（DI架构）
│   ├── chef_service_new.py           # 厨师管理服务（DI架构）
│   ├── settlement_service_new.py     # 结算服务（每小时结算逻辑）
│   ├── eat_commands.py               # 【吃】指令处理器（替代原吃鱼）
│   └── config.py                     # 烹饪系统配置常量
│
├── models/
│   ├── restaurant.py                 # Restaurant + RestaurantStorage 模型(新增)
│   ├── chef.py                       # Chef + ChefCandidate 模型(新增)
│   ├── restaurant_log.py             # RestaurantLog 模型(新增)
│   ├── player_recipe.py              # PlayerRecipe 模型(新增)
│   └── auto_migrate.py               # 更新 REQUIRED_FIELDS
│
├── infrastructure/repositories/
│   ├── restaurant_repository.py      # 餐厅仓储(新增)
│   ├── chef_repository.py            # 厨师仓储(新增)
│   ├── restaurant_log_repository.py  # 日志仓储(新增)
│   └── player_recipe_repository.py   # 食谱仓储(新增)
│
├── data/
│   ├── items.yaml                    # 更新：新增 seasonings / dishes / recipes 分类
│   └── recipes.yaml                  # 食谱配置(新增)
│
├── fishing/
│   └── commands.py                   # 移除【吃鱼】指令（迁移到 cooking/eat_commands.py）
│
└── player/
    └── help.py                       # 更新帮助信息
```

---

## 12. 实现步骤

### 阶段一：基础框架（预计工作量：大）

1. **新增物品类型和调料**
   - 在 `ItemType` 枚举中添加 `SEASONING`, `DISH`, `RECIPE`
   - 在 `items.yaml` 中添加调料物品配置
   - 更新 `auto_migrate.py` 处理新枚举值

2. **创建数据模型**
   - 新建 `models/restaurant.py` (Restaurant, RestaurantStorage)
   - 新建 `models/chef.py` (Chef, ChefCandidate)
   - 新建 `models/restaurant_log.py` (RestaurantLog)
   - 新建 `models/player_recipe.py` (PlayerRecipe)
   - 更新 `models/__init__.py` 导出新模型
   - 更新 `auto_migrate.py` 的 REQUIRED_FIELDS

3. **创建 Repository**
   - `infrastructure/repositories/restaurant_repository.py`
   - `infrastructure/repositories/chef_repository.py`
   - `infrastructure/repositories/restaurant_log_repository.py`
   - `infrastructure/repositories/player_recipe_repository.py`

4. **注册到 UnitOfWork**
   - 在 `infrastructure/uow/unit_of_work.py` 中添加新 Repository 属性

### 阶段二：核心服务（预计工作量：大）

5. **创建食谱配置**
   - 新建 `data/recipes.yaml`，定义所有食谱
   - 在 `config.py` 中加载食谱配置

6. **烹饪服务**
   - `cooking/cooking_service_new.py`
   - 手动烹饪逻辑、品质判定、食材消耗

7. **厨师服务**
   - `cooking/chef_service_new.py`
   - 招募、雇佣、解雇、厨师属性生成

8. **餐厅服务**
   - `cooking/restaurant_service_new.py`
   - 餐厅创建、升级、仓库管理

### 阶段三：经营循环（预计工作量：中）

9. **结算服务**
   - `cooking/settlement_service_new.py`
   - 每小时结算逻辑、日志生成、收入计算
   - 注册定时任务（APScheduler 或 NoneBot2 定时机制）

10. **经营日志和报表**
    - 日志查询、报表统计

### 阶段四：指令与交互（预计工作量：中）

11. **烹饪/餐厅指令**
    - `cooking/commands.py` - 所有餐厅和烹饪相关指令

12. **【吃】指令**
    - `cooking/eat_commands.py` - 泛用食用指令
    - 迁移原 `fishing/commands.py` 中的【吃鱼】逻辑
    - 保持别名兼容

13. **调料商店**
    - 新增NPC商店或在现有商店中添加调料购买

### 阶段五：收尾（预计工作量：小）

14. **更新帮助系统**
    - 在 `player/help.py` 中添加所有新命令

15. **更新文档索引**
    - 更新 `llmdoc/index.md`

16. **测试与平衡**
    - 经济平衡调优
    - 边界情况测试

---

## 13. 经济平衡参考

### 投入产出比

```
白色菜(红烧鲤鱼)：
  食材成本：鲤鱼(50) + 酱油(8) = 58金
  普通售价：120 × 1.0 = 120金 → 利润62金(107%)
  完美售价：120 × 2.5 = 300金 → 利润242金(417%)

蓝色菜(三文鱼刺身)：
  食材成本：三文鱼(350) + 芥末(40) + 酱油(8) = 398金
  普通售价：900 × 1.0 = 900金 → 利润502金(126%)
  完美售价：900 × 2.5 = 2,250金 → 利润1,852金(465%)

紫色菜(龙鱼宴)：
  食材成本：龙鱼(1000) + 灵芝粉(150) + 香料×2(60) + 血肉结晶(600) = 1,810金
  普通售价：4,200 × 1.0 = 4,200金 → 利润2,390金(132%)
  完美售价：4,200 × 2.5 = 10,500金 → 利润8,690金(480%)
  失败亏损：消耗50%食材 = -905金
```

### 餐厅时薪收益估算（满配运营）

```
初期（等级1, 学徒×1, 白色菜单）：
  收入 ≈ 120金 × 2道/时 = 240金/时
  支出 = 20金(工资) + ~116金(食材) = 136金/时
  净利 ≈ 100金/时

中期（等级5, 厨师×3, 蓝色菜单）：
  收入 ≈ 900金 × 4道/时 × 3人 × 0.85(考虑失败) ≈ 9,180金/时
  支出 = 360金(工资) + ~4,776金(食材) = 5,136金/时
  净利 ≈ 4,044金/时

后期（等级9, 特级厨师×5, 紫色菜单）：
  收入 ≈ 4,200金 × 6道/时 × 5人 × 0.95 ≈ 119,700金/时
  支出 = 4,000金(工资) + ~54,300金(食材) = 58,300金/时
  净利 ≈ 61,400金/时
```

---

## 14. 系统联动图

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  钓鱼    │────→│  鱼类    │────→│         │
│  系统    │     │  食材    │     │         │
└─────────┘     └─────────┘     │         │     ┌─────────┐
                                │  烹饪   │────→│  菜肴    │
┌─────────┐     ┌─────────┐     │  系统   │     │  产出    │
│  跑商    │────→│  调料    │────→│         │     └────┬────┘
│  系统    │     │  食材    │     │         │          │
└─────────┘     └─────────┘     │         │     ┌────┴────┐
                                │         │     │         │
┌─────────┐     ┌─────────┐     │         │  餐厅售卖  玩家食用
│  诡域    │────→│  稀有    │────→│         │  (经济)   (buff)
│  系统    │     │  材料    │     └─────────┘     │         │
└─────────┘     └─────────┘                      │         │
                                            ┌────┴────┐    │
                                            │  金币    │    │
                                            │  收入    │    │
                                            └─────────┘    │
                                                      ┌────┴────┐
                                                      │ 回复理智 │
                                                      │ 临时buff │
                                                      └─────────┘
```

---

**文档版本**: 1.0
**最后更新**: 2026-02-08
**维护者**: 项目架构组
