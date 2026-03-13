# 龙刃鞋 · VIP定制装备设计规格

## 1. 基本信息

- **装备名称:** 龙刃鞋
- **item_id:** `vip_shoes_longren`
- **定价档位:** 500元
- **设计定位:** 踏风流·速度型，高固定属性加成，无比例，3项被动效果联动
- **设计日期:** 2026-03-13

## 2. 装备规格

### 2.1 基础属性

| 字段 | 值 |
|---|---|
| type | EQUIPMENT |
| rarity | red |
| durability | 300 |
| required_level | 10 |
| gem_slots | 5 |
| repair_cost | 5 |
| attr_bonus | attack: 2000, agility: 2000 |
| attr_ratio | 无（不配置） |

### 2.2 装备描述

> 龙纹刻于鞋底，踏出的每一步都带着刃光。

### 2.3 平衡性对比

| 装备 | 定价 | 固定加成 | 比例加成 | 被动数量 | 主动技能 |
|---|---|---|---|---|---|
| 斩龙闪 | 600元 | 攻/血/敏各+100 | 攻/血/敏各×1.0 | 6 | 无 |
| **龙刃鞋** | **500元** | **攻+2000, 敏+2000** | **无** | **3** | **无** |
| 折光年 | 1000元 | 攻/血/法/防各+100 | 攻×5.0, 血/法/防各×3.0 | 5 | 有 |

**设计意图:** 500元档以大固定值代替比例，适合前期属性底较低的玩家，高阶玩家比例类装备价值更高；效果数量相应减少，定位克制合理。

## 3. 战斗效果

### 3.1 效果一：龙踏闪步

- **触发时机:** `first_turn`（战斗开始）
- **触发概率:** 100%
- **效果类型:** `buff_dodge`（闪避率提升）
- **数值:** +10%
- **持续回合:** 3回合
- **描述:** 踏出第一步，气流随刃散开——前3回合闪避率+10%
- **实现:** 使用现有 `buff_dodge` EffectType，无需新增代码

### 3.2 效果二：风刃反击

- **触发时机:** `on_dodge`（闪避时）
- **触发概率:** 100%
- **效果类型:** `buff_combo`（连击率提升）
- **数值:** +15%
- **持续回合:** 2回合
- **描述:** 刃从脚下穿出，闪过的瞬间反手踏击——闪避时连击率+15%（持续2回合）
- **实现:** 使用现有 `buff_combo` EffectType，无需新增代码
- **联动说明:** 与效果一形成链式联动：[1] 提升闪避率 → [2] 闪避后获得连击bonus

### 3.3 效果三：龙鳞护足

- **触发时机:** `each_turn`（每回合）
- **触发概率:** 100%
- **效果类型:** `damage_reduction`（受到伤害减少）
- **数值:** 3%
- **持续回合:** 999（全场被动）
- **描述:** 鞋面龙纹暗涌护气，步步皆盾——受到伤害减少3%
- **实现:** 使用现有 `damage_reduction` EffectType，无需新增代码

### 3.4 主动技能

无。500元档，被动效果足够。

## 4. 实现要点

### 4.1 YAML配置（data/items.yaml）

在 VIP 装备区块（`vip_equipment` 分类）末尾追加：

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
      value: 10
      duration: 3
      description: "[1] 龙踏闪步：踏出第一步，气流随刃散开——前3回合闪避率+10%"
    - trigger: "on_dodge"
      chance: 100
      effect: "buff_combo"
      value: 15
      duration: 2
      description: "[2] 风刃反击：刃从脚下穿出，闪过的瞬间反手踏击——闪避时连击率+15%（持续2回合）"
    - trigger: "each_turn"
      chance: 100
      effect: "damage_reduction"
      value: 3
      duration: 999
      description: "[3] 龙鳞护足：鞋面龙纹暗涌护气，步步皆盾——受到伤害减少3%"
  repair_cost: 5
```

### 4.2 需同步更新的文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `plugins/xiuxian_game/data/items.yaml` | 追加配置 | 主配置 |
| `plugins/xiuxian_game/item/equipment_commands.py` | 追加到 `_VIP_EQUIPMENT_SKILL_MENUS` | 装备菜单显示 |
| `plugins/xiuxian_game/battle/enhanced_engine.py` | 追加到 `VIP_EQUIPMENT_IDS` 集合 | 0阶全解锁 |
| `plugins/xiuxian_game/item/catalog.py` | 追加到 `VIP_EQUIPMENT_IDS` 集合 | 图鉴解锁判定 |

### 4.3 无需新增的内容

- **无新 EffectType** - 三个效果全部使用现有类型
- **无新 TriggerType** - 全部使用现有触发器
- **无数据库迁移** - 不新增字段
- **无主动技能指令** - 无专属命令处理逻辑

## 5. 验证清单

- [ ] 重启机器人，检查启动日志无报错
- [ ] `【我的装备】` 能正确显示龙刃鞋属性和3个效果
- [ ] `【装备菜单】` 进入龙刃鞋显示被动效果说明
- [ ] 进入战斗，确认效果[1]开场触发闪避buff
- [ ] 成功闪避，确认效果[2]触发连击buff
- [ ] 受到攻击，确认效果[3]减伤3%生效
- [ ] 0阶装备即可解锁全部3个效果

---

**版本:** 1.0
**创建时间:** 2026-03-13
**状态:** 待实现
