# 装备词缀系统 Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现装备词缀系统 Phase 1 — 怪物掉落带随机词缀的装备 + 词缀战斗属性生效 + 装备详情展示词缀。

**Architecture:** 新增 `affixes.yaml` 配置词缀池，新增 `AffixService` 生成/管理词缀。词缀数据存储在 ItemInstance.extra_attrs["_affixes"] 中（`_` 前缀避免被 apply_attr_bonus 误读）。T1 词缀在 BattleAttributeCalculator 中累加战斗属性，T2 词缀在战斗初始化时复用 TriggerConfig 机制注册到 BattleEffectManager。怪物掉落装备逻辑扩展 dungeon_battle.py 的 handle_monster_drops。

**Tech Stack:** NoneBot2, SQLAlchemy (safe_session), YAML 配置, 现有战斗效果系统 (TriggerConfig/BattleEffectManager)

**Spec:** `docs/superpowers/specs/2026-03-18-equipment-affix-inscription-design.md`

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Create | `plugins/xiuxian_game/data/affixes.yaml` | 词缀池配置（T1×18 + T2×20） |
| Create | `plugins/xiuxian_game/item/affix_service.py` | 词缀生成、读取、格式化 |
| Modify | `plugins/xiuxian_game/world/dungeon_battle.py` | 怪物掉落装备逻辑 |
| Modify | `plugins/xiuxian_game/item/equipment_commands.py` | 装备详情展示词缀 |
| Modify | `plugins/xiuxian_game/battle/battle_attributes.py` | T1 词缀累加战斗属性 |
| Modify | `plugins/xiuxian_game/battle/enhanced_engine.py` | T2 词缀注册为战斗触发器 |
| Modify | `plugins/xiuxian_game/data/items.yaml` | 新增洗炼石消耗品定义 |
| Modify | `plugins/xiuxian_game/player/help.py` | 帮助信息更新 |

---

## Chunk 1: 词缀配置与服务

### Task 1: 创建词缀池配置 affixes.yaml

**Files:**
- Create: `plugins/xiuxian_game/data/affixes.yaml`

- [ ] **Step 1: 创建 affixes.yaml 配置文件**

```yaml
# 装备词缀配置
# T1: 数值型词缀 — 所有稀有度装备可出现，提供战斗属性固定百分比加成
# T2: 触发型词缀 — 仅蓝色及以上装备可出现，提供概率触发的战斗效果

# 词缀数量规则（按装备稀有度）
affix_count_rules:
  white:  {min: 0, max: 1, bonus_chance: 0.5}   # 50%概率带1条
  green:  {min: 1, max: 2, bonus_chance: 0.5}   # 50%概率2条
  blue:   {min: 2, max: 3, bonus_chance: 0.5}   # 50%概率3条
  purple: {min: 3, max: 4, bonus_chance: 0.5}   # 50%概率4条
  orange: {min: 4, max: 4, bonus_chance: 1.0}   # 必定4条

affixes:
  t1:
    - affix_id: "critical_rate"
      name: "锐利"
      description: "暴击率+{value}%"
      attribute: "critical_rate"
      ranges:
        white: [1.0, 2.0]
        green: [2.0, 4.0]
        blue: [3.0, 6.0]
        purple: [5.0, 8.0]
        orange: [7.0, 10.0]

    - affix_id: "combo_rate"
      name: "连斩"
      description: "连击率+{value}%"
      attribute: "combo_rate"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 4.5]
        purple: [3.5, 6.0]
        orange: [5.0, 8.0]

    - affix_id: "dodge_rate"
      name: "灵巧"
      description: "闪避率+{value}%"
      attribute: "dodge_rate"
      ranges:
        white: [1.0, 2.0]
        green: [2.0, 4.0]
        blue: [3.0, 6.0]
        purple: [5.0, 8.0]
        orange: [7.0, 10.0]

    - affix_id: "counter_rate"
      name: "反击"
      description: "反击率+{value}%"
      attribute: "counter_rate"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 5.0]
        purple: [4.0, 7.0]
        orange: [6.0, 9.0]

    - affix_id: "penetration_rate"
      name: "穿刺"
      description: "穿透率+{value}%"
      attribute: "penetration_rate"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 5.0]
        purple: [4.0, 7.0]
        orange: [6.0, 10.0]

    - affix_id: "anti_crit_rate"
      name: "坚韧"
      description: "抗暴率+{value}%"
      attribute: "anti_crit_rate"
      ranges:
        white: [1.0, 2.0]
        green: [2.0, 4.0]
        blue: [3.0, 6.0]
        purple: [5.0, 8.0]
        orange: [7.0, 10.0]

    - affix_id: "lifesteal_rate"
      name: "嗜血"
      description: "吸血率+{value}%"
      attribute: "lifesteal_rate"
      ranges:
        white: [0.3, 0.8]
        green: [0.5, 1.5]
        blue: [1.0, 2.5]
        purple: [2.0, 4.0]
        orange: [3.0, 5.0]

    - affix_id: "accuracy_rate"
      name: "精准"
      description: "命中率+{value}%"
      attribute: "accuracy_rate"
      ranges:
        white: [1.0, 2.0]
        green: [2.0, 4.0]
        blue: [3.0, 6.0]
        purple: [5.0, 8.0]
        orange: [7.0, 10.0]

    - affix_id: "critical_power"
      name: "暴力"
      description: "暴击伤害+{value}"
      attribute: "critical_power"
      ranges:
        white: [1, 2]
        green: [2, 4]
        blue: [3, 6]
        purple: [5, 8]
        orange: [7, 10]

    - affix_id: "skill_crit_rate"
      name: "灵爆"
      description: "灵爆率+{value}%"
      attribute: "skill_crit_rate"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 4.5]
        purple: [3.5, 6.0]
        orange: [5.0, 8.0]

    - affix_id: "immobilize_rate"
      name: "禁锢"
      description: "定身率+{value}%"
      attribute: "immobilize_rate"
      ranges:
        white: [0.3, 0.8]
        green: [0.5, 1.5]
        blue: [1.0, 2.5]
        purple: [2.0, 3.5]
        orange: [3.0, 5.0]

    - affix_id: "regen_rate"
      name: "回春"
      description: "回复率+{value}%"
      attribute: "regen_rate"
      ranges:
        white: [0.3, 0.8]
        green: [0.5, 1.5]
        blue: [1.0, 2.5]
        purple: [2.0, 4.0]
        orange: [3.0, 5.0]

    - affix_id: "first_strike_rate"
      name: "先手"
      description: "先手率+{value}%"
      attribute: "first_strike_rate"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 4.5]
        purple: [3.5, 6.0]
        orange: [5.0, 8.0]

    - affix_id: "tenacity"
      name: "韧性"
      description: "控制减免+{value}%"
      attribute: "tenacity"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 5.0]
        purple: [4.0, 7.0]
        orange: [6.0, 10.0]

    - affix_id: "mp_cost_reduction"
      name: "节能"
      description: "理智消耗减免+{value}%"
      attribute: "mp_cost_reduction"
      ranges:
        white: [0.5, 1.0]
        green: [1.0, 2.0]
        blue: [1.5, 3.0]
        purple: [2.5, 4.0]
        orange: [3.5, 5.0]

    - affix_id: "ignore_defense"
      name: "破甲"
      description: "无视防御+{value}"
      attribute: "ignore_defense"
      is_percentage: false
      ranges:
        white: [2, 5]
        green: [5, 12]
        blue: [10, 25]
        purple: [20, 40]
        orange: [35, 60]

    - affix_id: "block_reduction"
      name: "格挡"
      description: "格挡减伤+{value}%"
      attribute: "block_reduction"
      ranges:
        white: [0.5, 1.5]
        green: [1.0, 3.0]
        blue: [2.0, 5.0]
        purple: [4.0, 7.0]
        orange: [6.0, 10.0]

    - affix_id: "skill_crit_boost"
      name: "灵威"
      description: "技能暴击率+{value}%"
      attribute: "skill_crit_rate"
      ranges:
        white: [0.5, 1.0]
        green: [1.0, 2.0]
        blue: [1.5, 3.5]
        purple: [3.0, 5.0]
        orange: [4.5, 7.0]

    - affix_id: "true_damage_rate"
      name: "真伤"
      description: "真实伤害率+{value}%"
      attribute: "true_damage_rate"
      ranges:
        white: [0.3, 0.8]
        green: [0.5, 1.5]
        blue: [1.0, 2.5]
        purple: [2.0, 3.5]
        orange: [3.0, 5.0]

  t2:
    - affix_id: "fear_strike"
      name: "恐惧之力"
      description: "攻击时{value}%概率使敌人恐惧{value2}回合"
      trigger: "on_attack"
      effect: "fear"
      chance_ranges:
        blue: [5, 8]
        purple: [8, 12]
        orange: [12, 15]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "defense_pierce"
      name: "防御穿刺"
      description: "攻击时{value}%概率无视敌人{value2}%防御(2回合)"
      trigger: "on_attack"
      effect: "defense_penetration"
      chance_ranges:
        blue: [10, 15]
        purple: [15, 20]
        orange: [20, 25]
      value_ranges:
        blue: [15, 20]
        purple: [20, 25]
        orange: [25, 30]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 2]
        orange: [2, 3]

    - affix_id: "crit_lifesteal"
      name: "暴击吸血"
      description: "暴击时{value}%概率回复{value2}%造成伤害"
      trigger: "on_critical"
      effect: "lifesteal"
      chance_ranges:
        blue: [20, 30]
        purple: [30, 45]
        orange: [45, 60]
      value_ranges:
        blue: [8, 12]
        purple: [12, 18]
        orange: [18, 25]

    - affix_id: "damage_reflect"
      name: "伤害反弹"
      description: "被攻击时{value}%概率反弹{value2}%伤害"
      trigger: "on_attacked"
      effect: "reflect"
      chance_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      value_ranges:
        blue: [5, 10]
        purple: [10, 15]
        orange: [15, 20]

    - affix_id: "tough_reduce"
      name: "坚韧减伤"
      description: "被攻击时{value}%概率减少{value2}%伤害(1回合)"
      trigger: "on_attacked"
      effect: "damage_reduction"
      chance_ranges:
        blue: [15, 20]
        purple: [20, 28]
        orange: [28, 35]
      value_ranges:
        blue: [8, 12]
        purple: [12, 18]
        orange: [18, 25]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "true_damage_strike"
      name: "真伤附加"
      description: "攻击时{value}%概率附加{value2}%真实伤害(1回合)"
      trigger: "on_attack"
      effect: "true_damage"
      chance_ranges:
        blue: [8, 12]
        purple: [12, 18]
        orange: [18, 25]
      value_ranges:
        blue: [5, 10]
        purple: [10, 15]
        orange: [15, 20]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "first_strike_hit"
      name: "先手打击"
      description: "首回合{value}%概率提升{value2}%伤害(2回合)"
      trigger: "first_turn"
      effect: "damage_boost"
      chance_ranges:
        blue: [25, 35]
        purple: [35, 50]
        orange: [50, 65]
      value_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 2]
        orange: [2, 3]

    - affix_id: "execute_boost"
      name: "斩杀加伤"
      description: "目标低于30%血量时{value}%概率伤害+{value2}%"
      trigger: "on_attack"
      effect: "damage_boost"
      chance_ranges:
        blue: [20, 30]
        purple: [30, 45]
        orange: [45, 60]
      value_ranges:
        blue: [15, 20]
        purple: [20, 30]
        orange: [30, 40]
      threshold: 30

    - affix_id: "shield_condense"
      name: "护盾凝聚"
      description: "首回合{value}%概率获得{value2}%最大生命护盾"
      trigger: "first_turn"
      effect: "shield"
      chance_ranges:
        blue: [20, 30]
        purple: [30, 45]
        orange: [45, 60]
      value_ranges:
        blue: [5, 8]
        purple: [8, 12]
        orange: [12, 18]

    - affix_id: "kill_boost"
      name: "击杀加伤"
      description: "击杀后{value}%概率下次伤害+{value2}%"
      trigger: "on_kill"
      effect: "damage_boost"
      chance_ranges:
        blue: [30, 40]
        purple: [40, 55]
        orange: [55, 70]
      value_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "dodge_crit"
      name: "闪避必暴"
      description: "闪避成功后{value}%概率下次暴击+{value2}%"
      trigger: "on_dodge"
      effect: "buff_critical"
      chance_ranges:
        blue: [20, 30]
        purple: [30, 45]
        orange: [45, 60]
      value_ranges:
        blue: [15, 25]
        purple: [25, 40]
        orange: [40, 60]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "desperation_crit"
      name: "绝境暴击"
      description: "低血量时{value}%概率暴击率+{value2}%"
      trigger: "low_hp"
      effect: "buff_critical"
      chance_ranges:
        blue: [30, 40]
        purple: [40, 55]
        orange: [55, 70]
      value_ranges:
        blue: [10, 18]
        purple: [18, 28]
        orange: [28, 40]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 3]
        orange: [3, 3]

    - affix_id: "soul_burn"
      name: "灵魂灼烧"
      description: "攻击时{value}%概率灼烧敌人{value2}%理智(2回合)"
      trigger: "on_attack"
      effect: "debuff_defense"
      chance_ranges:
        blue: [8, 12]
        purple: [12, 18]
        orange: [18, 25]
      value_ranges:
        blue: [5, 8]
        purple: [8, 12]
        orange: [12, 18]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 2]
        orange: [2, 3]

    - affix_id: "periodic_regen"
      name: "周期回复"
      description: "每回合{value}%概率回复{value2}%最大生命"
      trigger: "each_turn"
      effect: "regen"
      chance_ranges:
        blue: [25, 35]
        purple: [35, 50]
        orange: [50, 65]
      value_ranges:
        blue: [2, 3]
        purple: [3, 5]
        orange: [5, 8]

    - affix_id: "cripple"
      name: "致残"
      description: "攻击时{value}%概率降低敌人{value2}%攻击(2回合)"
      trigger: "on_attack"
      effect: "debuff_attack"
      chance_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      value_ranges:
        blue: [5, 10]
        purple: [10, 15]
        orange: [15, 22]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 2]
        orange: [2, 3]

    - affix_id: "weaken"
      name: "弱化"
      description: "攻击时{value}%概率降低敌人{value2}%防御(2回合)"
      trigger: "on_attack"
      effect: "debuff_defense"
      chance_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      value_ranges:
        blue: [5, 10]
        purple: [10, 15]
        orange: [15, 22]
      duration_ranges:
        blue: [2, 2]
        purple: [2, 2]
        orange: [2, 3]

    - affix_id: "combo_stack"
      name: "连击叠伤"
      description: "连击时{value}%概率每次伤害+{value2}%"
      trigger: "on_attack"
      effect: "damage_boost"
      chance_ranges:
        blue: [15, 22]
        purple: [22, 30]
        orange: [30, 40]
      value_ranges:
        blue: [3, 5]
        purple: [5, 8]
        orange: [8, 12]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 1]

    - affix_id: "counter_stun"
      name: "反制"
      description: "被暴击时{value}%概率使敌人恐惧{value2}回合"
      trigger: "on_attacked"
      effect: "fear"
      chance_ranges:
        blue: [8, 12]
        purple: [12, 18]
        orange: [18, 25]
      duration_ranges:
        blue: [1, 1]
        purple: [1, 1]
        orange: [1, 2]

    - affix_id: "doom_judgment"
      name: "末日审判"
      description: "攻击时{value}%概率对低血量敌人伤害+{value2}%"
      trigger: "on_attack"
      effect: "damage_boost"
      chance_ranges:
        blue: [10, 15]
        purple: [15, 22]
        orange: [22, 30]
      value_ranges:
        blue: [20, 30]
        purple: [30, 45]
        orange: [45, 60]
      threshold: 20
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/data/affixes.yaml
git commit -m "feat(affix): 添加词缀池配置 affixes.yaml (T1×18 + T2×20)"
```

---

### Task 2: 创建 AffixService 词缀服务

**Files:**
- Create: `plugins/xiuxian_game/item/affix_service.py`

- [ ] **Step 1: 创建 affix_service.py**

```python
"""
装备词缀服务

负责：
1. 加载词缀配置
2. 为怪物掉落装备生成随机词缀
3. 从装备 extra_attrs["_affixes"] 读取词缀
4. 格式化词缀显示文本
5. 将 T2 词缀转换为 TriggerConfig 供战斗引擎使用
"""

import random
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import yaml
from nonebot import logger

from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


# VIP装备不参与词缀系统
VIP_EQUIPMENT_IDS = {
    "vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi",
    "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch",
    "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren",
}

# 词缀配置缓存
_affix_config: Optional[dict] = None


def _load_affix_config() -> dict:
    """加载并缓存词缀配置"""
    global _affix_config
    if _affix_config is not None:
        return _affix_config
    config_path = Path(__file__).parent.parent / "data" / "affixes.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        _affix_config = yaml.safe_load(f)
    logger.info(
        f"[AffixService] 加载词缀配置: "
        f"T1={len(_affix_config['affixes']['t1'])}种, "
        f"T2={len(_affix_config['affixes']['t2'])}种"
    )
    return _affix_config


def get_affix_config() -> dict:
    """获取词缀配置（外部接口）"""
    return _load_affix_config()


def generate_affixes(rarity: str, rng: random.Random = None) -> List[Dict]:
    """为怪物掉落的装备生成随机词缀

    Args:
        rarity: 装备稀有度 (white/green/blue/purple/orange)
        rng: 随机数生成器

    Returns:
        词缀数据列表，每项格式为：
        {"affix_id": str, "tier": "T1"/"T2", "value": float, "value2": float|None}
    """
    if rng is None:
        rng = random.Random()

    cfg = _load_affix_config()
    rules = cfg["affix_count_rules"].get(rarity)
    if not rules:
        return []

    # 确定词缀数量
    count = rules["min"]
    if rng.random() < rules["bonus_chance"]:
        count = rules["max"]

    if count == 0:
        return []

    # 构建候选词缀池
    t1_pool = cfg["affixes"]["t1"]
    t2_pool = cfg["affixes"]["t2"]

    # T2 仅蓝色及以上可出现
    t2_eligible = rarity in ("blue", "purple", "orange")
    candidates_t1 = [a for a in t1_pool if rarity in a.get("ranges", {})]
    candidates_t2 = [a for a in t2_pool if t2_eligible and rarity in a.get("chance_ranges", {})]

    # 选择词缀：优先保证至少有T1，剩余随机T1/T2
    selected = []
    used_ids = set()

    # 混合候选池（带权重：T1权重3, T2权重2）
    weighted_pool = []
    for a in candidates_t1:
        weighted_pool.append(("T1", a, 3))
    for a in candidates_t2:
        weighted_pool.append(("T2", a, 2))

    for _ in range(count):
        # 过滤已选中的 affix_id
        available = [(tier, a, w) for tier, a, w in weighted_pool if a["affix_id"] not in used_ids]
        if not available:
            break

        # 加权随机选择
        weights = [w for _, _, w in available]
        chosen_tier, chosen_affix, _ = rng.choices(available, weights=weights, k=1)[0]
        used_ids.add(chosen_affix["affix_id"])

        # 生成随机数值
        affix_data = _roll_affix_values(chosen_tier, chosen_affix, rarity, rng)
        selected.append(affix_data)

    return selected


def _roll_affix_values(tier: str, affix_cfg: dict, rarity: str, rng: random.Random) -> Dict:
    """为单条词缀掷随机数值"""
    if tier == "T1":
        value_range = affix_cfg["ranges"][rarity]
        value = round(rng.uniform(value_range[0], value_range[1]), 1)
        return {
            "affix_id": affix_cfg["affix_id"],
            "tier": "T1",
            "value": value,
            "value2": None,
        }
    else:  # T2
        chance_range = affix_cfg["chance_ranges"][rarity]
        value = round(rng.uniform(chance_range[0], chance_range[1]), 1)

        value2 = None
        if "value_ranges" in affix_cfg and rarity in affix_cfg["value_ranges"]:
            v2_range = affix_cfg["value_ranges"][rarity]
            value2 = round(rng.uniform(v2_range[0], v2_range[1]), 1)
        elif "duration_ranges" in affix_cfg and rarity in affix_cfg["duration_ranges"]:
            d_range = affix_cfg["duration_ranges"][rarity]
            value2 = rng.randint(d_range[0], d_range[1])

        return {
            "affix_id": affix_cfg["affix_id"],
            "tier": "T2",
            "value": value,
            "value2": value2,
        }


def get_affixes_from_equipment(extra_attrs: Optional[dict]) -> List[Dict]:
    """从装备的 extra_attrs 读取词缀列表"""
    if not extra_attrs:
        return []
    return extra_attrs.get("_affixes", [])


def get_affix_display_name(affix_data: dict) -> str:
    """获取词缀的格式化显示文本

    Returns:
        如 "锐利：暴击率+4.5%"
        或 "恐惧之力：攻击时12%概率使敌人恐惧1回合"
    """
    cfg = _load_affix_config()
    affix_id = affix_data["affix_id"]
    tier = affix_data["tier"]

    # 查找配置
    pool_key = "t1" if tier == "T1" else "t2"
    affix_cfg = None
    for a in cfg["affixes"][pool_key]:
        if a["affix_id"] == affix_id:
            affix_cfg = a
            break

    if not affix_cfg:
        return f"{affix_id}: 未知词缀"

    name = affix_cfg["name"]
    desc_template = affix_cfg["description"]
    value = affix_data["value"]
    value2 = affix_data.get("value2")

    desc = desc_template.replace("{value}", f"{value}")
    if value2 is not None:
        desc = desc.replace("{value2}", f"{value2}")

    return f"{name}：{desc}"


def format_affixes_display(affixes: List[Dict]) -> List[str]:
    """格式化词缀列表为展示文本行

    Returns:
        如 ["[1] 锐利：暴击率+3.2%", "[2] 恐惧之力：攻击时12%概率..."]
    """
    lines = []
    for i, affix in enumerate(affixes, 1):
        display = get_affix_display_name(affix)
        lines.append(f"  [{i}] {display}")
    return lines


def get_t1_battle_bonuses(affixes: List[Dict]) -> Dict[str, float]:
    """提取 T1 词缀的战斗属性加成，返回 {attribute: total_value}"""
    cfg = _load_affix_config()
    bonuses = {}

    for affix_data in affixes:
        if affix_data["tier"] != "T1":
            continue
        affix_id = affix_data["affix_id"]
        # 查找 attribute 映射
        for a in cfg["affixes"]["t1"]:
            if a["affix_id"] == affix_id:
                attr = a["attribute"]
                bonuses[attr] = bonuses.get(attr, 0) + affix_data["value"]
                break

    return bonuses


def get_t2_trigger_configs(affixes: List[Dict], source_name: str = "词缀") -> List[TriggerConfig]:
    """将 T2 词缀转换为 TriggerConfig 列表，供战斗引擎注册

    Args:
        affixes: 词缀数据列表
        source_name: 来源名称（用于战斗日志）

    Returns:
        TriggerConfig 列表
    """
    cfg = _load_affix_config()
    triggers = []

    for affix_data in affixes:
        if affix_data["tier"] != "T2":
            continue
        affix_id = affix_data["affix_id"]

        # 查找 T2 配置
        affix_cfg = None
        for a in cfg["affixes"]["t2"]:
            if a["affix_id"] == affix_id:
                affix_cfg = a
                break
        if not affix_cfg:
            continue

        # 构建 TriggerConfig
        trigger_type = TriggerType(affix_cfg["trigger"])
        effect_type = EffectType(affix_cfg["effect"])

        chance = affix_data["value"]
        value = 0.0
        duration = 0

        # value2 可能是效果值或持续回合
        if "value_ranges" in affix_cfg:
            value = affix_data.get("value2", 0) or 0
            # 如果同时有 duration_ranges，duration 取固定值
            if "duration_ranges" in affix_cfg:
                # value2 已经是 value_ranges 的值，duration 取中间值
                # 从配置推断 — 实际 duration 应在生成时也记录，但当前结构只有 value2
                # 约定：有 value_ranges 时 value2=效果值，duration 从配置最小值取
                for rarity_key in ("orange", "purple", "blue"):
                    if rarity_key in affix_cfg["duration_ranges"]:
                        d_range = affix_cfg["duration_ranges"][rarity_key]
                        duration = d_range[0]
                        break
            else:
                duration = 0
        elif "duration_ranges" in affix_cfg:
            # 只有 duration_ranges，value2 就是 duration
            duration = int(affix_data.get("value2", 1) or 1)
            value = 0

        threshold = affix_cfg.get("threshold", 0)

        tc = TriggerConfig(
            trigger=trigger_type,
            chance=chance,
            effect=effect_type,
            value=value,
            duration=duration,
            threshold=float(threshold),
            description=f"词缀·{affix_cfg['name']}",
            source_equipment=source_name,
        )
        triggers.append(tc)

    return triggers
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/item/affix_service.py
git commit -m "feat(affix): 添加 AffixService — 词缀生成、读取、显示、战斗转换"
```

---

## Chunk 2: 怪物掉落装备

### Task 3: 扩展怪物掉落逻辑

**Files:**
- Modify: `plugins/xiuxian_game/world/dungeon_battle.py:456-545` (handle_monster_drops 函数)

- [ ] **Step 1: 在 handle_monster_drops 末尾追加装备掉落逻辑**

在 `handle_monster_drops` 函数中，现有材料掉落逻辑结束后（`if drops:` 语句之前），插入装备掉落逻辑：

```python
    # ===== 装备掉落（词缀系统 Phase 1）=====
    from ..item.affix_service import generate_affixes, VIP_EQUIPMENT_IDS

    # 装备掉落率配置
    if is_elite:
        equip_drop_rate = 0.07  # 精英怪 7%
        equip_rarities = ["green", "blue"]
    elif monster_level > 100:
        equip_drop_rate = 0.02  # 高级普通怪 2%
        equip_rarities = ["white", "green"]
    elif monster_level > 60:
        equip_drop_rate = 0.015
        equip_rarities = ["white", "green"]
    else:
        equip_drop_rate = 0.01  # 低级普通怪 1%
        equip_rarities = ["white"]

    # 幸运值加成
    equip_drop_rate *= (1 + luck_prob(player.luck))

    if rng.random() < equip_drop_rate:
        # 选择掉落装备的稀有度
        drop_rarity = rng.choice(equip_rarities)

        # 从 items_config 中按稀有度筛选装备
        candidate_equips = []
        for item_id in config.items_config["by_type"].get("EQUIPMENT", []):
            item_cfg = config.items_config["by_id"].get(item_id)
            if not item_cfg:
                continue
            if item_cfg.rarity != drop_rarity:
                continue
            if item_id in VIP_EQUIPMENT_IDS:
                continue
            # 匹配怪物等级段
            if item_cfg.required_level <= monster_level:
                candidate_equips.append(item_id)

        if candidate_equips:
            chosen_equip_id = rng.choice(candidate_equips)
            chosen_cfg = config.items_config["by_id"][chosen_equip_id]

            # 生成词缀
            affixes = generate_affixes(drop_rarity, rng)

            # 创建装备实例
            new_equip = ItemInstance(
                player_id=player.id,
                item_id=chosen_equip_id,
                quantity=1,
                durability=chosen_cfg.durability,
                extra_attrs={"_affixes": affixes} if affixes else {},
            )
            session.add(new_equip)

            # 展示掉落信息
            affix_count = len(affixes)
            affix_hint = f"({affix_count}条词缀)" if affix_count > 0 else "(素装)"
            equip_display = f"{chosen_cfg.get_display_name()} {affix_hint}"
            if "⚔️" not in drops:
                drops[f"⚔️{equip_display}"] = 1
            else:
                drops[f"⚔️{equip_display}"] = 1
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/world/dungeon_battle.py
git commit -m "feat(affix): 怪物击杀概率掉落带词缀装备"
```

---

### Task 4: 世界Boss装备掉落（可选扩展）

**Files:**
- Modify: `plugins/xiuxian_game/item/world_boss_chest_service.py`

> 这是可选任务。世界Boss当前通过宝箱发奖，可以在宝箱奖励池中加入装备掉落。但 Phase 1 可以先跳过，仅实现诡域怪物掉落。标记为 **可选**，不阻塞主流程。

---

## Chunk 3: 装备详情展示词缀

### Task 5: 装备详情命令增加词缀展示

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_commands.py:165-356` (equipment_detail 处理器)

- [ ] **Step 1: 在装备详情展示中插入词缀区域**

在 `equipment_commands.py` 的装备详情处理器中，找到宝石镶嵌信息区域（`"💎 宝石镶嵌"` 行）**之前**，插入词缀展示块：

```python
        # ===== 词缀展示 =====
        from ..item.affix_service import get_affixes_from_equipment, format_affixes_display

        affixes = get_affixes_from_equipment(equip.extra_attrs)
        if affixes:
            lines.append("🔮 词缀：")
            lines.extend(format_affixes_display(affixes))
            lines.append("")
        # ===== 词缀展示结束 =====
```

这段代码应插入在 `equipment_commands.py` 中构建装备详情的属性区域之后、宝石区域之前。具体位置：找到 `# 宝石镶嵌信息` 注释（约270行），在其上方插入。

- [ ] **Step 2: 装备栏列表标记词缀装备**

在 `list_equipment` 处理器中（约130行），为装备信息行追加词缀标记：

```python
            # 词缀标记
            from ..item.affix_service import get_affixes_from_equipment
            affix_list = get_affixes_from_equipment(eq.extra_attrs)
            if affix_list:
                info_parts.append(f"🔮{len(affix_list)}词缀")
```

插入在 `info_parts.append(equip_state)` **之前**。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/equipment_commands.py
git commit -m "feat(affix): 装备详情和装备栏展示词缀信息"
```

---

## Chunk 4: 战斗引擎集成

### Task 6: T1 词缀累加战斗属性

**Files:**
- Modify: `plugins/xiuxian_game/battle/battle_attributes.py:38-85` (calculate_effective_attributes)
- Modify: `plugins/xiuxian_game/battle/integration_helper.py` (传递词缀加成)

- [ ] **Step 1: 在 BattleAttributeCalculator 中支持 affix_bonus 参数**

`calculate_effective_attributes` 和 `calculate_effective_attributes_async` 已经支持 `equipment_bonus` 参数。T1 词缀加成将由调用方（integration_helper）计算后通过这个参数传入，**不需要修改 BattleAttributeCalculator 本身**。

在 `integration_helper.py` 的 `enhanced_player_vs_player_battle` 和 `compact_player_vs_player_battle` 中，计算战斗属性时追加词缀加成：

找到计算 `BattleAttributeCalculator.calculate_effective_attributes_async` 的调用处（约行109-139），在调用前构建 affix_bonus：

```python
        # 收集 T1 词缀加成
        from ..item.affix_service import get_affixes_from_equipment, get_t1_battle_bonuses

        affix_bonus_p1 = {}
        for eq in player1_equipped_items:
            affixes = get_affixes_from_equipment(eq.extra_attrs)
            for attr, val in get_t1_battle_bonuses(affixes).items():
                affix_bonus_p1[attr] = affix_bonus_p1.get(attr, 0) + val

        affix_bonus_p2 = {}
        for eq in player2_equipped_items:
            affixes = get_affixes_from_equipment(eq.extra_attrs)
            for attr, val in get_t1_battle_bonuses(affixes).items():
                affix_bonus_p2[attr] = affix_bonus_p2.get(attr, 0) + val
```

然后将 `affix_bonus` 合并到 `equipment_bonus` 参数中传给 `calculate_effective_attributes_async`。如果当前未传 `equipment_bonus`，直接传入 `affix_bonus_p1`/`affix_bonus_p2`：

```python
        p1_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
            player1, session, equipment_bonus=affix_bonus_p1
        )
        p2_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
            player2, session, equipment_bonus=affix_bonus_p2
        )
```

同样需要在 `dungeon_battle.py` 的 PvE 战斗中传递词缀加成（搜索 `calculate_effective_attributes` 调用处）。

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/battle/integration_helper.py
git commit -m "feat(affix): T1词缀在战斗属性计算中生效"
```

---

### Task 7: T2 词缀注册为战斗触发器

**Files:**
- Modify: `plugins/xiuxian_game/battle/enhanced_engine.py:360-424` (_register_equipment_triggers)

- [ ] **Step 1: 在 _register_equipment_triggers 末尾追加词缀触发器注册**

在 `_register_equipment_triggers` 方法中，现有 `self.effect_manager.register_triggers(unit_id, triggers)` 之后，追加 T2 词缀触发器注册：

```python
            # ===== T2 词缀触发器注册 =====
            from ..item.affix_service import get_affixes_from_equipment, get_t2_trigger_configs

            affixes = get_affixes_from_equipment(item.extra_attrs)
            if affixes:
                affix_triggers = get_t2_trigger_configs(affixes, source_name=f"{config.name}·词缀")
                if affix_triggers:
                    self.effect_manager.register_triggers(unit_id, affix_triggers)
```

这段代码应紧接在每个装备的 `register_triggers` 调用之后。注意放在 `for item in equipped_items:` 循环体内。

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/battle/enhanced_engine.py
git commit -m "feat(affix): T2词缀在战斗中注册为触发效果"
```

---

## Chunk 5: 物品定义与帮助系统

### Task 8: 新增洗炼石消耗品

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml` (consumable 区域)

- [ ] **Step 1: 在 items.yaml 的 consumable 区域末尾追加洗炼石**

```yaml
    # ===== 词缀系统消耗品 =====
    - item_id: "affix_reroll_stone"
      name: "洗炼石"
      description: "对装备词缀进行洗炼，重随机数值。可通过分解装备获得。"
      type: "CONSUMABLE"
      price: 2000
      rarity: "green"
      effect_type: "NONE"
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml
git commit -m "feat(affix): 新增洗炼石消耗品定义"
```

---

### Task 9: 更新帮助系统

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`

- [ ] **Step 1: 在装备系统帮助中添加词缀说明**

在 `help.py` 中找到装备系统相关帮助处理器，追加词缀系统说明：

```python
        "━━━━━━━━━━━━━\n"
        "🔮 装备词缀：\n"
        "  击杀怪物有概率掉落带词缀的装备\n"
        "  词缀提供战斗属性加成和触发效果\n"
        "  锻造产出为素装（无词缀）\n"
        "  词缀数量取决于装备稀有度\n"
        "  使用【装备详情 编号】查看词缀\n"
```

- [ ] **Step 2: 更新 `_FULL_HELP_SYSTEMS` 列表**

在 `_FULL_HELP_SYSTEMS` 的装备相关项中追加词缀指令说明。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(affix): 更新帮助系统 — 词缀说明"
```

---

### Task 10: 更新 AI Knowledge Base

**Files:**
- Modify: `plugins/xiuxian_game/data/knowledge/equip_system_help.yaml`

- [ ] **Step 1: 在 equip_system_help.yaml 中同步帮助文本**

将 Task 9 中新增的帮助文本复制到对应 YAML 的 body 字段。

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/data/knowledge/equip_system_help.yaml
git commit -m "docs(affix): 同步AI知识库 — 词缀系统帮助"
```

---

## Chunk 6: 收尾与验证

### Task 11: 端到端验证

- [ ] **Step 1: 配置验证**

启动 Bot，检查日志中词缀配置加载信息：
```
[AffixService] 加载词缀配置: T1=18种, T2=20种
```

- [ ] **Step 2: 掉落验证**

在诡域中击杀怪物，观察是否有装备掉落（可临时将 `equip_drop_rate` 调高测试）。检查掉落装备的 extra_attrs 中是否有 `_affixes` 数据。

- [ ] **Step 3: 展示验证**

使用 `【装备详情 编号】` 查看掉落装备，确认词缀区域正确显示。

- [ ] **Step 4: 战斗验证**

穿戴带词缀装备后发起切磋，检查：
- T1 词缀是否影响了战斗属性（通过【面板】命令对比）
- T2 词缀是否在战斗日志中触发

- [ ] **Step 5: 兼容性验证**

检查：
- 老装备（无词缀）穿戴/卸下/升阶是否正常
- 锻造产出的装备是否确实无词缀
- VIP 装备是否不受影响
- 词缀装备升阶时词缀是否保留

- [ ] **Step 6: 最终提交**

```bash
git add -A
git commit -m "feat(affix): 装备词缀系统 Phase 1 完成 — 掉落+展示+战斗生效"
```

---

## 关键设计决策备忘

1. **词缀存储位置**: `extra_attrs["_affixes"]`，`_` 前缀确保 `apply_attr_bonus()` 不误读
2. **T1 生效方式**: 通过 `equipment_bonus` 参数传入 `BattleAttributeCalculator`，不修改计算器核心代码
3. **T2 生效方式**: 复用 `TriggerConfig` + `BattleEffectManager`，在 `_register_equipment_triggers` 中追加注册
4. **锻造不变**: 不修改 `equipment_craft.py`，锻造产出的 `extra_attrs` 默认为空
5. **VIP 豁免**: `VIP_EQUIPMENT_IDS` 集合明确排除，怪物不会掉落 VIP 装备
6. **升阶兼容**: 词缀独立于升阶系统，`get_upgrade_bonus_multiplier` 不影响词缀
