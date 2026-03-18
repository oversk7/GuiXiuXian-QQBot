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
from typing import List, Dict, Optional

from ..config import config
from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


# T2 词缀 affix_id → 铭文 item_id 映射表（分解提取用）
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
    # 以下T2词缀映射到语义更匹配的新铭文
    "kill_boost": "inscription_kill_attack",
    "desperation_crit": "inscription_lowhp_damage",
    "soul_burn": "inscription_hit_debuff_def",
    "combo_stack": "inscription_crit_boost",
    "doom_judgment": "inscription_execute",
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

    effect_cfg = _get_inscription_effect(item_id)
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


def _get_inscription_effect(item_id: str) -> Optional[dict]:
    """获取铭文的 inscription_effect 配置"""
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return None
    return getattr(item_cfg, 'inscription_effect', None)


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

    effect_cfg = _get_inscription_effect(item_id)
    if not effect_cfg:
        return None

    item_cfg = config.items_config["by_id"].get(item_id)
    insc_name = item_cfg.name if item_cfg else item_id

    trigger_type = TriggerType(effect_cfg["trigger"])
    effect_type = EffectType(effect_cfg["effect"])
    # 无 chance_range 的铭文（如被动类）默认100%触发
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


def get_affix_to_inscription_id(affix_id: str) -> Optional[str]:
    """T2词缀ID → 对应铭文item_id（分解提取用）"""
    return T2_AFFIX_TO_INSCRIPTION.get(affix_id)
