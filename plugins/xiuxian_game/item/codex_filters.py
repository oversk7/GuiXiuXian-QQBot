"""图鉴装备筛选：等级指装备要求的上限，不代表玩家满足转生等其他条件。"""
import re

from ..config import config

RARITIES = {
    '白色': 'white', '绿色': 'green', '蓝色': 'blue', '紫色': 'purple',
    '橙色': 'orange', '红色': 'red',
    '白': 'white', '绿': 'green', '蓝': 'blue', '紫': 'purple', '橙': 'orange', '红': 'red',
}


def parse_equipment_query(query: str) -> tuple[str | None, int | None, int] | None:
    """筛选必须显式包含品质或 N级，避免将装备目录页码误作等级。"""
    parts = query.split()
    if not parts or parts[0] != '装备' or len(parts) < 2:
        return None
    rarity = None
    max_level = None
    page = 1
    saw_page = False
    for token in parts[1:]:
        if token in RARITIES and rarity is None and not saw_page:
            rarity = RARITIES[token]
        elif (match := re.fullmatch(r'([0-9]{1,9})级', token)) and max_level is None and not saw_page:
            max_level = int(match[1])
        elif re.fullmatch(r'[0-9]{1,9}', token) and not saw_page:
            page = int(token)
            saw_page = True
        else:
            return None
    if rarity is None and max_level is None:
        return None
    return rarity, max_level, page


def filter_equipment(entries: list[dict], rarity: str | None = None, max_level: int | None = None) -> list[dict]:
    items = config.items_config['by_id']
    result = []
    for entry in entries:
        if not entry['key'].startswith('item:'):
            continue
        item = items.get(entry['key'][5:])
        if item is None or getattr(item.type, 'value', item.type) != 'EQUIPMENT':
            continue
        if rarity is not None and item.rarity != rarity:
            continue
        if max_level is not None and (item.required_level or 1) > max_level:
            continue
        result.append(entry)
    return sorted(result, key=lambda entry: ((items[entry['key'][5:]].required_level or 1), entry['name'], entry['key']))
