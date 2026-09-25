"""统一图鉴条目收集、搜索、分页及详情关系。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..config import config
from ..utils_markdown import cmd, plain_command_text

PAGE_SIZE = 8
DETAIL_PAGE_SIZE = 12

TYPE_CATEGORIES = {
    "EQUIPMENT": "装备", "MATERIAL": "材料", "CONSUMABLE": "丹药与消耗品",
    "GEM": "镶嵌物", "FISH": "鱼类", "SEASONING": "调味料",
    "DISH": "菜肴", "RECIPE": "食谱", "GIFT": "礼物",
    "VEGETABLE": "灵蔬", "HERB": "诡药", "SEED": "灵种",
    "GUARDIAN_BEAST": "守护兽", "INSCRIPTION": "铭文", "GOODS": "商品",
    "GHOST_FRAGMENT": "鬼魂碎片", "PET_ACCESSORY": "宠物饰品",
}

CATEGORY_ALIASES = {
    "丹药": "丹药与消耗品", "消耗品": "丹药与消耗品",
    "配方": "配方", "玩法": "玩法知识", "地图": "地点",
    "人物": "人物", "NPC": "人物", "丹方": "丹方", "食谱": "烹饪食谱",
    "锻造配方": "锻造配方",
}


def _entry(key: str, name: str, category: str, description: str = "", aliases=None, lines=None) -> dict:
    return {
        "key": str(key), "name": str(name), "category": str(category),
        "description": str(description or ""), "aliases": list(aliases or []),
        "lines": list(lines or []),
    }


def _item_key(item_id: str) -> str:
    return f"item:{item_id}"


def _item_entries() -> list[dict]:
    result = []
    for item_id, item in config.items_config["by_id"].items():
        item_type = getattr(getattr(item, "type", None), "value", "")
        category = TYPE_CATEGORIES.get(item_type, item_type or "物品")
        lines = []
        if "event_only" in getattr(item, "tags", set()):
            lines.append("活动限定物品；当前是否开放以游戏内活动状态为准。")
        result.append(_entry(_item_key(item_id), item.name, category, item.description, [item_id], lines))
    return result


def _recipe_entries() -> list[dict]:
    result = []
    items = config.items_config["by_id"]
    for recipe_id, recipe in config.elixirs_config.get("elixirs", {}).items():
        product = items.get(recipe.get("produce_item_id"))
        if not product:
            continue
        key = f"alchemy:{recipe_id}"
        materials = [
            f"材料：{_item_link(item_id, quantity)}"
            for item_id, quantity in recipe.get("materials", {}).items()
        ]
        result.append(_entry(
            key, f"{product.name}丹方", "丹方", f"炼制产物：{product.name}", [recipe_id],
            [f"产物：{_link(product.name, _item_key(product.item_id))} ×{recipe.get('quantity', 1)}",
             f"基础成功率：{recipe.get('base_success', 1) * 100:g}%（实际以炼丹加成为准）", *materials],
        ))
    return result


def _link(label: str, key: str) -> str:
    return cmd(label, f"图鉴 {key}")


def _item_link(item_id: str, quantity: Any | None = None) -> str:
    item = config.items_config["by_id"].get(item_id)
    name = item.name if item else item_id
    suffix = f" ×{quantity}" if quantity is not None else ""
    return f"{_link(name, _item_key(item_id))}{suffix}"


def _cooking_entries() -> list[dict]:
    from ..cooking.cooking_service import RecipeManager

    result = []
    for recipe in RecipeManager().get_all_recipes():
        materials = [
            f"食材：{_item_link(item_id, quantity)}"
            for item_id, quantity in recipe.ingredients.items()
        ]
        result.append(_entry(
            f"cooking:{recipe.recipe_id}", recipe.name, "烹饪食谱", recipe.description,
            [recipe.recipe_id], [f"基础售价：{recipe.base_price} 金币", f"厨房等级要求：{recipe.kitchen_level}", *materials],
        ))
    return result


def _craft_entries() -> list[dict]:
    result = []
    for item in config.items_config["by_id"].values():
        recipe = getattr(item, "recipe", None)
        if not recipe or getattr(getattr(item, "type", None), "value", "") != "EQUIPMENT":
            continue
        materials = dict(recipe.get("materials", {}))
        materials["flesh_crystal"] = max(materials.get("flesh_crystal", 0), 1)
        result.append(_entry(
            f"craft:{item.item_id}", f"{item.name}锻造配方", "锻造配方",
            f"锻造产物：{item.name}", [f"craft:{item.item_id}"],
            [f"产物：{_link(item.name, _item_key(item.item_id))}"]
            + [f"材料：{_item_link(mid, qty)}" for mid, qty in materials.items()]
            + [f"金币：{recipe.get('gold', 0)}"],
        ))
    return result


def _knowledge_entries() -> list[dict]:
    directory = Path(__file__).parent.parent / "data" / "knowledge"
    result = []
    for path in sorted(directory.glob("*.yaml")):
        if path.stem.startswith("admin"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        title = data.get("title")
        body = data.get("body")
        if not title or not isinstance(body, str):
            continue
        if path.stem.startswith(("admin_", "admin-")) or title.startswith("管理员"):
            continue
        clean_title = title.replace("（AI客服专用）", "").replace("(AI客服专用)", "").strip()
        body_lines = [line.strip() for line in body.splitlines() if line.strip()]
        body_lines = [line for line in body_lines if "供AI客服解答" not in line and "供AI客服使用" not in line]
        if not body_lines:
            continue
        from ..player.help_topics import render_topic
        rendered = render_topic(clean_title, "\n".join(body_lines))
        rendered_lines = rendered.splitlines()[1:]
        summary_index = next((index for index, line in enumerate(rendered_lines)
                              if line.strip() and line.strip() != "***"), None)
        description = rendered_lines[summary_index] if summary_index is not None else clean_title
        # 摘要使用纯文本；正文完整保留，不能切断 QQ 标签或丢失首段。
        description = plain_command_text(description)
        if len(description) > 120:
            description = description[:117] + "..."
        detail_lines = rendered_lines
        result.append(_entry(
            f"knowledge:{path.stem}", clean_title, "玩法知识", description,
            data.get("keywords", []), detail_lines,
        ))
    return result


def get_entries() -> list[dict]:
    """读取各资料域条目。来源用途在打开单个物品时按需计算。"""
    entries = _item_entries() + _recipe_entries() + _cooking_entries() + _craft_entries() + _knowledge_entries()
    from . import codex_world

    world_entries = codex_world.get_entries()
    for entry in world_entries:
        if entry["category"] == "地图":
            entry["category"] = "地点"
    entries.extend(world_entries)
    return entries


def get_item_relations(item_id: str) -> list[str]:
    """按需查询当前物品的来源、制造配方及用途关联。"""
    from . import codex_sources

    lines = codex_sources.source_lines(item_id)
    lines.extend(codex_sources.upgrade_use_lines(item_id))
    items = config.items_config["by_id"]
    for recipe_id, recipe in config.elixirs_config.get("elixirs", {}).items():
        if recipe.get("produce_item_id") == item_id:
            lines.append(f"丹方制造：{_link('查看丹方', f'alchemy:{recipe_id}')}")
        if item_id in recipe.get("materials", {}):
            product = items.get(recipe.get("produce_item_id"))
            if product:
                lines.append(f"丹方用途：{_link(product.name + '丹方', f'alchemy:{recipe_id}')}")
    from ..cooking.cooking_service import RecipeManager
    for recipe in RecipeManager().get_all_recipes():
        from ..cooking.dish_item_generator import DishItemGenerator
        dish_ids = {f"dish_{recipe.recipe_id}_{quality}" for quality in DishItemGenerator.QUALITY_NAMES}
        if item_id in dish_ids:
            lines.append(f"菜肴食谱：{_link(recipe.name, f'cooking:{recipe.recipe_id}')}")
        if item_id in recipe.ingredients:
            lines.append(f"烹饪用途：{_link(recipe.name, f'cooking:{recipe.recipe_id}')}")
    for product in items.values():
        recipe = getattr(product, "recipe", None)
        if not recipe:
            continue
        materials = dict(recipe.get("materials", {}))
        materials["flesh_crystal"] = max(materials.get("flesh_crystal", 0), 1)
        if product.item_id == item_id:
            lines.append(f"锻造制造：{_link('查看锻造配方', f'craft:{item_id}')}")
        if item_id in materials:
            lines.append(f"锻造用途：{_link(product.name + '锻造配方', f'craft:{product.item_id}')}")
    return list(dict.fromkeys(lines)) or ["来源资料待补充。"]


def categories(entries: list[dict] | None = None) -> list[str]:
    return sorted({entry["category"] for entry in (entries if entries is not None else get_entries())})


def resolve_category(value: str, entries: list[dict]) -> str | None:
    categories_set = set(categories(entries))
    if value in categories_set:
        return value
    target = CATEGORY_ALIASES.get(value)
    if target in categories_set:
        return target
    if value == "配方" and any(cat in categories_set for cat in ("丹方", "烹饪食谱", "锻造配方")):
        return "配方"
    return None


def category_entries(entries: list[dict], category: str) -> list[dict]:
    if category == "配方":
        return [entry for entry in entries if entry["category"] in {"丹方", "烹饪食谱", "锻造配方"}]
    return [entry for entry in entries if entry["category"] == category]


def page_entries(entries: list[dict], category: str | None = None, page: int = 1, page_size: int = PAGE_SIZE) -> tuple[list[dict], int, int]:
    filtered = category_entries(entries, category) if category else entries
    total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    return filtered[start:start + page_size], page, total_pages


def detail_page(entry: dict, page: int = 1, page_size: int = DETAIL_PAGE_SIZE) -> tuple[list[str], int, int]:
    lines = [entry.get("description", ""), *entry.get("lines", [])]
    lines = [line for line in lines if line]
    total_pages = max(1, (len(lines) + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    return lines[start:start + page_size], page, total_pages


def search_entries(query: str, entries: list[dict] | None = None) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    entries = entries if entries is not None else get_entries()
    # Exact item/world name wins over recipe aliases; stable keys are exact lookup targets.
    exact_item_names = [entry for entry in entries if entry["key"].startswith("item:") and query == entry["name"]]
    if exact_item_names:
        return exact_item_names
    exact_names = [entry for entry in entries if query == entry["name"]]
    if exact_names:
        return exact_names
    exact_keys = [entry for entry in entries if query == entry["key"]]
    if exact_keys:
        return exact_keys
    exact_aliases = [entry for entry in entries if query in entry["aliases"]]
    if exact_aliases:
        return exact_aliases
    folded = query.casefold()
    return [entry for entry in entries if folded in entry["name"].casefold()
            or folded in entry["description"].casefold()
            or any(folded in str(alias).casefold() for alias in entry["aliases"])
            or any(folded in str(line).casefold() for line in entry["lines"])]


def dungeon_entry(depth: int) -> dict:
    """延迟转发到 item.codex_world，允许查询无限深度。"""
    from . import codex_world

    return codex_world.dungeon_entry(depth)
