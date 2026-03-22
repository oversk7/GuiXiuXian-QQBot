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


def _roll_effect_values_biased(effect_cfg: dict, rng: random.Random,
                                luck_bonus: float = 0.0) -> dict:
    """合成专用：min(rand*4) 强偏低分布，幸运值缓和偏移

    luck_bonus: 0~1，来自 luck_prob()，用于将分布从偏低拉回均匀
        luck_bonus=0 → min(r1,r2,r3,r4)，概率集中在下品/中品
        luck_bonus=1 → 接近均匀分布（高幸运玩家几乎无惩罚）

    0幸运单维度概率：下品68% 中品30% 上品1.5% 极品0.01%
    """
    values = {}
    for key in ("chance", "value"):
        range_key = f"{key}_range"
        r = effect_cfg.get(range_key)
        if r:
            t_biased = min(rng.random() for _ in range(4))
            t_uniform = rng.random()
            # 按幸运值在偏低分布和均匀分布之间插值
            t = t_biased + (t_uniform - t_biased) * luck_bonus
            values[key] = round(r[0] + t * (r[1] - r[0]), 1)
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


def generate_synthesis_inscription(item_id: str, rng: random.Random,
                                    player_luck: float = 0) -> dict:
    """合成铭文专用：偏低分布 + 幸运缓和

    Returns:
        {"_inscription_values": [...], "_inscription_grade": "中品"}
    """
    from ..utils import luck_prob

    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return {}

    luck_bonus = luck_prob(player_luck, midpoint=800, steepness=400)
    eff_cfg = _get_inscription_effect(item_id)
    if not eff_cfg:
        return {}
    values = _roll_effect_values_biased(eff_cfg, rng, luck_bonus)
    values_list = [values]
    grade = evaluate_grade(values_list, [eff_cfg])
    return {
        "_inscription_values": values_list,
        "_inscription_grade": grade,
    }


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
        if not eff_cfg:
            return {}
        values = _roll_celestial_values(eff_cfg, rng) if celestial else _roll_effect_values(eff_cfg, rng)
        values_list = [values]
        grade = "仙品" if celestial else evaluate_grade(values_list, [eff_cfg])

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
        value = values.get("value")
        # Fallback: 当铭文无存储数值时（旧数据），从配置范围取中位值
        if chance is None or value is None:
            eff_cfg = getattr(item_cfg, 'inscription_effect', None)
            if eff_cfg:
                if chance is None:
                    cr = eff_cfg.get("chance_range")
                    if cr and len(cr) == 2:
                        chance = round((cr[0] + cr[1]) / 2, 1)
                if value is None:
                    vr = eff_cfg.get("value_range")
                    if vr and len(vr) == 2:
                        value = round((vr[0] + vr[1]) / 2, 1)
        if chance is not None:
            desc = desc.replace("{chance}", f"{chance}")
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
    max_stacks = effect_cfg.get("max_stacks", 1)
    return TriggerConfig(
        trigger=trigger_type,
        chance=chance,
        effect=effect_type,
        value=value,
        duration=duration,
        threshold=float(threshold),
        max_stacks=max_stacks,
        description=f"铭文·{insc_name}",
        source_equipment=source_name,
    )


def inscription_to_trigger_config(inscription_data: dict, source_name: str = "铭文") -> Optional[TriggerConfig]:
    """将基础铭文数据转换为单个TriggerConfig（向后兼容）"""
    item_id = inscription_data.get("item_id", "")
    values = inscription_data.get("values", {})
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
