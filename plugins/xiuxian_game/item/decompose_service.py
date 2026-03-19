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
    fragment_count: int = 0


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
