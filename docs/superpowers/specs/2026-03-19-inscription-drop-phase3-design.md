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
- **获取途径**: 铭文碎片合成（原分解出铭文途径移除）+ 精英怪掉落
- **定位**: 入门级铭文，人人可得但需积累碎片

### 2.2 高级铭文（新增12种模板）

- **效果**: 每个模板携带2-3条固定效果类型，数值随机浮动
- **获取途径**: 仅精英怪掉落
- **定位**: 稀有收藏品，核心战力提升手段

### 2.3 品阶系统

所有铭文（基础+高级）掉落/合成时根据数值roll质量自动评定品阶：

| 品阶 | 数值百分位 | 出现概率 | 显示格式 | 意义 |
|------|-----------|---------|---------|------|
| 下品 | 0-25% | ~40% | 铭文·度厄天书{下品} | 效果偏弱，可用于过渡 |
| 中品 | 25-65% | ~35% | 铭文·恐惧之力{中品} | 标准效果，实用水平 |
| 上品 | 65-90% | ~20% | 铭文·度厄天书{上品} | 优秀数值，有交易价值 |
| 极品 | 90-100% | ~5% | 铭文·度厄天书{极品} | 顶级数值，高收藏和交易价值 |

**品阶仅由数值质量决定**，不影响掉落概率。品阶的意义在于：同一铭文模板的极品版本比下品版本战斗效果强约2-3倍（因数值区间跨度大），构成铭文间的核心价值差异。

**品阶评定算法**: 对铭文所有随机数值取百分位均值，映射到品阶区间。

```python
def evaluate_grade(effect_values: list[dict], effect_configs: list[dict]) -> str:
    """
    Args:
        effect_values: [{"chance": 12.5, "value": 28}, ...] 每条效果的实际roll值
        effect_configs: [{"chance_range": [6,14], "value_range": [8,20]}, ...] YAML定义
    Returns: "下品"/"中品"/"上品"/"极品"
    """
    percentiles = []
    for vals, cfg in zip(effect_values, effect_configs):
        for key in ["chance", "value"]:
            range_key = f"{key}_range"
            if range_key in cfg and key in vals:
                low, high = cfg[range_key]
                pct = (vals[key] - low) / (high - low) if high > low else 1.0
                pct = max(0.0, min(1.0, pct))
                percentiles.append(pct)
    avg_pct = sum(percentiles) / len(percentiles) if percentiles else 0.5

    if avg_pct >= 0.90:
        return "极品"
    elif avg_pct >= 0.65:
        return "上品"
    elif avg_pct >= 0.25:
        return "中品"
    else:
        return "下品"
```

> **注意**: uniform分布多数值取均值后趋向正态分布，极品(top 10%区间)实际出现概率约5%。

---

## 3. 高级铭文模板设计

### 3.1 设计原则

- 每个模板2-3条效果，效果类型组合有主题性（攻击型/防御型/控制型等）
- 单条效果的数值上限 <= 对应基础铭文的同类效果上限
- 高级铭文优势在于**多效果协同**，而非单条更强
- 极品高级铭文总战力 ~= VIP装备special_effects水平，不超过
- 名称采用修仙/暗黑风格，优雅且有辨识度

### 3.2 高级铭文模板列表（12种）

#### 攻击型（4种）

**1. 铭文·修罗血典**（紫色）`adv_inscription_xiuluo`
- 攻击时{chance}%概率附加{value}%真实伤害(1回合) `chance_range:[6,14] value_range:[8,20]`
- 暴击时{chance}%概率吸取{value}%伤害为生命 `chance_range:[8,20] value_range:[8,22]`

**2. 铭文·灭世天书**（紫色）`adv_inscription_mieshi`
- 首回合{chance}%概率攻击力+{value}%(2回合) `chance_range:[12,28] value_range:[12,25]`
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[4,12]`

**3. 铭文·噬魂魔经**（紫色）`adv_inscription_shihun`
- 攻击时{chance}%概率降低敌人{value}%防御(2回合) `chance_range:[8,18] value_range:[6,15]`
- 攻击时{chance}%概率吸取{value}%伤害为生命 `chance_range:[8,18] value_range:[6,16]`
- 目标低于30%血量时{chance}%概率伤害+{value}% `chance_range:[12,25] value_range:[15,32]`

**4. 铭文·天罚雷章**（橙色）`adv_inscription_tianfa`
- 攻击时{chance}%概率附加{value}%真实伤害(1回合) `chance_range:[8,16] value_range:[10,22]`
- 首回合{chance}%概率暴击率+{value}%(3回合) `chance_range:[16,32] value_range:[12,28]`
- 暴击时{chance}%概率使敌人恐惧1回合 `chance_range:[8,18]`

#### 防御型（3种）

**5. 铭文·不灭金身**（紫色）`adv_inscription_bumie`
- 被攻击时{chance}%概率减少{value}%伤害(1回合) `chance_range:[8,18] value_range:[6,16]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[16,32] value_range:[6,14]`

**6. 铭文·归墟道经**（紫色）`adv_inscription_guixu`
- 每回合{chance}%概率回复{value}%最大生命 `chance_range:[12,28] value_range:[2,6]`
- 被攻击时{chance}%概率反弹{value}%伤害 `chance_range:[6,16] value_range:[8,20]`
- 低血量时{chance}%概率防御+{value}%(2回合) `chance_range:[16,32] value_range:[12,25]`

**7. 铭文·太虚镜录**（橙色）`adv_inscription_taixu`
- 被攻击时{chance}%概率反弹{value}%伤害 `chance_range:[8,20] value_range:[10,22]`
- 被攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[6,14]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[18,36] value_range:[8,16]`

#### 控制型（3种）

**8. 铭文·幽冥咒典**（紫色）`adv_inscription_youming`
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[4,12]`
- 攻击时{chance}%概率降低敌人{value}%攻击(2回合) `chance_range:[8,18] value_range:[6,14]`

**9. 铭文·封神禁录**（紫色）`adv_inscription_fengshen`
- 攻击时{chance}%概率降低敌人{value}%防御(2回合) `chance_range:[8,18] value_range:[6,14]`
- 攻击时{chance}%概率降低敌人{value}%攻击(2回合) `chance_range:[8,18] value_range:[6,14]`
- 被暴击时{chance}%概率使敌人恐惧1回合 `chance_range:[8,16]`

**10. 铭文·万劫魔章**（橙色）`adv_inscription_wanjie`
- 攻击时{chance}%概率使敌人恐惧1回合 `chance_range:[6,14]`
- 攻击时{chance}%概率附加{value}%真实伤害(1回合) `chance_range:[6,14] value_range:[8,18]`
- 攻击时{chance}%概率降低敌人{value}%防御(2回合) `chance_range:[8,18] value_range:[8,16]`

#### 综合型（2种）

**11. 铭文·轮回仙典**（橙色）`adv_inscription_lunhui`
- 首回合{chance}%概率攻击力+{value}%(2回合) `chance_range:[12,25] value_range:[10,22]`
- 首回合{chance}%概率获得{value}%最大生命护盾 `chance_range:[16,32] value_range:[6,14]`
- 每回合{chance}%概率回复{value}%最大生命 `chance_range:[12,25] value_range:[2,5]`

**12. 铭文·渡劫残页**（紫色）`adv_inscription_dujie`
- 闪避成功后{chance}%概率回复{value}%最大生命 `chance_range:[12,25] value_range:[4,10]`
- 闪避成功后{chance}%概率暴击率+{value}%(1回合) `chance_range:[12,25] value_range:[16,40]`

### 3.3 稀有度分布

| 稀有度 | 数量 | 定位 |
|--------|------|------|
| 紫色 | 8种 | 精英怪常规掉落 |
| 橙色 | 4种 | 高层精英怪(150级+)稀有掉落 |

---

## 4. 掉落机制

### 4.1 掉落规则

- **仅精英怪掉落**，普通怪不掉铭文
- 掉落判定在现有 `handle_monster_drops()` 末尾追加（装备掉落逻辑之后）

### 4.2 掉落概率

```python
# 精英怪铭文掉落配置（dungeon_battle.py 顶部常量区）
INSCRIPTION_DROP_RATES = {
    60: 0.0,     # 60级以下精英怪不掉铭文
    100: 0.03,   # 61-100级精英怪: 3%
    200: 0.04,   # 101-200级精英怪: 4%
    9999: 0.05,  # 200级以上精英怪: 5%
}
INSCRIPTION_TYPE_WEIGHTS = {"basic": 60, "advanced": 40}
ADVANCED_RARITY_WEIGHTS = {"purple": 80, "orange": 20}
ADVANCED_ORANGE_MIN_LEVEL = 150  # 橙色高级铭文最低怪物等级

# 铭文碎片掉落（独立于铭文掉落判定）
FRAGMENT_DROP_RATE = 0.20      # 精英怪20%概率掉碎片
FRAGMENT_DROP_QUANTITY = (1, 2) # 掉1-2个
```

### 4.3 幸运值影响

- 幸运值**仅影响掉落概率**：`final_rate = base_rate * (1 + luck_prob(player.luck))`
- 幸运值**不影响**铭文类型权重(基础/高级比例)、高级铭文稀有度权重、品阶评定
- 与现有材料/装备掉落行为一致

### 4.4 掉落流程

```
精英怪击杀 (is_elite=True)
  │
  ├─ [铭文掉落判定]
  │   → 怪物等级 < 60？跳过
  │   → roll掉落概率 (3-5% * 幸运加成)
  │     → 未中: 无铭文
  │     → 命中: 按权重决定类型
  │       ├─ 60% 基础铭文: 从34种中随机选1种
  │       └─ 40% 高级铭文: 按稀有度权重选1种模板
  │           └─ 橙色需 monster_level >= 150，否则降为紫色
  │   → 生成随机数值 → 评定品阶
  │   → try: 创建ItemInstance存入背包
  │     except ValueError: 提示"背包已满，铭文掉落未能入包"
  │
  └─ [碎片掉落判定]（独立判定，与铭文掉落互不影响）
      → roll 20%概率
      → 命中: 掉落1-2个铭文碎片
      → try: add_item → except ValueError: 跳过（背包满）
```

### 4.5 期望值计算

假设玩家稳定刷200级+精英怪（base_rate=5%，无幸运加成）：

| 目标 | 综合概率 | 期望战斗次数 |
|------|---------|------------|
| 任意铭文 | 5% | ~20次 |
| 任意基础铭文 | 5% x 60% = 3% | ~33次 |
| 任意高级紫色铭文 | 5% x 40% x 80% = 1.6% | ~63次 |
| 任意高级橙色铭文 | 5% x 40% x 20% = 0.4% | ~250次 |
| 特定高级橙色铭文 | 0.4% / 4 = 0.1% | ~1000次 |
| 特定高级橙色·极品 | 0.1% x 5% = 0.005% | ~20000次 |
| 铭文碎片 | 20% | ~5次 |

---

## 5. 铭文碎片系统

### 5.1 核心概念

铭文碎片(`inscription_fragment`)是一种新的可堆叠材料物品，用于合成基础铭文。

### 5.2 物品定义

```yaml
- item_id: "inscription_fragment"
  name: "铭文碎片"
  description: "蕴含残缺铭文力量的碎片，收集足够数量可合成铭文"
  type: "MATERIAL"
  rarity: "blue"
  price: 3000
```

### 5.3 获取途径

- **分解带T2词缀装备**: 每个T2词缀必出1个碎片（原来30%概率出铭文 -> 改为必出碎片）
- **精英怪掉落**: 20%概率掉1-2个（独立于铭文掉落判定）
- 设计意图：分解是碎片的稳定来源，精英怪是额外补充

### 5.4 合成规则

```
【合成铭文】 消耗5个铭文碎片 -> 随机获得1个基础铭文（34种之一）+ 品阶评定
```

---

## 6. 分解系统改造

### 6.1 变更内容

| 项目 | 改造前 | 改造后 |
|------|--------|--------|
| T2词缀装备分解 | 洗词石 + 30%概率出铭文 | 洗词石 + 必出铭文碎片(按T2词缀数) |
| DecomposeResult | `inscriptions: list[dict]` | `fragment_count: int` |

### 6.2 代码变更

**decompose_service.py**:
```python
@dataclass
class DecomposeResult:
    reroll_stones: int
    fragment_count: int  # 原来是 inscriptions: list[dict]

def calculate_decompose_yields(equipment, rng) -> DecomposeResult:
    # ... 洗词石计算不变 ...

    # T2 词缀 -> 铭文碎片（每个T2词缀产1个碎片）
    t2_count = sum(1 for a in affixes if a.get("tier") == "T2")

    return DecomposeResult(reroll_stones=total_stones, fragment_count=t2_count)
```

**decompose_commands.py**: 消息中 "提取铭文：xxx" -> "获得铭文碎片 x{count}"

---

## 7. 统一存储方案

### 7.1 核心设计：区分基础/高级铭文

通过 YAML 中的 `inscription_type` 字段区分：
- 基础铭文：无 `inscription_type` 字段（或值为空），使用 `inscription_effect`（单数，单条效果）
- 高级铭文：`inscription_type: "advanced"`，使用 `inscription_effects`（复数，多条效果列表）

### 7.2 YAML定义示例

```yaml
# 基础铭文（现有格式不变）
- item_id: "inscription_fear"
  name: "铭文：恐惧之力"
  type: "INSCRIPTION"
  rarity: "blue"
  price: 15000
  inscription_effect:          # 单数，单条效果
    trigger: "on_attack"
    effect: "fear"
    duration: 1
    chance_range: [5, 15]

# 高级铭文（新格式）
- item_id: "adv_inscription_xiuluo"
  name: "铭文·修罗血典"
  description: "攻击附加真伤，暴击吸血"
  type: "INSCRIPTION"
  rarity: "purple"
  price: 50000
  inscription_type: "advanced"
  inscription_effects:         # 复数，多条效果列表
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

### 7.3 ItemInstance.extra_attrs 存储

**统一规则**: `_inscription_values` 始终为**列表**格式，每个元素对应一条效果的roll值。

```python
# 基础铭文（单条效果 -> 长度为1的列表）
{
    "_inscription_values": [{"chance": 12, "value": 25}],
    "_inscription_grade": "中品"
}

# 高级铭文（多条效果 -> 长度为2-3的列表）
{
    "_inscription_values": [
        {"chance": 10.2, "value": 15.8},
        {"chance": 14.5, "value": 16.3},
    ],
    "_inscription_grade": "上品"
}
```

### 7.4 向后兼容

现有基础铭文的 `_inscription_values` 是扁平字典 `{"chance": 12}`，需要兼容处理：

```python
def normalize_inscription_values(extra_attrs: dict) -> list[dict]:
    """统一读取铭文数值，兼容旧格式"""
    raw = extra_attrs.get("_inscription_values", {})
    if isinstance(raw, list):
        return raw          # 新格式：直接返回
    if isinstance(raw, dict):
        return [raw]        # 旧格式：包装为单元素列表
    return []
```

新创建的基础铭文一律用列表格式。旧数据通过 `normalize_inscription_values()` 兼容读取，无需数据库迁移。

### 7.5 gem_slots_data 中的高级铭文

高级铭文镶嵌到装备孔位时，存储格式与基础铭文一致（复用现有结构）：

```python
gem_slots_data = {
    "0": "critical_bead_1",                          # 宝石
    "1": {                                            # 高级铭文
        "item_id": "adv_inscription_xiuluo",
        "values": [{"chance": 10.2, "value": 15.8}, {"chance": 14.5, "value": 16.3}]
    }
}
```

---

## 8. 战斗引擎集成

### 8.1 inscription_service.py 接口变更

```python
def inscription_to_trigger_configs(
    item_id: str,
    values: list[dict],
    source_name: str = ""
) -> list[TriggerConfig]:
    """将铭文转换为TriggerConfig列表（支持基础和高级铭文）

    Args:
        item_id: 铭文模板ID (如 "inscription_fear" 或 "adv_inscription_xiuluo")
        values: 标准化后的数值列表 [{"chance": 12}, ...]
        source_name: 来源装备名（用于战斗日志）

    Returns:
        list[TriggerConfig] - 基础铭文返回1个，高级铭文返回2-3个
    """
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return []

    is_advanced = getattr(item_cfg, 'inscription_type', None) == "advanced"

    if is_advanced:
        effect_cfgs = getattr(item_cfg, 'inscription_effects', [])
    else:
        single_eff = _get_inscription_effect(item_id)
        effect_cfgs = [single_eff] if single_eff else []

    triggers = []
    for i, eff_cfg in enumerate(effect_cfgs):
        vals = values[i] if i < len(values) else {}
        triggers.append(_build_trigger_config(eff_cfg, vals, item_cfg.name, source_name))

    return triggers
```

**现有 `inscription_to_trigger_config()`（单数）保留不动**，作为旧接口兼容。新代码统一调用复数版本 `inscription_to_trigger_configs()`。

### 8.2 enhanced_engine.py 调用侧

现有代码读取 gem_slots_data 中铭文并调用 `inscription_to_trigger_config()` 的位置，改为调用 `inscription_to_trigger_configs()` 并注册返回的所有 TriggerConfig。

### 8.3 效果叠加

- 高级铭文的多条效果各自独立触发，互不干扰
- 与其他来源（装备special_effects/词缀/其他铭文）的同类效果正常叠加

---

## 9. 合成铭文命令

### 9.1 命令定义

```python
# item/inscription_commands.py
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg

from ..models import Player
from ..models.inventory import ItemInstance
from ..models.db import safe_session
from ..config import config
from .inscription_service import generate_inscription_values, evaluate_grade, get_inscription_display

FRAGMENT_COST = 5  # 合成消耗碎片数
FRAGMENT_ITEM_ID = "inscription_fragment"

synthesize_cmd = on_command("合成铭文", priority=5, block=True)

@synthesize_cmd.handle()
async def handle_synthesize(event: MessageEvent, args: Message = CommandArg()):
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await synthesize_cmd.finish("你还没有创建角色")

        # 检查碎片数量
        fragments = await ItemInstance.get_item(session, player.id, FRAGMENT_ITEM_ID)
        if not fragments or fragments.quantity < FRAGMENT_COST:
            current = fragments.quantity if fragments else 0
            await synthesize_cmd.finish(
                f"铭文碎片不足！需要{FRAGMENT_COST}个，当前{current}个"
            )

        # 扣除碎片
        fragments.quantity -= FRAGMENT_COST
        if fragments.quantity <= 0:
            await session.delete(fragments)

        # 随机选择基础铭文（34种）
        import random
        rng = random.Random()
        basic_ids = [iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
                     if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)]
        chosen_id = rng.choice(basic_ids)

        # 生成随机数值 + 品阶评定
        values = generate_inscription_values(chosen_id, rng)
        values_list = [values]  # 标准化为列表
        grade = evaluate_grade(values_list, chosen_id)

        # 创建铭文实例
        try:
            inst = ItemInstance(
                player_id=player.id,
                item_id=chosen_id,
                quantity=1,
                extra_attrs={"_inscription_values": values_list, "_inscription_grade": grade},
            )
            session.add(inst)
        except ValueError:
            await synthesize_cmd.finish("背包已满，无法合成铭文")

        # 显示结果
        display = get_inscription_display(chosen_id, values_list, grade)
        msg = f"合成成功！消耗铭文碎片 x{FRAGMENT_COST}\n  获得：{display}"

    await synthesize_cmd.finish(Message(msg))
```

### 9.2 帮助文案

```python
# player/help.py 新增
"合成铭文": {
    "usage": "【合成铭文】",
    "description": "消耗5个铭文碎片，合成1个随机基础铭文。铭文碎片可通过分解T2词缀装备或击杀精英怪获得。",
    "examples": ["合成铭文"]
}
```

---

## 10. 显示格式

### 10.1 掉落消息

```
📜 精英怪掉落铭文：铭文·修罗血典{上品}
  ├ 攻击时10.2%概率附加15.8%真实伤害(1回合)
  └ 暴击时14.5%概率吸取16.3%伤害为生命
```

### 10.2 背包/图鉴显示

```
📜 铭文·修罗血典{上品}（紫色·高级铭文）
  攻击时10.2%概率附加15.8%真实伤害(1回合)
  暴击时14.5%概率吸取16.3%伤害为生命
```

### 10.3 碎片掉落消息

```
📜 精英怪掉落：铭文碎片 x2
```

---

## 11. 平衡性分析

### 11.1 获取难度对比

见第4.5节期望值计算表。

### 11.2 效果强度上限

- 高级铭文单条效果数值 <= 基础铭文同效果上限
- 高级铭文总效果量级 ~= VIP装备的special_effects（2-3条效果的总和）
- 极品高级橙色铭文 ~= VIP装备效果上限，不超过

### 11.3 经济影响

- 铭文碎片可交易（MATERIAL类型），价格由市场决定
- 高级铭文可通过挂牌交易，极品铭文将成为高价值交易品
- 碎片合成提供保底路径，防止纯非酋玩家无铭文可用

---

## 12. 涉及文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `data/items.yaml` | 修改 | 新增12种高级铭文模板(`adv_inscription_*`) + 铭文碎片物品 |
| `config.py` | 修改 | ItemConfig解析支持 `inscription_type` 和 `inscription_effects`(复数) |
| `item/inscription_service.py` | 修改 | 新增 `inscription_to_trigger_configs()`(复数)、`evaluate_grade()`、`normalize_inscription_values()`、`generate_advanced_inscription_values()`、`get_inscription_display()` |
| `world/dungeon_battle.py` | 修改 | `handle_monster_drops()` 末尾追加铭文+碎片掉落逻辑 |
| `item/decompose_service.py` | 修改 | `DecomposeResult.inscriptions` -> `fragment_count`，移除铭文提取逻辑 |
| `item/decompose_commands.py` | 修改 | 分解消息："提取铭文" -> "获得铭文碎片" |
| `item/inscription_commands.py` | 新增 | 【合成铭文】命令 |
| `battle/enhanced_engine.py` | 修改 | 铭文注册改用 `inscription_to_trigger_configs()`(复数) |
| `item/catalog.py` | 修改 | 铭文显示增加品阶标识 |
| `item/equipment_commands.py` | 修改 | 装备详情中铭文显示增加品阶 |
| `player/help.py` | 修改 | 新增【合成铭文】帮助，更新【分解】帮助 |
| `data/knowledge/inscription_system_help.yaml` | 新增 | 铭文系统AI知识库 |

---

## 13. 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| 背包满时掉落铭文 | 提示"背包已满，铭文掉落未能入包"（区别于材料的静默跳过） |
| 背包满时掉落碎片 | 静默跳过（与材料掉落一致） |
| 背包满时合成铭文 | 合成前检查，提示"背包已满" |
| 怪物等级<60的精英怪 | 不触发铭文掉落判定 |
| 怪物等级<150掉高级橙色 | 降级为紫色高级铭文 |
| 旧格式基础铭文(_inscription_values为dict) | `normalize_inscription_values()` 兼容读取 |
| 合成时碎片不足 | 提示当前数量和所需数量 |
