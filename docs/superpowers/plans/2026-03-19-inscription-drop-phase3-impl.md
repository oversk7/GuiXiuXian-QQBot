# Phase 3: 怪物掉落铭文系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现精英怪掉落铭文、高级铭文模板、品阶系统、铭文碎片合成

**Architecture:** 在现有 inscription_service.py 上扩展高级铭文支持（多效果+品阶评定），dungeon_battle.py 追加铭文+碎片掉落逻辑，decompose_service.py 改为产出碎片，新增 inscription_commands.py 处理合成命令

**Tech Stack:** NoneBot2 + SQLAlchemy 2.0 + YAML配置 + Python dataclass

**Spec:** `docs/superpowers/specs/2026-03-19-inscription-drop-phase3-design.md`

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Modify | `plugins/xiuxian_game/models/inventory.py` | ItemConfig 新增 inscription_type + inscription_effects 属性 |
| Modify | `plugins/xiuxian_game/data/items.yaml` | 新增12种高级铭文模板 + 铭文碎片物品 |
| Modify | `plugins/xiuxian_game/item/inscription_service.py` | 品阶评定、高级铭文数值生成、多效果TriggerConfig转换、兼容函数 |
| Modify | `plugins/xiuxian_game/world/dungeon_battle.py` | handle_monster_drops()追加铭文+碎片掉落 |
| Modify | `plugins/xiuxian_game/item/decompose_service.py` | DecomposeResult改为fragment_count，移除铭文提取 |
| Modify | `plugins/xiuxian_game/item/decompose_commands.py` | 分解消息改为铭文碎片 |
| Create | `plugins/xiuxian_game/item/inscription_commands.py` | 【合成铭文】命令 |
| Modify | `plugins/xiuxian_game/item/__init__.py` | 注册inscription_commands |
| Modify | `plugins/xiuxian_game/battle/enhanced_engine.py` | 铭文注册改用多效果版本 |
| Modify | `plugins/xiuxian_game/item/equipment_commands.py` | 铭文列表显示增加品阶 |
| Modify | `plugins/xiuxian_game/player/help.py` | 更新铭文/分解帮助文案 |
| Modify | `plugins/xiuxian_game/data/knowledge/equip_system_help.yaml` | 同步AI知识库 |

---

## Task 1: ItemConfig 扩展高级铭文属性

**Files:**
- Modify: `plugins/xiuxian_game/models/inventory.py:61-98`

- [ ] **Step 1: 添加 inscription_type 和 inscription_effects 属性**

在 `ItemConfig.__init__()` 中，在现有 `self.inscription_effect = data.get("inscription_effect")` 行之后追加：

```python
        # 高级铭文扩展
        self.inscription_type = data.get("inscription_type")  # "advanced" 或 None
        self.inscription_effects = data.get("inscription_effects")  # 多效果列表(高级铭文)
```

- [ ] **Step 2: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/models/inventory.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/models/inventory.py
git commit -m "feat(inscription): ItemConfig支持inscription_type和inscription_effects"
```

---

## Task 2: YAML 新增铭文碎片 + 12种高级铭文模板

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml`

- [ ] **Step 1: 在铭文区块末尾追加铭文碎片物品**

在 items.yaml 的铭文区块最末尾（`inscription_passive_crit` 之后）追加：

```yaml
    # ========== 铭文碎片 ==========
    - item_id: "inscription_fragment"
      name: "铭文碎片"
      description: "蕴含残缺铭文力量的碎片，收集5个可合成铭文"
      type: "MATERIAL"
      rarity: "blue"
      price: 3000
```

- [ ] **Step 2: 追加12种高级铭文模板**

紧接碎片之后追加（注意 `inscription_type: "advanced"` 和 `inscription_effects` 复数）：

```yaml
    # ========== 高级铭文（多效果模板，仅精英怪掉落） ==========

    # --- 攻击型（4种） ---
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

    - item_id: "adv_inscription_mieshi"
      name: "铭文·灭世天书"
      description: "首回合增攻，攻击恐惧"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 50000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "first_turn"
          effect: "damage_boost"
          duration: 2
          chance_range: [12, 28]
          value_range: [12, 25]
        - trigger: "on_attack"
          effect: "fear"
          duration: 1
          chance_range: [4, 12]

    - item_id: "adv_inscription_shihun"
      name: "铭文·噬魂魔经"
      description: "破甲吸血，低血斩杀"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 55000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attack"
          effect: "debuff_defense"
          duration: 2
          chance_range: [8, 18]
          value_range: [6, 15]
        - trigger: "on_attack"
          effect: "lifesteal"
          chance_range: [8, 18]
          value_range: [6, 16]
        - trigger: "on_attack"
          effect: "damage_boost"
          threshold: 30
          chance_range: [12, 25]
          value_range: [15, 32]

    - item_id: "adv_inscription_tianfa"
      name: "铭文·天罚雷章"
      description: "真伤暴击恐惧三位一体"
      type: "INSCRIPTION"
      rarity: "orange"
      price: 80000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attack"
          effect: "true_damage"
          duration: 1
          chance_range: [8, 16]
          value_range: [10, 22]
        - trigger: "first_turn"
          effect: "buff_critical"
          duration: 3
          chance_range: [16, 32]
          value_range: [12, 28]
        - trigger: "on_critical"
          effect: "fear"
          duration: 1
          chance_range: [8, 18]

    # --- 防御型（3种） ---
    - item_id: "adv_inscription_bumie"
      name: "铭文·不灭金身"
      description: "减伤护盾双防护"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 50000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attacked"
          effect: "damage_reduction"
          duration: 1
          chance_range: [8, 18]
          value_range: [6, 16]
        - trigger: "first_turn"
          effect: "shield"
          chance_range: [16, 32]
          value_range: [6, 14]

    - item_id: "adv_inscription_guixu"
      name: "铭文·归墟道经"
      description: "回血反伤绝境防御"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 55000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "each_turn"
          effect: "regen"
          chance_range: [12, 28]
          value_range: [2, 6]
        - trigger: "on_attacked"
          effect: "reflect"
          chance_range: [6, 16]
          value_range: [8, 20]
        - trigger: "low_hp"
          effect: "buff_defense"
          duration: 2
          chance_range: [16, 32]
          value_range: [12, 25]

    - item_id: "adv_inscription_taixu"
      name: "铭文·太虚镜录"
      description: "反伤恐惧护盾终极防御"
      type: "INSCRIPTION"
      rarity: "orange"
      price: 80000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attacked"
          effect: "reflect"
          chance_range: [8, 20]
          value_range: [10, 22]
        - trigger: "on_attacked"
          effect: "fear"
          duration: 1
          chance_range: [6, 14]
        - trigger: "first_turn"
          effect: "shield"
          chance_range: [18, 36]
          value_range: [8, 16]

    # --- 控制型（3种） ---
    - item_id: "adv_inscription_youming"
      name: "铭文·幽冥咒典"
      description: "恐惧破攻双控"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 48000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attack"
          effect: "fear"
          duration: 1
          chance_range: [4, 12]
        - trigger: "on_attack"
          effect: "debuff_attack"
          duration: 2
          chance_range: [8, 18]
          value_range: [6, 14]

    - item_id: "adv_inscription_fengshen"
      name: "铭文·封神禁录"
      description: "破攻破甲逆鳞三控"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 55000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attack"
          effect: "debuff_defense"
          duration: 2
          chance_range: [8, 18]
          value_range: [6, 14]
        - trigger: "on_attack"
          effect: "debuff_attack"
          duration: 2
          chance_range: [8, 18]
          value_range: [6, 14]
        - trigger: "on_attacked"
          effect: "fear"
          duration: 1
          chance_range: [8, 16]

    - item_id: "adv_inscription_wanjie"
      name: "铭文·万劫魔章"
      description: "恐惧真伤破甲极控"
      type: "INSCRIPTION"
      rarity: "orange"
      price: 80000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_attack"
          effect: "fear"
          duration: 1
          chance_range: [6, 14]
        - trigger: "on_attack"
          effect: "true_damage"
          duration: 1
          chance_range: [6, 14]
          value_range: [8, 18]
        - trigger: "on_attack"
          effect: "debuff_defense"
          duration: 2
          chance_range: [8, 18]
          value_range: [8, 16]

    # --- 综合型（2种） ---
    - item_id: "adv_inscription_lunhui"
      name: "铭文·轮回仙典"
      description: "增攻护盾回血全能"
      type: "INSCRIPTION"
      rarity: "orange"
      price: 85000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "first_turn"
          effect: "damage_boost"
          duration: 2
          chance_range: [12, 25]
          value_range: [10, 22]
        - trigger: "first_turn"
          effect: "shield"
          chance_range: [16, 32]
          value_range: [6, 14]
        - trigger: "each_turn"
          effect: "regen"
          chance_range: [12, 25]
          value_range: [2, 5]

    - item_id: "adv_inscription_dujie"
      name: "铭文·渡劫残页"
      description: "闪避触发回血暴击"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 48000
      inscription_type: "advanced"
      inscription_effects:
        - trigger: "on_dodge"
          effect: "heal"
          chance_range: [12, 25]
          value_range: [4, 10]
        - trigger: "on_dodge"
          effect: "buff_critical"
          duration: 1
          chance_range: [12, 25]
          value_range: [16, 40]
```

- [ ] **Step 3: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/items.yaml','r',encoding='utf-8')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml
git commit -m "feat(inscription): 新增铭文碎片+12种高级铭文模板"
```

---

## Task 3: inscription_service.py 扩展

**Files:**
- Modify: `plugins/xiuxian_game/item/inscription_service.py`

这是核心任务，需新增：品阶评定、高级铭文数值生成、标准化兼容函数、多效果TriggerConfig转换。

- [ ] **Step 1: 完整重写 inscription_service.py**

用以下内容**完整替换**文件（保留所有旧功能，新增扩展）：

```python
"""
铭文服务

负责：
1. 为铭文物品生成随机数值（_inscription_values）
2. 从装备 gem_slots_data 读取铭文数据
3. 格式化铭文显示文本
4. 将铭文转换为 TriggerConfig 供战斗引擎使用
5. 品阶评定（下品/中品/上品/极品/仙品）
6. 高级铭文多效果支持
"""

import random
from typing import List, Dict, Optional

from ..config import config
from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


# ==================== 品阶系统 ====================

GRADE_THRESHOLDS = [
    (0.90, "极品"),
    (0.65, "上品"),
    (0.25, "中品"),
    (0.00, "下品"),
]


def evaluate_grade(effect_values: list, effect_configs: list) -> str:
    """根据数值roll质量评定品阶

    Args:
        effect_values: [{"chance": 12.5, "value": 28}, ...] 每条效果的roll值
        effect_configs: [{"chance_range": [6,14], ...}, ...] YAML定义
    Returns:
        "下品"/"中品"/"上品"/"极品"
    """
    percentiles = []
    for vals, cfg in zip(effect_values, effect_configs):
        for key in ("chance", "value"):
            range_key = f"{key}_range"
            if range_key in cfg and key in vals:
                low, high = cfg[range_key]
                pct = (vals[key] - low) / (high - low) if high > low else 1.0
                pct = max(0.0, min(1.0, pct))
                percentiles.append(pct)
    avg_pct = sum(percentiles) / len(percentiles) if percentiles else 0.5

    for threshold, grade in GRADE_THRESHOLDS:
        if avg_pct >= threshold:
            return grade
    return "下品"


# ==================== 数值生成 ====================

def _roll_effect_values(effect_cfg: dict, rng: random.Random) -> dict:
    """为单条效果配置roll随机数值"""
    values = {}
    chance_range = effect_cfg.get("chance_range")
    if chance_range:
        values["chance"] = round(rng.uniform(chance_range[0], chance_range[1]), 1)
    value_range = effect_cfg.get("value_range")
    if value_range:
        values["value"] = round(rng.uniform(value_range[0], value_range[1]), 1)
    return values


def _roll_celestial_values(effect_cfg: dict, rng: random.Random, floor: float = 0.95) -> dict:
    """仙品专用：数值roll到区间的 floor~100% 范围"""
    values = {}
    chance_range = effect_cfg.get("chance_range")
    if chance_range:
        low = chance_range[0] + (chance_range[1] - chance_range[0]) * floor
        values["chance"] = round(rng.uniform(low, chance_range[1]), 1)
    value_range = effect_cfg.get("value_range")
    if value_range:
        low = value_range[0] + (value_range[1] - value_range[0]) * floor
        values["value"] = round(rng.uniform(low, value_range[1]), 1)
    return values


def generate_inscription_values(item_id: str, rng: random.Random = None) -> Dict:
    """为基础铭文物品生成随机数值（向后兼容，返回扁平dict）"""
    if rng is None:
        rng = random.Random()
    effect_cfg = _get_inscription_effect(item_id)
    if not effect_cfg:
        return {}
    return _roll_effect_values(effect_cfg, rng)


def generate_advanced_inscription_values(item_id: str, rng: random.Random = None,
                                          celestial: bool = False) -> List[Dict]:
    """为高级铭文生成多条效果的随机数值

    Returns:
        [{"chance": 10.2, "value": 15.8}, {"chance": 14.5}]
    """
    if rng is None:
        rng = random.Random()
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return []
    effects = getattr(item_cfg, 'inscription_effects', None) or []
    roll_fn = _roll_celestial_values if celestial else _roll_effect_values
    return [roll_fn(eff, rng) for eff in effects]


def generate_inscription_drop(item_id: str, rng: random.Random,
                               monster_level: int = 0) -> dict:
    """生成掉落铭文的完整extra_attrs

    Returns:
        {"_inscription_values": [...], "_inscription_grade": "上品"}
    """
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return {}

    is_advanced = getattr(item_cfg, 'inscription_type', None) == "advanced"

    # 仙品判定：3000级+精英怪 1%触发
    celestial = False
    if monster_level >= 3000 and rng.random() < 0.01:
        celestial = True

    if is_advanced:
        effects = getattr(item_cfg, 'inscription_effects', [])
        values_list = generate_advanced_inscription_values(item_id, rng, celestial)
        grade = "仙品" if celestial else evaluate_grade(values_list, effects)
    else:
        eff_cfg = _get_inscription_effect(item_id)
        values = _roll_celestial_values(eff_cfg, rng) if celestial else _roll_effect_values(eff_cfg, rng)
        values_list = [values]
        grade = "仙品" if celestial else evaluate_grade(values_list, [eff_cfg] if eff_cfg else [])

    return {
        "_inscription_values": values_list,
        "_inscription_grade": grade,
    }


# ==================== 兼容读取 ====================

def normalize_inscription_values(extra_attrs: dict) -> List[Dict]:
    """统一读取铭文数值，兼容旧格式（扁平dict）和新格式（列表）"""
    raw = (extra_attrs or {}).get("_inscription_values", {})
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []


def get_inscription_grade(extra_attrs: dict) -> str:
    """获取铭文品阶，无品阶数据时返回空字符串"""
    return (extra_attrs or {}).get("_inscription_grade", "")


# ==================== 配置读取 ====================

def _get_inscription_effect(item_id: str) -> Optional[dict]:
    """获取基础铭文的 inscription_effect 配置"""
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return None
    return getattr(item_cfg, 'inscription_effect', None)


def get_inscription_effect_configs(item_id: str) -> List[dict]:
    """获取铭文的效果配置列表（基础返回1项，高级返回多项）"""
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return []
    if getattr(item_cfg, 'inscription_type', None) == "advanced":
        return getattr(item_cfg, 'inscription_effects', []) or []
    single = getattr(item_cfg, 'inscription_effect', None)
    return [single] if single else []


# ==================== 显示格式化 ====================

def _format_effect_desc(effect_cfg: dict, values: dict) -> str:
    """格式化单条效果的描述文本"""
    trigger_names = {
        "on_attack": "攻击时", "on_attacked": "被攻击时", "on_critical": "暴击时",
        "first_turn": "首回合", "each_turn": "每回合", "on_dodge": "闪避后",
        "on_hit": "命中时", "on_kill": "击杀时", "low_hp": "低血量时",
    }
    effect_names = {
        "fear": "恐惧", "true_damage": "真实伤害", "lifesteal": "吸血",
        "damage_boost": "伤害提升", "damage_reduction": "减伤", "reflect": "反弹伤害",
        "shield": "护盾", "regen": "回血", "heal": "回复生命",
        "debuff_attack": "降攻", "debuff_defense": "降防", "defense_penetration": "无视防御",
        "buff_critical": "暴击率提升", "buff_defense": "防御提升", "buff_attack": "攻击提升",
    }
    trigger = trigger_names.get(effect_cfg.get("trigger", ""), effect_cfg.get("trigger", ""))
    effect = effect_names.get(effect_cfg.get("effect", ""), effect_cfg.get("effect", ""))
    chance = values.get("chance")
    value = values.get("value")
    duration = effect_cfg.get("duration", 0)
    threshold = effect_cfg.get("threshold", 0)

    parts = [trigger]
    if chance is not None:
        parts.append(f"{chance}%概率")
    if threshold:
        parts.append(f"(目标<{threshold}%血量)")
    if value is not None:
        parts.append(f"{effect}{value}%")
    else:
        parts.append(effect)
    if duration:
        parts.append(f"({duration}回合)")
    return "".join(parts)


def get_inscription_display(slot_data: dict) -> str:
    """格式化铭文孔位数据的显示文本（兼容基础和高级铭文）"""
    item_id = slot_data.get("item_id", "")
    raw_values = slot_data.get("values", {})

    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return f"铭文：未知({item_id})"

    name = item_cfg.name
    is_advanced = getattr(item_cfg, 'inscription_type', None) == "advanced"

    if is_advanced and isinstance(raw_values, list):
        effects = getattr(item_cfg, 'inscription_effects', [])
        descs = []
        for i, eff_cfg in enumerate(effects):
            vals = raw_values[i] if i < len(raw_values) else {}
            descs.append(_format_effect_desc(eff_cfg, vals))
        return f"{name}（{'；'.join(descs)}）"
    else:
        # 基础铭文：用原有的description模板替换
        desc = item_cfg.description or ""
        values = raw_values if isinstance(raw_values, dict) else (raw_values[0] if raw_values else {})
        chance = values.get("chance")
        if chance is not None:
            desc = desc.replace("{chance}", f"{chance}")
        value = values.get("value")
        if value is not None:
            desc = desc.replace("{value}", f"{value}")
        return f"{name}（{desc}）"


def get_inscription_display_from_item(item_instance) -> str:
    """从铭文 ItemInstance 获取显示文本（含品阶）"""
    item_cfg = item_instance.config
    if not item_cfg:
        return "未知铭文"

    extra = item_instance.extra_attrs or {}
    grade = get_inscription_grade(extra)
    grade_str = f"{{{grade}}}" if grade else ""
    name = item_cfg.name

    is_advanced = getattr(item_cfg, 'inscription_type', None) == "advanced"
    values_list = normalize_inscription_values(extra)

    if is_advanced:
        effects = getattr(item_cfg, 'inscription_effects', [])
        descs = []
        for i, eff_cfg in enumerate(effects):
            vals = values_list[i] if i < len(values_list) else {}
            descs.append(_format_effect_desc(eff_cfg, vals))
        return f"{name}{grade_str}（{'；'.join(descs)}）"
    else:
        desc = item_cfg.description or ""
        values = values_list[0] if values_list else {}
        chance = values.get("chance")
        if chance is not None:
            desc = desc.replace("{chance}", f"{chance}")
        value = values.get("value")
        if value is not None:
            desc = desc.replace("{value}", f"{value}")
        return f"{name}{grade_str}（{desc}）"


# ==================== 装备铭文提取 ====================

def get_inscriptions_from_equipment(gem_slots_data: Optional[dict]) -> List[Dict]:
    """从装备的 gem_slots_data 提取所有铭文数据"""
    if not gem_slots_data:
        return []
    inscriptions = []
    for slot_idx, slot_val in gem_slots_data.items():
        if isinstance(slot_val, dict) and "item_id" in slot_val:
            data = dict(slot_val)
            data["slot_index"] = int(slot_idx)
            inscriptions.append(data)
    return inscriptions


# ==================== 战斗引擎转换 ====================

def _build_trigger_config(effect_cfg: dict, values: dict, insc_name: str,
                           source_name: str) -> TriggerConfig:
    """从单条效果配置+数值构建TriggerConfig"""
    trigger_type = TriggerType(effect_cfg["trigger"])
    effect_type = EffectType(effect_cfg["effect"])
    chance = values.get("chance", 100 if not effect_cfg.get("chance_range") else 0)
    value = values.get("value", 0)
    duration = effect_cfg.get("duration", 0)
    threshold = effect_cfg.get("threshold", 0)
    return TriggerConfig(
        trigger=trigger_type,
        chance=chance,
        effect=effect_type,
        value=value,
        duration=duration,
        threshold=float(threshold),
        description=f"铭文·{insc_name}",
        source_equipment=source_name,
    )


def inscription_to_trigger_config(inscription_data: dict, source_name: str = "铭文") -> Optional[TriggerConfig]:
    """将基础铭文数据转换为单个TriggerConfig（向后兼容）"""
    item_id = inscription_data.get("item_id", "")
    values = inscription_data.get("values", {})
    # 兼容新格式：values可能是list
    if isinstance(values, list):
        values = values[0] if values else {}

    effect_cfg = _get_inscription_effect(item_id)
    if not effect_cfg:
        return None

    item_cfg = config.items_config["by_id"].get(item_id)
    insc_name = item_cfg.name if item_cfg else item_id
    return _build_trigger_config(effect_cfg, values, insc_name, source_name)


def inscription_to_trigger_configs(inscription_data: dict, source_name: str = "铭文") -> List[TriggerConfig]:
    """将铭文数据转换为TriggerConfig列表（支持基础和高级铭文）"""
    item_id = inscription_data.get("item_id", "")
    raw_values = inscription_data.get("values", {})

    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return []

    insc_name = item_cfg.name
    is_advanced = getattr(item_cfg, 'inscription_type', None) == "advanced"

    if is_advanced:
        effects = getattr(item_cfg, 'inscription_effects', []) or []
        values_list = raw_values if isinstance(raw_values, list) else [raw_values]
        triggers = []
        for i, eff_cfg in enumerate(effects):
            vals = values_list[i] if i < len(values_list) else {}
            triggers.append(_build_trigger_config(eff_cfg, vals, insc_name, source_name))
        return triggers
    else:
        tc = inscription_to_trigger_config(inscription_data, source_name)
        return [tc] if tc else []


# ==================== 分解映射（保留，但Phase3中分解不再产铭文） ====================

T2_AFFIX_TO_INSCRIPTION = {
    "fear_strike": "inscription_fear",
    "defense_pierce": "inscription_defense_pierce",
    "crit_lifesteal": "inscription_lifesteal",
    "damage_reflect": "inscription_reflect",
    "tough_reduce": "inscription_damage_reduction",
    "true_damage_strike": "inscription_true_damage",
    "first_strike_hit": "inscription_first_true",
    "execute_boost": "inscription_execute",
    "shield_condense": "inscription_shield",
    "periodic_regen": "inscription_regen",
    "cripple": "inscription_debuff_attack",
    "weaken": "inscription_debuff_defense",
    "counter_stun": "inscription_counter_fear",
    "dodge_crit": "inscription_buff_crit",
    "kill_boost": "inscription_kill_attack",
    "desperation_crit": "inscription_lowhp_damage",
    "soul_burn": "inscription_hit_debuff_def",
    "combo_stack": "inscription_crit_boost",
    "doom_judgment": "inscription_execute",
}


def get_affix_to_inscription_id(affix_id: str) -> Optional[str]:
    """T2词缀ID -> 对应铭文item_id"""
    return T2_AFFIX_TO_INSCRIPTION.get(affix_id)
```

- [ ] **Step 2: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/item/inscription_service.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/inscription_service.py
git commit -m "feat(inscription): 品阶评定+高级铭文多效果+仙品+兼容旧格式"
```

---

## Task 4: 战斗引擎改用多效果版本

**Files:**
- Modify: `plugins/xiuxian_game/battle/enhanced_engine.py:437-447`

- [ ] **Step 1: 替换铭文注册逻辑**

找到 `enhanced_engine.py` 中的铭文注册代码块（约437-447行），将：

```python
        # 注册铭文触发器
        from ..item.inscription_service import get_inscriptions_from_equipment, inscription_to_trigger_config
        for item in equipped_items:
            inscriptions = get_inscriptions_from_equipment(getattr(item, 'gem_slots_data', None))
            if not inscriptions:
                continue
            equip_name = getattr(getattr(item, 'config', None), 'name', '装备')
            for insc_data in inscriptions:
                tc = inscription_to_trigger_config(insc_data, source_name=equip_name)
                if tc:
                    self.effect_manager.register_triggers(unit_id, [tc])
```

替换为：

```python
        # 注册铭文触发器（支持基础+高级铭文多效果）
        from ..item.inscription_service import get_inscriptions_from_equipment, inscription_to_trigger_configs
        for item in equipped_items:
            inscriptions = get_inscriptions_from_equipment(getattr(item, 'gem_slots_data', None))
            if not inscriptions:
                continue
            equip_name = getattr(getattr(item, 'config', None), 'name', '装备')
            for insc_data in inscriptions:
                triggers = inscription_to_trigger_configs(insc_data, source_name=equip_name)
                if triggers:
                    self.effect_manager.register_triggers(unit_id, triggers)
```

- [ ] **Step 2: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/battle/enhanced_engine.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/battle/enhanced_engine.py
git commit -m "feat(inscription): 战斗引擎支持高级铭文多效果触发器"
```

---

## Task 5: 精英怪掉落铭文+碎片

**Files:**
- Modify: `plugins/xiuxian_game/world/dungeon_battle.py:70-77` (常量区) + `:602-607` (函数末尾)

- [ ] **Step 1: 在常量区追加铭文掉落配置**

在 `dungeon_battle.py` 顶部 `RARITY_WEIGHTS` 之后（约第77行后）追加：

```python
# -------- 铭文掉落配置（Phase 3）--------
INSCRIPTION_DROP_RATES = {60: 0.0, 100: 0.03, 200: 0.04, 9999: 0.05}
INSCRIPTION_TYPE_WEIGHTS = {"basic": 60, "advanced": 40}
ADVANCED_RARITY_WEIGHTS = {"purple": 80, "orange": 20}
ADVANCED_ORANGE_MIN_LEVEL = 150
CELESTIAL_GRADE_MIN_LEVEL = 3000
FRAGMENT_DROP_RATE = 0.20
FRAGMENT_ITEM_ID = "inscription_fragment"
```

- [ ] **Step 2: 在 handle_monster_drops() 末尾追加铭文+碎片掉落逻辑**

在 `handle_monster_drops()` 函数中，找到装备掉落代码块末尾（约601行 `drops[f"⚔️{equip_display}"] = 1` 之后），在 `if drops:` 语句**之前**追加：

```python
    # ===== 铭文掉落（Phase 3，仅精英怪）=====
    if is_elite:
        from ..item.inscription_service import generate_inscription_drop

        # 确定铭文掉落率
        insc_base_rate = 0.0
        for level_cap, rate in sorted(INSCRIPTION_DROP_RATES.items()):
            if monster_level <= level_cap:
                insc_base_rate = rate
                break
        insc_final_rate = insc_base_rate * (1 + luck_prob(player.luck))

        if insc_base_rate > 0 and rng.random() < insc_final_rate:
            # 决定铭文类型：基础 or 高级
            type_roll = rng.randint(1, 100)
            if type_roll <= INSCRIPTION_TYPE_WEIGHTS["basic"]:
                # 基础铭文：从34种中选1种（排除高级铭文）
                basic_ids = [iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
                             if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)
                             and not iid.startswith("adv_")]
                if basic_ids:
                    chosen_id = rng.choice(basic_ids)
                    drop_attrs = generate_inscription_drop(chosen_id, rng, monster_level)
                    try:
                        insc_inst = ItemInstance(
                            player_id=player.id, item_id=chosen_id, quantity=1,
                            extra_attrs=drop_attrs,
                        )
                        session.add(insc_inst)
                        insc_cfg = config.items_config["by_id"].get(chosen_id)
                        grade = drop_attrs.get("_inscription_grade", "")
                        grade_str = f"{{{grade}}}" if grade else ""
                        drops[f"📜{insc_cfg.name}{grade_str}"] = 1
                    except ValueError:
                        pass
            else:
                # 高级铭文：按稀有度权重选
                rarity_roll = rng.randint(1, 100)
                target_rarity = "orange" if rarity_roll <= ADVANCED_RARITY_WEIGHTS["orange"] else "purple"
                if target_rarity == "orange" and monster_level < ADVANCED_ORANGE_MIN_LEVEL:
                    target_rarity = "purple"

                adv_ids = [iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
                           if getattr(config.items_config["by_id"].get(iid), 'inscription_type', None) == "advanced"
                           and getattr(config.items_config["by_id"].get(iid), 'rarity', '') == target_rarity]
                if adv_ids:
                    chosen_id = rng.choice(adv_ids)
                    drop_attrs = generate_inscription_drop(chosen_id, rng, monster_level)
                    try:
                        insc_inst = ItemInstance(
                            player_id=player.id, item_id=chosen_id, quantity=1,
                            extra_attrs=drop_attrs,
                        )
                        session.add(insc_inst)
                        insc_cfg = config.items_config["by_id"].get(chosen_id)
                        grade = drop_attrs.get("_inscription_grade", "")
                        grade_str = f"{{{grade}}}" if grade else ""
                        drops[f"📜{insc_cfg.name}{grade_str}"] = 1
                    except ValueError:
                        pass

        # 铭文碎片掉落（独立于铭文判定）
        if rng.random() < FRAGMENT_DROP_RATE * (1 + luck_prob(player.luck)):
            frag_qty = rng.randint(1, 2)
            try:
                await ItemInstance.add_item(session, player.id, FRAGMENT_ITEM_ID, frag_qty)
                drops[f"📜铭文碎片"] = drops.get("📜铭文碎片", 0) + frag_qty
            except ValueError:
                pass
```

- [ ] **Step 3: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/world/dungeon_battle.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/world/dungeon_battle.py
git commit -m "feat(inscription): 精英怪掉落铭文+碎片，支持仙品触发"
```

---

## Task 6: 分解系统改造（碎片替代铭文）

**Files:**
- Modify: `plugins/xiuxian_game/item/decompose_service.py`
- Modify: `plugins/xiuxian_game/item/decompose_commands.py`

- [ ] **Step 1: 修改 decompose_service.py**

将 `DecomposeResult` 的 `inscriptions` 字段改为 `fragment_count`，并修改 `calculate_decompose_yields()`：

完整替换文件内容：

```python
"""
装备分解服务

功能：
- 销毁装备获得洗词石
- 带T2词缀的装备产出铭文碎片
"""

import random
from typing import Tuple
from dataclasses import dataclass

from ..item.affix_service import get_affixes_from_equipment, VIP_EQUIPMENT_IDS
from ..config import config


@dataclass
class DecomposeResult:
    """分解结果"""
    reroll_stones: int = 0
    fragment_count: int = 0  # 铭文碎片数量


# 分解产出表：{稀有度: (基础洗词石, 有词缀额外最小, 有词缀额外最大)}
DECOMPOSE_YIELDS = {
    "white":  (1, 1, 1),
    "green":  (2, 1, 2),
    "blue":   (4, 2, 3),
    "purple": (8, 3, 4),
    "orange": (15, 4, 5),
}

FRAGMENT_ITEM_ID = "inscription_fragment"


def validate_decompose(equipment) -> Tuple[bool, str]:
    """验证装备是否可分解"""
    if not equipment.is_equipment:
        return False, "只能分解装备"
    if equipment.equipped:
        return False, "请先卸下装备再分解"
    item_id = getattr(equipment, 'item_id', '')
    if item_id in VIP_EQUIPMENT_IDS:
        return False, "VIP定制装备不可分解"
    extra = equipment.extra_attrs or {}
    if extra.get("_frozen_for_trade") or extra.get("_frozen_for_auction"):
        return False, "正在交易/拍卖中的装备不可分解"
    return True, ""


def calculate_decompose_yields(equipment, rng: random.Random = None) -> DecomposeResult:
    """计算分解产出"""
    if rng is None:
        rng = random.Random()

    rarity = equipment.config.rarity if equipment.config else "white"
    yields = DECOMPOSE_YIELDS.get(rarity, (1, 0, 0))
    base_stones, extra_min, extra_max = yields

    affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
    has_affixes = len(affixes) > 0

    total_stones = base_stones
    if has_affixes:
        total_stones += rng.randint(extra_min, extra_max)

    # T2 词缀 -> 铭文碎片（每个T2词缀必出1个碎片）
    t2_count = sum(1 for a in affixes if a.get("tier") == "T2")

    return DecomposeResult(reroll_stones=total_stones, fragment_count=t2_count)
```

- [ ] **Step 2: 修改 decompose_commands.py**

将发放铭文的逻辑替换为发放碎片。完整替换文件内容：

```python
"""
分解系统命令处理

指令：
- 【分解 装备编号/名称】 - 分解装备获得洗词石+铭文碎片
"""

import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from .decompose_service import validate_decompose, calculate_decompose_yields, FRAGMENT_ITEM_ID


decompose_cmd = on_command("分解", priority=5, block=True)


@decompose_cmd.handle()
async def handle_decompose(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await decompose_cmd.finish("用法：【分解 装备编号/名称】\n分解装备获得洗词石，带T2词缀的装备可获得铭文碎片")

    msg = ""
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await decompose_cmd.finish("你还没有创建角色")

        equipment = await _find_equipment(session, player.id, raw_args)
        if not equipment:
            await decompose_cmd.finish(f"未找到装备：{raw_args}")

        can_decompose, reason = validate_decompose(equipment)
        if not can_decompose:
            await decompose_cmd.finish(reason)

        equip_name = equipment.config.name if equipment.config else equipment.item_id

        rng = random.Random()
        result = calculate_decompose_yields(equipment, rng)

        # 回收孔位中的宝石/铭文
        recovered_items = []
        if equipment.gem_slots_data:
            for slot_val in list(equipment.gem_slots_data.values()):
                if not slot_val:
                    continue
                if isinstance(slot_val, dict):
                    insc_id = slot_val.get("item_id", "")
                    insc_values = slot_val.get("values", {})
                    # 统一用列表格式存储
                    if not isinstance(insc_values, list):
                        insc_values = [insc_values]
                    inst = ItemInstance(
                        player_id=player.id,
                        item_id=insc_id,
                        quantity=1,
                        extra_attrs={"_inscription_values": insc_values},
                    )
                    session.add(inst)
                    insc_cfg = config.items_config["by_id"].get(insc_id)
                    recovered_items.append(insc_cfg.name if insc_cfg else insc_id)
                else:
                    try:
                        await ItemInstance.add_item(session, player.id, slot_val, 1)
                        gem_cfg = config.items_config["by_id"].get(slot_val)
                        recovered_items.append(gem_cfg.name if gem_cfg else slot_val)
                    except ValueError:
                        gem_cfg = config.items_config["by_id"].get(slot_val)
                        gold_value = gem_cfg.price if gem_cfg else 1000
                        player.gold += gold_value
                        recovered_items.append(f"{gem_cfg.name if gem_cfg else slot_val}(转为{gold_value}金币)")

        # 发放洗词石
        if result.reroll_stones > 0:
            await ItemInstance.add_item(session, player.id, "affix_reroll_stone", result.reroll_stones)

        # 发放铭文碎片
        if result.fragment_count > 0:
            await ItemInstance.add_item(session, player.id, FRAGMENT_ITEM_ID, result.fragment_count)

        # 删除装备
        await session.delete(equipment)

        # 构建消息
        lines = [f"分解成功：{equip_name}"]
        lines.append(f"  获得洗词石 x{result.reroll_stones}")
        if result.fragment_count > 0:
            lines.append(f"  获得铭文碎片 x{result.fragment_count}")
        if recovered_items:
            lines.append(f"  回收镶嵌物：{'、'.join(recovered_items)}")
        msg = "\n".join(lines)

    await decompose_cmd.finish(Message(msg))


async def _find_equipment(session, player_id: str, keyword: str):
    """按编号或名称查找装备"""
    try:
        idx = int(keyword)
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
        ).order_by(ItemInstance.id)
        all_items = (await session.execute(stmt)).scalars().all()
        equips = [i for i in all_items if i.is_equipment]
        if 1 <= idx <= len(equips):
            return equips[idx - 1]
    except ValueError:
        pass

    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
    )
    all_items = (await session.execute(stmt)).scalars().all()
    for item in all_items:
        if item.is_equipment and item.config and keyword in item.config.name:
            return item

    return None
```

- [ ] **Step 3: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/item/decompose_service.py','r',encoding='utf-8').read()); print('OK')" && python -c "import ast; ast.parse(open('plugins/xiuxian_game/item/decompose_commands.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK` (两次)

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/item/decompose_service.py plugins/xiuxian_game/item/decompose_commands.py
git commit -m "feat(inscription): 分解系统改为产出铭文碎片替代铭文"
```

---

## Task 7: 合成铭文命令

**Files:**
- Create: `plugins/xiuxian_game/item/inscription_commands.py`
- Modify: `plugins/xiuxian_game/item/__init__.py`

- [ ] **Step 1: 创建 inscription_commands.py**

```python
"""
铭文合成命令

指令：
- 【合成铭文】 - 消耗5个铭文碎片，合成1个随机基础铭文
"""

import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from .inscription_service import (
    generate_inscription_drop,
    get_inscription_display_from_item,
)

FRAGMENT_COST = 5
FRAGMENT_ITEM_ID = "inscription_fragment"

synthesize_cmd = on_command("合成铭文", priority=5, block=True)


@synthesize_cmd.handle()
async def handle_synthesize(event: MessageEvent, args: Message = CommandArg()):
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await synthesize_cmd.finish("你还没有创建角色")

        # 检查碎片数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == FRAGMENT_ITEM_ID,
        )
        fragments = (await session.execute(stmt)).scalars().first()
        current = fragments.quantity if fragments else 0
        if current < FRAGMENT_COST:
            await synthesize_cmd.finish(
                f"铭文碎片不足！需要{FRAGMENT_COST}个，当前{current}个\n"
                f"碎片来源：分解T2词缀装备、击杀精英怪"
            )

        # 扣除碎片
        fragments.quantity -= FRAGMENT_COST
        if fragments.quantity <= 0:
            await session.delete(fragments)

        # 随机选择基础铭文（排除高级铭文）
        rng = random.Random()
        basic_ids = [
            iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
            if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)
            and not iid.startswith("adv_")
        ]
        if not basic_ids:
            await synthesize_cmd.finish("系统错误：无可用铭文模板")

        chosen_id = rng.choice(basic_ids)
        drop_attrs = generate_inscription_drop(chosen_id, rng)

        # 创建铭文实例
        inst = ItemInstance(
            player_id=player.id,
            item_id=chosen_id,
            quantity=1,
            extra_attrs=drop_attrs,
        )
        session.add(inst)

        # 显示结果
        display = get_inscription_display_from_item(inst)
        msg = f"合成成功！消耗铭文碎片 x{FRAGMENT_COST}\n  获得：{display}"

    await synthesize_cmd.finish(Message(msg))
```

- [ ] **Step 2: 在 __init__.py 中注册**

在 `plugins/xiuxian_game/item/__init__.py` 末尾追加：

```python
from . import inscription_commands  # 铭文合成
```

- [ ] **Step 3: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/item/inscription_commands.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/item/inscription_commands.py plugins/xiuxian_game/item/__init__.py
git commit -m "feat(inscription): 新增【合成铭文】命令，碎片合成基础铭文"
```

---

## Task 8: 铭文列表显示增加品阶

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_commands.py:134-167`

- [ ] **Step 1: 更新铭文列表的空提示和查询**

找到 `equipment_commands.py` 中 `handle_inscription_list` 函数（约139行），将查询范围扩展支持 `adv_inscription_` 前缀，并更新空提示。

将：
```python
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id.like("inscription_%")
        )
```

替换为：
```python
        from sqlalchemy import or_
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            or_(
                ItemInstance.item_id.like("inscription_%"),
                ItemInstance.item_id.like("adv_inscription_%"),
            )
        )
```

将空提示：
```python
            msg = "📜 你还没有铭文物品\n💡 分解带T2词缀的装备有概率获得铭文"
```

替换为：
```python
            msg = "📜 你还没有铭文物品\n💡 击杀精英怪可掉落铭文，或用铭文碎片合成\n💡 发送【合成铭文】消耗5个碎片合成基础铭文"
```

- [ ] **Step 2: 语法验证**

Run: `python -c "import ast; ast.parse(open('plugins/xiuxian_game/item/equipment_commands.py','r',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/equipment_commands.py
git commit -m "feat(inscription): 铭文列表支持高级铭文+品阶显示"
```

---

## Task 9: 帮助系统 + AI知识库更新

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:134-146`
- Modify: `plugins/xiuxian_game/data/knowledge/equip_system_help.yaml:78-103`

- [ ] **Step 1: 更新 help.py 铭文和分解帮助文案**

在 `help.py` 中找到铭文系统帮助区块（约134行），将原来的铭文+分解帮助替换为：

```python
        "━━━━━━━━━━━━━\n"
        "📜 铭文系统：\n"
        "• 铭文分为基础铭文(单效果)和高级铭文(多效果)\n"
        "• 铭文有品阶：下品/中品/上品/极品/仙品\n"
        "• 来源：精英怪掉落(主要)、铭文碎片合成(基础)\n"
        "• 3000级+精英怪有极低概率触发仙品铭文\n"
        "【铭文列表】 查看背包中的铭文\n"
        "【合成铭文】 消耗5个铭文碎片合成随机基础铭文\n"
        "【镶嵌 装备编号 孔位 铭文名】 镶嵌铭文\n"
        "【拆卸 装备编号 孔位】 拆卸铭文\n"
        "━━━━━━━━━━━━━\n"
        "🔨 分解系统：\n"
        "• 销毁装备获得洗词石（按稀有度1~15个）\n"
        "• 带T2词缀装备分解获得铭文碎片\n"
        "• 已穿戴/VIP装备不可分解\n"
        "【分解 装备编号/名称】 分解装备\n"
```

- [ ] **Step 2: 更新 equip_system_help.yaml**

在 `equip_system_help.yaml` 的 keywords 列表中添加：
```yaml
  - 合成铭文
  - 铭文碎片
  - 高级铭文
  - 品阶
  - 仙品
```

将 body 中的铭文系统和分解系统段落替换为与 help.py 一致的文案（去掉 Python 字符串转义）。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/equip_system_help.yaml
git commit -m "docs: 帮助系统更新铭文碎片+高级铭文+品阶说明"
```

---

## 实现顺序总结

| 顺序 | Task | 依赖 | 说明 |
|------|------|------|------|
| 1 | Task 1: ItemConfig扩展 | 无 | 基础设施 |
| 2 | Task 2: YAML数据 | Task 1 | 铭文模板定义 |
| 3 | Task 3: inscription_service扩展 | Task 1,2 | 核心逻辑 |
| 4 | Task 4: 战斗引擎 | Task 3 | 多效果注册 |
| 5 | Task 5: 掉落逻辑 | Task 3 | 精英怪掉落 |
| 6 | Task 6: 分解改造 | Task 3 | 碎片替代铭文 |
| 7 | Task 7: 合成命令 | Task 3,6 | 新命令 |
| 8 | Task 8: 铭文列表 | Task 3 | 显示优化 |
| 9 | Task 9: 帮助系统 | Task 7 | 文档同步 |
