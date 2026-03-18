"""
装备分解服务

功能：
- 销毁装备获得洗词石
- 带T2词缀的装备有概率提取铭文
"""

import random
from typing import List, Tuple, Dict
from dataclasses import dataclass, field

from ..item.affix_service import get_affixes_from_equipment, VIP_EQUIPMENT_IDS
from ..config import config


@dataclass
class DecomposeResult:
    """分解结果"""
    reroll_stones: int = 0
    inscriptions: List[Dict] = field(default_factory=list)  # [{"item_id": str, "name": str}]


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

    # T2 词缀提取铭文
    extracted = []
    from .inscription_service import get_affix_to_inscription_id
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
            extracted.append({"item_id": inscription_id, "name": insc_name})

    return DecomposeResult(reroll_stones=total_stones, inscriptions=extracted)
