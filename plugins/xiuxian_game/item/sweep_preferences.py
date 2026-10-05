"""扫荡材料品质白名单；独立存储，不影响其他物品获取流程。"""
import re

PREFERENCE_KEY = "sweep_keep_rarities"
RARITY_ORDER = {"white": 0, "green": 1, "blue": 2, "purple": 3, "orange": 4}
RARITY_NAMES = {"white": "白色", "green": "绿色", "blue": "蓝色", "purple": "紫色", "orange": "橙色"}


def parse_keep_rarities(text: str) -> list[str]:
    """精确品质可多选；显式「以上」展开范围。非法或空输入抛出 ValueError。"""
    tokens = re.split(r"[\s,，、]+", text.lower().strip())
    if tokens == ["全部"]:
        return list(RARITY_ORDER)
    if tokens in (["无"], ["不保留"]):
        return []
    selected = set()
    for token in tokens:
        matched = False
        for rarity, name in RARITY_NAMES.items():
            for alias in (rarity, name, name[0]):
                if token == alias:
                    selected.add(rarity)
                    matched = True
                elif token in (alias + "以上", alias + "及以上"):
                    selected.update(r for r, rank in RARITY_ORDER.items() if rank >= RARITY_ORDER[rarity])
                    matched = True
        if not matched:
            raise ValueError("品质必须为白、绿、蓝、紫、橙、全部或无")
    return [r for r in RARITY_ORDER if r in selected]


def get_keep_rarities(player) -> list[str]:
    attrs = getattr(player, "extra_attrs", None)
    value = attrs.get(PREFERENCE_KEY) if isinstance(attrs, dict) else None
    if not isinstance(value, list) or any(not isinstance(r, str) or r not in RARITY_ORDER for r in value):
        return list(RARITY_ORDER)
    return [r for r in RARITY_ORDER if r in value]


def set_keep_rarities(player, text: str) -> list[str]:
    rarities = parse_keep_rarities(text)
    player.extra_attrs = {**(player.extra_attrs or {}), PREFERENCE_KEY: rarities}
    return rarities


def preference_label(rarities: list[str]) -> str:
    if not rarities:
        return "不保留任何材料"
    return "全部品质" if rarities == list(RARITY_ORDER) else "、".join(RARITY_NAMES[r] for r in rarities)
