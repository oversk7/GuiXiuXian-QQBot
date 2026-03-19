# Phase 3: 怪物掉落铭文系统设计

> **日期**: 2026-03-19
> **状态**: 设计中
> **前置**: Phase 1 (词缀系统) + Phase 2 (铭文/分解/洗炼系统)

---

## 1. 设计目标

- 为铭文增加**战斗掉落**获取途径，作为铭文的主要来源
- 引入**高级铭文**（多效果模板），与现有基础铭文形成层级差异
- 引入**品阶系统**，同名铭文通过数值质量区分
- 引入**铭文碎片**，替代分解出铭文的机制，提供确定性合成路径
- 确保铭文的**稀有性**：仅精英怪掉落，概率低，极品难得

---

## 2. 铭文分级体系

### 2.1 基础铭文（现有34种）

- **效果**: 单条效果，1-2个随机数值
- **获取途径**: 铭文碎片合成（原分解出铭文途径移除）
- **定位**: 入门级铭文，人人可得但需积累碎片

### 2.2 高级铭文（新增10-15种模板）

- **效果**: 每个模板携带2-3条固定效果类型，数值随机浮动
- **获取途径**: 仅精英怪掉落
- **定位**: 稀有收藏品，核心战力提升手段

### 2.3 品阶系统

所有铭文（基础+高级）掉落/合成时根据数值roll质量自动评定品阶：

| 品阶 | 数值百分位 | 出现概率 | 显示格式 |
|------|-----------|---------|---------|
| 下品 | 0-25% | 40% | 铭文·度厄天书{下品} |
| 中品 | 25-65% | 35% | 铭文·恐惧之力{中品} |
| 上品 | 65-90% | 20% | 铭文·度厄天书{上品} |
| 极品 | 90-100% | 5% | 铭文·度厄天书{极品} |

**品阶评定算法**: 对铭文所有随机数值取百分位均值，映射到品阶区间。

```python
def evaluate_grade(values: dict, effect_config: list) -> str:
    """
    values: {"chance": 12.5, "value": 28} 等实际roll值
    effect_config: 效果定义列表，包含 chance_range/value_range
    返回: "下品"/"中品"/"上品"/"极品"
    """
    percentiles = []
    for eff in effect_config:
        for key in ["chance", "value"]:
            range_key = f"{key}_range"
            if range_key in eff and key in values:
                low, high = eff[range_key]
                pct = (values[key] - low) / (high - low) if high > low else 0.5
                percentiles.append(pct)
    avg_pct = sum(percentiles) / len(percentiles) if percentiles else 0.5

    if avg_pct >= 0.90:
        return "极品"  # 5%
    elif avg_pct >= 0.65:
        return "上品"  # 20%
    elif avg_pct >= 0.25:
        return "中品"  # 35%
    else:
        return "下品"  # 40%
```

> **注意**: 由于 uniform 分布，品阶概率由区间宽度直接决定：极品10%区间≈10%概率，但多数值取均值后极品实际概率约5%（正态收敛效应）。

---

## 3. 高级铭文模板设计

### 3.1 设计原则

- 每个模板2-3条效果，效果类型组合有主题性（攻击型/防御型/控制型等）
- 单条效果的数值上限 ≤ 对应基础铭文的同类效果上限
- 高级铭文优势在于**多效果协同**，而非单条更强
- 极品高级铭文总战力 ≈ VIP装备special_effects水平，不超过
- 名称采用修仙/暗黑风格，优雅且有辨识度

### 3.2 高级铭文模板列表（12种）

#### 攻击型（4种）

**1. 铭文·修罗血典**（紫色）
- 攻击时{chance}%概率附加{value}%真实伤害（1回合）`chance_range:[6,14] value_range:[8,20]`
- 暴击时{chance}%概率吸取{value}%伤害为生命 `chance_range:[8,20] value_range:[8,22]`

**2. 铭文·灭世天书**（紫色）
- 首回合{chance}%概率攻击力+{value}%（2回合）`chance_range:[12,28] value_range:[12,25]`
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[4,12]`

**3. 铭文·噬魂魔经**（紫色）
- 攻击时{chance}%概率降低敌人{value}%防御（2回合）`chance_range:[8,18] value_range:[6,15]`
- 攻击时{chance}%概率吸取{value}%伤害为生命 `chance_range:[8,18] value_range:[6,16]`
- 目标低于30%血量时{chance}%概率伤害+{value}% `chance_range:[12,25] value_range:[15,32]`

**4. 铭文·天罚雷章**（橙色）
- 攻击时{chance}%概率附加{value}%真实伤害（1回合）`chance_range:[8,16] value_range:[10,22]`
- 首回合{chance}%概率暴击率+{value}%（3回合）`chance_range:[16,32] value_range:[12,28]`
- 暴击时{chance}%概率使敌人恐惧1回合 `chance_range:[8,18]`

#### 防御型（3种）

**5. 铭文·不灭金身**（紫色）
- 被攻击时{chance}%概率减少{value}%伤害（1回合）`chance_range:[8,18] value_range:[6,16]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[16,32] value_range:[6,14]`

**6. 铭文·归墟道经**（紫色）
- 每回合{chance}%概率回复{value}%最大生命 `chance_range:[12,28] value_range:[2,6]`
- 被攻击时{chance}%概率反弹{value}%伤害 `chance_range:[6,16] value_range:[8,20]`
- 低血量时{chance}%概率防御+{value}%（2回合）`chance_range:[16,32] value_range:[12,25]`

**7. 铭文·太虚镜录**（橙色）
- 被攻击时{chance}%概率反弹{value}%伤害 `chance_range:[8,20] value_range:[10,22]`
- 被攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[6,14]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[18,36] value_range:[8,16]`

#### 控制型（3种）

**8. 铭文·幽冥咒典**（紫色）
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[4,12]`
- 攻击时{chance}%概率降低敌人{value}%攻击（2回合）`chance_range:[8,18] value_range:[6,14]`

**9. 铭文·封神禁录**（紫色）
- 攻击时{chance}%概率降低敌人{value}%防御（2回合）`chance_range:[8,18] value_range:[6,14]`
- 攻击时{chance}%概率降低敌人{value}%攻击（2回合）`chance_range:[8,18] value_range:[6,14]`
- 被暴击时{chance}%概率使敌人恐惧1回合 `chance_range:[8,16]`

**10. 铭文·万劫魔章**（橙色）
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[6,14]`
- 攻击时{chance}%概率附加{value}%真实伤害（1回合）`chance_range:[6,14] value_range:[8,18]`
- 攻击时{chance}%概率降低敌人{value}%防御（2回合）`chance_range:[8,18] value_range:[8,16]`

#### 综合型（2种）

**11. 铭文·轮回仙典**（橙色）
- 首回合{chance}%概率攻击力+{value}%（2回合）`chance_range:[12,25] value_range:[10,22]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[16,32] value_range:[6,14]`
- 每回合{chance}%概率回复{value}%最大生命 `chance_range:[12,25] value_range:[2,5]`

**12. 铭文·渡劫残页**（紫色）
- 闪避成功后{chance}%概率回复{value}%最大生命 `chance_range:[12,25] value_range:[4,10]`
- 闪避成功后{chance}%概率暴击率+{value}%（1回合）`chance_range:[12,25] value_range:[16,40]`

### 3.3 稀有度分布

| 稀有度 | 数量 | 定位 |
|--------|------|------|
| 紫色 | 8种 | 精英怪常规掉落 |
| 橙色 | 4种 | 高层精英怪稀有掉落 |

---

## 4. 掉落机制

### 4.1 掉落规则

- **仅精英怪掉落**，普通怪不掉铭文
- 掉落判定在现有 `handle_monster_drops()` 末尾追加

### 4.2 掉落概率

```python
# 精英怪铭文掉落配置
INSCRIPTION_DROP_CONFIG = {
    # 基于怪物等级的掉落率
    "base_rate": {
        (1, 60): 0.0,       # 60级以下精英怪不掉铭文
        (61, 100): 0.03,    # 61-100级精英怪: 3%
        (101, 200): 0.04,   # 101-200级精英怪: 4%
        (201, 999): 0.05,   # 200级以上精英怪: 5%
    },
    # 掉落铭文类型权重
    "type_weights": {
        "basic": 60,        # 60%概率掉基础铭文（34种之一）
        "advanced": 40,     # 40%概率掉高级铭文（12种之一）
    },
    # 高级铭文稀有度权重（仅当掉落高级铭文时）
    "advanced_rarity_weights": {
        "purple": 80,       # 80%紫色
        "orange": 20,       # 20%橙色
    },
    # 橙色高级铭文需要的最低怪物等级
    "orange_min_level": 150,
}
```

### 4.3 幸运值影响

与现有掉落一致：`final_rate = base_rate * (1 + luck_prob(player.luck))`

### 4.4 掉落流程

```
精英怪击杀
  → 是否满足等级门槛？(60级+)
    → 否: 不掉铭文
    → 是: roll掉落概率 (3-5% * 幸运加成)
      → 未中: 不掉铭文
      → 命中: 决定铭文类型
        → 60%基础铭文: 从34种中随机选1种，生成随机数值
        → 40%高级铭文: 按稀有度权重选1种模板，生成随机数值
          → 评定品阶 (下品/中品/上品/极品)
          → 创建 ItemInstance，存入背包
          → 显示掉落信息
```

---

## 5. 铭文碎片系统

### 5.1 核心概念

铭文碎片(`inscription_fragment`)是一种新的消耗品物品，用于合成基础铭文。

### 5.2 物品定义

```yaml
- item_id: "inscription_fragment"
  name: "铭文碎片"
  description: "蕴含残缺铭文力量的碎片，收集足够数量可合成铭文"
  type: "MATERIAL"
  rarity: "blue"
  price: 3000
  stackable: true
```

### 5.3 获取途径

- **分解带T2词缀装备**: 原来概率出铭文 → 改为必定出1-3个铭文碎片（按T2词缀数量）
- **精英怪掉落**: 精英怪除了铭文掉落判定外，额外有独立的碎片掉落（15-25%概率掉1-2个）

### 5.4 合成规则

```
【合成铭文】 消耗5个铭文碎片 → 随机获得1个基础铭文（34种之一）
```

- 合成的基础铭文同样走品阶评定
- 高级铭文**不可**通过碎片合成，仅精英怪掉落

---

## 6. 分解系统改造

### 6.1 变更内容

| 项目 | 改造前 | 改造后 |
|------|--------|--------|
| T2词缀装备分解 | 洗词石 + 概率出铭文 | 洗词石 + 必出铭文碎片(按T2词缀数) |
| 铭文提取概率 | 30% (INSCRIPTION_EXTRACT_CHANCE) | 移除 |
| 碎片产出 | 无 | 每个T2词缀必出1个碎片 |

### 6.2 代码影响

- `decompose_service.py`: `calculate_decompose_yields()` 返回碎片数量替代铭文列表
- `decompose_commands.py`: 显示消息调整
- `inscription_service.py`: 移除 `T2_AFFIX_TO_INSCRIPTION` 映射（或保留但不再在分解中使用）

---

## 7. 高级铭文存储方案

### 7.1 YAML定义

高级铭文在 `items.yaml` 中定义为独立物品，每个模板一个条目：

```yaml
- item_id: "adv_inscription_xiuluo"
  name: "铭文·修罗血典"
  description: "攻击附加真伤，暴击吸血"
  type: "INSCRIPTION"
  rarity: "purple"
  price: 50000
  inscription_type: "advanced"
  inscription_effects:
    - trigger: "on_attack"
      effect: "true_damage"
      duration: 1
      chance_range: [6, 14]
      value_range: [8, 20]
    - trigger: "on_critical"
      effect: "lifesteal"
      chance_range: [8, 20]
      value_range: [8, 22]
```

### 7.2 ItemInstance 存储

```python
# 高级铭文的 extra_attrs
{
    "_inscription_values": {
        "effects": [
            {"chance": 10.2, "value": 15.8},   # 第1条效果的roll值
            {"chance": 14.5, "value": 16.3},    # 第2条效果的roll值
        ]
    },
    "_inscription_grade": "上品"   # 品阶
}
```

### 7.3 与基础铭文的兼容

基础铭文保持现有存储格式不变：
```python
# 基础铭文的 extra_attrs（现有格式，新增品阶字段）
{
    "_inscription_values": {"chance": 12, "value": 25},
    "_inscription_grade": "中品"   # 新增
}
```

---

## 8. 战斗引擎集成

### 8.1 高级铭文转TriggerConfig

高级铭文的每条效果独立转换为一个 `TriggerConfig`，与基础铭文的处理方式一致。
现有 `inscription_service.py` 的 `inscription_to_trigger_config()` 需扩展支持多效果。

### 8.2 效果叠加

- 高级铭文的多条效果各自独立触发，互不干扰
- 与其他来源的同类效果正常叠加（遵循现有叠加规则）

---

## 9. 显示格式

### 9.1 掉落消息

```
📜 精英怪掉落铭文：铭文·修罗血典{上品}
  ├ 攻击时10.2%概率附加15.8%真实伤害(1回合)
  ├ 暴击时14.5%概率吸取16.3%伤害为生命
```

### 9.2 背包/图鉴显示

```
📜 铭文·修罗血典{上品}（紫色·高级铭文）
  攻击时10.2%概率附加15.8%真实伤害(1回合)
  暴击时14.5%概率吸取16.3%伤害为生命
```

### 9.3 合成消息

```
🔮 合成成功！消耗铭文碎片 x5
  获得：铭文·恐惧之力{中品}
  攻击时9.8%概率使敌人恐惧1回合
```

---

## 10. 平衡性分析

### 10.1 获取难度对比

| 获取方式 | 难度 | 产出 |
|---------|------|------|
| 碎片合成 | 中（需5碎片，碎片来自分解T2装备或精英怪） | 随机基础铭文 |
| 精英怪掉落(基础) | 高（精英怪3-5% × 60%） | 随机基础铭文 |
| 精英怪掉落(高级紫) | 很高（精英怪3-5% × 40% × 80%） | 随机紫色高级铭文 |
| 精英怪掉落(高级橙) | 极高（精英怪3-5% × 40% × 20%，需150级+） | 随机橙色高级铭文 |
| 精英怪掉落(高级橙·极品) | 传说级（上述 × 5%品阶概率） | 极品橙色高级铭文 |

### 10.2 效果强度上限

- 高级铭文单条效果数值 ≤ 基础铭文同效果上限
- 高级铭文总效果量级 ≈ VIP装备的special_effects（2-3条效果的总和）
- 极品高级橙色铭文 ≈ VIP装备效果上限，不超过

### 10.3 经济影响

- 铭文碎片可交易，价格由市场决定
- 高级铭文可交易，极品铭文将成为高价值交易品
- 碎片合成提供保底路径，防止纯非酋玩家无铭文可用

---

## 11. 新增命令

### 11.1 合成铭文

```
【合成铭文】 - 消耗5个铭文碎片，合成1个随机基础铭文
```

### 11.2 现有命令调整

- 【分解】 - 输出消息从"提取铭文"改为"获得铭文碎片"
- 【背包】/【图鉴】 - 铭文显示增加品阶标识

---

## 12. 涉及文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `data/items.yaml` | 修改 | 新增12种高级铭文模板 + 铭文碎片物品 |
| `item/inscription_service.py` | 修改 | 支持高级铭文多效果、品阶评定、掉落生成 |
| `world/dungeon_battle.py` | 修改 | `handle_monster_drops()` 末尾追加铭文掉落逻辑 |
| `item/decompose_service.py` | 修改 | T2词缀分解产出改为铭文碎片 |
| `item/decompose_commands.py` | 修改 | 分解消息调整 |
| `item/inscription_commands.py` | 新增 | 【合成铭文】命令 |
| `player/help.py` | 修改 | 新增合成铭文帮助信息 |
| `data/knowledge/*.yaml` | 修改 | 同步AI知识库 |
