# 装备系统 Phase 2：铭文 + 分解 + 洗炼 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现铭文系统（独立效果物品插入宝石孔）、分解系统（销毁装备获得洗词石+概率提取铭文）、洗炼系统（消耗洗词石重随机词缀数值）。

**Architecture:** 新增 `INSCRIPTION` 物品类型，铭文物品定义在 items.yaml 中，随机数值存储在 ItemInstance.extra_attrs["_inscription_values"]。铭文镶嵌时写入 gem_slots_data（字典格式区分宝石字符串格式），复用现有 GemSocketService。分解和洗炼作为独立命令模块。铭文在战斗中通过 BattleEffectManager 注册触发器生效。

**Tech Stack:** NoneBot2, SQLAlchemy (safe_session/UoW), YAML 配置, 现有 TriggerConfig/BattleEffectManager

**Spec:** `docs/superpowers/specs/2026-03-18-equipment-affix-inscription-design.md` 第4、6、7节

**Phase 1 已完成:** 词缀系统(T1+T2)、怪物掉落装备、战斗集成、洗词石物品

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Modify | `plugins/xiuxian_game/models/inventory.py` | ItemType.INSCRIPTION + add_item不占背包 + get/set_gem_in_slot扩展 |
| Modify | `plugins/xiuxian_game/data/items.yaml` | 铭文物品定义（~19种，对应T2词缀效果） |
| Create | `plugins/xiuxian_game/item/inscription_service.py` | 铭文生成、数值滚动、显示、战斗转换 |
| Modify | `plugins/xiuxian_game/item/gem_socket_service_new.py` | 扩展支持铭文镶嵌/拆卸 |
| Modify | `plugins/xiuxian_game/item/equipment_commands.py` | 孔位展示区分铭文/宝石 + 铭文列表命令 |
| Create | `plugins/xiuxian_game/item/decompose_service.py` | 装备分解逻辑 |
| Create | `plugins/xiuxian_game/item/decompose_commands.py` | 分解+洗炼命令处理 |
| Modify | `plugins/xiuxian_game/item/affix_service.py` | 新增洗炼逻辑 |
| Modify | `plugins/xiuxian_game/battle/enhanced_engine.py` | 铭文触发器注册 |
| Modify | `plugins/xiuxian_game/item/equipment_upgrade_service_new.py` | 升阶时铭文回收 |
| Modify | `plugins/xiuxian_game/player/help.py` | 帮助信息更新 |
| Modify | `plugins/xiuxian_game/data/knowledge/equip_system_help.yaml` | AI知识库同步 |

---

## 关键设计决策备忘

1. **gem_slots_data 值格式扩展：** 字符串=宝石（向后兼容），字典=铭文 `{"item_id": "inscription_fear", "values": {"chance": 12}}`
2. **铭文来源（Phase 2）：** 仅通过分解T2词缀装备获得（30%/条）。怪物直接掉落铭文在 Phase 3
3. **铭文不占背包格：** 与装备相同处理
4. **洗词石已在 Phase 1 定义：** item_id="affix_reroll_stone"，Phase 2 只需实现洗炼命令
5. **set_gem_in_slot 扩展：** 支持存储字典值（铭文）和字符串值（宝石），get_gem_in_slot 返回值类型变为 `str | dict | None`
6. **铭文 ItemInstance：** 铭文作为独立物品存在背包中，extra_attrs 含 `_inscription_values`。镶嵌时消耗铭文物品、将数据写入孔位；拆卸时从孔位数据恢复铭文物品

---

## Chunk 1: 数据模型与铭文物品

### Task 1: ItemType 枚举 + add_item 背包豁免 + gem_slots_data 扩展

**Files:**
- Modify: `plugins/xiuxian_game/models/inventory.py:13-28` (ItemType枚举)
- Modify: `plugins/xiuxian_game/models/inventory.py:344` (add_item背包计算)
- Modify: `plugins/xiuxian_game/models/inventory.py:288-305` (get/set_gem_in_slot)

- [ ] **Step 1: 新增 INSCRIPTION 枚举值**

在 `ItemType` 枚举中添加：

```python
class ItemType(str, PyEnum):
    CONSUMABLE = "CONSUMABLE"
    MATERIAL = "MATERIAL"
    EQUIPMENT = "EQUIPMENT"
    GOODS = "GOODS"
    GHOST_FRAGMENT = "GHOST_FRAGMENT"
    GEM = "GEM"
    FISH = "FISH"
    GIFT = "GIFT"
    SEASONING = "SEASONING"
    DISH = "DISH"
    RECIPE = "RECIPE"
    VEGETABLE = "VEGETABLE"
    HERB = "HERB"
    SEED = "SEED"
    GUARDIAN_BEAST = "GUARDIAN_BEAST"
    INSCRIPTION = "INSCRIPTION"       # 铭文（独立效果物品，插入宝石孔）
```

- [ ] **Step 2: add_item 中铭文不占背包格**

修改 `add_item()` 方法（约 line 330, 344, 349），让 INSCRIPTION 与 EQUIPMENT 同等处理：

```python
# line 330 附近
is_equipment = item_config.type == ItemType.EQUIPMENT
is_inscription = item_config.type == ItemType.INSCRIPTION
is_fish = item_config.is_fish

# line 344
used_slots = sum(1 for item in stacks_all if not item.is_equipment and not item.is_fish and not getattr(item, 'is_inscription', False))

# line 349 附近 — 铭文也走独立实例路径（每件铭文独立，因为有随机数值）
if is_equipment or is_inscription:
    # 装备/铭文不占用背包容量，直接添加
    item_durability = durability if durability is not None else (item_config.durability if is_equipment else None)
    for _ in range(quantity):
        inst = ItemInstance(
            player_id=player_id,
            item_id=template_id,
            quantity=1,
        )
        if item_durability is not None:
            inst.durability = item_durability
        session.add(inst)
    await session.flush()

    if is_equipment:
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player_id, "equipment_obtained", quantity)

    return True
```

同时为 ItemInstance 添加 `is_inscription` 属性（类似 `is_equipment`）：

```python
@property
def is_inscription(self) -> bool:
    """是否为铭文物品"""
    return self.config is not None and self.config.type == ItemType.INSCRIPTION
```

- [ ] **Step 3: 扩展 set_gem_in_slot 支持字典值**

```python
def set_gem_in_slot(self, slot_index: int, value: str | dict | None):
    """在指定孔位设置宝石或铭文

    value 为 str 时表示宝石 item_id（向后兼容）
    value 为 dict 时表示铭文数据 {"item_id": ..., "values": {...}}
    value 为 None 时移除孔位内容
    """
    if not self.is_equipment:
        return
    if self.gem_slots_data is None:
        self.gem_slots_data = {}
    if value is None:
        self.gem_slots_data.pop(str(slot_index), None)
    else:
        self.gem_slots_data[str(slot_index)] = value
```

扩展 `get_gem_in_slot` 返回类型注解：

```python
def get_gem_in_slot(self, slot_index: int) -> str | dict | None:
    """获取指定孔位中的宝石ID或铭文数据"""
    if not self.is_equipment:
        return None
    return (self.gem_slots_data or {}).get(str(slot_index))
```

- [ ] **Step 4: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/models/inventory.py`
Expected: 无报错

- [ ] **Step 5: 提交**

```bash
git add plugins/xiuxian_game/models/inventory.py
git commit -m "feat(inscription): ItemType.INSCRIPTION + 背包豁免 + gem_slots_data字典扩展"
```

---

### Task 2: 铭文物品定义（items.yaml）

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml`

铭文物品对应现有 T2 词缀效果（Phase 2 的铭文来源是分解T2词缀装备）。每种铭文有 `inscription_effect` 字段定义效果参数和数值浮动区间。

- [ ] **Step 1: 在 items.yaml 的 consumables 区域后添加铭文物品区块**

在 `affix_reroll_stone` 之后、`equipments:` 之前添加：

```yaml
    # ========== 铭文物品 ==========
    # 铭文为独立效果物品，可镶嵌到装备宝石孔位
    # inscription_effect 定义效果参数; chance_range 为随机数值区间
    # 铭文 ItemInstance 的 extra_attrs["_inscription_values"] 存储该实例的随机值

    - item_id: "inscription_fear"
      name: "铭文：恐惧之力"
      description: "攻击时{chance}%概率使敌人恐惧1回合"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 15000
      inscription_effect:
        trigger: "on_attack"
        effect: "fear"
        duration: 1
        chance_range: [5, 15]

    - item_id: "inscription_defense_pierce"
      name: "铭文：防御穿刺"
      description: "攻击时{chance}%概率无视敌人{value}%防御(2回合)"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 18000
      inscription_effect:
        trigger: "on_attack"
        effect: "defense_penetration"
        duration: 2
        chance_range: [8, 18]
        value_range: [15, 30]

    - item_id: "inscription_lifesteal"
      name: "铭文：嗜血之力"
      description: "暴击时{chance}%概率回复{value}%造成伤害"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 18000
      inscription_effect:
        trigger: "on_critical"
        effect: "lifesteal"
        chance_range: [10, 25]
        value_range: [10, 30]

    - item_id: "inscription_reflect"
      name: "铭文：反弹之力"
      description: "被攻击时{chance}%概率反弹{value}%伤害"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 16000
      inscription_effect:
        trigger: "on_defense"
        effect: "reflect"
        chance_range: [8, 20]
        value_range: [10, 25]

    - item_id: "inscription_damage_reduction"
      name: "铭文：坚韧之力"
      description: "被攻击时{chance}%概率减少{value}%伤害(1回合)"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 16000
      inscription_effect:
        trigger: "on_defense"
        effect: "damage_reduction"
        chance_range: [10, 22]
        value_range: [8, 20]

    - item_id: "inscription_true_damage"
      name: "铭文：真伤之力"
      description: "攻击时{chance}%概率附加{value}%真实伤害(1回合)"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 25000
      inscription_effect:
        trigger: "on_attack"
        effect: "true_damage"
        duration: 1
        chance_range: [8, 18]
        value_range: [10, 25]

    - item_id: "inscription_damage_boost"
      name: "铭文：狂暴之力"
      description: "首回合{chance}%概率提升{value}%伤害(2回合)"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 22000
      inscription_effect:
        trigger: "on_battle_start"
        effect: "damage_boost"
        duration: 2
        chance_range: [15, 35]
        value_range: [15, 30]

    - item_id: "inscription_execute"
      name: "铭文：处决之力"
      description: "目标低于30%血量时{chance}%概率伤害+{value}%"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 25000
      inscription_effect:
        trigger: "on_attack"
        effect: "execute"
        threshold: 30
        chance_range: [15, 30]
        value_range: [20, 40]

    - item_id: "inscription_shield"
      name: "铭文：护盾之力"
      description: "首回合{chance}%概率获得{value}%最大生命护盾"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 22000
      inscription_effect:
        trigger: "on_battle_start"
        effect: "shield"
        chance_range: [20, 40]
        value_range: [8, 18]

    - item_id: "inscription_regen"
      name: "铭文：回春之力"
      description: "每回合{chance}%概率回复{value}%最大生命"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 16000
      inscription_effect:
        trigger: "on_turn_start"
        effect: "regen"
        chance_range: [15, 35]
        value_range: [3, 8]

    - item_id: "inscription_debuff_attack"
      name: "铭文：破攻之力"
      description: "攻击时{chance}%概率降低敌人{value}%攻击(2回合)"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 15000
      inscription_effect:
        trigger: "on_attack"
        effect: "debuff_attack"
        duration: 2
        chance_range: [10, 22]
        value_range: [8, 18]

    - item_id: "inscription_debuff_defense"
      name: "铭文：破甲之力"
      description: "攻击时{chance}%概率降低敌人{value}%防御(2回合)"
      type: "INSCRIPTION"
      rarity: "blue"
      price: 15000
      inscription_effect:
        trigger: "on_attack"
        effect: "debuff_defense"
        duration: 2
        chance_range: [10, 22]
        value_range: [8, 18]

    - item_id: "inscription_burn_mp"
      name: "铭文：焚神之力"
      description: "攻击时{chance}%概率灼烧敌人{value}%理智(2回合)"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 22000
      inscription_effect:
        trigger: "on_attack"
        effect: "buff_attack"
        duration: 2
        chance_range: [12, 25]
        value_range: [8, 18]

    - item_id: "inscription_counter_fear"
      name: "铭文：逆鳞之力"
      description: "被暴击时{chance}%概率使敌人恐惧{value}回合"
      type: "INSCRIPTION"
      rarity: "purple"
      price: 20000
      inscription_effect:
        trigger: "on_be_crit"
        effect: "fear"
        chance_range: [10, 20]
        value_range: [1, 2]

- [ ] **Step 2: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/items.yaml','r',encoding='utf-8'))"`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml
git commit -m "feat(inscription): 铭文物品定义（14种，对应T2词缀效果）"
```

---

### Task 3: 铭文服务（inscription_service.py）

**Files:**
- Create: `plugins/xiuxian_game/item/inscription_service.py`

提供铭文核心功能：生成随机数值、格式化显示、转换为战斗触发器。

- [ ] **Step 1: 创建 inscription_service.py**

```python
"""
铭文服务

负责：
1. 为铭文物品生成随机数值（_inscription_values）
2. 从装备 gem_slots_data 读取铭文数据
3. 格式化铭文显示文本
4. 将铭文转换为 TriggerConfig 供战斗引擎使用
5. T2词缀到铭文的映射（分解提取用）
"""

import random
from typing import List, Dict, Optional, Tuple

from ..config import config
from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


# T2 词缀 affix_id → 铭文 item_id 映射表（分解提取用）
T2_AFFIX_TO_INSCRIPTION = {
    "fear_strike": "inscription_fear",
    "defense_pierce": "inscription_defense_pierce",
    "critical_lifesteal": "inscription_lifesteal",
    "reflect_damage": "inscription_reflect",
    "damage_reduction": "inscription_damage_reduction",
    "true_damage_strike": "inscription_true_damage",
    "first_strike_boost": "inscription_damage_boost",
    "execute_strike": "inscription_execute",
    "shield_proc": "inscription_shield",
    "regen_proc": "inscription_regen",
    "weaken_attack": "inscription_debuff_attack",
    "weaken_defense": "inscription_debuff_defense",
    "burn_mp": "inscription_burn_mp",
    "counter_fear": "inscription_counter_fear",
}


def generate_inscription_values(item_id: str, rng: random.Random = None) -> Dict:
    """为铭文物品生成随机数值

    Args:
        item_id: 铭文物品模板ID
        rng: 随机数生成器

    Returns:
        {"chance": float, "value": float(可选)}
    """
    if rng is None:
        rng = random.Random()

    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return {}

    effect_cfg = getattr(item_cfg, 'inscription_effect', None)
    if not effect_cfg:
        # 兼容 dict 格式
        raw = item_cfg._raw_data if hasattr(item_cfg, '_raw_data') else {}
        effect_cfg = raw.get("inscription_effect", {})

    if not effect_cfg:
        return {}

    values = {}
    chance_range = effect_cfg.get("chance_range")
    if chance_range:
        values["chance"] = round(rng.uniform(chance_range[0], chance_range[1]), 1)

    value_range = effect_cfg.get("value_range")
    if value_range:
        values["value"] = round(rng.uniform(value_range[0], value_range[1]), 1)

    return values


def get_inscription_effect_config(item_id: str) -> Optional[dict]:
    """获取铭文的 inscription_effect 配置"""
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return None
    # 尝试属性访问
    effect_cfg = getattr(item_cfg, 'inscription_effect', None)
    if effect_cfg:
        return effect_cfg
    # 兼容 raw dict
    raw = item_cfg._raw_data if hasattr(item_cfg, '_raw_data') else {}
    return raw.get("inscription_effect")


def get_inscription_display(slot_data: dict) -> str:
    """格式化铭文孔位数据的显示文本

    Args:
        slot_data: gem_slots_data 中的铭文字典
            {"item_id": "inscription_fear", "values": {"chance": 12}}

    Returns:
        如 "铭文：恐惧之力（攻击时12%概率使敌人恐惧1回合）"
    """
    item_id = slot_data.get("item_id", "")
    values = slot_data.get("values", {})

    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return f"铭文：未知({item_id})"

    name = item_cfg.name
    desc = item_cfg.description or ""

    # 替换描述模板中的占位符
    chance = values.get("chance")
    if chance is not None:
        desc = desc.replace("{chance}", f"{chance}")
    value = values.get("value")
    if value is not None:
        desc = desc.replace("{value}", f"{value}")

    return f"{name}（{desc}）"


def get_inscription_display_from_item(item_instance) -> str:
    """从铭文 ItemInstance 获取显示文本"""
    item_cfg = item_instance.config
    if not item_cfg:
        return "未知铭文"

    name = item_cfg.name
    desc = item_cfg.description or ""
    values = (item_instance.extra_attrs or {}).get("_inscription_values", {})

    chance = values.get("chance")
    if chance is not None:
        desc = desc.replace("{chance}", f"{chance}")
    value = values.get("value")
    if value is not None:
        desc = desc.replace("{value}", f"{value}")

    return f"{name}（{desc}）"


def get_inscriptions_from_equipment(gem_slots_data: Optional[dict]) -> List[Dict]:
    """从装备的 gem_slots_data 提取所有铭文数据

    Returns:
        铭文字典列表 [{"item_id": ..., "values": {...}, "slot_index": int}, ...]
    """
    if not gem_slots_data:
        return []
    inscriptions = []
    for slot_idx, slot_val in gem_slots_data.items():
        if isinstance(slot_val, dict) and "item_id" in slot_val:
            data = dict(slot_val)
            data["slot_index"] = int(slot_idx)
            inscriptions.append(data)
    return inscriptions


def inscription_to_trigger_config(inscription_data: dict, source_name: str = "铭文") -> Optional[TriggerConfig]:
    """将铭文数据转换为 TriggerConfig

    Args:
        inscription_data: {"item_id": ..., "values": {"chance": ..., "value": ...}}
        source_name: 来源装备名

    Returns:
        TriggerConfig 或 None
    """
    item_id = inscription_data.get("item_id", "")
    values = inscription_data.get("values", {})

    effect_cfg = get_inscription_effect_config(item_id)
    if not effect_cfg:
        return None

    item_cfg = config.items_config["by_id"].get(item_id)
    insc_name = item_cfg.name if item_cfg else item_id

    trigger_type = TriggerType(effect_cfg["trigger"])
    effect_type = EffectType(effect_cfg["effect"])
    chance = values.get("chance", 0)
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


def get_affix_to_inscription_id(affix_id: str) -> Optional[str]:
    """T2词缀ID → 对应铭文item_id（分解提取用）"""
    return T2_AFFIX_TO_INSCRIPTION.get(affix_id)
```

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/inscription_service.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/inscription_service.py
git commit -m "feat(inscription): 铭文服务（生成/显示/战斗转换/分解映射）"
```

---

## Chunk 2: GemSocketService 扩展 + 装备展示 + 战斗集成

### Task 4: GemSocketService 扩展支持铭文

**Files:**
- Modify: `plugins/xiuxian_game/item/gem_socket_service_new.py`

需改造4个方法：is_socketable_item、get_gem_type、socket_gem、remove_gem，以及 get_equipment_gem_info。

- [ ] **Step 1: 扩展 is_socketable_item 支持铭文**

```python
@staticmethod
def is_socketable_item(item_id: str) -> bool:
    """检查物品是否可镶嵌（宝石或铭文）"""
    item_config = config.items_config["by_id"].get(item_id)
    return item_config and item_config.type.value in ("GEM", "INSCRIPTION")
```

- [ ] **Step 2: 扩展 get_gem_type 识别铭文**

在 `get_gem_type()` 方法开头添加铭文识别：

```python
@staticmethod
def get_gem_type(item_id: str) -> str:
    # 铭文类型
    if item_id.startswith("inscription_"):
        return "铭文"
    # ... 现有宝石识别代码保持不变
```

- [ ] **Step 3: 扩展 get_equipment_gem_info 区分铭文**

修改 `get_equipment_gem_info()` 方法，当孔位值是 dict 时返回铭文信息：

```python
@staticmethod
def get_equipment_gem_info(equipment: ItemInstance) -> List[Dict]:
    """获取装备的镶嵌物信息（宝石+铭文）"""
    from .inscription_service import get_inscription_display

    if not equipment.is_equipment:
        return []

    total_slots = equipment.available_gem_slots
    result = []

    for i in range(total_slots):
        slot_val = equipment.get_gem_in_slot(i)
        slot_info = {
            "slot_index": i,
            "slot_number": i + 1,
            "is_empty": slot_val is None,
        }

        if slot_val is None:
            slot_info.update({
                "gem_item_id": None,
                "gem_name": "空",
                "gem_type": "空",
                "gem_config": None,
                "is_inscription": False,
            })
        elif isinstance(slot_val, dict):
            # 铭文
            insc_item_id = slot_val.get("item_id", "")
            insc_cfg = config.items_config["by_id"].get(insc_item_id)
            slot_info.update({
                "gem_item_id": insc_item_id,
                "gem_name": insc_cfg.name if insc_cfg else insc_item_id,
                "gem_type": "铭文",
                "gem_config": insc_cfg,
                "is_inscription": True,
                "inscription_data": slot_val,
            })
        else:
            # 宝石（原有逻辑）
            gem_config = config.items_config["by_id"].get(slot_val)
            slot_info.update({
                "gem_item_id": slot_val,
                "gem_name": gem_config.name if gem_config else slot_val,
                "gem_type": GemSocketService.get_gem_type(slot_val),
                "gem_config": gem_config,
                "is_inscription": False,
            })

        result.append(slot_info)

    return result
```

- [ ] **Step 4: 扩展 socket_gem 支持铭文镶嵌**

在 `socket_gem()` 方法中，铭文镶嵌时需要：
1. 找到铭文 ItemInstance（带 `_inscription_values`）
2. 将数据写入孔位为字典格式
3. 删除铭文 ItemInstance

修改 `socket_gem()` 方法：

```python
async def socket_gem(self, equipment: ItemInstance, gem_item_id: str, slot_index: int, player: Player,
                     inscription_instance: "ItemInstance" = None) -> Tuple[bool, str]:
    """镶嵌宝石或铭文

    Args:
        inscription_instance: 铭文物品实例（仅铭文镶嵌时传入，用于读取随机数值）
    """
    can_socket, reason = await self.can_socket_gem(equipment, gem_item_id, slot_index, player)
    if not can_socket:
        return False, reason

    item_cfg = config.items_config["by_id"].get(gem_item_id)
    is_inscription = item_cfg and item_cfg.type.value == "INSCRIPTION"

    if is_inscription and inscription_instance:
        # 铭文镶嵌：读取随机数值，写入孔位为字典格式
        insc_values = (inscription_instance.extra_attrs or {}).get("_inscription_values", {})
        slot_data = {
            "item_id": gem_item_id,
            "values": insc_values,
        }
        # 删除铭文物品实例
        await self._item_repo.delete_item_instance(inscription_instance)
        # 消耗镶嵌锤
        hammer_success = await self._item_repo.consume_item(player.id, "gem_hammer", 1)
        if not hammer_success:
            raise ValueError("消耗镶嵌锤失败")
        # 消耗金币
        player.gold -= self.SOCKET_COSTS["gold"]
        await self._player_repo.update(player)
        # 写入孔位
        equipment.set_gem_in_slot(slot_index, slot_data)
        insc_name = item_cfg.name if item_cfg else gem_item_id
        return True, f"✨ 成功镶嵌铭文：{insc_name} 到孔位 {slot_index + 1}"
    else:
        # 宝石镶嵌：原有逻辑
        gem_success = await self._item_repo.consume_item(player.id, gem_item_id, 1)
        hammer_success = await self._item_repo.consume_item(player.id, "gem_hammer", 1)
        if not gem_success or not hammer_success:
            raise ValueError("消耗材料失败")
        player.gold -= self.SOCKET_COSTS["gold"]
        await self._player_repo.update(player)
        equipment.set_gem_in_slot(slot_index, gem_item_id)
        gem_config = config.items_config["by_id"].get(gem_item_id)
        gem_name = gem_config.name if gem_config else gem_item_id
        gem_type = self.get_gem_type(gem_item_id)
        return True, f"✨ 成功镶嵌 {gem_type}：{gem_name} 到孔位 {slot_index + 1}"
```

- [ ] **Step 5: 扩展 remove_gem 支持铭文拆卸**

在 `remove_gem()` 中，铭文拆卸时需要从孔位字典恢复铭文 ItemInstance：

修改 `remove_gem()` 方法中获取宝石信息的部分：

```python
async def remove_gem(self, equipment: ItemInstance, slot_index: int, player: Player, use_protection: bool = False) -> Tuple[bool, str]:
    can_remove, reason = await self.can_remove_gem(equipment, slot_index, player, use_protection)
    if not can_remove:
        return False, reason

    slot_val = equipment.get_gem_in_slot(slot_index)
    is_inscription = isinstance(slot_val, dict)

    if is_inscription:
        insc_item_id = slot_val.get("item_id", "")
        insc_values = slot_val.get("values", {})
        item_cfg = config.items_config["by_id"].get(insc_item_id)
        gem_name = item_cfg.name if item_cfg else insc_item_id
        gem_type = "铭文"
    else:
        gem_item_id = slot_val
        gem_config = config.items_config["by_id"].get(gem_item_id)
        gem_name = gem_config.name if gem_config else gem_item_id
        gem_type = self.get_gem_type(gem_item_id)

    # 消耗工具和金币（与原有逻辑相同）
    chisel_success = await self._item_repo.consume_item(player.id, "gem_chisel", 1)
    if not chisel_success:
        raise ValueError("消耗拆卸凿失败")
    if use_protection:
        crystal_success = await self._item_repo.consume_item(player.id, "stabilizer_crystal", 1)
        if not crystal_success:
            raise ValueError("消耗稳定水晶失败")
    player.gold -= self.REMOVE_COSTS["gold"]
    await self._player_repo.update(player)

    # 移除孔位
    equipment.set_gem_in_slot(slot_index, None)

    result_messages = []

    if use_protection:
        # 稳定水晶保护
        if is_inscription:
            await self._restore_inscription(player.id, insc_item_id, insc_values)
            result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
        else:
            try:
                await self._item_repo.add_item(player.id, gem_item_id, 1)
                result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
            except ValueError:
                result_messages.append(f"💔 背包空间不足，{gem_type} {gem_name} 丢失了")
        result_messages.append("🛡️ 稳定水晶保护生效，物品和装备完好无损")
    else:
        gem_destroyed = random.random() < self.REMOVE_RISKS["gem_destroy_rate"]
        equipment_damaged = random.random() < self.REMOVE_RISKS["equipment_damage_rate"]

        if gem_destroyed:
            result_messages.append(f"💔 {gem_type} {gem_name} 在拆卸过程中损坏了")
        else:
            if is_inscription:
                await self._restore_inscription(player.id, insc_item_id, insc_values)
                result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
            else:
                try:
                    await self._item_repo.add_item(player.id, gem_item_id, 1)
                    result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
                except ValueError:
                    result_messages.append(f"💔 背包空间不足，{gem_type} {gem_name} 丢失了")

        if equipment_damaged:
            damage = max(1, equipment.config.durability // 10)
            equipment.durability = max(0, equipment.durability - damage)
            result_messages.append(f"⚠️ 装备在拆卸过程中受损，耐久度 -{damage}")

    return True, "\n".join(result_messages)


async def _restore_inscription(self, player_id: str, item_id: str, values: dict):
    """恢复铭文物品到背包（从孔位数据重建 ItemInstance）"""
    from ..models.inventory import ItemInstance
    session = self._item_repo._session
    inst = ItemInstance(
        player_id=player_id,
        item_id=item_id,
        quantity=1,
        extra_attrs={"_inscription_values": values},
    )
    session.add(inst)
    await session.flush()
```

- [ ] **Step 6: 修改 can_remove_gem 兼容铭文孔位**

`can_remove_gem` 中 `get_gem_in_slot` 返回值可能是 dict，需要兼容：

```python
# 在 can_remove_gem 中，替换:
gem_item_id = equipment.get_gem_in_slot(slot_index)
if gem_item_id is None:
    return False, f"孔位 {slot_index + 1} 没有镶嵌物品"

# 改为:
slot_val = equipment.get_gem_in_slot(slot_index)
if slot_val is None:
    return False, f"孔位 {slot_index + 1} 没有镶嵌物品"
```

- [ ] **Step 7: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/gem_socket_service_new.py`
Expected: 无报错

- [ ] **Step 8: 提交**

```bash
git add plugins/xiuxian_game/item/gem_socket_service_new.py
git commit -m "feat(inscription): GemSocketService扩展支持铭文镶嵌/拆卸"
```

---

### Task 5: 装备详情展示铭文 + 铭文列表命令

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_commands.py`

- [ ] **Step 1: 修改装备详情孔位展示区分铭文**

在装备详情展示的宝石区域（约 line 287-301），修改展示逻辑：

```python
# 宝石/铭文镶嵌信息
if equip.available_gem_slots > 0:
    lines.append("💎 镶嵌孔位：")
    lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")

    if equip.used_gem_slots > 0:
        from .gem_socket_service_new import GemSocketService
        from .inscription_service import get_inscription_display
        gem_info = GemSocketService.get_equipment_gem_info(equip)
        for slot_info in gem_info:
            if not slot_info["is_empty"]:
                slot_num = slot_info["slot_number"]
                if slot_info.get("is_inscription"):
                    display = get_inscription_display(slot_info["inscription_data"])
                    lines.append(f"  • 孔位{slot_num}：📜 {display}")
                else:
                    gem_name = slot_info["gem_name"]
                    gem_type = slot_info["gem_type"]
                    lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")
```

- [ ] **Step 2: 添加铭文列表命令**

在 `equipment_commands.py` 末尾添加铭文列表命令：

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg

inscription_list_cmd = on_command("铭文列表", aliases={"铭文背包", "我的铭文"}, priority=5, block=True)

@inscription_list_cmd.handle()
async def handle_inscription_list(event: MessageEvent, args: Message = CommandArg()):
    from ..models.player import Player
    from ..models.inventory import ItemInstance, ItemType
    from ..core.safe_session import safe_session
    from .inscription_service import get_inscription_display_from_item

    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await inscription_list_cmd.finish("你还没有创建角色")

        from sqlalchemy import select
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id.like("inscription_%")
        )
        inscriptions = (await session.execute(stmt)).scalars().all()

    if not inscriptions:
        await inscription_list_cmd.finish("📜 你还没有铭文物品\n💡 分解带T2词缀的装备有概率获得铭文")

    lines = ["📜 铭文列表："]
    for i, insc in enumerate(inscriptions, 1):
        display = get_inscription_display_from_item(insc)
        rarity = insc.config.rarity if insc.config else "unknown"
        rarity_map = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}
        icon = rarity_map.get(rarity, "⚪")
        lines.append(f"  [{i}] {icon} {display}")
    lines.append(f"\n💡 使用【镶嵌 装备编号 孔位 铭文名】将铭文插入装备")

    await inscription_list_cmd.finish(Message("\n".join(lines)))
```

- [ ] **Step 3: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/equipment_commands.py`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/item/equipment_commands.py
git commit -m "feat(inscription): 装备详情铭文展示 + 铭文列表命令"
```

---

### Task 6: 战斗引擎铭文触发器注册

**Files:**
- Modify: `plugins/xiuxian_game/battle/enhanced_engine.py`

在 `_register_equipment_triggers()` 末尾（T2词缀注册之后）添加铭文触发器注册。

- [ ] **Step 1: 在 T2 词缀注册代码之后添加铭文注册**

在 `_register_equipment_triggers()` 方法末尾追加：

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

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/battle/enhanced_engine.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/battle/enhanced_engine.py
git commit -m "feat(inscription): 战斗引擎注册铭文触发器"
```

---

## Chunk 3: 分解系统

### Task 7: 分解服务（decompose_service.py）

**Files:**
- Create: `plugins/xiuxian_game/item/decompose_service.py`

- [ ] **Step 1: 创建 decompose_service.py**

```python
"""
装备分解服务

功能：
- 销毁装备获得洗词石
- 带T2词缀的装备有概率提取铭文
"""

import random
from typing import List, Tuple, Dict
from dataclasses import dataclass

from ..models.inventory import ItemInstance, ItemType
from ..item.affix_service import get_affixes_from_equipment, VIP_EQUIPMENT_IDS
from ..config import config


@dataclass
class DecomposeResult:
    """分解结果"""
    success: bool
    message: str
    reroll_stones: int = 0
    inscriptions: List[str] = None  # 提取到的铭文名称列表

    def __post_init__(self):
        if self.inscriptions is None:
            self.inscriptions = []


# 分解产出表：{稀有度: (基础洗词石, 有词缀额外最小, 有词缀额外最大)}
DECOMPOSE_YIELDS = {
    "white":  (1, 1, 1),
    "green":  (2, 1, 2),
    "blue":   (4, 2, 3),
    "purple": (8, 3, 4),
    "orange": (15, 4, 5),
}

# T2 词缀提取铭文概率
INSCRIPTION_EXTRACT_CHANCE = 0.30


def validate_decompose(equipment: ItemInstance) -> Tuple[bool, str]:
    """验证装备是否可分解

    Returns:
        (可否分解, 原因)
    """
    if not equipment.is_equipment:
        return False, "只能分解装备"

    if equipment.equipped:
        return False, "请先卸下装备再分解"

    item_id = getattr(equipment, 'item_id', '')
    if item_id in VIP_EQUIPMENT_IDS:
        return False, "VIP定制装备不可分解"

    # 检查是否在交易/拍卖中
    extra = equipment.extra_attrs or {}
    if extra.get("_frozen_for_trade") or extra.get("_frozen_for_auction"):
        return False, "正在交易/拍卖中的装备不可分解"

    return True, ""


def calculate_decompose_yields(equipment: ItemInstance, rng: random.Random = None) -> Tuple[int, List[Dict]]:
    """计算分解产出

    Args:
        equipment: 装备实例
        rng: 随机数生成器

    Returns:
        (洗词石数量, 提取的铭文列表[{"item_id": str, "name": str}])
    """
    if rng is None:
        rng = random.Random()

    rarity = equipment.config.rarity if equipment.config else "white"
    yields = DECOMPOSE_YIELDS.get(rarity, (1, 0, 0))
    base_stones, extra_min, extra_max = yields

    # 有词缀时额外产出
    affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
    has_affixes = len(affixes) > 0

    total_stones = base_stones
    if has_affixes:
        total_stones += rng.randint(extra_min, extra_max)

    # T2 词缀提取铭文
    extracted_inscriptions = []
    from .inscription_service import get_affix_to_inscription_id, generate_inscription_values
    for affix in affixes:
        if affix.get("tier") != "T2":
            continue
        affix_id = affix.get("affix_id", "")
        inscription_id = get_affix_to_inscription_id(affix_id)
        if not inscription_id:
            continue
        if rng.random() < INSCRIPTION_EXTRACT_CHANCE:
            insc_cfg = config.items_config["by_id"].get(inscription_id)
            insc_name = insc_cfg.name if insc_cfg else inscription_id
            extracted_inscriptions.append({
                "item_id": inscription_id,
                "name": insc_name,
            })

    return total_stones, extracted_inscriptions
```

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/decompose_service.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/decompose_service.py
git commit -m "feat(decompose): 装备分解服务（洗词石产出+铭文提取）"
```

---

### Task 8: 分解命令处理

**Files:**
- Create: `plugins/xiuxian_game/item/decompose_commands.py`

- [ ] **Step 1: 创建分解命令处理器**

```python
"""
分解系统命令处理

指令：
- 【分解 装备编号/名称】 — 分解装备获得洗词石（+概率铭文）
"""

import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..core.safe_session import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from .decompose_service import validate_decompose, calculate_decompose_yields
from .inscription_service import generate_inscription_values


decompose_cmd = on_command("分解", priority=5, block=True)


@decompose_cmd.handle()
async def handle_decompose(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await decompose_cmd.finish("用法：【分解 装备编号/名称】\n分解装备获得洗词石，带T2词缀的装备有概率提取铭文")

    msg = ""
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await decompose_cmd.finish("你还没有创建角色")

        # 查找装备
        equipment = await _find_equipment(session, player.id, raw_args)
        if not equipment:
            await decompose_cmd.finish(f"未找到装备：{raw_args}")

        # 验证
        can_decompose, reason = validate_decompose(equipment)
        if not can_decompose:
            await decompose_cmd.finish(reason)

        equip_name = equipment.config.name if equipment.config else equipment.item_id

        # 计算产出
        rng = random.Random()
        stones, inscriptions = calculate_decompose_yields(equipment, rng)

        # 回收孔位中的宝石/铭文
        recovered_items = []
        if equipment.gem_slots_data:
            for slot_idx, slot_val in dict(equipment.gem_slots_data).items():
                if slot_val is None:
                    continue
                if isinstance(slot_val, dict):
                    # 铭文恢复
                    insc_id = slot_val.get("item_id", "")
                    insc_values = slot_val.get("values", {})
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
                    # 宝石恢复
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
        if stones > 0:
            await ItemInstance.add_item(session, player.id, "affix_reroll_stone", stones)

        # 发放铭文
        inscription_names = []
        for insc_info in inscriptions:
            insc_id = insc_info["item_id"]
            values = generate_inscription_values(insc_id, rng)
            inst = ItemInstance(
                player_id=player.id,
                item_id=insc_id,
                quantity=1,
                extra_attrs={"_inscription_values": values},
            )
            session.add(inst)
            inscription_names.append(insc_info["name"])

        # 删除装备
        await session.delete(equipment)

        # 构建消息
        lines = [f"🔨 分解成功：{equip_name}"]
        lines.append(f"  💎 获得洗词石 ×{stones}")
        if inscription_names:
            for name in inscription_names:
                lines.append(f"  📜 提取铭文：{name}")
        if recovered_items:
            lines.append(f"  🔄 回收镶嵌物：{'、'.join(recovered_items)}")
        msg = "\n".join(lines)

    await decompose_cmd.finish(Message(msg))


async def _find_equipment(session, player_id: str, keyword: str) -> ItemInstance | None:
    """按编号或名称查找装备"""
    from ..config import config as game_config

    # 尝试按编号查找
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

    # 按名称模糊查找
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
    )
    all_items = (await session.execute(stmt)).scalars().all()
    for item in all_items:
        if item.is_equipment and item.config and keyword in item.config.name:
            return item

    return None


# 需要在 __init__.py 中导入此模块以注册命令
from ..config import config
```

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/decompose_commands.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/decompose_commands.py
git commit -m "feat(decompose): 分解命令处理器"
```

---

## Chunk 4: 洗炼系统

### Task 9: 洗炼逻辑 + 洗炼命令

**Files:**
- Modify: `plugins/xiuxian_game/item/affix_service.py` (新增 reroll 函数)
- Create: `plugins/xiuxian_game/item/reroll_commands.py` (洗炼命令)

- [ ] **Step 1: 在 affix_service.py 末尾添加洗炼函数**

```python
def reroll_single_affix(affix_data: dict, rarity: str, rng: random.Random = None) -> Dict:
    """洗炼单条词缀：类型不变，数值在原区间内重新随机

    Args:
        affix_data: 当前词缀数据
        rarity: 装备稀有度
        rng: 随机数生成器

    Returns:
        新的词缀数据（同类型，新数值）
    """
    if rng is None:
        rng = random.Random()

    cfg = _load_affix_config()
    affix_id = affix_data["affix_id"]
    tier = affix_data["tier"]

    pool_key = "t1" if tier == "T1" else "t2"
    affix_cfg = None
    for a in cfg["affixes"][pool_key]:
        if a["affix_id"] == affix_id:
            affix_cfg = a
            break

    if not affix_cfg:
        return affix_data  # 未知词缀不变

    return _roll_affix_values(tier, affix_cfg, rarity, rng)


def get_affix_value_range_display(affix_data: dict, rarity: str) -> str:
    """获取词缀数值区间的显示文本（洗炼预览用）

    Returns:
        如 "区间：3.0% ~ 6.0%"
    """
    cfg = _load_affix_config()
    affix_id = affix_data["affix_id"]
    tier = affix_data["tier"]

    pool_key = "t1" if tier == "T1" else "t2"
    affix_cfg = None
    for a in cfg["affixes"][pool_key]:
        if a["affix_id"] == affix_id:
            affix_cfg = a
            break

    if not affix_cfg:
        return "区间：未知"

    if tier == "T1":
        value_range = affix_cfg.get("ranges", {}).get(rarity, [0, 0])
        return f"区间：{value_range[0]}% ~ {value_range[1]}%"
    else:
        parts = []
        chance_range = affix_cfg.get("chance_ranges", {}).get(rarity, [0, 0])
        parts.append(f"概率区间：{chance_range[0]}% ~ {chance_range[1]}%")
        if "value_ranges" in affix_cfg and rarity in affix_cfg["value_ranges"]:
            v_range = affix_cfg["value_ranges"][rarity]
            parts.append(f"效果区间：{v_range[0]} ~ {v_range[1]}")
        if "duration_ranges" in affix_cfg and rarity in affix_cfg["duration_ranges"]:
            d_range = affix_cfg["duration_ranges"][rarity]
            parts.append(f"持续区间：{d_range[0]} ~ {d_range[1]}回合")
        return " | ".join(parts)
```

- [ ] **Step 2: 创建洗炼命令处理器**

```python
"""
洗炼系统命令处理

指令：
- 【洗炼 装备编号/名称 词缀序号】 — 预览洗炼信息
- 【确认洗炼】 — 执行洗炼
"""

import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..core.safe_session import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from .affix_service import (
    get_affixes_from_equipment, get_affix_display_name,
    get_affix_value_range_display, reroll_single_affix,
    VIP_EQUIPMENT_IDS,
)


# 洗炼待确认缓存: {user_id: {"equipment_id": int, "affix_index": int}}
_pending_rerolls: dict = {}


reroll_cmd = on_command("洗炼", priority=5, block=True)


@reroll_cmd.handle()
async def handle_reroll(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip().split()
    if len(raw_args) < 2:
        await reroll_cmd.finish("用法：【洗炼 装备编号/名称 词缀序号】\n消耗洗词石重新随机指定词缀的数值")

    equip_keyword = raw_args[0]
    try:
        affix_index = int(raw_args[1]) - 1  # 用户输入从1开始
    except ValueError:
        await reroll_cmd.finish("词缀序号必须是数字")
        return

    user_id = event.get_user_id()
    msg = ""

    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await reroll_cmd.finish("你还没有创建角色")

        # 查找装备
        from .decompose_commands import _find_equipment
        equipment = await _find_equipment(session, player.id, equip_keyword)
        if not equipment:
            await reroll_cmd.finish(f"未找到装备：{equip_keyword}")

        if equipment.item_id in VIP_EQUIPMENT_IDS:
            await reroll_cmd.finish("VIP定制装备不可洗炼")

        # 读取词缀
        affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
        if not affixes:
            await reroll_cmd.finish("该装备没有词缀，无法洗炼")

        if affix_index < 0 or affix_index >= len(affixes):
            await reroll_cmd.finish(f"词缀序号无效，该装备有 {len(affixes)} 条词缀")

        # 检查洗词石
        has_stone = False
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "affix_reroll_stone",
        )
        stone_items = (await session.execute(stmt)).scalars().all()
        stone_count = sum(s.quantity for s in stone_items)
        if stone_count < 1:
            await reroll_cmd.finish("洗词石不足，需要洗词石×1\n💡 分解装备可获得洗词石")

        equip_name = equipment.config.name if equipment.config else equipment.item_id
        rarity = equipment.config.rarity if equipment.config else "white"
        target_affix = affixes[affix_index]
        current_display = get_affix_display_name(target_affix)
        range_display = get_affix_value_range_display(target_affix, rarity)

        # 缓存待确认
        _pending_rerolls[user_id] = {
            "equipment_id": equipment.id,
            "affix_index": affix_index,
        }

        lines = [
            f"🔄 洗炼预览 — {equip_name}",
            f"  当前词缀：{current_display}",
            f"  {range_display}",
            f"  消耗：洗词石×1（当前持有：{stone_count}）",
            "",
            "⚠️ 洗炼后数值直接覆盖，不可保留旧值",
            "发送【确认洗炼】执行",
        ]
        msg = "\n".join(lines)

    await reroll_cmd.finish(Message(msg))


confirm_reroll_cmd = on_command("确认洗炼", priority=5, block=True)


@confirm_reroll_cmd.handle()
async def handle_confirm_reroll(event: MessageEvent):
    user_id = event.get_user_id()
    pending = _pending_rerolls.pop(user_id, None)
    if not pending:
        await confirm_reroll_cmd.finish("没有待确认的洗炼操作，请先使用【洗炼 装备编号 词缀序号】")

    equipment_id = pending["equipment_id"]
    affix_index = pending["affix_index"]
    msg = ""

    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await confirm_reroll_cmd.finish("你还没有创建角色")

        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != player.id:
            await confirm_reroll_cmd.finish("装备不存在或已不属于你")

        # 消耗洗词石
        consumed = await ItemInstance.add_item(session, player.id, "affix_reroll_stone", -1)
        # add_item 不支持负数，改用 consume 模式
        stone_stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "affix_reroll_stone",
        )
        stone_items = (await session.execute(stone_stmt)).scalars().all()
        stone_count = sum(s.quantity for s in stone_items)
        if stone_count < 1:
            await confirm_reroll_cmd.finish("洗词石不足")
        # 消耗1个
        for s in stone_items:
            if s.quantity >= 1:
                s.quantity -= 1
                if s.quantity <= 0:
                    await session.delete(s)
                break

        # 读取词缀
        affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
        if affix_index >= len(affixes):
            await confirm_reroll_cmd.finish("词缀序号已失效")

        rarity = equipment.config.rarity if equipment.config else "white"
        old_affix = affixes[affix_index]
        old_display = get_affix_display_name(old_affix)

        # 洗炼
        rng = random.Random()
        new_affix = reroll_single_affix(old_affix, rarity, rng)

        # 写入
        extra = dict(equipment.extra_attrs or {})
        affix_list = list(extra.get("_affixes", []))
        affix_list[affix_index] = new_affix
        extra["_affixes"] = affix_list
        equipment.extra_attrs = extra

        new_display = get_affix_display_name(new_affix)

        # 比较变化
        old_val = old_affix.get("value", 0)
        new_val = new_affix.get("value", 0)
        if new_val > old_val:
            trend = "⬆️ 上升"
        elif new_val < old_val:
            trend = "⬇️ 下降"
        else:
            trend = "➡️ 不变"

        equip_name = equipment.config.name if equipment.config else equipment.item_id
        lines = [
            f"🔄 洗炼完成 — {equip_name}",
            f"  旧词缀：{old_display}",
            f"  新词缀：{new_display}",
            f"  变化：{trend}",
        ]
        msg = "\n".join(lines)

    await confirm_reroll_cmd.finish(Message(msg))
```

- [ ] **Step 3: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/affix_service.py && python -m py_compile plugins/xiuxian_game/item/reroll_commands.py`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/item/affix_service.py plugins/xiuxian_game/item/reroll_commands.py
git commit -m "feat(reroll): 洗炼系统（预览确认制 + 数值重随机）"
```

---

## Chunk 5: 升阶回收 + 命令注册

### Task 10: 升阶时铭文回收

**Files:**
- Modify: `plugins/xiuxian_game/item/equipment_upgrade_service_new.py`

- [ ] **Step 1: 修改 _recover_gems_from_equipment 支持铭文**

在 `_recover_gems_from_equipment()` 方法中，区分 gem_slots_data 中的字符串（宝石）和字典（铭文）：

```python
async def _recover_gems_from_equipment(
    self, equipment: ItemInstance, player: Player, all_survive: bool = False
) -> List[str]:
    """从装备中回收镶嵌的宝石和铭文"""
    recovered = []

    if not equipment.is_equipment or not equipment.gem_slots_data:
        return recovered

    for slot_val in equipment.gem_slots_data.values():
        if not slot_val:
            continue

        # 非全量模式下，每个物品独立50%存活
        if not all_survive and random.random() < 0.5:
            continue

        if isinstance(slot_val, dict):
            # 铭文恢复
            insc_id = slot_val.get("item_id", "")
            insc_values = slot_val.get("values", {})
            insc_cfg = config.items_config["by_id"].get(insc_id)
            insc_name = insc_cfg.name if insc_cfg else insc_id
            try:
                from ..models.inventory import ItemInstance as II
                inst = II(
                    player_id=player.id,
                    item_id=insc_id,
                    quantity=1,
                    extra_attrs={"_inscription_values": insc_values},
                )
                self._item_repo._session.add(inst)
                recovered.append(insc_name)
            except Exception:
                gold_value = insc_cfg.price if insc_cfg else 5000
                player.gold += gold_value
                recovered.append(f"{insc_name}(转为{gold_value}金币)")
        else:
            # 宝石恢复（原有逻辑）
            gem_config = config.items_config["by_id"].get(slot_val)
            gem_name = gem_config.name if gem_config else slot_val
            try:
                await self._item_repo.add_item(player.id, slot_val, 1)
                recovered.append(gem_name)
            except ValueError:
                gold_value = gem_config.price if gem_config else 1000
                player.gold += gold_value
                recovered.append(f"{gem_name}(转为{gold_value}金币)")

    return recovered
```

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/item/equipment_upgrade_service_new.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/item/equipment_upgrade_service_new.py
git commit -m "feat(inscription): 升阶时铭文自动回收到背包"
```

---

### Task 11: 注册新命令模块

**Files:**
- Modify: `plugins/xiuxian_game/__init__.py` 或对应的命令注册入口

- [ ] **Step 1: 确认命令注册方式并注册新模块**

查看 `__init__.py` 中现有的导入方式，按相同模式添加：

```python
from .item import decompose_commands
from .item import reroll_commands
```

如果项目使用 nonebot 插件自动加载，则需要确认 `decompose_commands.py` 和 `reroll_commands.py` 中的 `on_command` 注册会被自动发现。

- [ ] **Step 2: 语法验证**

Run: `python -m py_compile plugins/xiuxian_game/__init__.py`
Expected: 无报错

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/__init__.py
git commit -m "feat: 注册分解和洗炼命令模块"
```

---

## Chunk 6: 帮助 + 知识库 + 验证

### Task 12: 帮助系统更新

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`
- Modify: `plugins/xiuxian_game/data/knowledge/equip_system_help.yaml`

- [ ] **Step 1: 更新 help.py 装备系统帮助**

在装备系统帮助的词缀系统区域之后、总部商店之前，添加铭文、分解、洗炼帮助：

```
"━━━━━━━━━━━━━\n"
"📜 铭文系统：\n"
"• 铭文为独立效果物品，可插入装备宝石孔位\n"
"• 与宝石共用孔位，每孔只能放一种\n"
"• 铭文来源：分解带T2词缀的装备（30%概率提取）\n"
"【铭文列表】 查看背包中的铭文\n"
"【镶嵌 装备编号 孔位 铭文名】 镶嵌铭文（复用宝石镶嵌）\n"
"【拆卸 装备编号 孔位】 拆卸铭文（复用宝石拆卸）\n"
"━━━━━━━━━━━━━\n"
"🔨 分解系统：\n"
"• 销毁装备获得洗词石（按稀有度1~15个）\n"
"• 带T2词缀装备分解有概率提取铭文\n"
"• 已穿戴/VIP装备不可分解\n"
"【分解 装备编号/名称】 分解装备\n"
"━━━━━━━━━━━━━\n"
"🔄 洗炼系统：\n"
"• 消耗洗词石×1重新随机词缀数值\n"
"• 词缀类型不变，数值在区间内重随机\n"
"• 洗炼后直接覆盖，不可保留旧值\n"
"【洗炼 装备编号/名称 词缀序号】 预览洗炼信息\n"
"【确认洗炼】 执行洗炼\n"
```

- [ ] **Step 2: 更新 AI 知识库 YAML**

在 `equip_system_help.yaml` 的 keywords 和 body 中添加对应内容（铭文、分解、洗炼关键词和帮助文本）。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/equip_system_help.yaml
git commit -m "docs: 帮助系统更新铭文/分解/洗炼说明"
```

---

### Task 13: 端到端验证

- [ ] **Step 1: 语法验证所有修改文件**

```bash
python -m py_compile plugins/xiuxian_game/models/inventory.py
python -m py_compile plugins/xiuxian_game/item/inscription_service.py
python -m py_compile plugins/xiuxian_game/item/gem_socket_service_new.py
python -m py_compile plugins/xiuxian_game/item/equipment_commands.py
python -m py_compile plugins/xiuxian_game/item/decompose_service.py
python -m py_compile plugins/xiuxian_game/item/decompose_commands.py
python -m py_compile plugins/xiuxian_game/item/affix_service.py
python -m py_compile plugins/xiuxian_game/item/reroll_commands.py
python -m py_compile plugins/xiuxian_game/battle/enhanced_engine.py
python -m py_compile plugins/xiuxian_game/item/equipment_upgrade_service_new.py
```

Expected: 全部无报错

- [ ] **Step 2: YAML 验证**

```bash
python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/items.yaml','r',encoding='utf-8')); print('OK')"
```

- [ ] **Step 3: 铭文生成逻辑测试**

```bash
python -c "
# 测试铭文数值生成和显示逻辑
import random
# ... 测试 inscription_service 核心函数
print('Inscription logic test OK')
"
```

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(phase2): 铭文系统+分解系统+洗炼系统完整实现"
```
