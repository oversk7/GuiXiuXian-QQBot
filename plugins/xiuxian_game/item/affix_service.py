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
from typing import List, Dict, Optional
from pathlib import Path

import yaml
from nonebot import logger

from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


# VIP装备不参与词缀系统
VIP_EQUIPMENT_IDS = {
    "vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi",
    "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch",
    "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren",
    "vip_pendant_fuze",
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

    # 混合候选池（带权重：T1权重3, T2权重2）
    weighted_pool = []
    for a in candidates_t1:
        weighted_pool.append(("T1", a, 3))
    for a in candidates_t2:
        weighted_pool.append(("T2", a, 2))

    selected = []
    used_ids = set()

    for _ in range(count):
        # 过滤已选中的 affix_id（同一装备不重复词缀类型）
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
        duration = None
        if "value_ranges" in affix_cfg and rarity in affix_cfg["value_ranges"]:
            v2_range = affix_cfg["value_ranges"][rarity]
            value2 = round(rng.uniform(v2_range[0], v2_range[1]), 1)
        if "duration_ranges" in affix_cfg and rarity in affix_cfg["duration_ranges"]:
            d_range = affix_cfg["duration_ranges"][rarity]
            duration = rng.randint(d_range[0], d_range[1])
            # 无 value_ranges 时，value2 用于描述模板中的 {value2} 显示
            if value2 is None:
                value2 = duration

        return {
            "affix_id": affix_cfg["affix_id"],
            "tier": "T2",
            "value": value,
            "value2": value2,
            "duration": duration,
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
    duration = affix_data.get("duration")
    if duration is not None:
        desc = desc.replace("{duration}", f"{duration}")

    return f"{name}：{desc}"


def format_affixes_display(affixes: List[Dict]) -> List[str]:
    """格式化词缀列表为展示文本行

    Returns:
        如 ["  [1] 锐利：暴击率+3.2%", "  [2] 恐惧之力：攻击时12%概率..."]
    """
    lines = []
    for i, affix in enumerate(affixes, 1):
        display = get_affix_display_name(affix)
        lines.append(f"  [{i}] {display}")
    return lines


def get_t1_battle_bonuses(affixes: List[Dict]) -> Dict[str, float]:
    """提取 T1 词缀的战斗属性加成，返回 {attribute: total_value}"""
    cfg = _load_affix_config()
    bonuses: Dict[str, float] = {}

    for affix_data in affixes:
        if affix_data["tier"] != "T1":
            continue
        affix_id = affix_data["affix_id"]
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

        # value2 = 效果值, duration = 持续回合（各自独立存储）
        if "value_ranges" in affix_cfg:
            value = affix_data.get("value2", 0) or 0
        if "duration_ranges" in affix_cfg:
            duration = int(affix_data.get("duration", 1) or 1)

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
            require_critical=bool(affix_cfg.get("require_critical", False)),
        )
        triggers.append(tc)

    return triggers


def reroll_single_affix(affix_data: dict, rarity: str, rng: random.Random = None) -> Dict:
    """洗炼单条词缀：类型不变，数值在原区间内重新随机"""
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
        return affix_data

    return _roll_affix_values(tier, affix_cfg, rarity, rng)


def get_affix_value_range_display(affix_data: dict, rarity: str) -> str:
    """获取词缀数值区间的显示文本（洗炼预览用）"""
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
