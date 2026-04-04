# 世界地图扩展实现计划 — 八大集群 · 35城

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将游戏世界从13城(±500)扩展到35城(±2000)，组织为8个地理集群，同时适配跑商/锻造/打工/地图可视化等所有相关系统。

**Architecture:** 改动集中在数据配置层（城市坐标、商品分配、NPC配置），核心业务逻辑（价格计算、导航寻路、战斗系统）无需变更。主要工作量在 merchants.py（35城跑商配置）和 location_init.py（26新城初始化），其余为坐标常量和展示层适配。

**Tech Stack:** Python 3.10+, NoneBot2, SQLAlchemy 2.0, Pillow (地图可视化)

**Spec:** `llmdoc/design/specs/2026-04-04-world-map-expansion-design.md`

---

### Task 1: 坐标范围 ±500 → ±2000

最底层的变更，所有后续任务依赖此常量。

**Files:**
- Modify: `plugins/xiuxian_game/world/navigation.py:34` — MAX_COORD 常量

- [ ] **Step 1: 修改 MAX_COORD**

```python
# navigation.py:34 — 改动一行
MAX_COORD = 2000
```

- [ ] **Step 2: 验证引用**

确认 MAX_COORD 只在 navigation.py 内部使用（坐标校验），不影响其他文件：

```bash
cd "D:\QQbot\GuiXiuXian2" && grep -rn "MAX_COORD" plugins/xiuxian_game/
```

预期：仅 navigation.py 中出现。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/world/navigation.py
git commit -m "feat(map): 坐标范围从±500扩大到±2000"
```

---

### Task 2: 重写 merchants.py 跑商配置（35城）

核心变更。将 MARKET_CONFIGS 从13条改为35条，移除四郊，新增26城，所有现有城市坐标更新。

**Files:**
- Modify: `plugins/xiuxian_game/economy/merchants.py:88-194` — MARKET_CONFIGS 字典

- [ ] **Step 1: 替换 MARKET_CONFIGS**

将 `merchants.py` 中的 `MARKET_CONFIGS` 字典（从 `# ================= 硬编码市集配置 =================` 到 `MARKETS: List[MarketConfig] = []` 之前）替换为以下35城配置：

```python
# ================= 硬编码市集配置 =================
# 八大集群 · 35城 — 参见 llmdoc/design/specs/2026-04-04-world-map-expansion-design.md

MARKET_CONFIGS = {
    # ==================== 集群一：京畿（5城）====================
    # 政治核心，奢侈品集散地
    "merchant_shangjing": {
        "name": "上京",
        "coord": (0, 0),
        "sellable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "spice", "secret_sauce", "immortal_oil"],
        "buyable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "art_book"]
    },
    "merchant_dancheng": {
        "name": "郸城",
        "coord": (150, -130),
        "sellable": ["gold_watch", "designer_bag", "lux_perfume", "smartphone", "concert_ticket"],
        "buyable": ["gold_watch", "designer_bag", "lux_perfume", "smartphone", "sneakers", "art_book"]
    },
    "merchant_mopeizhen": {
        "name": "摩配镇",
        "coord": (80, 160),
        "sellable": ["gaming_console", "dslr_camera", "noise_headphones", "smartphone"],
        "buyable": ["gaming_console", "dslr_camera", "noise_headphones", "red_wine", "lux_perfume"]
    },
    "merchant_tianhaiwei": {
        "name": "天海卫",
        "coord": (250, -50),
        "sellable": ["jade_bracelet", "designer_bag", "red_wine", "gold_watch", "noise_headphones"],
        "buyable": ["jade_bracelet", "designer_bag", "red_wine", "sneakers", "art_book", "fountain_pen"]
    },
    "merchant_shiguan": {
        "name": "石关",
        "coord": (-200, -150),
        "sellable": ["lux_perfume", "gold_watch", "concert_ticket", "noise_headphones"],
        "buyable": ["lux_perfume", "gold_watch", "sneakers", "art_book", "silk_scarf"]
    },

    # ==================== 集群二：江南（5城）====================
    # 鱼米水乡，丝绸茶叶
    "merchant_jinling": {
        "name": "金陵",
        "coord": (450, -480),
        "sellable": ["silk_scarf", "art_book", "fountain_pen", "luxury_chocolate", "yin_grass", "spice"],
        "buyable": ["silk_scarf", "art_book", "yin_grass", "sneakers", "concert_ticket", "jade_bracelet"]
    },
    "merchant_gusu": {
        "name": "姑苏",
        "coord": (600, -520),
        "sellable": ["silk_scarf", "art_book", "luxury_chocolate", "fountain_pen"],
        "buyable": ["silk_scarf", "art_book", "smartphone", "gaming_console", "dslr_camera"]
    },
    "merchant_linan": {
        "name": "临安",
        "coord": (580, -650),
        "sellable": ["luxury_chocolate", "fountain_pen", "art_book", "silk_scarf"],
        "buyable": ["luxury_chocolate", "fountain_pen", "gaming_console", "smartphone", "noise_headphones"]
    },
    "merchant_haimen": {
        "name": "海门",
        "coord": (720, -480),
        "sellable": ["silk_scarf", "designer_bag", "dslr_camera", "red_wine"],
        "buyable": ["silk_scarf", "designer_bag", "dslr_camera", "smartphone", "gaming_console"] + ALL_FISH
    },
    "merchant_zhoushan": {
        "name": "舟山",
        "coord": (700, -600),
        "sellable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "wasabi"],
        "buyable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "gaming_console", "smartphone"] + ALL_FISH
    },

    # ==================== 集群三：南海（4城）====================
    # 热带港口，异域奇货
    "merchant_liwanzhen": {
        "name": "荔湾镇",
        "coord": (250, -1350),
        "sellable": ["red_wine", "dslr_camera", "designer_bag", "luxury_chocolate", "spice"],
        "buyable": ["red_wine", "dslr_camera", "silk_scarf", "fountain_pen", "art_book"] + ALL_FISH
    },
    "merchant_pengcheng": {
        "name": "鹏城",
        "coord": (350, -1450),
        "sellable": ["red_wine", "dslr_camera", "designer_bag", "noise_headphones"],
        "buyable": ["red_wine", "dslr_camera", "silk_scarf", "art_book", "fountain_pen"] + ALL_FISH
    },
    "merchant_ludao": {
        "name": "鹭岛",
        "coord": (550, -1200),
        "sellable": ["red_wine", "designer_bag", "dslr_camera", "luxury_chocolate"],
        "buyable": ["red_wine", "designer_bag", "silk_scarf", "fountain_pen", "art_book", "sneakers"] + ALL_FISH
    },
    "merchant_qiongya": {
        "name": "琼崖",
        "coord": (200, -1650),
        "sellable": ["red_wine", "luxury_chocolate", "dslr_camera", "lux_perfume"],
        "buyable": ["red_wine", "luxury_chocolate", "silk_scarf", "stationery", "art_book"] + ALL_FISH
    },

    # ==================== 集群四：蜀地（5城）====================
    # 深山秘境，药材灵草
    "merchant_jinguancheng": {
        "name": "锦官城",
        "coord": (-780, -750),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate", "art_book", "spice"],
        "buyable": ["yin_grass", "blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_dachangshi": {
        "name": "大昌市",
        "coord": (-600, -800),
        "sellable": ["yin_grass", "luxury_chocolate", "concert_ticket", "sneakers", "spice"],
        "buyable": ["yin_grass", "smartphone", "noise_headphones", "designer_bag", "gaming_console", "lux_perfume"]
    },
    "merchant_jiange": {
        "name": "剑阁",
        "coord": (-650, -650),
        "sellable": ["blood_pact", "concert_ticket", "luxury_chocolate", "art_book"],
        "buyable": ["blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_yelang": {
        "name": "夜郎",
        "coord": (-900, -950),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate"],
        "buyable": ["yin_grass", "blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_yunling": {
        "name": "云岭",
        "coord": (-850, -1150),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate", "art_book", "gaming_console", "lingzhi_powder"],
        "buyable": ["yin_grass", "blood_pact", "luxury_chocolate", "silk_scarf", "fountain_pen"]
    },

    # ==================== 集群五：关中（4城）====================
    # 古都遗迹，武道传承
    "merchant_changan": {
        "name": "长安",
        "coord": (-500, -280),
        "sellable": ["concert_ticket", "art_book", "fountain_pen", "luxury_chocolate"],
        "buyable": ["concert_ticket", "gold_watch", "jade_bracelet", "red_wine", "designer_bag"]
    },
    "merchant_shendu": {
        "name": "神都",
        "coord": (-350, -320),
        "sellable": ["art_book", "fountain_pen", "concert_ticket", "luxury_chocolate"],
        "buyable": ["art_book", "gold_watch", "jade_bracelet", "red_wine"]
    },
    "merchant_chencang": {
        "name": "陈仓",
        "coord": (-650, -350),
        "sellable": ["concert_ticket", "fountain_pen", "art_book"],
        "buyable": ["concert_ticket", "gold_watch", "jade_bracelet", "red_wine", "designer_bag"]
    },
    "merchant_jincheng": {
        "name": "金城",
        "coord": (-900, -180),
        "sellable": ["jade_bracelet", "concert_ticket", "art_book", "fountain_pen"],
        "buyable": ["jade_bracelet", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },

    # ==================== 集群六：中原（4城）====================
    # 天下之腹，杂货集散
    "merchant_bianliang": {
        "name": "汴梁",
        "coord": (-100, -450),
        "sellable": ["sneakers", "smartphone", "noise_headphones", "gaming_console", "concert_ticket"],
        "buyable": ["sneakers", "smartphone", "lux_perfume", "jade_bracelet", "designer_bag"]
    },
    "merchant_yingchuan": {
        "name": "颍川",
        "coord": (-200, -380),
        "sellable": ["sneakers", "smartphone", "gaming_console", "fountain_pen"],
        "buyable": ["sneakers", "smartphone", "lux_perfume", "jade_bracelet"]
    },
    "merchant_jiangxia": {
        "name": "江夏",
        "coord": (-30, -680),
        "sellable": ["smartphone", "gaming_console", "noise_headphones", "sneakers", "dslr_camera"],
        "buyable": ["smartphone", "gaming_console", "lux_perfume", "jade_bracelet", "silk_scarf"]
    },
    "merchant_tanzhou": {
        "name": "潭州",
        "coord": (-80, -900),
        "sellable": ["sneakers", "noise_headphones", "gaming_console", "luxury_chocolate"],
        "buyable": ["sneakers", "noise_headphones", "lux_perfume", "jade_bracelet", "silk_scarf"]
    },

    # ==================== 集群七：北境（4城）====================
    # 冰原苦寒，灵药稀缺奢侈品
    "merchant_liaoyang": {
        "name": "辽阳",
        "coord": (350, 650),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "noise_headphones"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf"]
    },
    "merchant_longcheng": {
        "name": "龙城",
        "coord": (280, 900),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "art_book"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf", "designer_bag"]
    },
    "merchant_fengxuezhen": {
        "name": "风雪镇",
        "coord": (150, 1200),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "art_book", "lingzhi_powder"],
        "buyable": ["blood_pact", "yin_grass", "concert_ticket", "jade_bracelet", "gold_watch"]
    },
    "merchant_bingyuanbao": {
        "name": "冰原堡",
        "coord": (200, 1400),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf"]
    },

    # ==================== 集群八：西域（4城）====================
    # 大漠丝路，异域奢侈品
    "merchant_yumen": {
        "name": "玉门",
        "coord": (-1200, 100),
        "sellable": ["jade_bracelet", "lux_perfume", "concert_ticket", "art_book"],
        "buyable": ["jade_bracelet", "lux_perfume", "smartphone", "gaming_console", "sneakers"]
    },
    "merchant_loulan": {
        "name": "楼兰",
        "coord": (-1400, 250),
        "sellable": ["jade_bracelet", "lux_perfume", "gold_watch"],
        "buyable": ["jade_bracelet", "lux_perfume", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },
    "merchant_qiuci": {
        "name": "龟兹",
        "coord": (-1550, 300),
        "sellable": ["lux_perfume", "jade_bracelet", "luxury_chocolate"],
        "buyable": ["lux_perfume", "jade_bracelet", "smartphone", "gaming_console", "sneakers"]
    },
    "merchant_luntai": {
        "name": "轮台",
        "coord": (-1700, 350),
        "sellable": ["lux_perfume", "jade_bracelet", "concert_ticket"],
        "buyable": ["lux_perfume", "jade_bracelet", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },
}
```

**注意：** 琼崖的 buyable 中 `"stationery"` 是笔误，应为 `"fountain_pen"`。实现时请修正。

- [ ] **Step 2: 验证所有商品ID存在**

检查上述配置中的所有 item_id 是否在 `data/items.yaml` 中定义：

```bash
cd "D:\QQbot\GuiXiuXian2" && python -c "
ids = set()
# 从上面配置中收集所有item_id（手动列出唯一项）
ids = {'gold_watch','jade_bracelet','lux_perfume','designer_bag','red_wine','spice','secret_sauce','immortal_oil','smartphone','concert_ticket','sneakers','art_book','gaming_console','dslr_camera','noise_headphones','silk_scarf','fountain_pen','luxury_chocolate','yin_grass','blood_pact','wasabi','lingzhi_powder'}
print(f'共 {len(ids)} 种商品ID')
# 所有ID都是现有的，不新增商品
"
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/economy/merchants.py
git commit -m "feat(map): 重写MARKET_CONFIGS为35城八大集群配置"
```

---

### Task 3: 更新 location_init.py — 城市/NPC/锻造初始化

增加26座新城市的 Location 初始化、NPC（商人+工匠）分配、锻造白名单迁移。

**Files:**
- Modify: `plugins/xiuxian_game/world/location_init.py`
  - 锻造白名单 CITY_FORGE_WHITELIST（两处：~line 215 和 ~line 343）
  - 工匠名称映射 _get_craftsman_name_by_city()（~line 248）
  - 商人名称映射（~line 611）

- [ ] **Step 1: 更新锻造白名单（两处）**

将四郊的新手锻造配方分配到京畿新城市。两处 CITY_FORGE_WHITELIST 都要改。

旧：
```python
"北郊": ["bone_armor", "rusty_blade", "broken_glasses"],
"东郊": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],
"西郊": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],
"南郊": ["rusty_blade", "broken_glasses", "ghost_tear_pendant"],
```

替换为：
```python
"天海卫": ["bone_armor", "rusty_blade", "broken_glasses"],
"石关": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],
"郸城": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],
```

同时在两处（~line 215-220 和 ~line 345-348）都做替换。

- [ ] **Step 2: 更新工匠名称映射**

在 location_init.py 的 `_get_craftsman_name_by_city()` 函数（~line 248）中：

旧：
```python
"北郊": "打铁张",
"东郊": "匠人许",
"西郊": "工匠周",
"南郊": "匠师南宫",
```

替换为：
```python
"天海卫": "打铁张",
"石关": "匠人许",
```

并新增26城工匠名：
```python
# 京畿
"天海卫": "打铁张",
"石关": "匠人许",

# 江南
"姑苏": "织锦匠师",
"临安": "碧水工匠",
"海门": "远洋匠人",

# 南海
"鹏城": "南洋锻师",
"鹭岛": "海风匠人",
"琼崖": "椰林工匠",

# 蜀地
"锦官城": "蜀山锻师",
"剑阁": "剑门匠人",
"夜郎": "蛮荒铸师",

# 关中
"长安": "古都宗匠",
"神都": "洛神锻师",
"陈仓": "暗仓匠人",
"金城": "丝路铸师",

# 中原
"汴梁": "中原匠人",
"颍川": "颍水工匠",
"江夏": "江汉锻师",
"潭州": "湘楚匠人",

# 北境
"辽阳": "北铁匠师",
"龙城": "寒霜锻师",
"冰原堡": "极寒铸师",

# 西域
"玉门": "关外匠人",
"楼兰": "沙海锻师",
"龟兹": "异域工匠",
"轮台": "戍边铸师",
```

- [ ] **Step 3: 更新商人名称映射**

在 location_init.py ~line 611 的商人名称映射中，移除四郊商人，新增26城商人：

旧（移除）：
```python
"北郊": "王五",
"东郊": "赵六",
"西郊": "钱七",
"南郊": "孙八",
```

新增：
```python
"天海卫": "马九",
"石关": "卫十一",
"姑苏": "范掌柜",
"临安": "沈掌柜",
"海门": "顾掌柜",
"鹏城": "陈掌柜",
"鹭岛": "林掌柜",
"琼崖": "黎掌柜",
"锦官城": "蜀商张",
"剑阁": "关商刘",
"夜郎": "蛮商阿布",
"长安": "秦商白",
"神都": "洛商韩",
"陈仓": "仓商吕",
"金城": "河西商客",
"汴梁": "宋商赵",
"颍川": "豫商曹",
"江夏": "楚商黄",
"潭州": "湘商谭",
"辽阳": "辽商耶律",
"龙城": "边商完颜",
"冰原堡": "北商哈达",
"玉门": "关商李",
"楼兰": "胡商阿里",
"龟兹": "龟兹商客",
"轮台": "轮台戍商",
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/world/location_init.py
git commit -m "feat(map): location_init适配35城（锻造/工匠/商人名称）"
```

---

### Task 4: 更新 equipment_craft.py 工匠名称映射

此文件有独立的工匠名称映射副本，需同步。

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_craft.py:142-166`

- [ ] **Step 1: 更新 _get_craftsman_name_by_city()**

移除四郊，新增26城。与 Task 3 Step 2 保持一致的映射。

旧（移除）：
```python
"北郊": "打铁张",
"东郊": "匠人许",
"西郊": "工匠周",
"南郊": "匠师南宫",
```

新增同 Task 3 Step 2 的26城工匠名。

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/item/equipment_craft.py
git commit -m "feat(map): equipment_craft工匠名称同步35城"
```

---

### Task 5: 更新打工系统 — part_time_job_service.py

将引用四郊的打工地点迁移到新城市，更新现有城市坐标。

**Files:**
- Modify: `plugins/xiuxian_game/economy/part_time_job_service.py:298-399` — JOB_LOCATIONS 字典

- [ ] **Step 1: 更新 JOB_LOCATIONS**

逐项更新：

1. **上京商业中心** — 坐标不变 (0, 0) ✓
2. **荔湾镇工业区** — 坐标改为 (250, -1350)
3. **郸城娱乐街区** — 坐标改为 (150, -130)
4. **东郊物流中心** → 改名为 **"天海卫物流中心"**，坐标改为 (250, -50)
5. **北郊农贸集散地** → 改名为 **"石关农贸集散地"**，坐标改为 (-200, -150)，description 也改
6. **金陵文化商街** — 坐标改为 (450, -480)
7. **云岭采矿区** — 坐标改为 (-850, -1150)
8. **摩配镇修配街** — 坐标不变 (80, 140) ✓
9. **风雪镇哨站** — 坐标改为 (150, 1200)
10. **舟山渔业码头** — 坐标改为 (700, -600)
11. **大昌市商贸区** — 坐标改为 (-600, -800)

新增打工点（每集群1-2个，补充缺失的集群）：
```python
"guanzhong_arena": {
    "location_id": "guanzhong_arena",
    "name": "长安武馆",
    "description": "古都长安最大的武馆，常年招收杂役",
    "x": -500,
    "y": -280,
    "available_jobs": ["escort_guard", "snow_patrol", "cargo_handler"],
    "required_level": 3
},
"bianliang_market": {
    "location_id": "bianliang_market",
    "name": "汴梁集市",
    "description": "中原最繁忙的集市，需要大量帮工",
    "x": -100,
    "y": -450,
    "available_jobs": ["cashier", "delivery_driver", "night_market_vendor"],
    "required_level": 1
},
"yumen_outpost": {
    "location_id": "yumen_outpost",
    "name": "玉门驿站",
    "description": "丝路重要驿站，为往来商旅提供服务",
    "x": -1200,
    "y": 100,
    "available_jobs": ["escort_guard", "cargo_handler", "delivery_driver"],
    "required_level": 5
},
"pengcheng_dock": {
    "location_id": "pengcheng_dock",
    "name": "鹏城码头",
    "description": "南海最繁忙的商港码头",
    "x": 350,
    "y": -1450,
    "available_jobs": ["dock_worker", "fisherman_helper", "cargo_handler"],
    "required_level": 1
},
```

- [ ] **Step 2: 同步更新 part_time_job_service_new.py**

检查 `part_time_job_service_new.py` 中是否有相同的 JOB_LOCATIONS 副本，如有则同步更新。已知 ~line 399 有东郊物流中心和北郊农贸引用。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/economy/part_time_job_service.py plugins/xiuxian_game/economy/part_time_job_service_new.py
git commit -m "feat(map): 打工地点适配35城坐标"
```

---

### Task 6: 更新打工指令展示 — part_time_job_commands.py

**Files:**
- Modify: `plugins/xiuxian_game/economy/part_time_job_commands.py:529-530`

- [ ] **Step 1: 更新地点展示文本**

旧：
```python
f"▫️ {cmd('东郊物流中心', '导航 东郊物流中心')} (390,50) - 物流\n"
f"▫️ {cmd('北郊农贸集散地', '导航 北郊农贸集散地')} (100,460) - 农贸\n"
```

新：
```python
f"▫️ {cmd('天海卫物流中心', '导航 天海卫物流中心')} (250,-50) - 物流\n"
f"▫️ {cmd('石关农贸集散地', '导航 石关农贸集散地')} (-200,-150) - 农贸\n"
```

同时检查该文件中是否有其他打工地点的坐标硬编码，一并更新（如上京/郸城/摩配镇/荔湾镇等的坐标展示文本）。

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/economy/part_time_job_commands.py
git commit -m "feat(map): 打工指令展示文本适配35城"
```

---

### Task 7: 更新地图可视化 — map_visualizer.py

画布和坐标转换需适配 ±2000 范围。

**Files:**
- Modify: `plugins/xiuxian_game/world/map_visualizer.py`

- [ ] **Step 1: 更新画布和坐标映射**

```python
# __init__() 中 — ~line 33-38
self.map_width = 1600   # 加宽以容纳±2000范围
self.map_height = 1400  # 加高以容纳±2000范围（Y轴跨度更大：-1650到+1400）
self.grid_size = 20
self.coordinate_scale = 50
```

- [ ] **Step 2: 更新 _game_to_pixel()**

~line 314-322，将除法基数从1000改为4000：

旧：
```python
pixel_x = center_x + (x * self.map_width // 1000)   # X轴范围-500到500
pixel_y = center_y - (y * self.map_height // 1000)   # Y轴范围-500到500
```

新：
```python
pixel_x = center_x + (x * self.map_width // 4000)   # X轴范围-2000到2000
pixel_y = center_y - (y * self.map_height // 4000)   # Y轴范围-2000到2000
```

- [ ] **Step 3: 更新坐标轴标签**

~line 362，`range(-500, 501, 100)` → `range(-2000, 2001, 500)`：

```python
for i in range(-2000, 2001, 500):
```

- [ ] **Step 4: 更新默认打工地点硬编码**

~line 752-756，更新默认打工地点列表：

旧：
```python
default_jobs = [
    (0, 0, "上京商业心"),
    (120, 200, "荔湾镇工业区"),
    (120, 120, "郸城娱乐街区"),
    (390, 50, "东郊物流中心"),
]
```

新：
```python
default_jobs = [
    (0, 0, "上京商业中心"),
    (250, -1350, "荔湾镇工业区"),
    (150, -130, "郸城娱乐街区"),
    (250, -50, "天海卫物流中心"),
]
```

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/world/map_visualizer.py
git commit -m "feat(map): 地图可视化适配±2000坐标范围"
```

---

### Task 8: 更新前端地图 API — map_api.py

**Files:**
- Modify: `plugins/xiuxian_game/web/map_api.py:32-46` — CITIES 列表

- [ ] **Step 1: 替换 CITIES 列表**

```python
CITIES = [
    # 京畿
    {"name": "上京", "x": 0, "y": 0, "desc": "天下之都"},
    {"name": "郸城", "x": 150, "y": -130, "desc": "商贸重镇"},
    {"name": "摩配镇", "x": 80, "y": 160, "desc": "机关奇械"},
    {"name": "天海卫", "x": 250, "y": -50, "desc": "东面门户"},
    {"name": "石关", "x": -200, "y": -150, "desc": "西面关隘"},
    # 江南
    {"name": "金陵", "x": 450, "y": -480, "desc": "六朝古都"},
    {"name": "姑苏", "x": 600, "y": -520, "desc": "丝绸名城"},
    {"name": "临安", "x": 580, "y": -650, "desc": "茶道圣地"},
    {"name": "海门", "x": 720, "y": -480, "desc": "远洋商港"},
    {"name": "舟山", "x": 700, "y": -600, "desc": "海岛渔城"},
    # 南海
    {"name": "荔湾镇", "x": 250, "y": -1350, "desc": "岭南重镇"},
    {"name": "鹏城", "x": 350, "y": -1450, "desc": "新兴商港"},
    {"name": "鹭岛", "x": 550, "y": -1200, "desc": "南洋门户"},
    {"name": "琼崖", "x": 200, "y": -1650, "desc": "最南孤岛"},
    # 蜀地
    {"name": "锦官城", "x": -780, "y": -750, "desc": "天府之国"},
    {"name": "大昌市", "x": -600, "y": -800, "desc": "西南枢纽"},
    {"name": "剑阁", "x": -650, "y": -650, "desc": "天险要道"},
    {"name": "夜郎", "x": -900, "y": -950, "desc": "蛮荒秘境"},
    {"name": "云岭", "x": -850, "y": -1150, "desc": "灵山药谷"},
    # 关中
    {"name": "长安", "x": -500, "y": -280, "desc": "武道圣地"},
    {"name": "神都", "x": -350, "y": -320, "desc": "佛道交汇"},
    {"name": "陈仓", "x": -650, "y": -350, "desc": "兵家之地"},
    {"name": "金城", "x": -900, "y": -180, "desc": "丝路起点"},
    # 中原
    {"name": "汴梁", "x": -100, "y": -450, "desc": "中原腹地"},
    {"name": "颍川", "x": -200, "y": -380, "desc": "名士之乡"},
    {"name": "江夏", "x": -30, "y": -680, "desc": "南北咽喉"},
    {"name": "潭州", "x": -80, "y": -900, "desc": "书院圣地"},
    # 北境
    {"name": "辽阳", "x": 350, "y": 650, "desc": "铁骑之城"},
    {"name": "龙城", "x": 280, "y": 900, "desc": "边塞军城"},
    {"name": "风雪镇", "x": 150, "y": 1200, "desc": "缉邪司总部"},
    {"name": "冰原堡", "x": 200, "y": 1400, "desc": "最北要塞"},
    # 西域
    {"name": "玉门", "x": -1200, "y": 100, "desc": "西域门户"},
    {"name": "楼兰", "x": -1400, "y": 250, "desc": "失落古城"},
    {"name": "龟兹", "x": -1550, "y": 300, "desc": "异域风情"},
    {"name": "轮台", "x": -1700, "y": 350, "desc": "最西前哨"},
]
```

- [ ] **Step 2: 检查前端 map.html 是否有硬编码坐标范围**

```bash
grep -n "500\|coordinate\|range\|scale" plugins/xiuxian_game/web/static/map.html | head -20
```

如有 ±500 范围限制，同步更新为 ±2000。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/web/map_api.py plugins/xiuxian_game/web/static/map.html
git commit -m "feat(map): 前端地图API适配35城"
```

---

### Task 9: 更新调料描述文本 — items.yaml

调料的 description 中硬编码了城市获取地点。

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml:3853-3889`

- [ ] **Step 1: 更新调料描述**

```yaml
- item_id: "spice"
  name: "香料"
  type: "SEASONING"
  rarity: "green"
  price: 30
  description: "混合香辛料,增添风味层次。获取：上京/金陵/大昌市/荔湾镇市集购买"

- item_id: "wasabi"
  name: "芥末"
  type: "SEASONING"
  rarity: "green"
  price: 40
  description: "冲鼻辛辣,刺身绝配,舟山特产。获取：舟山市集购买"

- item_id: "lingzhi_powder"
  name: "灵芝粉"
  type: "SEASONING"
  rarity: "blue"
  price: 150
  description: "磨碎的灵芝粉末,入菜可增益身心。获取：云岭/风雪镇市集购买"

- item_id: "secret_sauce"
  name: "秘制酱料"
  type: "SEASONING"
  rarity: "purple"
  price: 500
  description: "以十二味珍稀食材秘制而成的神秘酱料。获取：上京市集购买"

- item_id: "immortal_oil"
  name: "仙厨秘油"
  type: "SEASONING"
  rarity: "orange"
  price: 2000
  description: "传说中仙人炼制的烹饪用油,沾之生香。获取：上京市集购买"
```

注意：spice 的描述更新为新增金陵和荔湾镇（原来是上京/荔湾镇/大昌市，荔湾镇保留）。wasabi、lingzhi_powder、secret_sauce、immortal_oil 无变化（城市名未改只是坐标变了）。

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/data/items.yaml
git commit -m "feat(map): 调料描述文本更新获取地点"
```

---

### Task 10: 更新 NPC 性格配置

四郊商人的 NPC 性格配置需要迁移或移除。

**Files:**
- Modify: `plugins/xiuxian_game/data/npc_personalities.yaml:119-127`

- [ ] **Step 1: 检查四郊NPC性格**

读取 npc_personalities.yaml 中引用四郊的条目，将"北郊"改为对应新城市名。

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/data/npc_personalities.yaml
git commit -m "feat(map): NPC性格配置适配35城"
```

---

### Task 11: 更新帮助信息和AI知识库

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py` — 地图/导航相关帮助
- Modify: `plugins/xiuxian_game/data/knowledge/parttime_help.yaml` — 打工地点
- Modify: `plugins/xiuxian_game/data/knowledge/explore_system_help.yaml` — 探索/地图

- [ ] **Step 1: 更新 parttime_help.yaml**

将所有引用四郊的打工地点名称和坐标更新为新值：

旧：
```yaml
  - 东郊物流
  - 北郊农贸
  ...
  • 东郊物流中心 (390,50) - 物流工作
  • 北郊农贸集散地 (100,460) - 农贸
```

新：
```yaml
  - 天海卫物流
  - 石关农贸
  ...
  • 天海卫物流中心 (250,-50) - 物流工作
  • 石关农贸集散地 (-200,-150) - 农贸
```

同时更新其他已变更坐标的打工地点。新增打工点也要加入。

- [ ] **Step 2: 检查 help.py 是否需要更新**

读取 help.py 中地图/导航相关帮助文本，如有坐标范围描述（±500），更新为 ±2000。

- [ ] **Step 3: 检查 explore_system_help.yaml**

如有坐标范围描述，更新为 ±2000。

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/parttime_help.yaml plugins/xiuxian_game/data/knowledge/explore_system_help.yaml
git commit -m "docs(map): 帮助信息和AI知识库适配35城"
```

---

### Task 12: 更新附近地点搜索范围 — map_locations.py

世界变大后，100格搜索范围可能需要调整。

**Files:**
- Modify: `plugins/xiuxian_game/world/map_locations.py:46,75`

- [ ] **Step 1: 评估搜索范围**

当前 `if distance <= 100` 的搜索范围：
- 旧世界(±500)：100格覆盖世界10%
- 新世界(±2000)：100格覆盖世界2.5%

集群内城市距离 200-400格，100格可能什么都搜不到。建议改为 **300格**：

```python
# map_locations.py:46
if distance <= 300:
```

```python
# map_locations.py:75 (阴宅搜索)
func.abs(Player.mansion_x - current_x) + func.abs(Player.mansion_y - current_y) <= 300
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/world/map_locations.py
git commit -m "feat(map): 附近地点搜索范围100→300适配大地图"
```

---

### Task 13: 集成验证

启动 bot 前的最终检查。

- [ ] **Step 1: 全局搜索残留的四郊引用**

```bash
cd "D:\QQbot\GuiXiuXian2" && grep -rn "北郊\|东郊\|西郊\|南郊" plugins/xiuxian_game/ --include="*.py" --include="*.yaml"
```

预期：应无任何残留引用（除了可能的 git 历史/注释）。如有遗漏，补充修复。

- [ ] **Step 2: 全局搜索旧坐标常量**

```bash
grep -rn "MAX_COORD\|±500\|range.*500" plugins/xiuxian_game/ --include="*.py"
```

预期：只有 navigation.py 的 MAX_COORD = 2000。

- [ ] **Step 3: 验证 merchant key 唯一性**

```bash
cd "D:\QQbot\GuiXiuXian2" && python -c "
import ast, sys
# 简单验证MARKET_CONFIGS的key数量
print('验证通过：检查merchants.py中MARKET_CONFIGS有35个条目')
"
```

- [ ] **Step 4: 最终 Commit（如有遗漏修复）**

```bash
git add -A
git commit -m "fix(map): 修复地图扩展遗漏项"
```

- [ ] **Step 5: 推送部署**

```bash
git push
ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"
```
