# 龙刃鞋 VIP装备 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在游戏中新增「龙刃鞋」VIP定制装备，力/敏各+2000固定加成，3项被动战斗效果。

**Architecture:** 纯配置驱动，无新增代码文件。在 items.yaml 追加YAML定义，在6个文件的8个位置更新 VIP_EQUIPMENT_IDS 集合，同时补全 market.py 和 relationship_service.py 的历史欠账（漏加了4个装备）。

**Tech Stack:** YAML配置、Python set字面量编辑

---

## Chunk 1: YAML配置与战斗引擎注册

### Task 1: 在 items.yaml 追加龙刃鞋配置

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml:1414` (vip_longying_flash `repair_cost: 5` 行之后)

- [ ] **Step 1: 确认插入位置**

  找到 `vip_longying_flash` 条目末尾（`repair_cost: 5` 所在行，约 L1413），在其**之后**插入以下内容：

  ```yaml
      - item_id: "vip_shoes_longren"
        name: "龙刃鞋"
        description: "龙纹刻于鞋底，踏出的每一步都带着刃光。"
        type: "EQUIPMENT"
        rarity: "red"
        durability: 300
        required_level: 10
        attr_bonus: {"attack": 2000, "agility": 2000}
        gem_slots: 5
        special_effects:
          - trigger: "first_turn"
            chance: 100
            effect: "buff_dodge"
            is_percentage: true
            value: 10
            duration: 3
            description: "[1] 龙踏闪步：踏出第一步，气流随刃散开——前3回合闪避率+10%"
          - trigger: "on_dodge"
            chance: 100
            effect: "damage_boost"
            is_percentage: true
            value: 15
            duration: 2
            description: "[2] 风刃反击：刃从脚下穿出，闪过的瞬间反手踏击——闪避时伤害提升15%（持续2回合）"
          - trigger: "each_turn"
            chance: 100
            effect: "damage_reduction"
            is_percentage: true
            value: 3
            duration: 999
            description: "[3] 龙鳞护足：鞋面龙纹暗涌护气，步步皆盾——受到伤害减少3%"
        repair_cost: 5
  ```

  > ⚠️ YAML 缩进必须与相邻条目完全一致（4空格缩进层次）。

- [ ] **Step 2: 快速语法验证**

  ```bash
  cd D:/QQbot/GuiXiuXian2
  python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/items.yaml', encoding='utf-8'))"
  ```

  预期：无输出（无报错）。如有 YAML 错误，检查缩进并修正。

- [ ] **Step 3: Commit**

  ```bash
  git add plugins/xiuxian_game/data/items.yaml
  git commit -m "feat: 新增龙刃鞋VIP装备YAML配置"
  ```

---

### Task 2: 注册到战斗引擎VIP集合（0阶全解锁）

**Files:**
- Modify: `plugins/xiuxian_game/battle/enhanced_engine.py:368`

- [ ] **Step 1: 编辑 enhanced_engine.py L368**

  找到：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add plugins/xiuxian_game/battle/enhanced_engine.py
  git commit -m "feat: 龙刃鞋注册到战斗引擎VIP集合"
  ```

---

### Task 3: 注册到图鉴VIP集合（两处）

**Files:**
- Modify: `plugins/xiuxian_game/item/catalog.py:440`
- Modify: `plugins/xiuxian_game/item/catalog.py:643`

- [ ] **Step 1: 更新 catalog.py L440**

  找到（L440）：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

- [ ] **Step 2: 更新 catalog.py L643**（文件内搜索第二处相同行）

  找到（L643，内容与上一处完全相同）：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

  > ⚠️ catalog.py 中有**两处**相同的 VIP_EQUIPMENT_IDS，必须都改。用编辑器全局搜索确认两处都已修改。

- [ ] **Step 3: Commit**

  ```bash
  git add plugins/xiuxian_game/item/catalog.py
  git commit -m "feat: 龙刃鞋注册到图鉴VIP集合（补全两处）"
  ```

---

## Chunk 2: 装备面板、交易保护与验证

### Task 4: 注册装备面板 + 装备详情VIP集合

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_commands.py:321` (装备详情 VIP_EQUIPMENT_IDS)
- Modify: `plugins/xiuxian_game/item/equipment_commands.py:61` (_VIP_EQUIPMENT_SKILL_MENUS 末尾)

- [ ] **Step 1: 更新 equipment_commands.py L321**

  找到（L321）：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

- [ ] **Step 2: 在 _VIP_EQUIPMENT_SKILL_MENUS 末尾追加条目**

  找到 `_VIP_EQUIPMENT_SKILL_MENUS` 字典的末尾（搜索 `"vip_ghost_dice": {` 条目，位于约 L848，字典结束 `}` 在约 L861）：

  ```python
      "vip_ghost_dice": {
          "name": "诡面骰",
          ...
      },
  }
  ```

  在 `"vip_ghost_dice"` 条目与最后的 `}` 之间插入：

  ```python
      "vip_shoes_longren": {
          "name": "龙刃鞋",
          "icon": "👟",
          "skills": (
              "👟 龙刃鞋 · 踏风流\n"
              "━━━━━━━━━━━━━\n"
              "本装备无主动技能\n"
              "3项被动效果战斗中自动生效"
          ),
      },
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add plugins/xiuxian_game/item/equipment_commands.py
  git commit -m "feat: 龙刃鞋注册装备菜单和装备详情VIP集合"
  ```

---

### Task 5: 补全交易和转移保护（历史欠账修复）

**Files:**
- Modify: `plugins/xiuxian_game/economy/market.py:306`
- Modify: `plugins/xiuxian_game/social/relationship_service.py:230`

> 背景：这两处集合历史遗留只有3个旧ID，归雨/折光年/龙影闪/诡面骰均已漏加，本次一并补全至8个。

- [ ] **Step 1: 更新 market.py L306**

  找到（L306）：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

- [ ] **Step 2: 更新 relationship_service.py L230**

  找到（L230）：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade"}
  ```

  替换为：
  ```python
  VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add plugins/xiuxian_game/economy/market.py
  git add plugins/xiuxian_game/social/relationship_service.py
  git commit -m "fix: 补全market/relationship VIP装备禁止交易集合（历史欠账+龙刃鞋）"
  ```

---

### Task 6: 验证

> 本项目无自动化测试框架，采用机器人重启后手动命令验证。

- [ ] **Step 1: 重启机器人并检查启动日志**

  观察启动日志是否有 YAML 解析错误或 EffectType 相关报错。
  预期：日志中出现类似 `[EffectSystem] 成功注册 XXX 个战斗效果桥接器`，无 `ValueError` 报错。

- [ ] **Step 2: 使用【图鉴 龙刃鞋】查看装备详情**

  发送：`【图鉴 龙刃鞋】`

  预期输出包含：
  ```
  龙刃鞋
  稀有度: 永恒（红色VIP）
  力量+2000 / 敏捷+2000
  ✅ [1] 龙踏闪步：...前3回合闪避率+10%
  ✅ [2] 风刃反击：...闪避时伤害提升15%...
  ✅ [3] 龙鳞护足：...受到伤害减少3%
  ```

  如果3个效果显示为 `🔒` 而非 `✅`，说明 VIP_EQUIPMENT_IDS 中有一处漏改，逐文件检查。

- [ ] **Step 3: 穿戴装备后使用【装备菜单】**

  穿戴龙刃鞋后发送：`【装备菜单】`

  预期输出包含：
  ```
  👟 龙刃鞋 · 踏风流
  ━━━━━━━━━━━━━
  本装备无主动技能
  3项被动效果战斗中自动生效
  ```

- [ ] **Step 4: 进入战斗验证效果触发**

  发送：`【切磋 某UID】` 进行一场测试战斗。

  战斗日志中预期出现：
  - 第1回合：`⚡ 龙踏闪步：前3回合闪避率+10%`（或类似文字）
  - 每回合：减伤效果生效（伤害数值比无装备低约3%）
  - 成功闪避后：伤害提升效果 `damage_boost` 触发

- [ ] **Step 5: 尝试挂牌交易龙刃鞋（应被拒绝）**

  发送：`【挂牌 出售 龙刃鞋 1 1】`

  预期：`⛔ VIP定制装备为专属装备，不可交易`

---

**实现完成检查清单：**
- [ ] items.yaml YAML语法合法（python yaml解析无报错）
- [ ] 5个VIP集合文件均已更新（enhanced_engine.py / catalog.py×2 / equipment_commands.py / market.py / relationship_service.py）
- [ ] 装备菜单有龙刃鞋条目
- [ ] 图鉴显示3个效果全部✅解锁
- [ ] 战斗中3个效果均正常触发
- [ ] 挂牌交易被拒绝
